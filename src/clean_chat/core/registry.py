"""Stage 이름 → (인터페이스, 실제 구현) 연결표. 새 Stage는 여기에 등록 (리드)."""

from __future__ import annotations

from importlib import import_module

from clean_chat.core.stage import MockStage, Stage

# name: (인터페이스 "모듈:클래스", 실제 구현 "모듈:클래스")
REGISTRY: dict[str, tuple[str, str]] = {
    "ocr": ("clean_chat.capture.stage:OcrStage", "clean_chat.capture.impl:OcrEngine"),
    "parse": ("clean_chat.text.stage:ParseStage", "clean_chat.text.parse:Parser"),
    "compose": ("clean_chat.text.stage:ComposeStage", "clean_chat.text.compose:Composer"),
    "normalize": ("clean_chat.text.stage:NormalizeStage", "clean_chat.text.normalize:Normalizer"),
    "classify": ("clean_chat.classify.stage:ClassifyStage", "clean_chat.classify.impl:Classifier"),
    "rewrite": ("clean_chat.rewrite.stage:RewriteStage", "clean_chat.rewrite.impl:Rewriter"),
    "incoming_policy": ("clean_chat.policy.stage:IncomingPolicyStage", "clean_chat.policy.impl:IncomingPolicy"),
    "outgoing_policy": ("clean_chat.policy.stage:OutgoingPolicyStage", "clean_chat.policy.impl:OutgoingPolicy"),
    "report": ("clean_chat.report.stage:ReportStage", "clean_chat.report.impl:ReportWriter"),
    "complaint": ("clean_chat.report.stage:ComplaintStage", "clean_chat.report.impl:ComplaintWriter"),
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
