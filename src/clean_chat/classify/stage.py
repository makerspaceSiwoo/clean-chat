"""[인터페이스 · 리드 소유] ClassifyStage: NormalizedMessage → Classification"""

from clean_chat.core.schemas import Classification, Level, NormalizedMessage
from clean_chat.core.stage import Stage


class ClassifyStage(Stage[NormalizedMessage, Classification]):
    name = "classify"
    input_model = NormalizedMessage
    output_model = Classification

    @classmethod
    def mock_default(cls, item: NormalizedMessage) -> Classification:
        """fixtures에 없는 입력용 '형식만 맞는' 값 (로직 아님)"""
        return Classification(msg_id=item.id, level=Level.L0_CLEAN, model_version="mock")
