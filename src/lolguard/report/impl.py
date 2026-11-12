"""[구현 · report 담당] 신고 문구 / 고소장 (AI 지점 A4)

ReportWriter 해야 할 일:
  1. speaker 의 report=True 인 Incident 만 모아 시간순 정리
  2. 닉네임, 시각, 원문(msg.raw), 유형을 담은 복사용 텍스트
ComplaintWriter 해야 할 일:
  1. complaint_candidate=True 인 Incident 만 사용
  2. 고정 양식(templates/complaint.md)에 사실 채우기, '사건 경위'만 LLM 요약 (실패 시 규칙 문장)
  3. 한글 폰트 포함 PDF → output_dir 에 저장, pdf_path 기록
  4. "법률 자문 아님" 고지 문구 필수
"""

from lolguard.core.schemas import ComplaintDraft, ComplaintRequest, ReportDraft, ReportRequest
from lolguard.report.stage import ComplaintStage, ReportStage


class ReportWriter(ReportStage):
    def run(self, item: ReportRequest) -> ReportDraft:
        raise NotImplementedError("report 담당: 신고 문구 구현")


class ComplaintWriter(ComplaintStage):
    def run(self, item: ComplaintRequest) -> ComplaintDraft:
        raise NotImplementedError("report 담당: 고소장 구현")
