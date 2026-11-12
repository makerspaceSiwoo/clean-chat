"""[인터페이스 · 리드 소유] OCR Stage: Frame(채팅창 이미지) → OcrResult(새 채팅 줄들)"""

from lolguard.core.schemas import Frame, OcrResult
from lolguard.core.stage import Stage


class OcrStage(Stage[Frame, OcrResult]):
    name = "ocr"
    input_model = Frame
    output_model = OcrResult

    @classmethod
    def mock_default(cls, item: Frame) -> OcrResult:
        return OcrResult(frame_id=item.id, lines=[])
