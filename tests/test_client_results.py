"""결과 화면(신고 메시지·고소장)의 클립보드·PDF·로컬 기록 연결을 검증한다."""

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton  # noqa: E402

from clean_chat.core.charges import ChargeId  # noqa: E402
from clean_chat.core.schemas import PostGameResult, ReportDraft  # noqa: E402
from clean_chat.ui.client import ClientWindow  # noqa: E402
from helpers import fixture_pairs  # noqa: E402


def drafts() -> list[ReportDraft]:
    """report fixture 결과에 core/modules.py 처럼 원문 증거와 적용 혐의를 붙인다."""
    return [
        draft.model_copy(
            update={
                "evidence": tuple(m for m in req.evidence if m.id in draft.incident_ids),
                "applied_charge_ids": req.applied_charge_ids,
            }
        )
        for req, draft in fixture_pairs("report")
    ]


def test_report_page_lists_users_copies_message_and_links_complaint() -> None:
    qt = QApplication.instance() or QApplication([])
    items = drafts()
    result = PostGameResult(session_id="20251112-130000", reports=items[:-1], complaints=[items[-1]])
    client = ClientWindow()
    client.show()
    client.show_result(result)
    qt.processEvents()
    assert client.pages.currentIndex() == 1
    assert client.result_title.text() == "나에게 욕설한 유저 2명"
    assert "2025.11.12 13:00" in client.result_meta.text()
    cards = client.user_cards
    assert [b.accessibleName() for b in cards] == ["불꽃남자 신고 대상 선택", "얼음땡 신고 대상 선택"]
    # 첫 유저가 선택되고, 고소장 후보가 아니면 고소장 버튼이 없다.
    assert cards[0].isChecked() and not cards[1].isChecked() and not client.btn_complaint.isVisible()
    assert "[팀]" not in client.raw_log.text() and "불꽃남자 (팀): 야 정글" in client.raw_log.text()
    client.btn_copy.click()
    assert qt.clipboard().text() == items[0].text
    assert client.btn_copy.text() == "복사됨 ✓" and "복사했습니다" in client.toast.text()
    cards[1].click()
    assert cards[1].isChecked() and not cards[0].isChecked()
    assert client.message.toPlainText() == items[1].text and client.btn_copy.text() == "신고 메시지 복사"
    assert client.btn_complaint.isVisible()
    client.btn_complaint.click()
    assert client.pages.currentIndex() == 2 and client.editor.draft is items[-1]
    client.close()


def test_complaint_editor_charges_ack_pdf_and_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    qt = QApplication.instance() or QApplication([])
    complaint = drafts()[-1]
    result = PostGameResult(session_id="경기 1", complaints=[complaint])
    history = tmp_path / "recent.json"
    client = ClientWindow(history)
    client.show()
    client.show_result(result)
    client.open_editor(complaint)
    qt.processEvents()
    editor = client.editor
    infos = [b.accessibleName() for b in editor.findChildren(QPushButton, "info")]
    assert "모욕죄 설명 보기" in infos and len(infos) == 1 + 5  # 자동 적용된 죄목 1개 + 주의사항 5개
    # 죄목은 분석 결과로 자동 적용되고, 사용자가 고르는 체크박스는 없다.
    assert editor.selected_charges() == [ChargeId.INSULT]
    assert not hasattr(editor, "charge_checks")
    assert "모욕죄" in editor.paper.toPlainText()
    # 닉네임은 화자에서 채워지고, 태그·주의사항 확인 전에는 다운로드가 잠긴다.
    assert editor.target.text() == "얼음땡" and not editor.download.isEnabled()
    editor.tag.setText("#KR1")
    assert not editor.download.isEnabled() and "주의사항" in editor.reason.text()
    editor.ack.setChecked(True)
    assert editor.download.isEnabled()
    text = editor.paper.toPlainText()
    assert "모욕죄" in text and "협박죄" not in text and "얼음땡#KR1" in text
    assert complaint.evidence[0].text in text
    editor.name.setText("테스트 작성자")
    assert "테스트 작성자" in editor.paper.toPlainText()
    path = tmp_path / "draft.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), "PDF"))
    editor.download.click()
    assert path.read_bytes().startswith(b"%PDF")
    assert editor.download.text() == "PDF 저장됨 ✓" and not editor.btn_open.isHidden()
    assert "PDF 저장 완료" in client.toast.text() and complaint.pdf_path == str(path)
    other = ClientWindow(history)
    assert other.results[result.session_id].complaints[0].pdf_path == str(path)
    other.close()
    client.close()


def test_filter_strength_checkboxes_and_pills_stay_in_sync() -> None:
    QApplication.instance() or QApplication([])
    client = ClientWindow()
    seen: list[str] = []
    client.strength_changed.connect(seen.append)
    checks = client.strength_checks.buttons()
    assert [c.text() for c in checks] == ["낮음", "보통", "높음"]
    assert client.strength_value() == "normal" and checks[1].isChecked()
    checks[2].click()
    assert client.strength_value() == "high" and client.strength_buttons.button(2).isChecked()
    assert not checks[1].isChecked()
    client.strength_buttons.button(0).click()
    assert checks[0].isChecked() and seen == ["high", "low"]
    client.close()


def test_nav_follows_accessibility_press_and_key_button_keeps_width() -> None:
    qt = QApplication.instance() or QApplication([])
    client = ClientWindow()
    client.show()
    qt.processEvents()
    # VoiceOver의 '누르기'는 클릭 신호 없이 체크만 바꾼다. 그래도 페이지가 바뀌어야 한다.
    client.nav_buttons[3].setChecked(True)
    assert client.pages.currentIndex() == 3
    client.nav_buttons[0].click()
    assert client.pages.currentIndex() == 0 and not client.nav_buttons[3].isChecked()
    client.pages.setCurrentIndex(2)  # 코드에서 페이지를 바꾸면 메뉴 강조도 따라간다.
    assert client.nav_buttons[2].isChecked()
    client.nav_buttons[3].click()
    qt.processEvents()
    before = (client.btn_key_show.width(), client.llm_key.width())
    client.btn_key_show.click()
    qt.processEvents()
    assert client.btn_key_show.text() == "숨기기"
    assert (client.btn_key_show.width(), client.llm_key.width()) == before
    client.close()


def test_capture_preview_option_is_a_switch():
    """캡처 미리보기는 스위치로 켜고 끈다 (클릭·스페이스). 판독(OCR)과는 무관하다."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QCheckBox

    from clean_chat.ui.client import ClientWindow
    from clean_chat.ui.client_widgets import Switch

    QApplication.instance() or QApplication([])
    client = ClientWindow()
    switch = client.preview_toggle
    assert isinstance(switch, Switch) and not isinstance(switch, QCheckBox)
    assert switch.isChecked() and switch.accessibleName() == "읽고 있는 영역 보기"
    QTest.mouseClick(switch, Qt.LeftButton)
    assert not switch.isChecked() and "꺼짐" in client.preview_info.text()
    QTest.keyClick(switch, Qt.Key_Space)
    assert switch.isChecked() and client.preview_info.text() == "캡처 미리보기"
    assert not switch.grab().isNull()  # 켜진 모습·꺼진 모습을 그릴 수 있다
    client.close()
