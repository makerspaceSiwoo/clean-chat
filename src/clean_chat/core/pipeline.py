"""모듈 함수들을 순서대로 연결하는 파이프라인 (구성, 리드 소유). 판단 로직은 넣지 않는다 — 판단은 각 모듈 몫.

두 흐름 (패턴: 파이프-필터, ADR-0017):
  흐름 A  IncomingPipeline  Frame → ocr → (줄 중복 제거) → parse → [공통] → 정책(incoming) → Incident (스트림)
  흐름 B  OutgoingPipeline  내 문장 → parse(source=self_input) → [공통] → 정책(outgoing) → Incident (동기)
  공통    MessageFilters    analyze → (L2 이상 & 피드백 조각이 있으면) rewrite

모듈 함수는 ModuleSet 하나로 두 흐름이 같이 쓴다. Mock 은 없다 — 구현이 없는 모듈을 만나면 ModuleNotImplemented.
테스트는 ModuleSet({"parse": 가짜함수, ...}) 로 연결 구조만 검증한다.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque

from clean_chat.core.config import settings
from clean_chat.core.modules import ModuleSet
from clean_chat.core.policy import decide_incoming, decide_outgoing
from clean_chat.core.schemas import (
    Action,
    Analysis,
    AnalyzeRequest,
    ChatMessage,
    Frame,
    Incident,
    Level,
    OcrResult,
    ParseRequest,
    ParseResult,
    Player,
    RawLine,
    Rewrite,
    RewriteRequest,
    Source,
)


class SentLog:
    """흐름 B 에서 내가 보낸(복사한) 문장을 잠시 기억했다가, 흐름 A 의 OCR 이 다시 읽으면 건너뛰게 한다.

    중복 판단 기준은 아직 미정(OPEN-13). 지금은 "내 채팅(is_me)이고, window_sec 안에 보낸 문장과 본문이 같으면" 중복.
    """

    def __init__(self, window_sec: float = 60.0) -> None:
        self.window_sec = window_sec
        self._sent: deque[tuple[float, str]] = deque()
        self._lock = threading.Lock()

    def remember(self, text: str, ts: float) -> None:
        with self._lock:
            self._prune(ts)
            self._sent.append((ts, text.strip()))

    def is_echo(self, message: ChatMessage) -> bool:
        if not message.is_me:
            return False
        with self._lock:
            self._prune(message.ts)
            return any(text == message.text.strip() for _, text in self._sent)

    def _prune(self, now: float) -> None:
        """window_sec 보다 오래된 문장은 잊는다 (계속 쌓이지 않게)."""
        while self._sent and now - self._sent[0][0] > self.window_sec:
            self._sent.popleft()


class Roster:
    """이번 게임 플레이어 명단 1곳 (두 흐름이 같은 명단을 본다). 단계 감지기가 채운다 (Live Client Data API)."""

    def __init__(self) -> None:
        self.players: list[Player] = []


class MessageFilters:
    """두 흐름이 같이 쓰는 처리: analyze → (조건부) rewrite. 최근 대화(history)를 기억해 analyze 에 넘긴다.

    흐름 A(백그라운드 스레드)와 흐름 B(입력 처리 스레드)가 동시에 부를 수 있어서 한 번에 하나씩만 실행한다.
    """

    def __init__(self, modules: ModuleSet, roster: Roster, history_size: int = 10) -> None:
        self.modules, self.roster = modules, roster
        self.history: deque[ChatMessage] = deque(maxlen=history_size)
        self._lock = threading.Lock()

    def run(self, message: ChatMessage) -> tuple[Analysis, Rewrite | None]:
        with self._lock:
            req = AnalyzeRequest(message=message, history=list(self.history), players=self.roster.players)
            analysis: Analysis = self.modules.run("analyze", req)
            self.history.append(message)
            rw = None
            if analysis.level >= Level.L2_ABUSIVE and analysis.feedback_spans:
                rw = self.modules.run("rewrite", RewriteRequest(message=message, analysis=analysis))
            return analysis, rw


class LineDedup:
    """OCR 은 보이는 줄을 전부 돌려준다. 앞 프레임에서 이미 처리한 줄을 건너뛴다 (채팅창은 위로 밀려 올라감).

    기준: 최근 window 줄 안에 같은 text 가 있으면 이미 본 줄. (같은 문장을 다시 친 경우는 OPEN-13 에서 다듬는다)
    """

    def __init__(self, window: int = 30) -> None:
        self._seen: deque[str] = deque(maxlen=window)
        self._lock = threading.Lock()

    def new_lines(self, lines: list[RawLine]) -> list[RawLine]:
        with self._lock:
            fresh = [ln for ln in lines if ln.text.strip() not in self._seen]
            self._seen.extend(ln.text.strip() for ln in fresh)
            return fresh


class IncomingPipeline:
    """흐름 A: 다른 유저 채팅 (캡처 주기마다 자동, 백그라운드 스트림)."""

    def __init__(self, modules: ModuleSet, filters: MessageFilters, sent_log: SentLog, roster: Roster) -> None:
        self.modules, self.filters, self.sent_log, self.roster = modules, filters, sent_log, roster
        self.dedup = LineDedup()

    def process_frame(self, frame: Frame) -> list[Incident]:
        """[Windows 실제 앱] 캡처 이미지 1장 → 새 채팅 줄들 처리"""
        result: OcrResult = self.modules.run("ocr", frame)
        return [inc for line in self.dedup.new_lines(result.lines) if (inc := self.process_line(line))]

    def process_line(self, line: RawLine) -> Incident | None:
        """채팅 한 줄 (OCR 결과 / 데모 재생). 채팅이 아닌 줄이나 내가 보낸 문장의 재인식이면 None"""
        parsed: ParseResult = self.modules.run("parse", ParseRequest(line=line, my_name=settings.my_name))
        if parsed.message is None or self.sent_log.is_echo(parsed.message):
            return None
        msg = parsed.message
        analysis, rw = self.filters.run(msg)
        return Incident(msg=msg, analysis=analysis, decision=decide_incoming(msg, analysis, rw), rewrite=rw)


class OutgoingPipeline:
    """흐름 B: 내 입력 (오버레이 입력칸 Enter → 결과 1개를 바로 돌려줌, 동기 요청-응답)."""

    def __init__(self, modules: ModuleSet, filters: MessageFilters, sent_log: SentLog) -> None:
        self.modules, self.filters, self.sent_log = modules, filters, sent_log

    def submit(self, text: str, *, msg_id: str | None = None, ts: float | None = None) -> Incident | None:
        """내 문장 1개 → Incident. decision.action 이 copy* 면 display_text 를 클립보드로, block 이면 차단 안내.

        parse 가 채팅이 아니라고 하면(빈 문장 등) None.
        """
        line = RawLine(
            id=msg_id or f"self-{uuid.uuid4().hex[:8]}",
            ts=ts or time.time(),
            text=text.strip(),
            source=Source.SELF_INPUT,
        )
        parsed: ParseResult = self.modules.run("parse", ParseRequest(line=line, my_name=settings.my_name))
        if parsed.message is None:
            return None
        msg = parsed.message
        analysis, rw = self.filters.run(msg)
        dec = decide_outgoing(msg, analysis, rw)
        if dec.action != Action.BLOCK and dec.display_text:
            self.sent_log.remember(dec.display_text, line.ts)
        return Incident(msg=msg, analysis=analysis, decision=dec, rewrite=rw)


class Pipelines:
    """앱이 쓰는 두 흐름을 한 번에 조립 (ModuleSet·필터·SentLog·명단 공유)."""

    def __init__(self, modules: ModuleSet | None = None) -> None:
        self.modules = modules or ModuleSet()
        self.sent_log = SentLog()
        self.roster = Roster()
        filters = MessageFilters(self.modules, self.roster)
        self.incoming = IncomingPipeline(self.modules, filters, self.sent_log, self.roster)
        self.outgoing = OutgoingPipeline(self.modules, filters, self.sent_log)

    def set_players(self, players: list[Player]) -> None:
        self.roster.players = list(players)
