"""[인터페이스 · 리드 소유] 정책 Stage 2개 (HANDOFF 5-1, SPEC 5장)

- IncomingPolicyStage: 흐름 A, 다른 유저 채팅 → 표시/숨김/신고 (SPEC 5-1 표)
- OutgoingPolicyStage: 흐름 B, 내 입력 → 복사/차단 (SPEC 5-2 표)
둘 다 PolicyRequest → Decision. 분류(classify)는 분류만 하고, 처리 결정은 여기서만 한다.
"""

from clean_chat.core.schemas import Action, Decision, PolicyRequest
from clean_chat.core.stage import Stage


class IncomingPolicyStage(Stage[PolicyRequest, Decision]):
    name = "incoming_policy"
    input_model = PolicyRequest
    output_model = Decision

    @classmethod
    def mock_default(cls, item: PolicyRequest) -> Decision:
        """fixtures에 없는 입력용 '형식만 맞는' 값 (로직 아님)"""
        return Decision(
            msg_id=item.message.id,
            is_me=item.message.is_me,
            action=Action.SHOW,
            display_text=item.message.text,
            reason="mock",
        )


class OutgoingPolicyStage(Stage[PolicyRequest, Decision]):
    name = "outgoing_policy"
    input_model = PolicyRequest
    output_model = Decision

    @classmethod
    def mock_default(cls, item: PolicyRequest) -> Decision:
        """fixtures에 없는 입력용 '형식만 맞는' 값 (로직 아님)"""
        return Decision(
            msg_id=item.message.id,
            is_me=True,
            action=Action.COPY,
            display_text=item.message.text,
            reason="mock",
        )
