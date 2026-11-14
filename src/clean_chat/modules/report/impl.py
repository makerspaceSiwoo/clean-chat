"""⑤ report — 신고 문구 / 고소장 초안  (명세: docs/MODULES.md#report, 예시: fixtures/report/)

게임이 끝난 뒤(POST_GAME)에만 구성이 부른다. 입력은 이번 게임 기록 전체(GameSession)다.
- kind=report:    복사해 붙여넣을 신고 문구 (자동 신고 금지, ADR-0007)
- kind=complaint: 고소장 초안 + 한글 PDF (ADR-0008)
"""

from __future__ import annotations

from clean_chat.core.schemas import GameSession, Incident, ReportDraft, ReportRequest


def run(req: ReportRequest) -> ReportDraft:
    """대상 화자의 기록을 모아 신고 문구 또는 고소장 초안을 만든다.

    입력: ReportRequest(kind, session, speaker, complainant?, output_dir?) → 출력: ReportDraft
    예) kind=report, speaker="원딜러" →
        text="신고 대상: 원딜러\\n사유: 언어 폭력 2건\\n[2025-11-12 13:00:03] 야 정글 ㅂㅅ아 용 먼저 치라고 (욕설, 비난)\\n...",
        incident_ids=["L3", "L4"]
    예) kind=complaint, speaker="상대탑" →
        text="피고소인은 게임 중 전체 채팅으로 고소인의 가족을 모욕하는 채팅을 1회 하였다.",
        incident_ids=["L5"], pdf_path=".clean-chat/complaints/complaint_상대탑.pdf"
    순서: report    → _pick_incidents(decision.report) → _format_line → 머리말(대상, 건수)
          complaint → _pick_incidents(decision.complaint_candidate) → _summarize → _fill_template → _render_pdf
    주의: 원문은 msg.text 를 그대로 인용(고치지 않음). 시각은 한국 시간. 자동으로 보내지 않는다.
          고소장에는 "법률 자문이 아님" 고지 필수. '사건 경위'만 LLM, 실패하면 규칙 문장. PDF 는 git 에 올리지 않는다.
    관련: ADR-0007, ADR-0008, OPEN-04
    """
    raise NotImplementedError("report 담당: run")


def _pick_incidents(session: GameSession, speaker: str, complaint: bool) -> list[Incident]:
    """세션에서 speaker 의 decision.report(또는 complaint_candidate)=True 기록만, 시간순."""
    raise NotImplementedError


def _format_line(incident: Incident) -> str:
    """기록 1건 → "[2025-11-12 13:00:03] 원문 (욕설, 비난)". 유형은 한국어 이름으로."""
    raise NotImplementedError


def _summarize(incidents: list[Incident]) -> str:
    """사건 경위 한 문단 (LLM, 실패 시 규칙 문장). 사실만, 추측·과장 금지."""
    raise NotImplementedError


def _fill_template(req: ReportRequest, incidents: list[Incident], summary: str) -> str:
    """고정 양식에 고소인·피고소인·일시·증거 목록·사건 경위·고지 문구를 채운다."""
    raise NotImplementedError


def _render_pdf(document: str, output_dir: str, speaker: str) -> str:
    """채운 문서 → 한글 폰트 PDF 파일. 저장한 경로를 돌려준다. (reportlab, uv sync --extra report)

    주의: output_dir 은 core.config.resolve_repo_path 로 풀어서 저장. 돌려주는 경로는 입력과 같은 형식(상대면 상대).
    """
    raise NotImplementedError
