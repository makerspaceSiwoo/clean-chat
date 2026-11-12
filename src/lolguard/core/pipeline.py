"""Stage들을 순서대로 연결하는 파이프라인 (리드 소유). 판단 로직은 넣지 않는다.

모듈별 real/mock 은 settings.impl 로 선택:  Pipeline({"parse": "real"})  → parse만 실제, 나머지 mock
"""

from __future__ import annotations

from lolguard.core import registry
from lolguard.core.config import STAGE_NAMES, settings
from lolguard.core.schemas import (
    Frame,
    Incident,
    Level,
    Player,
    PolicyRequest,
    RawLine,
    RewriteRequest,
)


class Pipeline:
    def __init__(self, overrides: dict[str, str] | None = None) -> None:
        impl = {**settings.impl, **(overrides or {})}
        self.impl = impl
        self.st = {n: registry.create(n, impl[n]) for n in STAGE_NAMES}
        self.players: list[Player] = []

    def setup(self) -> None:
        for s in self.st.values():
            s.setup()

    def close(self) -> None:
        for s in self.st.values():
            s.close()

    # ── 진입점 ──
    def process_frame(self, frame: Frame) -> list[Incident]:
        """[Windows 실제 앱] 캡처 이미지 1장 → 새 채팅 줄들 처리"""
        result = self.st["ocr"].run(frame)
        return [inc for line in result.lines if (inc := self.process_line(line))]

    def process_line(self, line: RawLine) -> Incident | None:
        """채팅 한 줄 (OCR 결과 / 데모 재생 / 내 입력 SELF_INPUT 모두 여기로)"""
        parsed = self.st["parse"].run(line)
        if parsed.message is None:
            return None
        msg = self.st["normalize"].run(parsed.message)
        cls = self.st["classify"].run(msg)
        rw = None
        if cls.level >= Level.L2_ABUSIVE and cls.has_feedback:
            rw = self.st["rewrite"].run(RewriteRequest(message=msg, classification=cls))
        dec = self.st["policy"].run(PolicyRequest(message=msg, classification=cls, rewrite=rw, players=self.players))
        return Incident(msg=msg, classification=cls, decision=dec, rewrite=rw)
