"""결과 화면의 클립보드·고소장·로컬 기록 연결을 검증한다."""

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QPushButton  # noqa: E402

from clean_chat.core.config import FIXTURES  # noqa: E402
from clean_chat.core.schemas import PostGameResult, ReportDraft  # noqa: E402
from clean_chat.ui.client import ClientWindow  # noqa: E402


def test_client_results_clipboard_pdf_and_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    qt = QApplication.instance() or QApplication([])
    drafts = [
        ReportDraft.model_validate_json(line) for line in (FIXTURES / "report/expected.jsonl").read_bytes().splitlines()
    ]
    report, complaint = drafts[0], drafts[-1]
    result = PostGameResult(session_id="경기 1", reports=drafts[:-1], complaints=[complaint])
    history = tmp_path / "recent.json"
    client = ClientWindow(history)
    client.show()
    client.show_result(result)
    qt.processEvents()
    copy = next(
        b
        for b in client.result_content.findChildren(QPushButton)
        if b.accessibleName() == report.speaker + " 신고 문구 복사"
    )
    content = client.result_content.findChildren(QLabel, "original")[0]
    assert not content.isVisible()
    copy.click()
    assert qt.clipboard().text() == content.text()
    assert "[팀]" in content.text() and report.evidence[0].text in content.text()
    assert "복사했습니다" in client.toast.text()
    client.result_content.findChildren(QPushButton, "toggle")[0].click()
    assert content.isVisible()
    client.open_editor(complaint)
    editor = client.editor
    infos = [b.accessibleName() for b in editor.findChildren(QPushButton, "info")]
    assert "모욕 설명" in infos or "모욕죄 설명" in infos
    assert not editor.download.isEnabled()
    editor.name.setText("테스트 작성자")
    editor.tag.setText("KR1")
    editor.ack.setChecked(True)
    assert editor.download.isEnabled()
    msg, checkbox = editor.evidence_checks[0]
    checkbox.setChecked(False)
    assert not editor.download.isEnabled() and msg.text not in editor.paper.toPlainText()
    checkbox.setChecked(True)
    assert msg.text in editor.paper.toPlainText() and "테스트 작성자" in editor.paper.toPlainText()
    path = tmp_path / "draft.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), "PDF"))
    editor.download.click()
    assert path.read_bytes().startswith(b"%PDF")
    assert "PDF 저장 완료" in client.toast.text() and complaint.pdf_path == str(path)
    other = ClientWindow(history)
    assert other.results[result.session_id].complaints[0].pdf_path == str(path)
    other.close()
    client.close()
