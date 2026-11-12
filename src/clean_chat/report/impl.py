"""[구현 · WP6] 신고 문구 / 고소장 초안 (명세: docs/MODULES.md#report, AI 지점 A4)

입력은 GameSession(이번 게임 기록 전체)이고, 게임이 끝난 뒤(POST_GAME)에만 호출된다.
- ReportWriter    (report):    세션 + 대상 → 복사용 신고 문구 (자동 신고 금지, ADR-0007)
- ComplaintWriter (complaint): 세션 + 대상 + 고소인 → 고소장 초안 + 한글 PDF (ADR-0008)
"""

from __future__ import annotations

from clean_chat.core.schemas import ComplaintDraft, ComplaintRequest, GameSession, Incident, ReportDraft, ReportRequest
from clean_chat.report.stage import ComplaintStage, ReportStage


class ReportWriter(ReportStage):
    """[구현 · WP6] ReportRequest → ReportDraft"""

    def run(self, item: ReportRequest) -> ReportDraft:
        """대상 화자의 신고 대상 기록을 모아 그대로 붙여넣을 신고 문구를 만든다.

        입력: ReportRequest(session, speaker) → 출력: ReportDraft(speaker, text, incident_ids)
        예) speaker="원딜러" →
            "신고 대상: 원딜러\\n사유: 언어 폭력 2건\\n[2025-11-12 13:00:03] 야 정글 ㅂㅅ아 용 먼저 치라고 (욕설, 비난)\\n..."
            incident_ids=["L3", "L4"]
        순서: _pick_incidents(report=True) → _format_line(각 기록) → 머리말(대상, 건수)
        주의: 원문은 msg.text 를 그대로 인용(고치지 않음). 시각은 한국 시간. 자동으로 보내지 않는다.
        관련: ADR-0007
        """
        raise NotImplementedError("report 담당: report run")

    def _pick_incidents(self, session: GameSession, speaker: str) -> list[Incident]:
        """세션에서 speaker 의 decision.report=True 기록만, 시간순."""
        raise NotImplementedError

    def _format_line(self, incident: Incident) -> str:
        """기록 1건 → "[2025-11-12 13:00:03] 원문 (욕설, 비난)". 유형은 한국어 이름으로."""
        raise NotImplementedError


class ComplaintWriter(ComplaintStage):
    """[구현 · WP6] ComplaintRequest → ComplaintDraft (+ PDF 파일)"""

    def setup(self) -> None:
        """고소장 양식(templates/)과 한글 폰트(fonts/, 라이선스 확인) 로딩, 요약용 LLM 백엔드 준비."""
        raise NotImplementedError("report 담당: complaint setup")

    def run(self, item: ComplaintRequest) -> ComplaintDraft:
        """고소 후보 기록으로 고정 양식의 고소장 초안을 채우고 한글 PDF 로 저장한다.

        입력: ComplaintRequest(session, speaker, complainant, output_dir) → 출력: ComplaintDraft
        예) speaker="상대탑" → summary="피고소인은 게임 중 전체 채팅으로 고소인의 가족을 모욕하는 채팅을 1회 하였다.",
            incident_ids=["L5"], pdf_path=".clean-chat/complaints/complaint_상대탑.pdf"
        순서: _pick_incidents(complaint_candidate=True) → _summarize → _fill_template → _render_pdf
        주의: "법률 자문이 아님" 고지 필수. 원문(raw)과 시각은 그대로 인용. '사건 경위'만 LLM, 실패하면 규칙 문장.
              PDF 는 git 에 올리지 않는다(.gitignore).
        관련: ADR-0008, OPEN-04
        """
        raise NotImplementedError("report 담당: complaint run")

    def _pick_incidents(self, session: GameSession, speaker: str) -> list[Incident]:
        """세션에서 speaker 의 decision.complaint_candidate=True 기록만, 시간순."""
        raise NotImplementedError

    def _summarize(self, incidents: list[Incident]) -> str:
        """사건 경위 한 문단 (LLM, 실패 시 규칙 문장). 사실만, 추측·과장 금지."""
        raise NotImplementedError

    def _fill_template(self, item: ComplaintRequest, incidents: list[Incident], summary: str) -> str:
        """고정 양식(templates/complaint.md)에 고소인·피고소인·일시·증거 목록·사건 경위·고지 문구를 채운다."""
        raise NotImplementedError

    def _render_pdf(self, document: str, output_dir: str, speaker: str) -> str:
        """채운 문서 → 한글 폰트 PDF 파일. 저장한 경로를 돌려준다. (reportlab, uv sync --extra report)"""
        raise NotImplementedError
