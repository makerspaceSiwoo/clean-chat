"""[구현 · WP1] 정책 Stage 2개: 분류 결과 → 처리 결정  (명세: docs/MODULES.md#policy, SPEC 5장)

- IncomingPolicy (흐름 A, 다른 유저 채팅): SPEC 5-1 표 → 표시/가림/피드백만/숨김 + 신고·고소 후보
- OutgoingPolicy (흐름 B, 내 입력):       SPEC 5-2 표 → 복사/가려서 복사/피드백만 복사/차단
결과가 정해진 규칙 모듈이라 fixtures 와 정확히 같아야 한다(STRICT). 분류는 다시 하지 않는다.
"""

from __future__ import annotations

from clean_chat.core.schemas import Action, Decision, Player, PolicyRequest
from clean_chat.policy.stage import IncomingPolicyStage, OutgoingPolicyStage


class IncomingPolicy(IncomingPolicyStage):
    """[구현 · WP1] PolicyRequest → Decision (다른 유저 채팅)"""

    def setup(self) -> None:
        """화자별 누적 횟수 기억 초기화. 관련: OPEN-07"""
        raise NotImplementedError("policy 담당: incoming setup")

    def run(self, item: PolicyRequest) -> Decision:
        """SPEC 5-1 표를 그대로 적용한다.

        입력: PolicyRequest(message, classification, rewrite?, players) → 출력: Decision
        표: L0 → show / L1 → show_masked(비속어만 ***) / L2+피드백 → show_rewritten(신고) /
            L2 → hide(신고) / L3 → hide(신고 + 고소 후보, 피드백 있으면 피드백만 표시)
        예) "야 정글 ㅂㅅ아 용 먼저 치라고"(L2, 피드백) → show_rewritten "용 먼저 치자", target="정글", report=True
        예) "탑 니애미 tlqkf"(L3) → hide, target="탑", report=True, complaint_candidate=True
        예) "아 ㅅㅂ 내가 실수함"(L1) → show_masked "아 ** 내가 실수함", report=False
        순서: _choose_action → _display_text → _guess_target → _reason
        주의: rewrite 가 None(실패)이면 피드백 표시 대신 hide. 내가 게임에 직접 친 채팅(is_me)은 그대로 표시.
        관련: SPEC 5-1, OPEN-07(L1 마스킹), ADR-0007
        """
        raise NotImplementedError("policy 담당: incoming run")

    def _choose_action(self, item: PolicyRequest) -> tuple[Action, bool, bool]:
        """등급·피드백·리라이트 성공 여부 → (처리, 신고 여부, 고소 후보 여부)."""
        raise NotImplementedError

    def _display_text(self, item: PolicyRequest, action: Action) -> str | None:
        """처리에 맞는 표시 문장. show=원문, show_masked=_mask_profanity, show_rewritten=rewrite.rewritten, hide=None."""
        raise NotImplementedError

    def _mask_profanity(self, text: str, text_norm: str) -> str:
        """비속어 부분만 ** 로 가린다. 예) "아 ㅅㅂ 내가 실수함" → "아 ** 내가 실수함"."""
        raise NotImplementedError

    def _guess_target(self, text: str, players: list[Player]) -> str | None:
        """공격 대상 추정: 포지션 단어(탑/정글/미드/원딜/서폿) → 명단의 닉네임·챔피언 → 직전 대화 상대. 모르면 None."""
        raise NotImplementedError

    def _reason(self, action: Action, level: int, has_feedback: bool) -> str:
        """사람이 읽는 판단 근거. 예) "L2 + 피드백 → 피드백만 표시, 원문 신고"."""
        raise NotImplementedError


class OutgoingPolicy(OutgoingPolicyStage):
    """[구현 · WP1] PolicyRequest → Decision (내 입력)"""

    def run(self, item: PolicyRequest) -> Decision:
        """SPEC 5-2 표를 그대로 적용한다.

        입력: PolicyRequest(message.is_me=True, ...) → 출력: Decision(is_me=True)
        표: L0 → copy / L1 → copy_masked / L2+피드백 → copy_rewritten / 그 외(L2, L3) → block
        예) "아 정글 ㅂㅅ 왜 안 와"(L2, 피드백) → copy_rewritten "정글 합류 부탁해요", target="정글"
        예) "정글 개새끼"(L2) → block, display_text=None, reason="내 채팅 L2 → 전송 차단"
        순서: _choose_action → _display_text → _guess_target → _reason
        주의: 신고·고소 표시는 하지 않는다(report=False). rewrite 실패(None)면 block.
        관련: SPEC 5-2, ADR-0006
        """
        raise NotImplementedError("policy 담당: outgoing run")

    def _choose_action(self, item: PolicyRequest) -> Action:
        """등급·피드백·리라이트 성공 여부 → copy / copy_masked / copy_rewritten / block."""
        raise NotImplementedError

    def _display_text(self, item: PolicyRequest, action: Action) -> str | None:
        """복사할 문장. copy=원문, copy_masked=비속어 가림, copy_rewritten=rewrite.rewritten, block=None."""
        raise NotImplementedError

    def _guess_target(self, text: str, players: list[Player]) -> str | None:
        """내 문장이 향하는 대상 (IncomingPolicy 와 같은 기준)."""
        raise NotImplementedError

    def _reason(self, action: Action, level: int, has_feedback: bool) -> str:
        """예) "내 채팅 L2 + 피드백 → 피드백만 전송"."""
        raise NotImplementedError
