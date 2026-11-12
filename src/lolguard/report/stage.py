"""[인터페이스 · 리드 소유] ReportStage, ComplaintStage"""

from lolguard.core.schemas import ComplaintDraft, ComplaintRequest, ReportDraft, ReportRequest
from lolguard.core.stage import Stage


class ReportStage(Stage[ReportRequest, ReportDraft]):
    """처리 내역 → 복사용 신고 문구 (ADR-0007: 자동 신고 금지)"""

    name = "report"
    input_model = ReportRequest
    output_model = ReportDraft

    @classmethod
    def mock_default(cls, item: ReportRequest) -> ReportDraft:
        return ReportDraft(speaker=item.speaker, text="(mock 신고 문구)", incident_ids=[])


class ComplaintStage(Stage[ComplaintRequest, ComplaintDraft]):
    """처리 내역 → 고소장 초안 + PDF (ADR-0008: 고정 양식)"""

    name = "complaint"
    input_model = ComplaintRequest
    output_model = ComplaintDraft

    @classmethod
    def mock_default(cls, item: ComplaintRequest) -> ComplaintDraft:
        return ComplaintDraft(speaker=item.speaker, summary="(mock 사건 경위)", incident_ids=[])
