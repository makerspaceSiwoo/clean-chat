"""라이트 모드 데스크톱 클라이언트. 실제 세션 결과만 목록에 표시한다."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from PySide6.QtCore import QIODevice, QSaveFile, QSize, Qt, QTime, QTimer, QUrl, Slot
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clean_chat.core.config import resolve_repo_path
from clean_chat.core.schemas import GamePhase, GameSession, Incident, PostGameResult, ReportDraft
from clean_chat.ui.client_widgets import STYLE, card, client_icon, label, overlay_diagram, scroll_page
from clean_chat.ui.complaint import ComplaintEditor, quote


class ClientWindow(QMainWindow):
    def __init__(self, history_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Clean Chat")
        self.resize(1080, 760)
        self.setMinimumSize(740, 490)
        palette = self.palette()
        for role, color in [
            (QPalette.Window, "#f5f7fa"),
            (QPalette.WindowText, "#222e40"),
            (QPalette.Base, "#ffffff"),
            (QPalette.Text, "#222e40"),
            (QPalette.ButtonText, "#222e40"),
            (QPalette.Button, "#ffffff"),
            (QPalette.Highlight, "#2458bd"),
            (QPalette.HighlightedText, "#ffffff"),
        ]:
            palette.setColor(role, QColor(color))
        self.setPalette(palette)
        self.setStyleSheet(STYLE)
        self.history_path = history_path
        self.history_format = TypeAdapter(list[PostGameResult])
        self.results: dict[str, PostGameResult] = {}
        self.current_result = None
        self.preview_count = 0

        shell = QWidget()
        self.setCentralWidget(shell)
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        rail = QWidget()
        rail.setObjectName("rail")
        rail.setFixedWidth(180)
        menu = QVBoxLayout(rail)
        menu.setContentsMargins(12, 22, 12, 12)
        brand = QHBoxLayout()
        mark = QLabel()
        mark.setFixedWidth(32)
        mark.setPixmap(client_icon("brand").pixmap(32, 32))
        brand.addWidget(mark)
        brand.addWidget(label("Clean Chat", "brand"), 1)
        menu.addLayout(brand)
        menu.addSpacing(20)
        row.addWidget(rail)
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        row.addLayout(body, 1)
        self.crumb = label("클라이언트   /   홈 · 오버레이", "breadcrumb")
        self.crumb.setContentsMargins(22, 9, 12, 9)
        self.crumb.setFixedHeight(46)
        body.addWidget(self.crumb)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self.navigation = QButtonGroup(self)
        self.nav_buttons = []
        panels = []
        for i, title in enumerate(("홈 · 오버레이", "신고 메시지", "고소장", "설정")):
            page, layout = scroll_page()
            self.pages.addWidget(page)
            panels.append(layout)
            b = QPushButton(title)
            b.setObjectName("nav")
            b.setIcon(client_icon(("home", "reports", "complaint", "settings")[i]))
            b.setIconSize(QSize(18, 18))
            b.setCheckable(True)
            self.navigation.addButton(b, i)
            self.nav_buttons.append(b)
            menu.addWidget(b)
        menu.addStretch()
        menu.addWidget(label("●  로컬 클라이언트", "muted"))
        self.navigation.idClicked.connect(self.pages.setCurrentIndex)
        self.pages.currentChanged.connect(self._navigated)
        self._navigated(0)
        home, reports, complaint, preferences = panels
        self.preview_page = self.pages.widget(0)
        self._page_for = {
            GamePhase.IDLE: self.preview_page,
            GamePhase.IN_GAME: self.preview_page,
            GamePhase.POST_GAME: self.pages.widget(1),
        }

        home.addWidget(label("홈 · 오버레이", "title"))
        hero, controls = card("오버레이 시작하기", "hero")
        home.addWidget(hero)
        hero_row = QHBoxLayout()
        controls.addLayout(hero_row)
        controls = QVBoxLayout()
        hero_row.addLayout(controls, 1)
        hero_row.addWidget(overlay_diagram(), 0, Qt.AlignRight | Qt.AlignVCenter)
        controls.addWidget(label("게임 채팅 전체를 가린 뒤 위치를 잠그면 캡처가 시작됩니다.", "muted"))
        actions = QHBoxLayout()
        self.btn_start = QPushButton("Clean Chat 시작")
        self.btn_start.setObjectName("primary")
        self.btn_lock = QPushButton("위치 잠금")
        self.btn_lock.setEnabled(False)
        for button in (self.btn_start, self.btn_lock):
            actions.addWidget(button)
        actions.addStretch()
        controls.addLayout(actions)
        self.preview_only = QCheckBox("오버레이 아래 화면 미리보기 (OCR 끔)")
        self.preview_only.setChecked(True)
        controls.addWidget(self.preview_only)
        self.permission_settings = QPushButton("화면 기록 설정")
        self.permission_settings.clicked.connect(self.open_capture_settings)
        self.reveal_app = QPushButton("Finder에서 앱 보기")
        self.reveal_app.clicked.connect(self.reveal_capture_app)
        permission = QHBoxLayout()
        permission.addWidget(self.permission_settings)
        permission.addWidget(self.reveal_app)
        permission.addStretch()
        controls.addLayout(permission)
        self.show_capture_settings(False)

        metrics = QHBoxLayout()
        home.addLayout(metrics)
        for title, text, attr in [
            ("게임 상태", "게임 대기", "game_state"),
            ("채팅창 영역", "위치 조정 대기", "region_state"),
            ("필터 강도", "보통", "strength_state"),
        ]:
            tile, col = card(title)
            value = label(text, "muted")
            setattr(self, attr, value)
            col.addWidget(value)
            if attr == "strength_state":
                segments = QHBoxLayout()
                self.strength_buttons = QButtonGroup(self)
                for index, caption in enumerate(("낮음", "보통", "높음")):
                    segment = QPushButton(caption)
                    segment.setObjectName("segment")
                    segment.setCheckable(True)
                    self.strength_buttons.addButton(segment, index)
                    segments.addWidget(segment)
                segments.addStretch()
                col.addLayout(segments)
                value.hide()
            metrics.addWidget(tile, 1)

        preview, content = card("캡처 미리보기")
        home.addWidget(preview)
        self.preview_info = label("위치 잠금 대기", "muted")
        self.preview_image = label("위치 잠금 후 첫 이미지가 표시됩니다.")
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.preview_image.setMinimumHeight(115)
        content.addWidget(self.preview_info)
        content.addWidget(self.preview_image)
        self.live_card, live_layout = card("이번 게임 처리 내역")
        self.game_label = label("게임 중 · 채팅은 오버레이에서 확인하세요.", "muted")
        self.live = QListWidget()
        live_layout.addWidget(self.game_label)
        live_layout.addWidget(self.live)
        home.addWidget(self.live_card)
        recent, recent_layout = card("최근 게임")
        self.history = QListWidget()
        self.history.setMaximumHeight(95)
        self.history.itemActivated.connect(lambda item: self.open_result(item.data(Qt.UserRole)))
        self.history.itemClicked.connect(lambda item: self.open_result(item.data(Qt.UserRole)))
        recent_layout.addWidget(self.history)
        self.no_history = label("완료된 게임이 없습니다.", "muted")
        recent_layout.addWidget(self.no_history)
        self.history.hide()
        home.insertWidget(home.indexOf(preview), recent)
        home.addStretch()

        reports.addWidget(label("신고 메시지", "title"))
        reports.addWidget(label("닉네임을 펼쳐 원문을 확인하거나 클립보드 버튼으로 바로 복사하세요.", "muted"))
        self.result_holder = QWidget()
        self.result_layout = QVBoxLayout(self.result_holder)
        self.result_layout.setContentsMargins(0, 0, 0, 0)
        self.result_content = QWidget()
        self.result_layout.addWidget(self.result_content)
        reports.addWidget(self.result_holder)
        self.btn_close_result = QPushButton("닫기")
        reports.addWidget(self.btn_close_result, 0, Qt.AlignLeft)

        complaint.addWidget(label("고소장 만들기", "title"))
        complaint.addWidget(label("내 이름과 상대 계정을 입력하고, 초안에 포함할 채팅을 선택하세요.", "muted"))
        self.editor_layout = complaint
        self.editor = ComplaintEditor()
        complaint.addWidget(self.editor)
        self._render_result(None)
        preferences.addWidget(label("설정", "title"))
        settings_card, fields = card("플레이어 설정")
        preferences.addWidget(settings_card)
        fields.addWidget(label("내 소환사명"))
        self.my_name = QLineEdit()
        self.my_name.setPlaceholderText("게임에 표시되는 닉네임")
        fields.addWidget(self.my_name)
        fields.addWidget(label("필터 강도"))
        self.strength = QComboBox()
        for title, value in [("낮음", "low"), ("보통", "normal"), ("높음", "high")]:
            self.strength.addItem(title, value)
        self.strength_buttons.idClicked.connect(self.strength.setCurrentIndex)
        self.strength.currentIndexChanged.connect(lambda i: self.strength_buttons.button(i).setChecked(True))
        self.strength.setCurrentIndex(1)
        fields.addWidget(self.strength, 0, Qt.AlignLeft)
        fields.addWidget(
            label(
                "낮음은 가벼운 혼잣말을 표시하고, 보통은 비속어만 가립니다. 높음은 가벼운 비속어도 줄 전체를 숨깁니다. 시스템 메시지는 모든 강도에서 표시됩니다.",
                "muted",
            )
        )
        self.toast = label("")
        self.toast.setObjectName("toast")
        self.toast.setParent(shell)
        self.toast.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.toast.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)
        self.show_phase(GamePhase.IDLE, None)
        self._load_history()

    def _navigated(self, index: int) -> None:
        button = self.nav_buttons[index]
        button.setChecked(True)
        self.crumb.setText("클라이언트   /   " + button.text())

    def notify(self, message: str) -> None:
        self.toast.setText(message)
        self.toast.adjustSize()
        self.toast.move(
            max(8, self.centralWidget().width() - self.toast.width() - 18),
            max(8, self.centralWidget().height() - self.toast.height() - 16),
        )
        self.toast.raise_()
        self.toast.show()
        self.toast_timer.start(5000)

    def show_capture_settings(self, needed: bool) -> None:
        self.permission_settings.setVisible(needed)
        self.reveal_app.setVisible(needed and sys.platform == "darwin" and getattr(sys, "frozen", False))

    def open_capture_settings(self) -> None:
        QDesktopServices.openUrl(QUrl("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"))

    def reveal_capture_app(self) -> None:
        subprocess.Popen(["/usr/bin/open", "-R", str(Path(sys.executable).parents[2])])

    @Slot(QImage)
    def show_preview(self, image: QImage) -> None:
        if image.isNull():
            self.preview_count = 0
            self.preview_info.setText("캡처 미리보기")
            self.preview_image.setText("캡처 대기 중")
            return
        self.preview_count += 1
        stamp = QTime.currentTime().toString("HH:mm:ss.zzz")
        self.preview_info.setText(f"캡처 {self.preview_count} · {stamp} · {image.width()} × {image.height()} px")
        size = image.size().boundedTo(self.preview_image.contentsRect().size())
        self.preview_image.setPixmap(QPixmap.fromImage(image).scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def show_phase(self, phase: GamePhase, session: GameSession | None) -> None:
        self.live_card.setVisible(phase == GamePhase.IN_GAME)
        self.game_state.setText(
            {GamePhase.IDLE: "게임 대기", GamePhase.IN_GAME: "게임 중", GamePhase.POST_GAME: "게임 종료"}[phase]
        )
        if phase == GamePhase.POST_GAME and session and session.id != self.current_result:
            self._render_result(None)
            self.open_editor(None, navigate=False)
        self.pages.setCurrentWidget(self._page_for[phase])

    def add_incident(self, inc: Incident) -> None:
        self.live.addItem(f"{inc.msg.speaker} · {inc.decision.display_text or '숨김'}")
        if self.live.count() > 200:
            self.live.takeItem(0)

    def _load_history(self) -> None:
        if self.history_path is None:
            return
        try:
            saved = self.history_format.validate_json(self.history_path.read_bytes())
        except FileNotFoundError:
            return
        except (OSError, ValidationError):
            self.notify("최근 게임 기록을 읽을 수 없습니다.")
            return
        self.results = {game.session_id: game for game in saved[-3:]}
        self._refresh_history()
        if self.results:
            self.open_result(next(reversed(self.results)))
            self.pages.setCurrentIndex(0)

    def _save_history(self) -> None:
        if self.history_path is None:
            return
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            file = QSaveFile(str(self.history_path))
            data = self.history_format.dump_json(list(self.results.values()))
            if not file.open(QIODevice.WriteOnly) or file.write(data) != len(data) or not file.commit():
                raise OSError(file.errorString())
        except OSError:
            self.notify("최근 게임 기록을 저장할 수 없습니다.")

    def show_result(self, result: PostGameResult) -> None:
        self.results.pop(result.session_id, None)
        self.results[result.session_id] = result
        if len(self.results) > 3:
            del self.results[next(iter(self.results))]
        self._save_history()
        self._refresh_history()
        self.open_result(result.session_id)

    def _refresh_history(self) -> None:
        self.history.clear()
        for key in reversed(self.results):
            try:
                title = datetime.strptime(key, "%Y%m%d-%H%M%S").strftime("%Y.%m.%d   %H:%M")
            except ValueError:
                title = key
            self.history.addItem(
                f"{title}　·　신고 대상 {len(self.results[key].reports)}명　·　고소장 초안 {len(self.results[key].complaints)}건"
            )
            self.history.item(self.history.count() - 1).setData(Qt.UserRole, key)
        self.history.setFixedHeight(16 + sum(self.history.sizeHintForRow(i) for i in range(self.history.count())))
        self.no_history.setVisible(not self.results)
        self.history.setVisible(bool(self.results))

    def open_result(self, session_id: str) -> None:
        result = self.results[session_id]
        self.current_result = session_id
        self._render_result(result)
        self.open_editor(result.complaints[0] if result.complaints else None, navigate=False)
        self.pages.setCurrentIndex(1)

    def _render_result(self, result: PostGameResult | None) -> None:
        old = self.result_content
        self.result_layout.removeWidget(old)
        old.hide()
        old.deleteLater()
        self.result_content = QWidget()
        self.result_layout.addWidget(self.result_content)
        stack = QVBoxLayout(self.result_content)
        stack.setContentsMargins(0, 0, 0, 0)
        reports = result.reports if result else []
        complaints = result.complaints if result else []
        box, rows = card(f"신고 대상　{len(reports)}명")
        stack.addWidget(box)
        if not reports:
            rows.addWidget(label("신고 대상이 없습니다.", "muted"))
        for draft in reports:
            self._report_row(rows, draft)
        box, rows = card("고소장 초안")
        stack.addWidget(box)
        if not complaints:
            rows.addWidget(label("작성 가능한 초안이 없습니다.", "muted"))
        for draft in complaints:
            row = QHBoxLayout()
            row.addWidget(label(draft.speaker), 1)
            edit = QPushButton("초안 작성")
            edit.clicked.connect(lambda _, d=draft: self.open_editor(d))
            row.addWidget(edit)
            if draft.pdf_path:
                op = QPushButton("PDF 열기")
                op.clicked.connect(lambda _, d=draft: self.open_pdf(d))
                row.addWidget(op)
            rows.addLayout(row)

    def _report_row(self, layout: QVBoxLayout, draft: ReportDraft) -> None:
        message = draft.text
        if draft.evidence:
            lines = "\n".join(quote(msg) for msg in draft.evidence)
            if lines not in message:
                message += "\n\n채팅 원문\n" + lines
        line = QHBoxLayout()
        expand = QPushButton("▸  " + draft.speaker.replace("&", "&&"))
        expand.setObjectName("toggle")
        expand.setCheckable(True)
        line.addWidget(expand)
        line.addStretch()
        copy = QPushButton()
        copy.setIcon(client_icon("clipboard"))
        copy.setToolTip("신고 문구 복사")
        copy.setAccessibleName(draft.speaker + " 신고 문구 복사")
        line.addWidget(copy)
        layout.addLayout(line)
        content = label(message, "original")
        content.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(content)
        content.hide()

        def toggle(on: bool) -> None:
            content.setVisible(on)
            expand.setText(("▾  " if on else "▸  ") + draft.speaker.replace("&", "&&"))

        expand.toggled.connect(toggle)

        def copy_report() -> None:
            QApplication.clipboard().setText(message)
            self.notify(f"신고 문구를 복사했습니다 · {draft.speaker}")

        copy.clicked.connect(copy_report)

    def open_editor(self, draft: ReportDraft | None, navigate: bool = True) -> None:
        if self.editor.draft is not draft:
            old = self.editor
            self.editor_layout.removeWidget(old)
            old.hide()
            old.deleteLater()
            self.editor = ComplaintEditor(draft)
            self.editor.notice.connect(self.notify)
            if draft:
                self.editor.saved.connect(lambda path: self._saved(draft, path))
            self.editor_layout.addWidget(self.editor)
        if navigate:
            self.pages.setCurrentIndex(2)

    def _saved(self, draft: ReportDraft, path: str) -> None:
        draft.pdf_path = path
        self._save_history()
        self._render_result(self.results.get(self.current_result))

    def open_pdf(self, draft: ReportDraft) -> None:
        path = resolve_repo_path(draft.pdf_path)
        if not path.is_file():
            self.notify("저장된 PDF를 찾을 수 없습니다. 초안에서 다시 저장하세요.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
            self.notify(
                "저장 폴더에서 PDF를 선택해 다른 앱으로 여세요." if opened else f"PDF를 열 수 없습니다 · {path}"
            )

    def show_engine_error(self, message: str) -> None:
        self.statusBar().showMessage(message)
        self.game_label.setText(f"멈춤 · {message}")
