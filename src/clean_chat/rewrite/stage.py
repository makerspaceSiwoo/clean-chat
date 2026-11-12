"""[인터페이스 · 리드 소유] RewriteStage: RewriteRequest → Rewrite"""

from clean_chat.core.schemas import Rewrite, RewriteRequest
from clean_chat.core.stage import Stage


class RewriteStage(Stage[RewriteRequest, Rewrite]):
    name = "rewrite"
    input_model = RewriteRequest
    output_model = Rewrite

    @classmethod
    def mock_default(cls, item: RewriteRequest) -> Rewrite:
        """fixtures에 없는 입력용 '형식만 맞는' 값 (로직 아님)"""
        return Rewrite(msg_id=item.message.id, rewritten=None, backend="mock")
