"""전부 mock 으로 끝까지 돌렸을 때 시나리오 기대 결과와 같은지 (연결 구조 검증)."""

from clean_chat.core.config import FIXTURES
from clean_chat.core.engine import Engine
from clean_chat.core.pipeline import Pipeline
from clean_chat.core.schemas import Incident
from clean_chat.core.sources import DemoLineSource
from clean_chat.core.stage import read_jsonl


def test_mock_pipeline_matches_scenario():
    got: list[Incident] = []
    eng = Engine(Pipeline(), DemoLineSource(FIXTURES / "scenario" / "lines.jsonl", delay_sec=0))
    eng.subscribe(got.append)
    eng.start(block=True)
    assert got == read_jsonl(FIXTURES / "scenario" / "expected_incidents.jsonl", Incident)
