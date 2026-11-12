"""Stage 들을 순서대로 연결하는 파이프라인 (리드 소유). 판단 로직은 넣지 않는다 — 판단은 각 Stage 몫.

두 흐름 (HANDOFF 5-1, 패턴: 파이프-필터):
  흐름 A  IncomingPipeline  Frame/RawLine → ocr → parse → [공통 필터] → incoming_policy → Incident (스트림)
  흐름 B  OutgoingPipeline  내 문장 → compose → [공통 필터] → outgoing_policy → Incident (동기 요청-응답)
  공통 필터 MessageFilters  normalize → classify → (L2 이상 & 피드백이면) rewrite

Stage 인스턴스는 StageSet 하나로 만들어 두 흐름이 같이 쓴다 (분류 모델을 두 번 로딩하지 않게).
모듈별 real/mock 은 settings.impl 로 선택:  StageSet({"parse": "real"})  → parse만 실제, 나머지 mock
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque

from clean_chat.core import registry
from clean_chat.core.config import STAGE_NAMES, settings
from clean_chat.core.schemas import (
    Action,
    ChatMessage,
    Classification,
    Frame,
    Incident,
    Level,
    NormalizedMessage,
    OutgoingText,
    Player,
    PolicyRequest,
    RawLine,
    Rewrite,
    RewriteRequest,
)
from clean_chat.core.stage import Stage


class StageSet:
    """모든 Stage 인스턴스 묶음 (Strategy + Registry: 이름마다 real/mock 구현을 골라 끼움)."""

    def __init__(self, overrides: dict[str, str] | None = None) -> None:
        self.impl = {**settings.impl, **(overrides or {})}
        self._stages: dict[str, Stage] = {n: registry.create(n, self.impl.get(n, "mock")) for n in STAGE_NAMES}

    def __getitem__(self, name: str) -> Stage:
        return self._stages[name]

    def setup(self) -> None:
        for s in self._stages.values():
            s.setup()

    def close(self) -> None:
        for s in self._stages.values():
            s.close()


class MessageFilters:
    """두 흐름이 같이 쓰는 필터: normalize → classify → (조건부) rewrite.

    흐름 A(백그라운드 스레드)와 흐름 B(입력 처리 스레드)가 동시에 부를 수 있어서 한 번에 하나씩만 실행한다.
    """

    def __init__(self, stages: StageSet) -> None:
        self.st = stages
        self._lock = threading.Lock()

    def run(self, message: ChatMessage) -> tuple[NormalizedMessage, Classification, Rewrite | None]:
        with self._lock:
            msg = self.st["normalize"].run(message)
            cls = self.st["classify"].run(msg)
            rw = None
            if cls.level >= Level.L2_ABUSIVE and cls.has_feedback:
                rw = self.st["rewrite"].run(RewriteRequest(message=msg, classification=cls))
            return msg, cls, rw


class SentLog:
    """흐름 B 에서 내가 보낸(복사한) 문장을 잠시 기억했다가, 흐름 A 의 OCR 이 다시 읽으면 건너뛰게 한다.

    중복 판단 기준은 아직 미정(OPEN-11). 지금은 "내 채팅(is_me)이고, window_sec 안에 보낸 문장과 본문이 같으면" 중복.
    """

    def __init__(self, window_sec: float = 60.0) -> None:
        self.window_sec = window_sec
        self._sent: deque[tuple[float, str]] = deque()
        self._lock = threading.Lock()

    def remember(self, text: str, ts: float) -> None:
        with self._lock:
            self._sent.append((ts, text.strip()))

    def is_echo(self, message: ChatMessage) -> bool:
        if not message.is_me:
            return False
        with self._lock:
            while self._sent and message.ts - self._sent[0][0] > self.window_sec:
                self._sent.popleft()
            return any(text == message.text.strip() for _, text in self._sent)


class IncomingPipeline:
    """흐름 A: 다른 유저 채팅 (캡처 주기마다 자동, 백그라운드 스트림)."""

    def __init__(self, stages: StageSet, filters: MessageFilters, sent_log: SentLog) -> None:
        self.st, self.filters, self.sent_log = stages, filters, sent_log
        self.players: list[Player] = []  # 단계 감지기가 게임 시작 때 채움 (Live Client Data API)

    def process_frame(self, frame: Frame) -> list[Incident]:
        """[Windows 실제 앱] 캡처 이미지 1장 → 새 채팅 줄들 처리"""
        result = self.st["ocr"].run(frame)
        return [inc for line in result.lines if (inc := self.process_line(line))]

    def process_line(self, line: RawLine) -> Incident | None:
        """채팅 한 줄 (OCR 결과 / 데모 재생). 잡음 줄이나 내가 보낸 문장의 재인식이면 None"""
        parsed = self.st["parse"].run(line)
        if parsed.message is None or self.sent_log.is_echo(parsed.message):
            return None
        msg, cls, rw = self.filters.run(parsed.message)
        req = PolicyRequest(message=msg, classification=cls, rewrite=rw, players=self.players)
        dec = self.st["incoming_policy"].run(req)
        return Incident(msg=msg, classification=cls, decision=dec, rewrite=rw)


class OutgoingPipeline:
    """흐름 B: 내 입력 (오버레이 입력칸 Enter → 결과 1개를 바로 돌려줌, 동기 요청-응답)."""

    def __init__(self, stages: StageSet, filters: MessageFilters, sent_log: SentLog) -> None:
        self.st, self.filters, self.sent_log = stages, filters, sent_log
        self.players: list[Player] = []

    def submit(self, text: str, *, msg_id: str | None = None, ts: float | None = None) -> Incident:
        """내 문장 1개 → Incident. decision.action 이 copy* 면 display_text 를 클립보드로, block 이면 차단 안내."""
        item = OutgoingText(id=msg_id or f"self-{uuid.uuid4().hex[:8]}", ts=ts or time.time(), text=text.strip())
        message = self.st["compose"].run(item)
        msg, cls, rw = self.filters.run(message)
        req = PolicyRequest(message=msg, classification=cls, rewrite=rw, players=self.players)
        dec = self.st["outgoing_policy"].run(req)
        if dec.action != Action.BLOCK and dec.display_text:
            self.sent_log.remember(dec.display_text, item.ts)
        return Incident(msg=msg, classification=cls, decision=dec, rewrite=rw)


class Pipelines:
    """앱이 쓰는 두 흐름을 한 번에 조립 (StageSet·필터·SentLog 공유)."""

    def __init__(self, overrides: dict[str, str] | None = None) -> None:
        self.stages = StageSet(overrides)
        filters = MessageFilters(self.stages)
        self.sent_log = SentLog()
        self.incoming = IncomingPipeline(self.stages, filters, self.sent_log)
        self.outgoing = OutgoingPipeline(self.stages, filters, self.sent_log)

    def set_players(self, players: list[Player]) -> None:
        self.incoming.players = players
        self.outgoing.players = players

    def setup(self) -> None:
        self.stages.setup()

    def close(self) -> None:
        self.stages.close()
