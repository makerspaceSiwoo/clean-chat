"""[구현 · policy 담당] PolicyStage 실제 구현

해야 할 일 (docs/SPEC.md 5장 정책표를 그대로):
  1. is_me 여부에 따라 타 유저 표 / 내 채팅 표 적용
  2. target 추정: 포지션 → players 명단(닉네임·챔피언) → 직전 대화 상대
  3. report / complaint_candidate / reason 채우기
  4. 같은 화자 누적 횟수 반영 (상태 유지)
"""

from clean_chat.core.schemas import Decision, PolicyRequest
from clean_chat.policy.stage import PolicyStage


class PolicyEngine(PolicyStage):
    def setup(self) -> None:
        pass  # 무거운 준비(모델·사전 로딩)는 여기서 1번만

    def run(self, item: PolicyRequest) -> Decision:
        raise NotImplementedError("policy 담당: 구현 필요")
