"""게임 단계 상태 기계 + 세션 저장소 + 게임 종료 배치 처리 (리드 소유, HANDOFF 5-2).

    대기(IDLE) ──IN_GAME──▶ 게임 중(IN_GAME) ──POST_GAME──▶ 게임 종료(POST_GAME) ──사용자가 닫음──▶ 대기

패턴
- 상태(State): GameStateMachine 이 지금 단계와 이번 게임 세션을 들고, 허용된 전환만 받는다.
- 저장소(Repository): SessionRepository 로 세션을 저장·조회 (메모리 / JSONL 파일 구현을 골라 끼움).
- 배치 처리: PostGameBatch 가 끝난 세션 전체를 한 번에 report 모듈(kind=report / complaint)로 보낸다.
판단(신고 대상 여부 등)은 하지 않는다. 정책표(core/policy.py)가 Decision 에 표시한 report / complaint_candidate 만 따른다.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Protocol

from clean_chat.core.config import settings
from clean_chat.core.modules import ModuleSet
from clean_chat.core.schemas import (
    GamePhase,
    GameSession,
    Incident,
    PhaseEvent,
    Player,
    PostGameResult,
    ReportKind,
    ReportRequest,
)

KST = timezone(timedelta(hours=9))  # 세션 id 는 한국 시간 기준 (한국 서버 전용 앱)

# 감지기가 보낸 단계 → 실제로 옮겨 갈 단계. 표에 없는 조합은 무시한다 (같은 단계 반복 보고 포함).
TRANSITIONS: dict[tuple[GamePhase, GamePhase], GamePhase] = {
    (GamePhase.IDLE, GamePhase.IN_GAME): GamePhase.IN_GAME,
    (GamePhase.IN_GAME, GamePhase.POST_GAME): GamePhase.POST_GAME,
    # 게임 중 대기 보고(튕김·재접속 등): idle_grace_sec 동안 계속될 때만 게임 종료로 본다 (아래 _resolve, OPEN-12)
    (GamePhase.IN_GAME, GamePhase.IDLE): GamePhase.POST_GAME,
    # 게임 종료 화면은 사용자가 닫을 때까지 유지 → (POST_GAME, IDLE) 은 감지기 이벤트로는 넘어가지 않음
    (GamePhase.POST_GAME, GamePhase.IN_GAME): GamePhase.IN_GAME,  # 결과 화면을 안 닫고 다음 게임 시작
}


def session_id_for(ts: float) -> str:
    """게임 시작 시각 → 세션 id (예: 1762919900.0 → "20251112-125820")"""
    return datetime.fromtimestamp(ts, tz=KST).strftime("%Y%m%d-%H%M%S")


class GameStateMachine:
    """지금 게임 단계와 이번 게임 세션. 여러 스레드(단계 감지, 캡처, UI)가 부르므로 잠금으로 보호한다."""

    def __init__(self, idle_grace_sec: float | None = None) -> None:
        self.phase = GamePhase.IDLE
        self.session: GameSession | None = None
        # 게임 중 대기 보고가 이만큼 계속돼야 게임 종료로 본다 (재접속 등 잠깐의 대기로 게임이 쪼개지지 않게)
        self.idle_grace_sec = settings.idle_grace_sec if idle_grace_sec is None else idle_grace_sec
        self._idle_since: float | None = None  # 게임 중 대기 보고가 처음 온 시각
        self._lock = threading.Lock()

    def _resolve(self, event: PhaseEvent) -> GamePhase | None:
        """이벤트를 적용하면 옮겨 갈 단계 (상태는 바꾸지 않음). 잠금 안에서만 부른다."""
        target = TRANSITIONS.get((self.phase, event.phase))
        if (self.phase, event.phase) == (GamePhase.IN_GAME, GamePhase.IDLE):
            started = event.ts if self._idle_since is None else self._idle_since
            return target if event.ts - started >= self.idle_grace_sec else None
        return target

    def peek(self, event: PhaseEvent) -> GamePhase | None:
        """handle() 을 부르면 옮겨 갈 단계 (바꾸지는 않음). 없으면 None."""
        with self._lock:
            return self._resolve(event)

    def handle(self, event: PhaseEvent) -> GamePhase | None:
        """감지기 이벤트 1건 적용. 단계가 바뀌었으면 새 단계를, 아니면 None 을 돌려준다.

        감지기는 같은 단계를 여러 번 보내도 된다(LCU 는 확인 주기마다 보냄). 게임 중 대기 보고는 유예 시간을 잰다.
        """
        with self._lock:
            target = self._resolve(event)
            if self.phase == GamePhase.IN_GAME:
                if event.phase == GamePhase.IDLE and self._idle_since is None:
                    self._idle_since = event.ts
                elif event.phase != GamePhase.IDLE:
                    self._idle_since = None  # 다시 게임 중 → 잠깐의 대기였음
            if target is None:
                return None
            if target == GamePhase.IN_GAME:
                self.session = GameSession(id=session_id_for(event.ts), started_at=event.ts)
            elif target == GamePhase.POST_GAME and self.session is not None:
                # 대기 유예 끝에 종료되면, 실제 종료 시각은 대기가 처음 보고된 시각
                self.session.ended_at = self._idle_since if event.phase == GamePhase.IDLE else event.ts
            self._idle_since = None
            self.phase = target
            return target

    def dismiss(self) -> bool:
        """사용자가 '이번 게임 결과' 화면을 닫음 → 대기. 게임 종료 단계가 아니면 아무것도 안 함."""
        with self._lock:
            if self.phase != GamePhase.POST_GAME:
                return False
            self.phase, self.session = GamePhase.IDLE, None
            return True

    def set_players(self, players: list[Player]) -> None:
        with self._lock:
            if self.session is not None:
                self.session.players = list(players)

    def record(self, incident: Incident) -> bool:
        """흐름 A 결과를 이번 세션에 기록. 게임 중이 아니면 기록하지 않고 False."""
        with self._lock:
            if self.phase != GamePhase.IN_GAME or self.session is None:
                return False
            self.session.incidents.append(incident)
            return True


class SessionRepository(Protocol):
    """세션 저장소 (포트). 구현: MemorySessionRepository(기본), session.store.JsonlSessionRepository(리드)."""

    def save(self, session: GameSession) -> None: ...

    def load(self, session_id: str) -> GameSession: ...

    def list_ids(self) -> list[str]: ...


class MemorySessionRepository:
    """프로그램이 켜져 있는 동안만 기억하는 저장소 (테스트·데모용, 파일을 남기지 않음)."""

    def __init__(self) -> None:
        self._items: dict[str, GameSession] = {}

    def save(self, session: GameSession) -> None:
        self._items[session.id] = session.model_copy(deep=True)

    def load(self, session_id: str) -> GameSession:
        return self._items[session_id].model_copy(deep=True)

    def list_ids(self) -> list[str]:
        return sorted(self._items)


class PostGameBatch:
    """게임 종료 후 배치 처리: 세션 → 화자별 신고 문구 + 고소장 초안 (report 모듈, kind 만 다르게)."""

    def __init__(self, modules: ModuleSet) -> None:
        self.modules = modules

    def run(self, session: GameSession) -> PostGameResult:
        report_speakers = _speakers(session, lambda inc: inc.decision.report)
        complaint_speakers = _speakers(session, lambda inc: inc.decision.complaint_candidate)
        reports = [
            self.modules.run("report", ReportRequest(kind=ReportKind.REPORT, session=session, speaker=s))
            for s in report_speakers
        ]
        complaints = [
            self.modules.run(
                "report",
                ReportRequest(
                    kind=ReportKind.COMPLAINT,
                    session=session,
                    speaker=s,
                    complainant=settings.my_name,
                    output_dir=settings.complaint_output_dir,
                ),
            )
            for s in complaint_speakers
        ]
        return PostGameResult(session_id=session.id, reports=reports, complaints=complaints)


def _speakers(session: GameSession, flagged) -> list[str]:
    """정책표가 표시한 기록이 있는 화자 목록 (처음 나온 순서, 중복 없음)."""
    names = [inc.msg.speaker for inc in session.incidents if flagged(inc) and inc.msg.speaker]
    return list(dict.fromkeys(names))
