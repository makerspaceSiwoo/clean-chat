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

    def clear(self) -> None:
        with self._lock:
            self._sent.clear()

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
        self._rewrite_lock = threading.Lock()
        self.history: deque[ChatMessage] = deque(maxlen=history_size)
        self._lock = threading.Lock()

    def reset_history(self) -> None:
        with self._lock:
            self.history.clear()

    def analyze(self, message: ChatMessage) -> Analysis:
        with self._lock:
            req = AnalyzeRequest(message=message, history=list(self.history), players=self.roster.players)
            analysis = self.modules.run("analyze", req)
            self.history.append(message)
            return analysis

    def rewrite(self, message: ChatMessage, analysis: Analysis) -> Rewrite | None:
        if analysis.level >= Level.L2_ABUSIVE and analysis.feedback_spans:
            with self._rewrite_lock:
                return self.modules.run("rewrite", RewriteRequest(message=message, analysis=analysis))
        return None

    def run(self, message: ChatMessage) -> tuple[Analysis, Rewrite | None]:
        analysis = self.analyze(message)
        return analysis, self.rewrite(message, analysis)


class LineDedup:
    """이전 화면의 끝과 현재 화면의 시작에서 겹치는 가장 긴 줄 목록을 찾아 새 줄만 돌려준다.

    채팅창은 위로 밀릴 뿐 한 번에 통째로 바뀌지 않는다. 그래서 이전 화면과 한 줄도 겹치지 않는 화면은
    OCR 오작동(빈 화면에서 잡음 인식 등)으로 보고 버린다. 같은 화면이 CONFIRM_FRAMES 번 연속 나오면
    (예: 채팅창이 숨겨진 동안 채팅이 많이 올라온 경우) 실제 화면으로 받아들인다.
    """

    CONFIRM_FRAMES = 3

    def __init__(self) -> None:
        self.previous: list[str] = []
        self._pending: list[str] = []
        self._pending_count = 0

    def new_lines(self, lines: list[RawLine]) -> list[RawLine]:
        lines = [line for line in lines if line.text.strip()]
        if not lines:
            return []  # 채팅창이 잠깐 숨겨짐 → 비교 기준을 바꾸지 않는다.
        current = [" ".join(line.text.split()) for line in lines]
        overlap = min(len(self.previous), len(current))
        while overlap and self.previous[-overlap:] != current[:overlap]:
            overlap -= 1
        if self.previous and overlap == 0 and not self._confirmed(current):
            return []  # 연속성 없음 → 오작동으로 보고 기준을 유지한다.
        self._pending, self._pending_count = [], 0
        self.previous = current
        return lines[overlap:]

    def _confirmed(self, current: list[str]) -> bool:
        """겹치지 않는 같은 화면이 연속으로 CONFIRM_FRAMES 번 나왔는지 센다."""
        self._pending_count = self._pending_count + 1 if current == self._pending else 1
        self._pending = current
        return self._pending_count >= self.CONFIRM_FRAMES


class IncomingPipeline:
    """흐름 A: 다른 유저 채팅 (캡처 주기마다 자동, 백그라운드 스트림)."""

    def __init__(self, modules: ModuleSet, filters: MessageFilters, sent_log: SentLog, roster: Roster) -> None:
        self.modules, self.filters, self.sent_log, self.roster = modules, filters, sent_log, roster
        self.dedup = LineDedup()

    def process_frame(self, frame: Frame) -> list[Incident]:
        """[Windows 실제 앱] 캡처 이미지 1장 → 새 채팅 줄들 처리"""
        return [inc for line in self.read_frame(frame) if (inc := self.process_line(line))]

    def read_frame(self, frame: Frame) -> list[RawLine]:
        result: OcrResult = self.modules.run("ocr", frame)
        return self.dedup.new_lines(result.lines)

    def parse(self, line: RawLine) -> ParseResult:
        return self.modules.run("parse", ParseRequest(line=line, my_name=settings.my_name))

    def process_line(self, line: RawLine) -> Incident | None:
        msg = self.parse(line).message
        if msg is None or self.sent_log.is_echo(msg):
            return None
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

    def reset_session(self) -> None:
        self.sent_log.clear()
        self.incoming.filters.reset_history()
        self.incoming.dedup = LineDedup()
        self.set_players([])

    def set_players(self, players: list[Player]) -> None:
        self.roster.players = list(players)
