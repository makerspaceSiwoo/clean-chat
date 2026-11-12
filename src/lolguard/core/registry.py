"""Stage 이름 → (인터페이스, 실제 구현) 연결표. 새 Stage는 여기에 등록 (리드)."""

from __future__ import annotations

from importlib import import_module

from lolguard.core.stage import MockStage, Stage

# name: (인터페이스 "모듈:클래스", 실제 구현 "모듈:클래스")
REGISTRY: dict[str, tuple[str, str]] = {
    "ocr": ("lolguard.capture.stage:OcrStage", "lolguard.capture.impl:OcrEngine"),
    "parse": ("lolguard.parse.stage:ParseStage", "lolguard.parse.impl:Parser"),
    "normalize": ("lolguard.normalize.stage:NormalizeStage", "lolguard.normalize.impl:Normalizer"),
    "classify": ("lolguard.classify.stage:ClassifyStage", "lolguard.classify.impl:Classifier"),
    "rewrite": ("lolguard.rewrite.stage:RewriteStage", "lolguard.rewrite.impl:Rewriter"),
    "policy": ("lolguard.policy.stage:PolicyStage", "lolguard.policy.impl:PolicyEngine"),
    "report": ("lolguard.report.stage:ReportStage", "lolguard.report.impl:ReportWriter"),
    "complaint": ("lolguard.report.stage:ComplaintStage", "lolguard.report.impl:ComplaintWriter"),
}


def _load(path: str) -> type:
    mod, cls = path.split(":")
    return getattr(import_module(mod), cls)


def interface(name: str) -> type[Stage]:
    return _load(REGISTRY[name][0])


def create(name: str, impl: str = "mock") -> Stage:
    """impl = "mock" | "real" """
    if impl == "mock":
        return MockStage(interface(name))
    if impl == "real":
        return _load(REGISTRY[name][1])()
    raise ValueError(f"impl은 mock 또는 real: {impl!r}")
