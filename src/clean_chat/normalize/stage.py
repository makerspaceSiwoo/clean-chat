"""[인터페이스 · 리드 소유] NormalizeStage: ChatMessage → NormalizedMessage"""

from clean_chat.core.schemas import ChatMessage, NormalizedMessage
from clean_chat.core.stage import Stage


class NormalizeStage(Stage[ChatMessage, NormalizedMessage]):
    name = "normalize"
    input_model = ChatMessage
    output_model = NormalizedMessage

    @classmethod
    def mock_default(cls, item: ChatMessage) -> NormalizedMessage:
        """fixtures에 없는 입력용 '형식만 맞는' 값 (로직 아님)"""
        return NormalizedMessage(**item.model_dump(), text_norm=item.text, hints=[])
