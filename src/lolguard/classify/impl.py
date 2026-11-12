"""[구현 · classify 담당] ClassifyStage 실제 구현

해야 할 일 (docs/MODULES.md#classify, AI 지점 A2):
  1. setup(): 분류 모델 로딩 (models/ 폴더, 없으면 사전 규칙만으로 동작하도록)
  2. text_norm → harm_types(다중), level(L0~L3), has_feedback, scores
  3. 분류만 한다. 숨김/신고 판단은 policy 몫
  4. CPU 1문장 0.2초 이내, model_version 기록
"""

from lolguard.classify.stage import ClassifyStage
from lolguard.core.schemas import Classification, NormalizedMessage


class Classifier(ClassifyStage):
    def setup(self) -> None:
        pass  # 무거운 준비(모델·사전 로딩)는 여기서 1번만

    def run(self, item: NormalizedMessage) -> Classification:
        raise NotImplementedError("classify 담당: 구현 필요")
