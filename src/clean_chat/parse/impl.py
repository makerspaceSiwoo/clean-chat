"""[구현 · parse 담당] ParseStage 실제 구현

해야 할 일 (docs/MODULES.md#parse):
  1. "[팀] 닉네임 (챔피언): 본문" 형식에서 channel / speaker / champion / text 분리
  2. 핑·스펠체크 문구 → channel=ping, 시스템 메시지 → channel=system
  3. source == self_input 이면 speaker=settings.my_name, is_me=True
  4. 화자가 settings.my_name 이면 is_me=True
  5. 채팅이 아닌 잡음 줄 → message=None
  6. OCR 오인식(콜론·괄호 깨짐)에 강하게
"""

from clean_chat.core.schemas import ChatMessage, OutgoingText, ParseResult, RawLine
from clean_chat.parse.stage import ComposeStage, ParseStage


class Parser(ParseStage):
    def setup(self) -> None:
        pass  # 무거운 준비(모델·사전 로딩)는 여기서 1번만

    def run(self, item: RawLine) -> ParseResult:
        raise NotImplementedError("parse 담당: 구현 필요")


class Composer(ComposeStage):
    def run(self, item: OutgoingText) -> ChatMessage:
        raise NotImplementedError("parse 담당: compose 구현")
