"""[인터페이스 · 리드 소유] 채팅 메시지를 만드는 Stage 2개

- ParseStage: 흐름 A, OCR 줄(RawLine) → ParseResult(ChatMessage 또는 잡음이면 None)
- ComposeStage: 흐름 B, 내 입력(OutgoingText) → ChatMessage (OCR·parse 를 거치지 않음)
"""

from clean_chat.core.schemas import Channel, ChatMessage, OutgoingText, ParseResult, RawLine, Source
from clean_chat.core.stage import Stage


class ParseStage(Stage[RawLine, ParseResult]):
    name = "parse"
    input_model = RawLine
    output_model = ParseResult

    @classmethod
    def mock_default(cls, item: RawLine) -> ParseResult:
        """fixtures에 없는 입력용 '형식만 맞는' 값 (로직 아님)"""
        return ParseResult(
            line_id=item.id,
            message=ChatMessage(
                id=item.id,
                ts=item.ts,
                source=item.source,
                channel=Channel.UNKNOWN,
                speaker=None,
                text=item.text,
                raw=item.text,
            ),
        )


class ComposeStage(Stage[OutgoingText, ChatMessage]):
    name = "compose"
    input_model = OutgoingText
    output_model = ChatMessage

    @classmethod
    def mock_default(cls, item: OutgoingText) -> ChatMessage:
        """fixtures에 없는 입력용 '형식만 맞는' 값 (로직 아님)"""
        return ChatMessage(
            id=item.id,
            ts=item.ts,
            source=Source.SELF_INPUT,
            channel=Channel.TEAM,
            speaker=None,
            text=item.text,
            is_me=True,
            raw=item.text,
        )
