"""⑤ report 모듈의 신고 문구, 고소장 HTML, 키 없는 LiteLLM 연결 검증."""

from html import unescape

import pytest

from clean_chat.core.config import settings
from clean_chat.core.game import PostGameBatch
from clean_chat.core.modules import ModuleSet
from clean_chat.core.policy import decide_incoming
from clean_chat.core.schemas import HarmType, ReportKind, ReportRequest
from clean_chat.modules.report.impl import run
from helpers import fixture_pairs


@pytest.mark.parametrize(("req", "expected"), fixture_pairs("report"))
def test_report_fixtures(req, expected, monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    req = req.model_copy(deep=True)
    req.session.incidents.reverse()
    assert run(req) == expected


@pytest.fixture
def complaint(monkeypatch) -> ReportRequest:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    req, _ = next(pair for pair in fixture_pairs("report") if pair[0].kind == ReportKind.COMPLAINT)
    return req.model_copy(update={"output_dir": None, "complainant": "테스트 고소인"}, deep=True)


def test_complaint_returns_full_styled_html_without_writing_files(complaint, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    complaint.speaker = "달빛 <고양이>&"
    complaint.complainant = "신고인 <이름>&"
    incident = next(incident for incident in complaint.session.incidents if incident.msg.id == "L5")
    incident.msg.speaker = complaint.speaker
    incident.msg.text = "첫 줄 <script>alert(1)</script> &  원문\n둘째 줄"

    assert complaint.output_dir is None
    draft = run(complaint)
    html = draft.text
    assert draft.incident_ids == ["L5"]
    assert draft.pdf_path is None
    assert html.startswith('<article lang="ko"')
    for fragment in (
        "Gungsuh, AppleMyungjo",
        "font-size: 25pt",
        "font-size: 14pt",
        "font-size: 11pt",
        "font-weight: bold",
        "white-space: pre-wrap",
        "overflow-wrap: anywhere",
        ">고소장</h1>",
        ">초안</p>",
        ">고소인</h2>",
        ">피고소인</h2>",
        ">고소취지</h2>",
        ">범죄사실</h2>",
        ">고소이유</h2>",
        ">증거자료</h2>",
        ">작성 및 제출</h2>",
        "사건 경위:",
        "메시지 1건",
        "채팅 기록 1건\n1. [L5] 2025-11-12 13:00:05 (전체 채팅)",
        "고소인 서명:",
        "실제 제출 전 전문가 검토가 필요합니다.",
    ):
        assert fragment in html
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp;" in html
    for value in (complaint.speaker, complaint.complainant, incident.msg.text):
        assert value in unescape(html)

    legacy_destination = tmp_path / "complaints"
    assert run(complaint.model_copy(update={"output_dir": str(legacy_destination)})) == draft
    assert not list(tmp_path.iterdir())


def test_post_game_returns_both_drafts_for_complaint_speaker(complaint, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "complaint_output_dir", str(tmp_path / "complaints"))
    for incident in complaint.session.incidents:
        incident.decision = decide_incoming(incident.msg, incident.analysis, incident.rewrite)
    evidence = next(incident for incident in complaint.session.incidents if incident.msg.id == "L5")
    assert evidence.decision.report and evidence.decision.complaint_candidate

    result = PostGameBatch(ModuleSet()).run(complaint.session)
    reports = {draft.speaker: draft for draft in result.reports}
    complaints = {draft.speaker: draft for draft in result.complaints}
    assert set(reports) == {"불꽃남자", complaint.speaker}
    assert set(complaints) == {complaint.speaker}

    report = reports[complaint.speaker]
    assert report.kind == ReportKind.REPORT
    assert report.incident_ids == ["L5"]
    assert report.text.splitlines() == [
        f"신고 대상: {complaint.speaker} ({evidence.msg.champion})",  # 닉네임 + 챔피언이 한 사람
        "사유: 언어 폭력 1건",
        f"[2025-11-12 13:00:05] {evidence.msg.text} (욕설, 패드립)",
    ]
    assert report.champion == evidence.msg.champion

    draft = complaints[complaint.speaker]
    assert draft.kind == ReportKind.COMPLAINT
    assert draft.incident_ids == ["L5"]
    assert "<h1 " in draft.text and ">고소장</h1>" in draft.text
    assert "사건 경위:" in draft.text
    assert f"[L5] 2025-11-12 13:00:05 (전체 채팅) {evidence.msg.text}" in unescape(draft.text)
    assert "고소인 서명:" in draft.text
    assert report.pdf_path is None and draft.pdf_path is None
    assert not list(tmp_path.iterdir())


def test_threat_in_report_and_complaint(complaint):
    incident = next(incident for incident in complaint.session.incidents if incident.msg.id == "L5")
    incident.analysis.harm_types = [HarmType.THREAT, HarmType.FAMILY_INSULT]
    report = run(complaint.model_copy(update={"kind": ReportKind.REPORT}))
    assert "(협박, 패드립)" in report.text

    draft = run(complaint)
    assert draft.incident_ids == ["L5"]
    assert "가족을 언급한 비하 표현, 게임 밖에서 해악을 가하겠다고 고지하는 표현" in draft.text
    assert "협박 관련 기록 (1건)</h2>" in draft.text
    assert "증거 ID: L5" in draft.text
    assert "형법 제283조 제1항(협박)" in draft.text
    assert "일반적으로 공포심을 일으키기에 충분하였는지" in draft.text
    assert "상대방에게 도달하여 상대방이 그 의미를 인식하였는지" in draft.text
    assert incident.msg.text in unescape(draft.text)


def _gemini_reply(text):
    return {"choices": [{"finish_reason": "stop", "message": {"content": text, "refusal": None}}], "usage": {}}


def test_complaint_gemini_and_fallback(complaint, monkeypatch):
    from clean_chat.core import gemini

    fallback = run(complaint).text
    monkeypatch.setenv("LLM_MODEL", "gemini/test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    calls = []
    summary = "전체 채팅에서 가족을 언급한 비하 표현과 비속어를 사용한 표현이 포함된 메시지 1건이 확인됩니다."

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return _gemini_reply(summary)

    monkeypatch.setattr(gemini, "completion", fake_completion)
    assert f"사건 경위: {summary}" in run(complaint).text
    (call,) = calls
    assert call["model"] == "gemini/test-model"
    assert call["api_key"] == "test-key"
    assert call["messages"][-1]["content"] == (
        "전체 채팅에서 가족을 언급한 비하 표현, 비속어를 사용한 표현에 해당하는 것으로 분류된 메시지 1건"
    )

    summary = "전체 채팅에서 메시지 9건이 확인됩니다."
    assert run(complaint).text == fallback

    def failed_completion(**_kwargs):
        raise gemini.GeminiError(503, "Service Unavailable")

    monkeypatch.setattr(gemini, "completion", failed_completion)
    assert run(complaint).text == fallback


def test_complaint_without_evidence(complaint):
    draft = run(complaint.model_copy(update={"speaker": "기록 없는 화자"}))
    assert draft.incident_ids == []
    assert draft.pdf_path is None
    assert "고소장 초안에 포함할 채팅 기록이 없습니다." in draft.text
    assert "채팅 기록 0건" in draft.text
    assert "고소인 서명:" in draft.text


def test_complaint_uses_default_model_with_key_only(complaint, monkeypatch):
    from clean_chat.core import gemini
    from clean_chat.modules.report import impl

    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-key")  # 앱 설정은 키만 저장한다
    calls = []
    summary = "전체 채팅에서 가족을 언급한 비하 표현과 비속어를 사용한 표현이 포함된 메시지 1건이 확인됩니다."
    monkeypatch.setattr(gemini, "completion", lambda **kwargs: calls.append(kwargs) or _gemini_reply(summary))
    assert f"사건 경위: {summary}" in run(complaint).text
    assert calls[0]["model"] == impl.DEFAULT_MODEL == "gemini/gemini-3.1-flash-lite"


def test_same_nickname_with_different_champions_are_different_targets(complaint, tmp_path, monkeypatch):
    """채팅에는 태그 없는 닉네임만 보인다. 닉네임이 같아도 챔피언이 다르면 다른 사람으로 신고·고소 대상을 나눈다."""
    monkeypatch.setattr(settings, "complaint_output_dir", str(tmp_path / "complaints"))
    session = complaint.session
    for incident in session.incidents:
        incident.decision = decide_incoming(incident.msg, incident.analysis, incident.rewrite)
    original = next(incident for incident in session.incidents if incident.msg.id == "L5")
    twin = original.model_copy(deep=True)  # 닉네임이 같은 다른 사람 (다른 챔피언)
    twin.msg.id, twin.msg.champion, twin.msg.text = "L5-twin", "티모", "다른 사람이 한 말"
    session.incidents.append(twin)

    result = PostGameBatch(ModuleSet()).run(session)
    same_name = [draft for draft in result.reports if draft.speaker == original.msg.speaker]
    assert {draft.champion: draft.incident_ids for draft in same_name} == {
        original.msg.champion: ["L5"],
        "티모": ["L5-twin"],
    }
    assert all(f"({draft.champion})" in draft.text.splitlines()[0] for draft in same_name)
    complaints = [draft for draft in result.complaints if draft.speaker == original.msg.speaker]
    assert sorted(draft.incident_ids for draft in complaints) == [["L5"], ["L5-twin"]]
    assert all(f"사용 챔피언: {draft.champion}" in unescape(draft.text) for draft in complaints)
    # 챔피언을 주지 않은 예전 요청은 닉네임만으로 고른다 (기존 예시 그대로).
    legacy = run(ReportRequest(kind=ReportKind.REPORT, session=session, speaker=original.msg.speaker))
    assert (
        legacy.incident_ids == ["L5", "L5-twin"] and legacy.text.splitlines()[0] == f"신고 대상: {original.msg.speaker}"
    )
