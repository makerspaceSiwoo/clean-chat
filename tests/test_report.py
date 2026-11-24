"""⑤ report 모듈의 신고 문구, 고소장 PDF, 키 없는 LiteLLM 연결 검증."""

from pathlib import Path

import pytest

from clean_chat.core.schemas import HarmType, ReportKind, ReportRequest
from clean_chat.modules.report import impl
from clean_chat.modules.report.impl import run
from helpers import fixture_pairs


@pytest.mark.parametrize(("req", "expected"), fixture_pairs("report")[:2])
def test_report_fixtures(req, expected):
    req.session.incidents.reverse()
    assert run(req) == expected


@pytest.fixture
def complaint(tmp_path, monkeypatch) -> ReportRequest:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    req, _ = next(pair for pair in fixture_pairs("report") if pair[0].kind == ReportKind.COMPLAINT)
    return req.model_copy(update={"output_dir": str(tmp_path), "complainant": "테스트 고소인"})


def test_complaint_without_credentials(complaint, tmp_path):
    pytest.importorskip("reportlab")
    draft = run(complaint)

    assert draft.incident_ids == ["L5"]
    assert "전체 채팅" in draft.text
    assert "1건" in draft.text
    assert draft.pdf_path is not None
    path = Path(draft.pdf_path)
    assert path.parent == tmp_path
    assert path.read_bytes().startswith(b"%PDF-")


def test_threat_in_report_and_complaint(complaint, monkeypatch):
    incident = next(incident for incident in complaint.session.incidents if incident.msg.id == "L5")
    incident.analysis.harm_types = [HarmType.THREAT, HarmType.FAMILY_INSULT]
    report = run(complaint.model_copy(update={"kind": ReportKind.REPORT}))
    assert "(협박, 패드립)" in report.text

    documents = []

    def capture_document(document, output_dir, speaker):
        documents.append(document)
        return "complaint.pdf"

    monkeypatch.setattr(impl, "_render_pdf", capture_document)
    draft = run(complaint)
    assert draft.incident_ids == ["L5"]
    assert "가족을 언급한 비하 표현, 게임 밖에서 해악을 가하겠다고 고지하는 표현" in draft.text
    (document,) = documents
    sections = dict(document)
    assert sections["협박 관련 기록 (1건)"] == "증거 ID: L5"
    assert "형법 제283조 제1항(협박)" in sections["고소이유"]
    assert "일반적으로 공포심을 일으키기에 충분하였는지" in sections["고소이유"]
    assert "상대방에게 도달하여 상대방이 그 의미를 인식하였는지" in sections["고소이유"]
    assert incident.msg.text in sections["증거자료"]


def test_complaint_litellm_and_fallback(complaint, monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    litellm = pytest.importorskip("litellm")
    completion = litellm.completion
    fallback = run(complaint).text
    monkeypatch.setenv("LLM_MODEL", "gemini/test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    calls = []
    summary = "전체 채팅에서 가족을 언급한 비하 표현과 비속어를 사용한 표현이 포함된 메시지 1건이 확인됩니다."

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return completion(**kwargs, mock_response=summary)

    monkeypatch.setattr(litellm, "completion", fake_completion)
    assert run(complaint).text == summary
    (call,) = calls
    assert call["model"] == "gemini/test-model"
    assert call["api_key"] == "test-key"
    assert call["messages"][-1]["content"] == (
        "전체 채팅에서 가족을 언급한 비하 표현, 비속어를 사용한 표현에 해당하는 것으로 분류된 메시지 1건"
    )

    def failed_completion(**_kwargs):
        raise TimeoutError

    monkeypatch.setattr(litellm, "completion", failed_completion)
    assert run(complaint).text == fallback


def test_complaint_without_evidence(complaint, tmp_path):
    draft = run(complaint.model_copy(update={"speaker": "기록 없는 화자"}))
    assert draft.incident_ids == []
    assert draft.pdf_path is None
    assert not list(tmp_path.iterdir())
