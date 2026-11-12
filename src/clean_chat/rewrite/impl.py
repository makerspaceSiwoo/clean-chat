"""[구현 · rewrite 담당] RewriteStage 실제 구현

해야 할 일 (docs/MODULES.md#rewrite, AI 지점 A3):
  1. 피드백 추출: 원문에서 게임 플레이 지적·방향만 feedback_spans 로
  2. 다듬기: 자연스러운 롤 용어 문장 1개 → rewritten
  3. LLM 백엔드(settings.llm_backend)는 내부 클래스로 분리, 3초 제한
  4. 실패·지연·결과에 욕설 잔존 → rewritten=None (policy가 숨김 처리)
"""

from clean_chat.core.schemas import Rewrite, RewriteRequest
from clean_chat.rewrite.stage import RewriteStage


class Rewriter(RewriteStage):
    def setup(self) -> None:
        pass  # 무거운 준비(모델·사전 로딩)는 여기서 1번만

    def run(self, item: RewriteRequest) -> Rewrite:
        raise NotImplementedError("rewrite 담당: 구현 필요")
