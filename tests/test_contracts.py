"""계약 테스트: fixtures(통신 포맷 예시)가 스키마와 맞는지. 리드가 스키마를 바꾸면 여기서 먼저 깨짐."""

import pytest

from clean_chat.core import registry
from clean_chat.core.config import FIXTURES, STAGE_NAMES
from clean_chat.core.schemas import Incident, RawLine
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
