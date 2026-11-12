"""[인터페이스 · 리드 소유] ParseStage: RawLine → ParseResult"""

from lolguard.core.schemas import Channel, ChatMessage, ParseResult, RawLine
from lolguard.core.stage import Stage


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
