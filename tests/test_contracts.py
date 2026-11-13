"""계약 테스트: fixtures(통신 포맷 예시)가 스키마와 맞는지. 리드가 스키마를 바꾸면 여기서 먼저 깨짐."""

import pytest

from clean_chat.core import registry
from clean_chat.core.config import FIXTURES, STAGE_NAMES
from clean_chat.core.schemas import (
    ComplaintRequest,
    GamePhase,
    GameSession,
    Incident,
    PhaseEvent,
    RawLine,
    ReportRequest,
)
from clean_chat.core.stage import read_jsonl


@pytest.mark.parametrize("name", STAGE_NAMES)
def test_fixture_pairs_match_schema(name):
    iface = registry.interface(name)
    ins = read_jsonl(FIXTURES / name / "input.jsonl", iface.input_model)
    outs = read_jsonl(FIXTURES / name / "expected.jsonl", iface.output_model)
    assert ins and len(ins) == len(outs)


def test_scenario_files():
    assert read_jsonl(FIXTURES / "scenario" / "lines.jsonl", RawLine)
    assert read_jsonl(FIXTURES / "scenario" / "expected_incidents.jsonl", Incident)


@pytest.mark.parametrize("name", STAGE_NAMES)
def test_mock_default_is_valid(name):
    """fixtures에 없는 입력이 와도 mock이 형식에 맞는 값을 돌려주는지"""
    iface = registry.interface(name)
    item = read_jsonl(FIXTURES / name / "input.jsonl", iface.input_model)[0]
    out = iface.mock_default(item)
    assert isinstance(out, iface.output_model)


@pytest.mark.parametrize(("name", "model"), [("report", ReportRequest), ("complaint", ComplaintRequest)])
def test_report_inputs_are_game_sessions(name, model):
    """신고·고소장 입력은 게임 세션 기반이고, 세션에는 다른 유저 채팅(흐름 A)만 기록된다 (HANDOFF 5-1, 5-2)."""
    for req in read_jsonl(FIXTURES / name / "input.jsonl", model):
        assert isinstance(req.session, GameSession)
        assert req.session.ended_at is not None  # POST_GAME 에서만 실행 → 끝난 게임
        assert req.session.incidents
        assert not any(inc.msg.is_me for inc in req.session.incidents)


def test_session_round_trip_jsonl():
    """세션 저장소(.clean-chat/sessions/<id>.jsonl)가 쓰는 JSON 한 줄 직렬화가 손실 없이 돌아오는지"""
    session = read_jsonl(FIXTURES / "report" / "input.jsonl", ReportRequest)[0].session
    assert GameSession.model_validate_json(session.model_dump_json()) == session


def test_phase_event_values():
    assert [p.value for p in GamePhase] == ["idle", "in_game", "post_game"]
    ev = PhaseEvent.model_validate_json('{"ts": 1.0, "phase": "in_game", "raw": "InProgress"}')
    assert ev.phase is GamePhase.IN_GAME


def test_shared_contracts_file_is_up_to_date():
    """contracts/stages.schema.json 이 schemas.py 와 같아야 웹앱이 같은 계약을 쓴다 (ADR-0015).

    실패하면: uv run python scripts/export_contracts.py 실행 후 함께 커밋
    """
    import importlib.util

    from clean_chat.core.config import ROOT

    spec = importlib.util.spec_from_file_location("export_contracts", ROOT / "scripts" / "export_contracts.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--check"]) == 0
