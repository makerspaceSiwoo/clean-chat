"""③ analyze — 누가 누구에게 얼마나 나쁜 말을 했나 + 피드백 조각  (명세: docs/MODULES.md#analyze, 예시: fixtures/analyze/)

**판단만** 한다. 숨김·신고·차단 같은 처리는 구성(core/policy.py)이 Analysis 를 보고 정한다.
모든 채팅에 실행되므로 빠른 소형 모델(KcBERT/KcELECTRA 계열) 또는 사전 규칙을 쓴다(ADR-0005).
모델 로딩처럼 무거운 준비는 functools.cache 로 한 번만, 무거운 import(torch 등)는 함수 안에서 한다.
"""

from __future__ import annotations

from clean_chat.core.schemas import Analysis, AnalyzeRequest, ChatMessage, HarmType, Level, Player


def run(req: AnalyzeRequest) -> Analysis:
    """메시지 1개(+ 앞 대화, 명단) → 대상(target), 등급 L0~L3, 유해 유형, 비속어 조각, 피드백 조각.

    입력: AnalyzeRequest(message, history, players) → 출력: Analysis
    예) 원딜러: "야 정글 ㅂㅅ아 용 먼저 치라고" (text_norm "야 정글 병신아 용 먼저 치라고")
        → target="정글", level=2, harm_types=[profanity, blame], profanity_spans=["ㅂㅅ"], feedback_spans=["용 먼저 치라고"]
    예) 미드킹: "아 ㅅㅂ 내가 실수함" → target=None, level=1 (대상 없는 혼잣말), profanity_spans=["ㅅㅂ"]
    예) 상대탑: "탑 니애미 tlqkf" → target="탑", level=3, harm_types=[profanity, family_insult]
    예) 탑솔장인: "다들 화이팅" → level=0, 나머지 빈 값
    순서: _predict_harm → _guess_target → _decide_level → _find_profanity → _extract_feedback
    주의: 내 채팅과 다른 유저 채팅에 같은 기준. CPU 1문장 0.2초 이내. model_version 기록.
          profanity_spans·feedback_spans 는 message.text(원문)에 있는 그대로의 조각이어야 한다.
    관련: SPEC 4장, ADR-0005, docs/LABELING_GUIDE.md
    """
    raise NotImplementedError("analyze 담당: run")


def _predict_harm(text_norm: str) -> dict[str, float]:
    """유해 유형별 점수 0~1. 예) {"profanity": 0.9, "blame": 0.9}"""
    raise NotImplementedError


def _guess_target(message: ChatMessage, history: list[ChatMessage], players: list[Player]) -> str | None:
    """공격 대상 추정: 포지션 단어(탑/정글/미드/원딜/서폿) → 명단의 닉네임·챔피언 → 직전 대화 상대. 모르면 None."""
    raise NotImplementedError


def _decide_level(scores: dict[str, float], target: str | None) -> tuple[Level, list[HarmType]]:
    """점수 + 대상 여부 → 등급과 유형 목록. 기준은 SPEC 4-2 (대상 없는 비속어 = L1, 특정인 비난 = L2, 패드립·성희롱 = L3)."""
    raise NotImplementedError


def _find_profanity(message: ChatMessage) -> list[str]:
    """원문(text)에서 가릴 비속어 조각. 예) "아 ㅅㅂ 내가 실수함" → ["ㅅㅂ"]. hints 로 원문 위치를 찾는다."""
    raise NotImplementedError


def _extract_feedback(message: ChatMessage, level: Level) -> list[str]:
    """L2 이상일 때 게임 지시·지적 부분(용, 합류, 와드 등)만. 예) "야 정글 ㅂㅅ아 용 먼저 치라고" → ["용 먼저 치라고"]"""
    raise NotImplementedError
