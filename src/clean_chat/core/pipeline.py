"""모듈 함수들을 순서대로 연결하는 파이프라인 (구성, 리드 소유). 판단 로직은 넣지 않는다 — 판단은 각 모듈 몫.

두 흐름 (패턴: 파이프-필터, ADR-0017):
  흐름 A  IncomingPipeline  Frame → ocr → (줄 중복 제거) → parse → [공통] → 정책(incoming) → Incident (스트림)
  흐름 B  OutgoingPipeline  내 문장 → parse(source=self_input) → [공통] → 정책(outgoing) → Incident (동기)
  공통    MessageFilters    analyze → (L2 이상 & 피드백 조각이 있으면) rewrite

모듈 함수는 ModuleSet 하나로 두 흐름이 같이 쓴다. Mock 은 없다 — 구현이 없는 모듈을 만나면 ModuleNotImplemented.
테스트는 ModuleSet({"parse": 가짜함수, ...}) 로 연결 구조만 검증한다.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from difflib import SequenceMatcher

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
        """L1 → 욕설을 뺀 문장(로컬, 바로 끝남) / L2 이상 + 피드백 → 피드백만 다듬은 문장(LLM, 최대 3초)."""
        req = RewriteRequest(message=message, analysis=analysis, players=self.roster.players)
        if analysis.level == Level.L1_MILD:
            return self.modules.run("rewrite", req)  # 로컬 처리라 LLM 순화가 끝나길 기다리지 않는다
        if analysis.level >= Level.L2_ABUSIVE and analysis.feedback_spans:
            with self._rewrite_lock:
                return self.modules.run("rewrite", req)
        return None

    def run(self, message: ChatMessage) -> tuple[Analysis, Rewrite | None]:
        analysis = self.analyze(message)
        return analysis, self.rewrite(message, analysis)


capture_log = logging.getLogger("clean_chat.capture")  # 앱이 사용자 데이터 폴더의 파일로 연결한다 (ui/app.py)


def _key(text: str) -> str:
    """비교용 글자만 남긴다. 띄어쓰기·기호는 OCR 이 읽을 때마다 달라져서 뺀다."""
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def line_similarity(a: str, b: str) -> float:
    """두 줄이 같은 채팅 줄을 읽은 것이면 0보다 큰 값(같을수록 1에 가깝다), 다른 줄이면 0.

    같은 줄도 OCR 이 읽을 때마다 조금씩 다르게 읽는다 (반투명 배경 뒤로 게임 화면이 움직여서).
    `화자: 내용` 은 화자와 내용을 따로 본다. 화자 부분이 길어서 통째로 비교하면 같은 사람의 다른 말이 같은 줄로 보인다.
    """
    if a == b:
        return 1.0
    head_a, sep_a, body_a = a.partition(":")
    head_b, sep_b, body_b = b.partition(":")
    if sep_a and sep_b and _key(body_a) and _key(body_b):
        head = SequenceMatcher(None, _key(head_a), _key(head_b)).ratio()
        body = SequenceMatcher(None, _key(body_a), _key(body_b)).ratio()
        return (head + body) / 2 if head >= HEAD_SIMILARITY and body >= BODY_SIMILARITY else 0.0
    whole = SequenceMatcher(None, _key(a), _key(b)).ratio()
    return whole if whole >= LINE_SIMILARITY else 0.0


HEAD_SIMILARITY = 0.7  # 화자 부분 ("[전체] 닉네임 (챔피언)")
BODY_SIMILARITY = 0.7  # 내용 부분. 실제 게임에서 같은 줄을 읽은 변형들이 0.78 이상이었다.
LINE_SIMILARITY = 0.75  # `화자: 내용` 꼴이 아닌 줄 (시스템 메시지 등)


class LineDedup:
    """화면의 줄을 지금까지 본 줄과 순서대로 맞춰 보고, 마지막으로 맞은 줄 아래의 줄만 새 줄로 돌려준다.

    - 같은 줄인지는 글자가 '거의 같은지'로 본다 (line_similarity). 한 줄이 다르게 읽혀도 나머지 줄은 그대로 맞는다.
    - 직전 화면 하나가 아니라 최근에 본 줄 목록(history)과 비교한다. OCR 이 한 화면에서 줄을 빠뜨려도
      다음 화면에서 그 줄을 새 줄로 다시 내지 않는다.
    - 같은 말이 연달아 올라오면(용, 용) 화면의 앞쪽 줄부터 맞춰서 뒤의 것을 새 줄로 본다.
    - OCR 이 아무것도 읽지 못한 화면(채팅창 숨김, 인식 실패)은 목록을 바꾸지 않는다.
    - 맞는 줄이 하나도 없으면(숨김 동안 채팅이 많이 올라옴) 보이는 줄을 모두 새 줄로 본다.
    - 채팅으로 읽히지 않은 줄은 retry() 로 표시해 둔다. 그 줄이 다음에 다르게 읽히면 한 번 더 내보낸다
      (첫 판독이 깨져서 채팅을 놓치는 일을 줄인다).
    """

    HISTORY = 12  # 비교할 최근 줄 수. 화면에 보이는 줄(5~6줄)보다 넉넉하게.

    def __init__(self) -> None:
        self.previous: list[str] = []  # 최근에 본 줄 (오래된 것부터)
        self._unread: set[str] = set()  # previous 중 채팅으로 읽히지 않은 줄

    def new_lines(self, lines: list[RawLine]) -> list[RawLine]:
        lines = [line for line in lines if line.text.strip()]
        if not lines:
            return []  # 읽은 글자가 없음 → 비교 기준을 그대로 둔다.
        current = [" ".join(line.text.split()) for line in lines]
        fresh = self._last_match(current) + 1
        again = [j for j in range(fresh) if self._reread(current[j])]
        self.previous = (self.previous + current[fresh:])[-self.HISTORY :]
        self._unread &= set(self.previous)
        return [lines[j] for j in again] + lines[fresh:]

    def retry(self, line: RawLine) -> None:
        """이 줄은 채팅으로 읽히지 않았다. 같은 줄이 다르게 읽히면 다시 내보내도록 표시한다."""
        text = " ".join(line.text.split())
        if text in self.previous:
            self._unread.add(text)

    def _reread(self, text: str) -> bool:
        """이미 본 줄이지만 채팅으로 읽히지 않았고, 이번에는 다르게 읽혔는가. 맞으면 새 판독으로 바꿔 둔다."""
        for old in self._unread:
            if old != text and line_similarity(old, text):
                self._unread.discard(old)
                self.previous[self.previous.index(old)] = text
                return True
        return False

    def _last_match(self, current: list[str]) -> int:
        """history 와 순서를 지키며 가장 잘 맞춘 짝에서, 마지막으로 맞은 current 줄의 위치 (없으면 -1).

        점수가 같으면 current 의 앞쪽 줄과 맞춘 쪽을 고른다 (연달아 올라온 같은 말의 뒤쪽을 새 줄로 보려고).
        """
        best = [(0.0, 1)] * (len(current) + 1)  # (점수 합, -마지막으로 맞은 위치) — 맞은 줄이 없으면 1
        for old in self.previous:
            row = [(0.0, 1)]
            for j, text in enumerate(current, start=1):
                options = [best[j], row[j - 1]]
                if score := line_similarity(old, text):
                    options.append((best[j - 1][0] + score, -(j - 1)))
                row.append(max(options))
            best = row
        return -best[-1][1]


class SpeakerBook:
    """이번 게임에서 채팅을 친 사람 목록. 사람은 닉네임 + 챔피언으로 구분한다.

    OCR 이 같은 사람의 닉네임을 조금씩 다르게 읽으면(따옴표가 끼거나 한 글자가 바뀜) 신고 대상이 여러 명으로
    갈라진다. 챔피언이 같고 닉네임이 거의 같으면 같은 사람으로 보고, 명단(Live Client Data API)이나
    처음 읽은 표기로 닉네임을 맞춘다. 닉네임이 같아도 챔피언이 다르면 다른 사람이므로 건드리지 않는다.
    """

    SIMILARITY = 0.6  # 같은 챔피언일 때 같은 사람으로 볼 닉네임 유사도

    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []  # (닉네임, 챔피언)

    def resolve(self, message: ChatMessage, players: list[Player]) -> ChatMessage:
        if not message.speaker or not message.champion or message.is_me:
            return message
        known = [(p.name, p.champion) for p in players if p.champion] + self.seen
        name = self._match(message.speaker, message.champion, known)
        if name is None:
            self.seen.append((message.speaker, message.champion))
            return message
        return message if name == message.speaker else message.model_copy(update={"speaker": name})

    def _match(self, speaker: str, champion: str, known: list[tuple[str, str]]) -> str | None:
        best, best_score = None, self.SIMILARITY
        for name, champ in known:
            if champ != champion:
                continue
            score = 1.0 if name == speaker else SequenceMatcher(None, _key(name), _key(speaker)).ratio()
            if score >= best_score and (best is None or score > best_score):
                best, best_score = name, score
        return best


class IncomingPipeline:
    """흐름 A: 다른 유저 채팅 (캡처 주기마다 자동, 백그라운드 스트림)."""

    def __init__(self, modules: ModuleSet, filters: MessageFilters, sent_log: SentLog, roster: Roster) -> None:
        self.modules, self.filters, self.sent_log, self.roster = modules, filters, sent_log, roster
        self.dedup = LineDedup()
        self.speakers = SpeakerBook()

    def process_frame(self, frame: Frame) -> list[Incident]:
        """[Windows 실제 앱] 캡처 이미지 1장 → 새 채팅 줄들 처리"""
        return [inc for line in self.read_frame(frame) if (inc := self.process_line(line))]

    def read_frame(self, frame: Frame) -> list[RawLine]:
        started = time.perf_counter()
        result: OcrResult = self.modules.run("ocr", frame)
        fresh = self.dedup.new_lines(result.lines)
        size = "x".join(map(str, frame.image.size)) if frame.image is not None else frame.image_path
        capture_log.info(
            "캡처 %s · OCR %.0fms · 읽은 줄 %d · 새 줄 %d%s",
            size,
            (time.perf_counter() - started) * 1000,
            len(result.lines),
            len(fresh),
            "".join(f"\n    + {line.text}" for line in fresh),
        )
        return fresh

    def parse(self, line: RawLine) -> ParseResult:
        result: ParseResult = self.modules.run("parse", ParseRequest(line=line, my_name=settings.my_name))
        if result.message is not None:  # 같은 사람(닉네임 + 챔피언)은 같은 닉네임 표기로 맞춘다
            result.message = self.speakers.resolve(result.message, self.roster.players)
        return result

    def process_line(self, line: RawLine) -> Incident | None:
        parsed = self.parse(line)
        msg = parsed.message
        if msg is None and not parsed.system_text:
            self.dedup.retry(line)  # 채팅도 시스템 문구도 아님 → 다르게 읽히면 다시 본다
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
        self.incoming.speakers = SpeakerBook()
        self.set_players([])

    def set_players(self, players: list[Player]) -> None:
        self.roster.players = list(players)
