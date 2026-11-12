"""[구현 · capture 담당] OCR 엔진. Mac에서도 스크린샷 파일로 개발·테스트 가능.

해야 할 일 (docs/MODULES.md#capture):
  1. image_path 의 이미지를 연다
  2. 전처리: 확대, 흑백, 대비, 채팅 글자 색만 남기기 (롤 채팅 설정과 함께 조정)
  3. OCR → 줄 단위 텍스트 (엔진은 OPEN-03에서 결정. 엔진은 교체 가능하게 내부 클래스로 분리)
  4. 이전 프레임에서 이미 내보낸 줄은 제외 (중복 제거, 상태 유지)
  5. 줄마다 RawLine(id, ts, text, source=ocr, ocr_confidence)
"""

from lolguard.capture.stage import OcrStage
from lolguard.core.schemas import Frame, OcrResult


class OcrEngine(OcrStage):
    def setup(self) -> None:
        pass  # TODO: OCR 엔진 로딩

    def run(self, item: Frame) -> OcrResult:
        raise NotImplementedError("capture 담당: OCR 구현")
