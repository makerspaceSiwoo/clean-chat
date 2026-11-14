"""정책표 (구성, core/policy.py): SPEC 5-1 / 5-2 표를 그대로 적용하는지."""

import json
from pathlib import Path

import pytest

from clean_chat.core.policy import decide_incoming, decide_outgoing, mask_profanity
from clean_chat.core.schemas import Action, Analysis, ChatMessage, Level, Rewrite

CASES = [json.loads(line) for line in (Path(__file__).parent / "data" / "policy_cases.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("case", CASES, ids=[f"{c['flow']}-{c['message']['id']}" for c in CASES])
def test_policy_table(case):
    msg = ChatMessage.model_validate(case["message"])
    analysis = Analysis.model_validate(case["analysis"])
    rewrite = Rewrite.model_validate(case["rewrite"]) if case["rewrite"] else None
    d = (decide_incoming if case["flow"] == "incoming" else decide_outgoing)(msg, analysis, rewrite)
    assert d.action == case["expected_action"]
    assert d.display_text == case["expected_display_text"]
    assert (d.report, d.complaint_candidate) == (case["expected_report"], case["expected_complaint_candidate"])
    assert d.target == analysis.target and d.msg_id == msg.id


def _msg(text: str, is_me: bool = False) -> ChatMessage:
    return ChatMessage(
        id="m", ts=0, source="ocr", channel="team", speaker="a", text=text, text_norm=text, is_me=is_me, raw=text
    )


def _an(level: int, feedback: list[str] | None = None) -> Analysis:
    return Analysis(msg_id="m", level=level, feedback_spans=feedback or [], model_version="t")


def test_rewrite_failure_hides_or_blocks():
    failed = Rewrite(msg_id="m", rewritten=None, backend="t")
    assert decide_incoming(_msg("x"), _an(2, ["y"]), failed).action == Action.HIDE
    assert decide_outgoing(_msg("x", True), _an(2, ["y"]), failed).action == Action.BLOCK


def test_l3_with_feedback_shows_feedback_only():
    d = decide_incoming(_msg("x"), _an(Level.L3_LEGAL, ["y"]), Rewrite(msg_id="m", rewritten="좋게", backend="t"))
    assert (d.action, d.display_text, d.report, d.complaint_candidate) == (Action.SHOW_REWRITTEN, "좋게", True, True)


def test_my_own_chat_read_from_screen_is_shown_as_is():
    assert decide_incoming(_msg("ㅅㅂ", is_me=True), _an(2)).action == Action.SHOW


def test_l3_outgoing_is_blocked_even_with_feedback():
    d = decide_outgoing(_msg("x", True), _an(3, ["y"]), Rewrite(msg_id="m", rewritten="좋게", backend="t"))
    assert d.action == Action.BLOCK


def test_mask_longest_span_first():
    assert mask_profanity("개새끼 새끼", ["새끼", "개새끼"]) == "** **"
    assert mask_profanity("정상 문장", []) == "정상 문장"
