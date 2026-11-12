"""[구현 · normalize 담당] NormalizeStage 실제 구현

해야 할 일 (docs/MODULES.md#normalize):
  1. 한글 사이 숫자·특수문자 제거 (시1발 → 시발)
  2. 자모 사이 공백 제거 (ㅅ ㅂ → ㅅㅂ), 반복 축약 (ㅋㅋㅋㅋ → ㅋㅋ)
  3. 영타 → 한글 (tlqkf → 시발), 우회어 사전 치환 (data/lexicon/bypass.csv)
  4. OCR 오인식 보정표 적용
  5. 어떤 보정을 했는지 hints 에 기록
  ※ 학습 데이터에도 같은 함수를 적용해야 함 (training/)
"""

from clean_chat.core.schemas import ChatMessage, NormalizedMessage
from clean_chat.normalize.stage import NormalizeStage


class Normalizer(NormalizeStage):
    def setup(self) -> None:
        pass  # 무거운 준비(모델·사전 로딩)는 여기서 1번만

    def run(self, item: ChatMessage) -> NormalizedMessage:
        raise NotImplementedError("normalize 담당: 구현 필요")
