"""테스트 도우미 (리드 소유). 앱·시뮬레이터에는 Mock 이 없고(ADR-0017), 테스트만 가짜 함수를 쓴다.

- fixture_modules(): fixtures 기대값을 id 로 찾아 돌려주는 가짜 모듈 묶음 → 연결 구조(흐름 A/B, 세션, 종료 배치)만 검증
- check_module(): 모듈 1개를 실제 함수로 fixtures 에 돌려 본다. 구현 전이면 skip → 구현하는 순간 검사가 시작된다
"""

from __future__ import annotations

import pytest

from clean_chat.core import modules
from clean_chat.core.config import FIXTURES
from clean_chat.core.jsonl import read_jsonl
from clean_chat.core.modules import ModuleSet
from clean_chat.core.platform import PlatformNotSupported

SCENARIO = FIXTURES / "scenario"


def fixture_pairs(name: str) -> list[tuple]:
    spec = modules.MODULES[name]
    ins = read_jsonl(FIXTURES / name / "input.jsonl", spec.input_model)
    outs = read_jsonl(FIXTURES / name / "expected.jsonl", spec.output_model)
    return list(zip(ins, outs, strict=True))


def fixture_modules(**overrides) -> ModuleSet:
    """fixtures 기대값을 그대로 돌려주는 가짜 모듈 5개. 모르는 id 면 KeyError (조용히 값을 지어내지 않음)."""
    ocr = {i.id: o for i, o in fixture_pairs("ocr")}
    parse = {i.line.id: o for i, o in fixture_pairs("parse")}
    analyze = {i.message.id: o for i, o in fixture_pairs("analyze")}
    rewrite = {i.message.id: o for i, o in fixture_pairs("rewrite")}
    report = {(i.kind, i.speaker): o for i, o in fixture_pairs("report")}
    fakes = {
        "ocr": lambda frame: ocr[frame.id],
        "parse": lambda req: parse[req.line.id],
        "analyze": lambda req: analyze[req.message.id],
        "rewrite": lambda req: rewrite[req.message.id],
        "report": lambda req: report[(req.kind, req.speaker)],
    }
    return ModuleSet({**fakes, **overrides})


def check_module(name: str, strict: bool) -> None:
    """실제 모듈 함수를 fixtures 입력으로 실행. 출력 형식은 항상, strict 면 기대값과 정확히 같은지까지 본다."""
    pairs = fixture_pairs(name)
    fn = modules.load(name)
    try:
        outs = [modules.invoke(name, fn, i) for i, _ in pairs]
    except modules.ModuleNotImplemented:
        pytest.skip(f"{name}: 아직 구현 전")
    except PlatformNotSupported:
        pytest.skip(f"{name}: Windows 전용")
    if strict:
        assert outs == [o for _, o in pairs]
