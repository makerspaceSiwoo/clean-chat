"""[구현 · WP3] Parser (parse, 흐름 A): OCR 줄 RawLine → ParseResult  (명세: docs/MODULES.md#parse)

결과가 정해진 규칙 모듈이라 fixtures 와 정확히 같아야 한다(STRICT).
"""

from __future__ import annotations

from clean_chat.core.schemas import Channel, ParseResult, RawLine
from clean_chat.text.stage import ParseStage


class Parser(ParseStage):
    """[구현 · WP3] RawLine → ParseResult  (명세: docs/MODULES.md#parse)"""

    def setup(self) -> None:
        """채널 표기([팀]/[전체])·핑·시스템 문구 목록 로딩. 앱 시작 시 1번. 관련: OPEN-09"""
        raise NotImplementedError("text 담당(parse): setup")

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
        raise NotImplementedError("text 담당(parse): run")

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
