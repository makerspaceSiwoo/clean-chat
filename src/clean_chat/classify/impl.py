"""[구현 · WP4] ClassifyStage: NormalizedMessage → Classification  (명세: docs/MODULES.md#classify, AI 지점 A2)

모든 채팅에 실행되므로 빠른 소형 모델(KcBERT/KcELECTRA 계열)을 쓴다(ADR-0005).
**분류만** 한다. 숨김·신고·차단 같은 처리 결정은 policy 몫이다.
"""

from __future__ import annotations

from clean_chat.classify.stage import ClassifyStage
from clean_chat.core.schemas import Classification, HarmType, Level, NormalizedMessage


class Classifier(ClassifyStage):
    """[구현 · WP4] NormalizedMessage → Classification"""

    def setup(self) -> None:
        """분류 모델(models/classifier) 로딩. 모델 파일이 없으면 사전 규칙만으로 동작하도록 준비.

        순서: _load_model → (없으면) _load_rules
        주의: 무거운 import(torch, transformers)는 이 함수 안에서. 관련: ADR-0005, docs/DATA.md
        """
        raise NotImplementedError("classify 담당: setup")

    def run(self, item: NormalizedMessage) -> Classification:
        """정리된 문장(text_norm) → 유해 유형(여러 개), 등급 L0~L3, 피드백 포함 여부.

        입력: NormalizedMessage → 출력: Classification(msg_id, level, harm_types, has_feedback, scores, model_version)
        예) "야 정글 병신아 용 먼저 치라고" → level=2, harm_types=[profanity, blame], has_feedback=True
        예) "아 시발 내가 실수함" → level=1 (대상 없는 혼잣말), harm_types=[profanity], has_feedback=False
        예) "탑 니애미 시발" → level=3, harm_types=[profanity, family_insult]
        순서: _predict_harm → _decide_level → _detect_feedback
        주의: 내 채팅과 다른 유저 채팅에 같은 기준. CPU 1문장 0.2초 이내. model_version 기록.
        관련: SPEC 4장, ADR-0005, docs/LABELING_GUIDE.md
        """
        raise NotImplementedError("classify 담당: run")

    def _load_model(self) -> object | None:
        """models/classifier 에서 모델·토크나이저 로딩. 없으면 None."""
        raise NotImplementedError

    def _load_rules(self) -> object:
        """모델이 없을 때 쓸 사전 규칙(data/lexicon)."""
        raise NotImplementedError

    def _predict_harm(self, text: str) -> dict[str, float]:
        """유해 유형별 점수 0~1. 예) {"profanity": 0.9, "blame": 0.9}"""
        raise NotImplementedError

    def _decide_level(self, text: str, scores: dict[str, float]) -> tuple[Level, list[HarmType]]:
        """점수 + 대상 여부(특정인을 향함?) → 등급과 유형 목록. 기준은 SPEC 4-2."""
        raise NotImplementedError

    def _detect_feedback(self, text: str, level: Level) -> bool:
        """L2 이상이면서 게임 플레이 지적·방향 제시(용, 합류, 와드 등)가 섞여 있는지."""
        raise NotImplementedError
