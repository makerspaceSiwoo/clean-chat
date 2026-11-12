"""[구현 · WP2] OCR Stage: Frame(채팅창 이미지) → OcrResult(새로 나타난 채팅 줄)  (명세: docs/MODULES.md#ocr)

Mac 에서도 스크린샷 파일(fixtures/ocr/images/)로 개발·테스트할 수 있다. 화면 캡처 자체는 grabber.py(🪟).
OCR 엔진은 Strategy 로 바꿔 끼운다(OcrBackend). 엔진 선택은 OPEN-03.
"""

from __future__ import annotations

from typing import Protocol

from clean_chat.capture.stage import OcrStage
from clean_chat.core.schemas import Frame, OcrResult, RawLine


class OcrBackend(Protocol):
    """OCR 엔진 1개 (Windows 내장 OCR / PaddleOCR / EasyOCR 중 OPEN-03 에서 결정)."""

    def read(self, image: object) -> list[tuple[str, float]]:
        """전처리된 이미지 → [(줄 텍스트, 신뢰도 0~1), ...] 위에서 아래 순서."""
        ...


class OcrEngine(OcrStage):
    """[구현 · WP2] Frame → OcrResult"""

    def setup(self) -> None:
        """OCR 엔진 로딩(무거움, 앱 시작 시 1번)과 '이미 내보낸 줄' 기억 초기화.

        순서: _create_backend(엔진 이름) → 최근 줄 기억(예: 최근 30줄) 비우기
        주의: 모델 파일이 없으면 어떤 파일이 필요한지 안내하는 예외. 관련: OPEN-03
        """
        raise NotImplementedError("capture 담당: setup")

    def run(self, item: Frame) -> OcrResult:
        """채팅창 이미지 1장 → 이번 프레임에 **새로** 나타난 줄만.

        입력: Frame(image_path, region) → 출력: OcrResult(frame_id, lines=RawLine[])
        예) fixtures/ocr: sample_01.png → ["[팀] 탑솔장인 (가렌): 다들 화이팅", "정글러 (리신)님이 ... 신호를 보냈습니다", ...]
            다음 프레임에 같은 줄이 또 보이면 lines 에서 빠진다.
        순서: _load_image → _preprocess → backend.read → _merge_wrapped_lines → _drop_seen → _to_raw_lines
        주의: 프레임당 0.5초 이내. 실패하면 예외 대신 빈 lines (앱을 멈추지 않음). 오버레이가 찍히면 안 됨(ADR-0003).
        관련: ADR-0002, OPEN-02, OPEN-03, OPEN-06
        """
        raise NotImplementedError("capture 담당: run")

    def close(self) -> None:
        """OCR 엔진 자원 정리."""
        raise NotImplementedError("capture 담당: close")

    def _create_backend(self, name: str) -> OcrBackend:
        """엔진 이름("windows" | "paddle" | "easyocr") → OcrBackend. 무거운 import 는 여기 안에서."""
        raise NotImplementedError

    def _load_image(self, path: str) -> object:
        """PNG 경로 → 이미지 객체 (Pillow 또는 numpy 배열)."""
        raise NotImplementedError

    def _preprocess(self, image: object) -> object:
        """OCR 이 잘 읽도록: 2~3배 확대, 흑백, 대비 강화, 채팅 글자 색만 남기기(롤 채팅 색 설정과 함께 조정, OPEN-06)."""
        raise NotImplementedError

    def _merge_wrapped_lines(self, lines: list[tuple[str, float]]) -> list[tuple[str, float]]:
        """긴 채팅이 두 줄로 꺾여 보이면 한 줄로 합친다. 예) "[팀] 원딜러 (징크스): 야 정글" + "ㅂㅅ아 용 먼저 치라고"."""
        raise NotImplementedError

    def _drop_seen(self, lines: list[tuple[str, float]]) -> list[tuple[str, float]]:
        """앞 프레임에서 이미 내보낸 줄 제외 (채팅창은 위로 밀려 올라가므로 겹치는 구간을 찾는다). 상태 유지."""
        raise NotImplementedError

    def _to_raw_lines(self, frame: Frame, lines: list[tuple[str, float]]) -> list[RawLine]:
        """(텍스트, 신뢰도) → RawLine(id, ts=frame.ts, text, source=ocr, ocr_confidence). id 는 앱 실행 중 유일하게."""
        raise NotImplementedError
