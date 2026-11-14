"""처리 정책표 (구성, 리드 소유): Analysis → Decision. SPEC 5-1(다른 유저), 5-2(내 채팅)를 그대로 옮긴 표.

판단(등급·대상·피드백)은 analyze 모듈이 이미 했다. 여기서는 표만 적용하고 다시 분류하지 않는다.
"""

from __future__ import annotations

from clean_chat.core.schemas import Action, Analysis, ChatMessage, Decision, Level, Rewrite

MASK = "**"


def mask_profanity(text: str, spans: list[str]) -> str:
    """원문에서 비속어 조각만 ** 로 가린다. 예) ("아 ㅅㅂ 내가 실수함", ["ㅅㅂ"]) → "아 ** 내가 실수함"."""
    for span in sorted({s for s in spans if s}, key=len, reverse=True):  # 긴 조각부터 (겹침 방지)
        text = text.replace(span, MASK)
    return text


def _rewritten(analysis: Analysis, rewrite: Rewrite | None) -> str | None:
    """피드백만 보여 줄 수 있으면 그 문장. 피드백이 없거나 순화에 실패했으면 None."""
    if not analysis.feedback_spans or rewrite is None:
        return None
    return rewrite.rewritten or None


def decide_incoming(msg: ChatMessage, analysis: Analysis, rewrite: Rewrite | None = None) -> Decision:
    """흐름 A · 다른 유저 채팅 (SPEC 5-1).

    L0 → 그대로 / L1 → 비속어만 가림 / L2 + 피드백 → 피드백 문장만(신고) / L2 → 숨김(신고)
    L3 → 숨김, 피드백이 있으면 피드백만 (신고 + 고소 후보). 순화 실패(None)면 숨김.
    내가 게임에 직접 친 채팅(is_me)은 그대로 표시한다.
    """

    def out(action: Action, text: str | None, reason: str, report: bool = False, complaint: bool = False) -> Decision:
        return Decision(
            msg_id=msg.id,
            is_me=msg.is_me,
            action=action,
            display_text=text,
            target=analysis.target,
            report=report,
            complaint_candidate=complaint,
            reason=reason,
        )

    if msg.is_me:
        return out(Action.SHOW, msg.text, "내 채팅 → 그대로 표시")
    level = analysis.level
    if level == Level.L0_CLEAN:
        return out(Action.SHOW, msg.text, "L0")
    if level == Level.L1_MILD:
        return out(Action.SHOW_MASKED, mask_profanity(msg.text, analysis.profanity_spans), "L1 → 비속어만 가림")
    rewritten = _rewritten(analysis, rewrite)
    if level == Level.L2_ABUSIVE:
        if rewritten:
            return out(Action.SHOW_REWRITTEN, rewritten, "L2 + 피드백 → 피드백만 표시, 원문 신고", report=True)
        return out(Action.HIDE, None, "L2 → 숨김 + 신고", report=True)
    if rewritten:
        return out(Action.SHOW_REWRITTEN, rewritten, "L3 + 피드백 → 피드백만 표시, 신고 + 고소 후보", True, True)
    return out(Action.HIDE, None, "L3 → 숨김 + 신고 + 고소 후보", report=True, complaint=True)


def decide_outgoing(msg: ChatMessage, analysis: Analysis, rewrite: Rewrite | None = None) -> Decision:
    """흐름 B · 내 채팅 (SPEC 5-2). 신고·고소 표시는 하지 않는다.

    L0 → 그대로 복사 / L1 → 비속어만 가려 복사 / L2 + 피드백 → 피드백 문장 복사 / 그 외(L2, L3, 순화 실패) → 차단
    """

    def out(action: Action, text: str | None, reason: str) -> Decision:
        return Decision(
            msg_id=msg.id, is_me=True, action=action, display_text=text, target=analysis.target, reason=reason
        )

    level = analysis.level
    if level == Level.L0_CLEAN:
        return out(Action.COPY, msg.text, "내 채팅 L0 → 그대로 전송")
    if level == Level.L1_MILD:
        return out(Action.COPY_MASKED, mask_profanity(msg.text, analysis.profanity_spans), "내 채팅 L1 → 비속어만 가림")
    rewritten = _rewritten(analysis, rewrite)
    if level == Level.L2_ABUSIVE and rewritten:
        return out(Action.COPY_REWRITTEN, rewritten, "내 채팅 L2 + 피드백 → 피드백만 전송")
    return out(Action.BLOCK, None, f"내 채팅 L{int(level)} → 전송 차단")
