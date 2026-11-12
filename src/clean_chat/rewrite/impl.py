"""[구현 · WP5] RewriteStage: RewriteRequest → Rewrite  (명세: docs/MODULES.md#rewrite, AI 지점 A3)

L2 이상 & 피드백이 있을 때만 파이프라인이 부른다. LLM 백엔드는 Strategy 로 바꿔 끼운다(OPEN-04).
"""

from __future__ import annotations

from typing import Protocol

from clean_chat.core.schemas import Rewrite, RewriteRequest
from clean_chat.rewrite.stage import RewriteStage


class LlmBackend(Protocol):
    """문장 다듬기 엔진 1개 ("rule" | "local" | "api", settings.llm_backend)."""

    name: str

    def complete(self, prompt: str, timeout_sec: float) -> str | None:
        """프롬프트 → 생성 문장. 시간 초과·오류면 None."""
        ...


class Rewriter(RewriteStage):
    """[구현 · WP5] RewriteRequest → Rewrite"""

    def setup(self) -> None:
        """LLM 백엔드 준비(settings.llm_backend). API 키는 .env 에서 읽는다(git 금지).

        순서: _create_backend
        관련: OPEN-04, .env.example
        """
        raise NotImplementedError("rewrite 담당: setup")

    def run(self, item: RewriteRequest) -> Rewrite:
        """악성 문장에서 게임 피드백만 뽑아 공손한 롤 용어 문장 1개로 다듬는다.

        입력: RewriteRequest(message, classification) → 출력: Rewrite(feedback_spans, rewritten, backend)
        예) "야 정글 ㅂㅅ아 용 먼저 치라고" → feedback_spans=["용 먼저 치라고"], rewritten="용 먼저 치자"
        예) "아 정글 ㅂㅅ 왜 안 와" → feedback_spans=["왜 안 와"], rewritten="정글 합류 부탁해요"
        순서: _extract_feedback → _build_prompt → backend.complete → _clean_output → _still_abusive 검사
        주의: 3초 제한. 실패·지연·결과에 욕설이 남으면 rewritten=None (policy 가 숨김/차단).
              원문에 없는 내용을 지어내지 않는다.
        관련: ADR-0005, OPEN-04, SPEC 8장(리라이트 3초)
        """
        raise NotImplementedError("rewrite 담당: run")

    def _create_backend(self, name: str) -> LlmBackend:
        """백엔드 이름 → LlmBackend. 무거운 import 와 API 클라이언트 생성은 여기서."""
        raise NotImplementedError

    def _extract_feedback(self, text: str) -> list[str]:
        """원문에서 게임 지시·지적 부분만. 예) "야 정글 ㅂㅅ아 용 먼저 치라고" → ["용 먼저 치라고"]"""
        raise NotImplementedError

    def _build_prompt(self, spans: list[str], original: str) -> str:
        """LLM 에 줄 지시문. 롤 용어 유지, 한 문장, 존댓말 또는 청유형, 욕설·비난 금지."""
        raise NotImplementedError

    def _clean_output(self, generated: str) -> str:
        """LLM 출력 정리 (따옴표·설명 문장 제거, 한 줄로)."""
        raise NotImplementedError

    def _still_abusive(self, text: str) -> bool:
        """다듬은 문장에 비속어가 남았는지 (사전 검사). 남았으면 rewritten=None 으로."""
        raise NotImplementedError
