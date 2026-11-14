"""계약 테스트: fixtures(통신 포맷 예시)가 스키마와 맞는지. 리드가 스키마를 바꾸면 여기서 먼저 깨짐."""

import pytest

from clean_chat.core.config import FIXTURES
from clean_chat.core.jsonl import read_jsonl
from clean_chat.core.modules import MODULE_NAMES, MODULES
from clean_chat.core.schemas import GamePhase, GameSession, PhaseEvent, RawLine, ReportKind, ReportRequest
from helpers import fixture_pairs


def test_five_modules():
    assert MODULE_NAMES == ("ocr", "parse", "analyze", "rewrite", "report")


@pytest.mark.parametrize("name", MODULE_NAMES)
def test_fixture_pairs_match_schema(name):
    assert fixture_pairs(name)


@pytest.mark.parametrize("name", MODULE_NAMES)
def test_module_function_exists(name):
    """모듈마다 impl.run 이 있어야 연결표가 찾을 수 있다."""
    from clean_chat.core.modules import load

    assert callable(load(name))
    assert MODULES[name].path == f"src/clean_chat/modules/{name}/impl.py"


def test_parse_drops_system_messages_and_handles_my_input():
    """parse 예시: 시스템·핑·잡음은 None, 내 입력(self_input)은 화자 = my_name"""
    pairs = {i.line.id: (i, o) for i, o in fixture_pairs("parse")}
    assert pairs["L1"][1].message is None  # 핑
    assert pairs["L6"][1].message is None  # 잡음
    req, out = pairs["L7"]
    assert req.line.source == "self_input" and out.message.speaker == req.my_name and out.message.is_me


def test_analyze_spans_are_in_original_text():
    """비속어·피드백 조각은 원문(text)에 그대로 있어야 정책표가 가리고 rewrite 가 쓸 수 있다"""
    for req, out in fixture_pairs("analyze"):
        for span in out.profanity_spans + out.feedback_spans:
            assert span in req.message.text, (out.msg_id, span)


def test_scenario_files():
    assert read_jsonl(FIXTURES / "scenario" / "lines.jsonl", RawLine)


def test_report_inputs_are_game_sessions():
    """신고·고소장 입력은 게임 세션 기반이고, 세션에는 다른 유저 채팅(흐름 A)만 기록된다."""
    kinds = set()
    for req in read_jsonl(FIXTURES / "report" / "input.jsonl", ReportRequest):
        kinds.add(req.kind)
        assert req.session.ended_at is not None  # POST_GAME 에서만 실행 → 끝난 게임
        assert req.session.incidents
        assert not any(inc.msg.is_me for inc in req.session.incidents)
        if req.kind == ReportKind.COMPLAINT:
            assert req.complainant and req.output_dir
    assert kinds == {ReportKind.REPORT, ReportKind.COMPLAINT}


def test_session_round_trip_jsonl():
    """세션 저장소(.clean-chat/sessions/<id>.jsonl)가 쓰는 JSON 한 줄 직렬화가 손실 없이 돌아오는지"""
    session = read_jsonl(FIXTURES / "report" / "input.jsonl", ReportRequest)[0].session
    assert GameSession.model_validate_json(session.model_dump_json()) == session


def test_phase_event_values():
    assert [p.value for p in GamePhase] == ["idle", "in_game", "post_game"]
    ev = PhaseEvent.model_validate_json('{"ts": 1.0, "phase": "in_game", "raw": "InProgress"}')
    assert ev.phase is GamePhase.IN_GAME
