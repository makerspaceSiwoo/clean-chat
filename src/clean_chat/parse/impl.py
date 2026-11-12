"""[구현 · WP3] 채팅 메시지 만들기 (명세: docs/MODULES.md#parse)

- Parser   (parse,   흐름 A): OCR 줄 RawLine → ParseResult(ChatMessage 또는 잡음이면 None)
- Composer (compose, 흐름 B): 내 입력 OutgoingText → ChatMessage
둘 다 결과가 정해진 규칙 모듈이라 fixtures 와 정확히 같아야 한다(STRICT).
"""

from __future__ import annotations

from clean_chat.core.schemas import Channel, ChatMessage, OutgoingText, ParseResult, RawLine
from clean_chat.parse.stage import ComposeStage, ParseStage


class Parser(ParseStage):
    """[구현 · WP3] RawLine → ParseResult  (명세: docs/MODULES.md#parse)"""

    def setup(self) -> None:
        """채널 표기([팀]/[전체])·핑·시스템 문구 목록 로딩. 앱 시작 시 1번. 관련: OPEN-09"""
        raise NotImplementedError("parse 담당: setup")

    def run(self, item: RawLine) -> ParseResult:
        """한 줄을 채널/화자/챔피언/본문으로 분해한다.

        입력: RawLine → 출력: ParseResult(line_id, message)
        예) "[팀] 원딜러 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고"
            → channel=team, speaker="원딜러", champion="징크스", text="야 정글 ㅂㅅ아 용 먼저 치라고", is_me=False
        예) "[팀] 나 (쓰레쉬): 정글 합류 부탁해요" → 화자가 내 소환사명(settings.my_name)이므로 is_me=True
        예) "정글러 (리신)님이 점멸 쿨타임 신호를 보냈습니다" → channel=ping, speaker=None
        잡음 줄(채팅이 아닌 OCR 결과)이면 message=None.
        순서: _split_channel → _split_speaker → _classify_channel → _is_me → ChatMessage(raw=원본 줄 그대로)
        주의: raw 는 증거용이라 절대 고치지 않는다. OCR 오인식([ ↔ (, : ↔ ;)에 강하게.
        관련: ADR-0002, OPEN-09
        """
        raise NotImplementedError("parse 담당: run")

    def _split_channel(self, text: str) -> tuple[str | None, str]:
        """앞의 채널 표기와 나머지를 분리. 예) "[팀] 원딜러 (징크스): ..." → ("팀", "원딜러 (징크스): ...")"""
        raise NotImplementedError

    def _split_speaker(self, rest: str) -> tuple[str | None, str | None, str]:
        """닉네임·챔피언·본문 분리. 예) "원딜러 (징크스): 용 먼저" → ("원딜러", "징크스", "용 먼저"). 닉네임에 공백 가능."""
        raise NotImplementedError

    def _classify_channel(self, tag: str | None, body: str) -> Channel:
        """팀/전체/핑/시스템/모름 판별. 핑·스펠체크 문구 목록은 OPEN-09."""
        raise NotImplementedError

    def _is_me(self, speaker: str | None) -> bool:
        """화자가 내 소환사명(settings.my_name)인지. OCR 오인식을 고려해 비교 기준을 정한다."""
        raise NotImplementedError

    def _is_noise(self, text: str) -> bool:
        """채팅이 아닌 줄(빈 줄, 깨진 글자, UI 텍스트)인지."""
        raise NotImplementedError


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
        raise NotImplementedError("parse 담당: compose")

    def _channel_for(self, text: str) -> tuple[Channel, str]:
        """입력 앞의 채널 명령을 해석해 (채널, 본문). 명령이 없으면 (team, 그대로)."""
        raise NotImplementedError
