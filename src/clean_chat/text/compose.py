"""[구현 · WP3] Composer (compose, 흐름 B): 내 입력 OutgoingText → ChatMessage  (명세: docs/MODULES.md#compose)

결과가 정해진 규칙 모듈이라 fixtures 와 정확히 같아야 한다(STRICT).
"""

from __future__ import annotations

from clean_chat.core.schemas import Channel, ChatMessage, OutgoingText
from clean_chat.text.stage import ComposeStage


class Composer(ComposeStage):
    """[구현 · WP3] OutgoingText → ChatMessage  (명세: docs/MODULES.md#compose)"""

    def run(self, item: OutgoingText) -> ChatMessage:
        """오버레이 입력칸에 내가 쓴 문장 → ChatMessage. OCR·parse 를 거치지 않는다(흐름 B).

        입력: OutgoingText(id, ts, text) → 출력: ChatMessage
        예) {"id": "L7", "text": "아 정글 ㅂㅅ 왜 안 와"}
            → source=self_input, channel=team, speaker="나"(settings.my_name), champion=None, is_me=True,
              text="아 정글 ㅂㅅ 왜 안 와", raw="아 정글 ㅂㅅ 왜 안 와"
        순서: _channel_for → ChatMessage
        주의: 사용자가 "/all " 처럼 채널 명령을 붙여 쓰면 어떻게 할지 정한다(본문에서 떼고 channel=all).
        관련: ADR-0006, HANDOFF 5-1
        """
        raise NotImplementedError("text 담당(compose): run")

    def _channel_for(self, text: str) -> tuple[Channel, str]:
        """입력 앞의 채널 명령을 해석해 (채널, 본문). 명령이 없으면 (team, 그대로)."""
        raise NotImplementedError
