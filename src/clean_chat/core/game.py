"""게임 단계 상태 기계 + 세션 저장소 + 게임 종료 배치 처리 (리드 소유, HANDOFF 5-2).

    대기(IDLE) ──IN_GAME──▶ 게임 중(IN_GAME) ──POST_GAME──▶ 게임 종료(POST_GAME) ──사용자가 닫음──▶ 대기

패턴
- 상태(State): GameStateMachine 이 지금 단계와 이번 게임 세션을 들고, 허용된 전환만 받는다.
- 저장소(Repository): SessionRepository 로 세션을 저장·조회 (메모리 / JSONL 파일 구현을 골라 끼움).
- 배치 처리: PostGameBatch 가 끝난 세션 전체를 한 번에 report / complaint Stage 로 보낸다.
판단(신고 대상 여부 등)은 하지 않는다. policy 가 Decision 에 표시한 report / complaint_candidate 만 따른다.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Protocol

from clean_chat.core.config import settings
from clean_chat.core.schemas import (
    ComplaintRequest,
    GamePhase,
    GameSession,
    Incident,
    PhaseEvent,
    Player,
    PostGameResult,
    ReportRequest,
)

KST = timezone(timedelta(hours=9))  # 세션 id 는 한국 시간 기준 (한국 서버 전용 앱)

# 감지기가 보낸 단계 → 실제로 옮겨 갈 단계. 표에 없는 조합은 무시한다 (같은 단계 반복 보고 포함).
TRANSITIONS: dict[tuple[GamePhase, GamePhase], GamePhase] = {
    (GamePhase.IDLE, GamePhase.IN_GAME): GamePhase.IN_GAME,
    (GamePhase.IN_GAME, GamePhase.POST_GAME): GamePhase.POST_GAME,
    # 게임 중 바로 대기로 돌아감(튕김·다시하기 등): 기록을 잃지 않도록 게임 종료로 처리 (OPEN-10 실측 후 조정)
    (GamePhase.IN_GAME, GamePhase.IDLE): GamePhase.POST_GAME,
    # 게임 종료 화면은 사용자가 닫을 때까지 유지 → (POST_GAME, IDLE) 은 감지기 이벤트로는 넘어가지 않음
    (GamePhase.POST_GAME, GamePhase.IN_GAME): GamePhase.IN_GAME,  # 결과 화면을 안 닫고 다음 게임 시작
}


def session_id_for(ts: float) -> str:
    """게임 시작 시각 → 세션 id (예: 1762919900.0 → "20251112-125820")"""
    return datetime.fromtimestamp(ts, tz=KST).strftime("%Y%m%d-%H%M%S")


class GameStateMachine:
    """지금 게임 단계와 이번 게임 세션. 여러 스레드(단계 감지, 캡처, UI)가 부르므로 잠금으로 보호한다."""

    def __init__(self) -> None:
        self.phase = GamePhase.IDLE
        self.session: GameSession | None = None
        self._lock = threading.Lock()

    def peek(self, event: PhaseEvent) -> GamePhase | None:
        """handle() 을 부르면 옮겨 갈 단계 (바꾸지는 않음). 없으면 None."""
        with self._lock:
            return TRANSITIONS.get((self.phase, event.phase))

    def handle(self, event: PhaseEvent) -> GamePhase | None:
        """감지기 이벤트 1건 적용. 단계가 바뀌었으면 새 단계를, 아니면 None 을 돌려준다."""
        with self._lock:
            target = TRANSITIONS.get((self.phase, event.phase))
            if target is None:
                return None
            if target == GamePhase.IN_GAME:
                self.session = GameSession(id=session_id_for(event.ts), started_at=event.ts)
            elif target == GamePhase.POST_GAME and self.session is not None:
                self.session.ended_at = event.ts
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
    """세션 저장소 (포트). 구현: MemorySessionRepository(기본), session.store.JsonlSessionRepository(WP8)."""

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
    """게임 종료 후 배치 처리: 세션 → 화자별 신고 문구(report) + 고소장 초안(complaint)."""

    def __init__(self, stages) -> None:  # stages: core.pipeline.StageSet (순환 import 방지로 타입 생략)
        self.st = stages

    def run(self, session: GameSession) -> PostGameResult:
        report_speakers = _speakers(session, lambda inc: inc.decision.report)
        complaint_speakers = _speakers(session, lambda inc: inc.decision.complaint_candidate)
        reports = [self.st["report"].run(ReportRequest(session=session, speaker=s)) for s in report_speakers]
        complaints = [
            self.st["complaint"].run(
                ComplaintRequest(
                    session=session,
                    speaker=s,
                    complainant=settings.my_name,
                    output_dir=settings.complaint_output_dir,
                )
            )
            for s in complaint_speakers
        ]
        return PostGameResult(session_id=session.id, reports=reports, complaints=complaints)


def _speakers(session: GameSession, flagged) -> list[str]:
    """policy 가 표시한 기록이 있는 화자 목록 (처음 나온 순서, 중복 없음)."""
    names = [inc.msg.speaker for inc in session.incidents if flagged(inc) and inc.msg.speaker]
    return list(dict.fromkeys(names))
