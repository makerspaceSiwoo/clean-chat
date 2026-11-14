"""모듈 연결표 (리드 소유): 모듈 이름 → (입력 모델, 출력 모델, 함수 위치). ADR-0017.

모듈 = 함수 1개 (`src/clean_chat/modules/<이름>/impl.py` 의 run). Mock 은 없다 — 구현이 없으면 오류를 낸다.
  call("parse", {...})        # dict/JSON → 입력 검증 → run → 출력 검증 → 출력 모델
  ModuleSet()                 # 파이프라인이 쓰는 함수 묶음. 테스트에서는 가짜 함수를 넣어 연결 구조만 검증한다
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from pydantic import BaseModel

from clean_chat.core.schemas import (
    Analysis,
    AnalyzeRequest,
    Frame,
    OcrResult,
    ParseRequest,
    ParseResult,
    ReportDraft,
    ReportRequest,
    Rewrite,
    RewriteRequest,
)


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    number: str  # 화면·문서용 번호 (① ~ ⑤)
    title: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    @property
    def target(self) -> str:
        """함수 위치 "모듈경로:함수"."""
        return f"clean_chat.modules.{self.name}.impl:run"

    @property
    def path(self) -> str:
        """레포 안 구현 파일."""
        return f"src/clean_chat/modules/{self.name}/impl.py"


MODULES: dict[str, ModuleSpec] = {
    m.name: m
    for m in (
        ModuleSpec("ocr", "①", "OCR · 이미지 → 텍스트 줄", Frame, OcrResult),
        ModuleSpec("parse", "②", "채팅 추출 · 시스템 메시지 제외 + 정규화", ParseRequest, ParseResult),
        ModuleSpec("analyze", "③", "분석 · 대상·등급·피드백", AnalyzeRequest, Analysis),
        ModuleSpec("rewrite", "④", "순화 · 피드백만 공손하게", RewriteRequest, Rewrite),
        ModuleSpec("report", "⑤", "신고 문구 · 고소장 초안", ReportRequest, ReportDraft),
    )
}
MODULE_NAMES = tuple(MODULES)


class ModuleNotImplemented(RuntimeError):
    """모듈 함수가 아직 NotImplementedError 를 던짐 (담당자가 구현 전)."""

    def __init__(self, name: str, detail: str = "") -> None:
        super().__init__(f"모듈 '{name}' 구현이 아직 없습니다 ({MODULES[name].path}){f': {detail}' if detail else ''}")
        self.module = name


def load(name: str) -> Callable[[Any], Any]:
    """모듈 함수(run)를 가져온다. 이름이 없으면 KeyError."""
    mod, fn = MODULES[name].target.split(":")
    return getattr(import_module(mod), fn)


def invoke(name: str, fn: Callable[[Any], Any], item: BaseModel) -> BaseModel:
    """함수 1번 실행 + 출력 형식 검증. NotImplementedError → ModuleNotImplemented."""
    spec = MODULES[name]
    try:
        out = fn(item)
    except NotImplementedError as e:
        raise ModuleNotImplemented(name, str(e)) from e
    if not isinstance(out, BaseModel):
        raise TypeError(f"모듈 '{name}' 이 {spec.output_model.__name__} 대신 {type(out).__name__} 을 돌려줬습니다")
    return spec.output_model.model_validate(out.model_dump())


def call(name: str, data: Mapping[str, Any] | BaseModel) -> BaseModel:
    """dict(JSON) 또는 입력 모델 → 실제 모듈 실행 → 출력 모델. 입력 형식이 틀리면 pydantic.ValidationError."""
    spec = MODULES[name]
    item = data if isinstance(data, spec.input_model) else spec.input_model.model_validate(data)
    return invoke(name, load(name), item)


class ModuleSet:
    """파이프라인이 쓰는 모듈 함수 묶음. 기본은 실제 함수, 테스트에서는 overrides 로 가짜 함수를 넣는다."""

    def __init__(self, overrides: Mapping[str, Callable[[Any], Any]] | None = None) -> None:
        self._fns = dict(overrides or {})

    def run(self, name: str, item: BaseModel) -> Any:
        fn = self._fns.get(name)
        if fn is None:
            fn = self._fns[name] = load(name)
        return invoke(name, fn, item)
