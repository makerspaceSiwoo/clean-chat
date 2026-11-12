"""[인터페이스 · 리드 소유] PolicyStage: PolicyRequest → Decision"""

from lolguard.core.schemas import Action, Decision, PolicyRequest
from lolguard.core.stage import Stage


class PolicyStage(Stage[PolicyRequest, Decision]):
    name = "policy"
    input_model = PolicyRequest
    output_model = Decision

    @classmethod
    def mock_default(cls, item: PolicyRequest) -> Decision:
        """fixtures에 없는 입력용 '형식만 맞는' 값 (로직 아님)"""
        return Decision(
            msg_id=item.message.id,
            is_me=item.message.is_me,
            action=Action.COPY if item.message.is_me else Action.SHOW,
            display_text=item.message.text,
            reason="mock",
        )
