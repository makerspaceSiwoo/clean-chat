"""전부 mock 으로 끝까지 돌렸을 때 시나리오 기대 결과와 같은지 (연결 구조 검증)."""

from lolguard.core.config import FIXTURES
from lolguard.core.engine import Engine
from lolguard.core.pipeline import Pipeline
from lolguard.core.schemas import Incident
from lolguard.core.sources import DemoLineSource
from lolguard.core.stage import read_jsonl


def test_mock_pipeline_matches_scenario():
    got: list[Incident] = []
    eng = Engine(Pipeline(), DemoLineSource(FIXTURES / "scenario" / "lines.jsonl", delay_sec=0))
    eng.subscribe(got.append)
    eng.start(block=True)
    assert got == read_jsonl(FIXTURES / "scenario" / "expected_incidents.jsonl", Incident)
