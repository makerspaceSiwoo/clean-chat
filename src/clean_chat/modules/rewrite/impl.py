"""④ rewrite — 피드백 조각을 공손한 문장 1개로  (명세: docs/MODULES.md#rewrite, 예시: fixtures/rewrite/)

구성은 L2 이상이고 analysis.feedback_spans 가 있을 때만 부른다. LLM 백엔드는 settings.llm_backend(OPEN-04).
API 키는 .env 에서 읽는다(git 금지).
"""

from __future__ import annotations

from clean_chat.core.schemas import Rewrite, RewriteRequest


def run(req: RewriteRequest) -> Rewrite:
    """악성 문장의 피드백 조각만 롤 용어를 살린 공손한 문장 1개로 다듬는다.

    입력: RewriteRequest(message, analysis) → 출력: Rewrite(msg_id, rewritten, backend)
    예) "야 정글 ㅂㅅ아 용 먼저 치라고", feedback_spans=["용 먼저 치라고"] → rewritten="용 먼저 치자"
    예) "아 정글 ㅂㅅ 왜 안 와", feedback_spans=["왜 안 와"] → rewritten="정글 합류 부탁해요"
    순서: _build_prompt → _complete → _clean_output → _still_abusive 검사
    주의: 3초 제한. 실패·지연·결과에 욕설이 남으면 rewritten=None (구성이 숨김/차단). 원문에 없는 내용을 지어내지 않는다.
    관련: ADR-0005, OPEN-04, SPEC 8장(리라이트 3초)
    """
    raise NotImplementedError("rewrite 담당: run")


def _build_prompt(spans: list[str], original: str) -> str:
    """LLM 에 줄 지시문. 롤 용어 유지, 한 문장, 존댓말 또는 청유형, 욕설·비난 금지."""
    raise NotImplementedError


def _complete(prompt: str, timeout_sec: float) -> str | None:
    """백엔드("rule" | "local" | "api")로 문장 생성. 시간 초과·오류면 None."""
    raise NotImplementedError


def _clean_output(generated: str) -> str:
    """LLM 출력 정리 (따옴표·설명 문장 제거, 한 줄로)."""
    raise NotImplementedError


def _still_abusive(text: str) -> bool:
    """다듬은 문장에 비속어가 남았는지 (사전 검사). 남았으면 rewritten=None 으로."""
    raise NotImplementedError
