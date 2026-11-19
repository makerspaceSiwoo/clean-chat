"""게임 단계 상태 기계 (HANDOFF 5-2)."""

from clean_chat.core.config import FIXTURES
from clean_chat.core.game import GameStateMachine, session_id_for
from clean_chat.core.jsonl import read_jsonl
from clean_chat.core.schemas import GamePhase, PhaseEvent, ReportRequest


def ev(phase: str, ts: float = 1762919900.0) -> PhaseEvent:
    return PhaseEvent(ts=ts, phase=phase)


def test_normal_game_cycle():
    m = GameStateMachine()
    assert m.handle(ev("idle")) is None  # 같은 단계 반복 보고는 무시
    assert m.handle(ev("in_game")) == GamePhase.IN_GAME
    assert m.session is not None and m.session.id == "20251112-125820"
    assert m.handle(ev("in_game")) is None
    assert m.handle(ev("post_game", 1762921700.0)) == GamePhase.POST_GAME
    assert m.session.ended_at == 1762921700.0
    assert m.handle(ev("idle")) is None  # 결과 화면은 사용자가 닫을 때까지 유지
    assert m.dismiss() is True
    assert (m.phase, m.session) == (GamePhase.IDLE, None)


def test_invalid_transitions_are_ignored():
    m = GameStateMachine()
    assert m.handle(ev("post_game")) is None  # 게임 없이 종료 신호
    assert m.dismiss() is False
    assert m.phase == GamePhase.IDLE


def test_game_dropped_to_idle_ends_session_after_grace():
    """게임 중 대기 보고가 유예 시간 이상 계속되면(튕김 등) 기록을 잃지 않게 게임 종료로 처리"""
    m = GameStateMachine(idle_grace_sec=10)
    m.handle(ev("in_game"))
    assert m.handle(ev("idle", 1762920500.0)) is None  # 처음 대기 보고 → 유예 시작
    assert m.handle(ev("idle", 1762920505.0)) is None  # 아직 유예 중
    assert m.handle(ev("idle", 1762920510.0)) == GamePhase.POST_GAME
    assert m.session is not None and m.session.ended_at == 1762920500.0  # 종료 시각 = 대기가 시작된 때


def test_short_idle_during_game_does_not_split_session():
    """재접속처럼 잠깐 대기로 보고됐다가 돌아오면 같은 게임으로 이어진다"""
    m = GameStateMachine(idle_grace_sec=10)
    m.handle(ev("in_game"))
    first = m.session
    assert m.handle(ev("idle", 1762920500.0)) is None
    assert m.handle(ev("in_game", 1762920503.0)) is None
    assert m.handle(ev("idle", 1762920600.0)) is None  # 유예는 처음부터 다시 잰다
    assert (m.phase, m.session) == (GamePhase.IN_GAME, first)


def test_record_only_in_game():
    inc = read_jsonl(FIXTURES / "report" / "input.jsonl", ReportRequest)[0].session.incidents[0]
    m = GameStateMachine()
    assert m.record(inc) is False
    m.handle(ev("in_game"))
    assert m.record(inc) is True
    m.handle(ev("post_game"))
    assert m.record(inc) is False
    assert len(m.session.incidents) == 1


def test_session_id_uses_korea_time():
    assert session_id_for(0.0) == "19700101-090000"
