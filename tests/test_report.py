"""⑤ report 모듈의 신고 문구, 고소장 PDF, 키 없는 LiteLLM 연결 검증."""

from pathlib import Path

import pytest

from clean_chat.core.schemas import ReportKind, ReportRequest
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
