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


def test_chat_log_shows_every_chat_of_last_game_and_survives_restart(tmp_path):
    """채팅 기록 화면: 신고 여부와 상관없이 직전 게임의 채팅을 모두 보여 주고, 앱을 다시 열어도 남는다."""
    from PySide6.QtWidgets import QApplication

    from clean_chat.core.config import FIXTURES
    from clean_chat.core.jsonl import read_jsonl
    from clean_chat.core.schemas import GamePhase, ReportRequest
    from clean_chat.ui.client import LOG_COLUMNS, NAV, ClientWindow

    QApplication.instance() or QApplication([])
    session = read_jsonl(FIXTURES / "report" / "input.jsonl", ReportRequest)[0].session
    history = tmp_path / "recent-results.json"
    client = ClientWindow(history)
    assert client.log_table.rowCount() == 0 and not client.btn_copy_log.isEnabled()
    client.show_phase(GamePhase.POST_GAME, session)  # 오버레이 종료 직후
    table = client.log_table
    assert table.rowCount() == len(session.incidents) == 5
    cells = [[table.item(r, c).text() for c in range(len(LOG_COLUMNS))] for r in range(table.rowCount())]
    by_text = {row[2]: row for row in cells}
    assert by_text["다들 화이팅"][4] == "L0" and by_text["다들 화이팅"][7] == "그대로 표시"  # 신고와 무관한 줄도 보인다
    mild = by_text["아 ㅅㅂ 내가 실수함"]
    assert mild[3] == "아 시발 내가 실수함" and mild[8] == "아 내가 실수함" and mild[9] == ""
    assert any(row[7] == "숨김" and row[9] in ("신고", "고소 후보") for row in cells)
    assert "채팅 5줄" in client.log_meta.text()
    client.copy_chat_log()
    copied = QApplication.clipboard().text().splitlines()
    assert copied[0].split("\t") == list(LOG_COLUMNS) and len(copied) == 6
    client.nav_buttons[NAV.index("채팅 기록")].click()  # 왼쪽 메뉴에서 연다
    assert client.pages.currentIndex() == NAV.index("채팅 기록") and table.isVisibleTo(client)
    client.close()

    reopened = ClientWindow(history)  # 앱을 다시 열어도 직전 게임 기록이 남아 있다
    assert reopened.log_table.rowCount() == 5 and reopened.btn_copy_log.isEnabled()
    reopened.close()


def _ready_editor(qt, tmp_path: Path):
    complaint = drafts()[-1]
    client = ClientWindow(tmp_path / "recent.json")
    client.show()
    client.show_result(PostGameResult(session_id="경기 1", complaints=[complaint]))
    client.open_editor(complaint)
    qt.processEvents()
    editor = client.editor
    editor.tag.setText("KR1")
    editor.ack.setChecked(True)
    return client, editor


def test_pdf_default_location_is_writable_even_when_app_runs_from_root(tmp_path: Path, monkeypatch) -> None:
    """설치한 앱의 작업 폴더는 "/" (읽기 전용) 다. 기본 이름만 주면 저장 창이 "/" 에서 열려 저장이 실패했다."""
    qt = QApplication.instance() or QApplication([])
    (tmp_path / "Downloads").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir("/")
    asked = []
    # 사용자가 기본 위치 그대로 "저장" 을 누른 경우
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (asked.append(args[2]) or args[2], "PDF"))
    client, editor = _ready_editor(qt, tmp_path)
    editor.download.click()
    saved = Path(asked[0])
    assert saved.is_absolute() and saved.parent == tmp_path / "Downloads"
    assert saved.name.startswith("고소장-초안-얼음땡-") and saved.suffix == ".pdf"
    assert saved.read_bytes().startswith(b"%PDF") and "PDF 저장 완료" in client.toast.text()
    client.close()


def test_pdf_text_is_document_size(tmp_path: Path) -> None:
    """미리보기의 px 글자 크기가 1200dpi 로 찍혀 A4 에 글자가 아주 작게 나오던 문제."""
    pytest.importorskip("PySide6.QtPdf")
    from PySide6.QtPdf import QPdfDocument

    qt = QApplication.instance() or QApplication([])
    client, editor = _ready_editor(qt, tmp_path)
    path = tmp_path / "draft.pdf"
    editor.save_pdf(path)
    doc = QPdfDocument()
    doc.load(str(path))
    title = doc.getSelectionAtIndex(0, 0, 3).boundingRectangle()  # "고 소 장"
    assert title.height() >= 12  # pt (A4 = 595 × 842 pt). 고치기 전에는 2pt 쯤이었다
    client.close()


@pytest.mark.parametrize(
    ("typed", "shown"),
    [
        ("01012345678", "010-1234-5678"),
        ("0101234567", "010-123-4567"),
        ("0212345678", "02-1234-5678"),
        ("021234567", "02-123-4567"),
        ("15881234", "1588-1234"),
        ("0101", "010-1"),
        ("010-1234-5678", "010-1234-5678"),
        ("010 abc 1234 5678 9", "010-1234-5678"),  # 숫자가 아니면 버리고 11자리까지
        ("", ""),
    ],
)
def test_phone_number_is_digits_with_hyphens(typed: str, shown: str) -> None:
    from clean_chat.ui.complaint import format_phone

    assert format_phone(typed) == shown


def test_contact_field_accepts_digits_only_and_shows_hyphens(tmp_path: Path) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    qt = QApplication.instance() or QApplication([])
    client, editor = _ready_editor(qt, tmp_path)
    QTest.keyClicks(editor.contact, "010ab1234-5678")
    assert editor.contact.text() == "010-1234-5678"
    assert "010-1234-5678" in editor.paper.toPlainText()  # 미리보기·PDF 에도 하이픈이 들어간 번호
    QTest.keyClick(editor.contact, Qt.Key_Backspace)
    assert editor.contact.text() == "010-123-4567"  # 10자리는 3-3-4 로 다시 나눈다
    editor.contact.setCursorPosition(4)  # "010-|123…" → 하이픈만 지우면 그 앞 숫자가 지워진다
    QTest.keyClick(editor.contact, Qt.Key_Backspace)
    assert editor.contact.text() == "011-234-567"
    client.close()
