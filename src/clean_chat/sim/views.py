"""시뮬레이터 화면 목록: 모듈 5개(core/modules.py) + 모듈 폴더 안의 추가 함수.

모듈 연결표(계약)는 그대로 두고, 시뮬레이터에서만 따로 돌려 볼 함수를 여기에 더한다.
지금은 analyze 폴더의 **대화 판단**(judge) 하나 — 아직 앱 흐름에는 연결되지 않은 함수다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from clean_chat.core import modules
from clean_chat.core.config import FIXTURES
from clean_chat.modules.analyze.judge import JudgeRequest, Judgment


@dataclass(frozen=True)
class View:
    name: str
    number: str
    title: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    target: str  # "모듈경로:함수"
    path: str  # 레포 안 구현 파일
    examples: Path  # 예시 입력 JSONL


def _of(spec: modules.ModuleSpec) -> View:
    return View(
        spec.name,
        spec.number,
        spec.title,
        spec.input_model,
        spec.output_model,
        spec.target,
        spec.path,
        FIXTURES / spec.name / "input.jsonl",
    )


EXTRA: dict[str, tuple[View, ...]] = {  # 이 모듈 바로 뒤에 보여 줄 추가 화면
    "analyze": (
        View(
            "judge",
            "③+",
            "대화 판단 · 전체 대화 → 신고 권고·고소 후보",
            JudgeRequest,
            Judgment,
            "clean_chat.modules.analyze.judge:judge",
            "src/clean_chat/modules/analyze/judge.py",
            FIXTURES / "analyze" / "judge_input.jsonl",
        ),
    ),
}
VIEWS: dict[str, View] = {
    v.name: v for spec in modules.MODULES.values() for v in (_of(spec), *EXTRA.get(spec.name, ()))
}
VIEW_NAMES = tuple(VIEWS)


def load(name: str) -> Callable[[Any], Any]:
    mod, fn = VIEWS[name].target.split(":")
    return getattr(import_module(mod), fn)


def invoke(name: str, fn: Callable[[Any], Any], item: BaseModel) -> BaseModel:
    """함수 1번 실행 + 출력 형식 검증. 모듈 5개는 연결표의 invoke 를 그대로 쓴다."""
    if name in modules.MODULES:
        return modules.invoke(name, fn, item)
    out = fn(item)
    if not isinstance(out, BaseModel):
        raise TypeError(f"'{name}' 이 {VIEWS[name].output_model.__name__} 대신 {type(out).__name__} 을 돌려줬습니다")
    return VIEWS[name].output_model.model_validate(out.model_dump())
