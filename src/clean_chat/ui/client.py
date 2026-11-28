"""라이트 모드 데스크톱 클라이언트 (클라이언트 목업: 홈 · 신고 메시지 · 고소장). 실제 세션 결과만 표시한다."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from PySide6.QtCore import QIODevice, QSaveFile, Qt, QTime, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clean_chat.core.config import resolve_repo_path
from clean_chat.core.schemas import GamePhase, GameSession, Incident, PostGameResult, ReportDraft
from clean_chat.ui.client_widgets import STYLE, SelectCard, Switch, button, card, heading, label, restyle, scroll_page
from clean_chat.ui.complaint import ComplaintEditor, quote

NAV = ("홈 · 오버레이", "신고 메시지", "고소장", "설정")
STRENGTHS = (("낮음", "low"), ("보통", "normal"), ("높음", "high"))
PHASE_TEXT = {GamePhase.IDLE: "게임 대기 중", GamePhase.IN_GAME: "게임 진행 중", GamePhase.POST_GAME: "게임 종료"}


def game_title(session_id: str) -> str:
    """세션 ID(시작 시각)를 '2026.11.26 21:12' 형태로."""
    try:
        return datetime.strptime(session_id, "%Y%m%d-%H%M%S").strftime("%Y.%m.%d %H:%M")
    except ValueError:
        return session_id


def styled(widget: QWidget, role: str) -> QWidget:
    widget.setObjectName(role)
    widget.setAttribute(Qt.WA_StyledBackground)
    return widget


def target_label(draft: ReportDraft) -> str:
    """신고·고소 대상 한 사람을 가리키는 이름. 닉네임이 같아도 챔피언이 다르면 다른 사람이다."""
    return f"{draft.speaker} ({draft.champion})" if draft.champion else draft.speaker


def mask_key(api_key: str) -> str:
    """API 키는 끝 4자리만 보여 준다. 짧은 키는 전부 가린다."""
    return f"••••{api_key[-4:]}" if len(api_key) >= 12 else "••••"


class ClientWindow(QMainWindow):
    strength_changed = Signal(str)  # 필터 강도 값: low · normal · high
    llm_save_requested = Signal(str)  # Gemini API 키 (모델은 rewrite·report가 정한다)
    llm_clear_requested = Signal()

    def __init__(self, history_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Clean Chat · 데스크톱 클라이언트")
        self.resize(1120, 760)
        self.setMinimumSize(960, 600)
        palette = self.palette()
        for role, color in [
            (QPalette.Window, "#ffffff"),
            (QPalette.WindowText, "#1a1d21"),
            (QPalette.Base, "#ffffff"),
            (QPalette.Text, "#1a1d21"),
            (QPalette.ButtonText, "#1a1d21"),
            (QPalette.Button, "#ffffff"),
            (QPalette.Highlight, "#2457d6"),
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
        self.users: dict[str, tuple[ReportDraft | None, ReportDraft | None]] = {}
        self.selected = ""

        shell = QWidget()
        self.setCentralWidget(shell)
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        rail = styled(QWidget(), "rail")
        rail.setFixedWidth(200)
        menu = QVBoxLayout(rail)
        menu.setContentsMargins(12, 16, 12, 16)
        menu.setSpacing(4)
        row.addWidget(rail)
        self.pages = QStackedWidget()
        row.addWidget(self.pages, 1)
        self.navigation = QButtonGroup(self)
        self.nav_buttons = []
        panels = []
        for i, title in enumerate(NAV):
            page, layout = scroll_page() if i == 0 else scroll_page((32, 24, 32, 24))
            self.pages.addWidget(page)
            panels.append(layout)
            b = button(title, "nav")
            b.setCheckable(True)
            self.navigation.addButton(b, i)
            self.nav_buttons.append(b)
            menu.addWidget(b)
        menu.addStretch()
        # 마우스 클릭뿐 아니라 VoiceOver 같은 보조 기능의 '누르기'(체크만 바꿈)에도 페이지를 바꾼다.
        self.navigation.idToggled.connect(lambda i, on: on and self.pages.setCurrentIndex(i))
        self.pages.currentChanged.connect(lambda i: self.nav_buttons[i].setChecked(True))
        self.nav_buttons[0].setChecked(True)
        home, reports, complaint, preferences = panels
        self.preview_page = self.pages.widget(0)
        self._page_for = {
            GamePhase.IDLE: self.preview_page,
            GamePhase.IN_GAME: self.preview_page,
            GamePhase.POST_GAME: self.pages.widget(1),
        }
        self._build_home(home)
        self._build_reports(reports)
        self.editor_layout = complaint
        self.editor = ComplaintEditor()
        complaint.addWidget(self.editor)
        self._build_settings(preferences)
        self._render_result(None)

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

    # ── 홈 · 오버레이 ─────────────────────────────────────────
    def _build_home(self, home: QVBoxLayout) -> None:
        home.addWidget(label("홈", "title"))
        hero = QFrame()
        hero.setObjectName("hero")
        hero_row = QHBoxLayout(hero)
        hero_row.setContentsMargins(24, 24, 24, 24)
        hero_row.setSpacing(24)
        text = QVBoxLayout()
        text.setSpacing(6)
        text.addWidget(label("오버레이 채팅창", "muted"))
        self.status_title = label("중지됨", "status")
        self.status_desc = label("오버레이를 실행하면 다음 게임부터 채팅 필터가 동작합니다.", "muted")
        text.addWidget(self.status_title)
        text.addWidget(self.status_desc)
        self.permission_settings = button("화면 기록 설정")
        self.permission_settings.clicked.connect(self.open_capture_settings)
        self.reveal_app = button("Finder에서 앱 보기")
        self.reveal_app.clicked.connect(self.reveal_capture_app)
        permission = QHBoxLayout()
        permission.addWidget(self.permission_settings)
        permission.addWidget(self.reveal_app)
        permission.addStretch()
        text.addLayout(permission)
        hero_row.addLayout(text, 1)
        self.btn_lock = button("위치 잠금", "primary", large=True)
        self.btn_lock.setEnabled(False)
        self.btn_start = button("오버레이 실행", "primary", large=True)
        hero_row.addWidget(self.btn_lock)
        hero_row.addWidget(self.btn_start)
        home.addWidget(hero)
        self.show_capture_settings(False)

        tiles = QHBoxLayout()
        tiles.setSpacing(16)
        home.addLayout(tiles)
        tile, col = self._tile("게임 감지")
        self.game_state = label("게임 대기 중", "value")
        self.game_caption = label("게임 시작 시 오버레이 자동 표시", "caption")
        col.addWidget(self.game_state)
        col.addWidget(self.game_caption)
        tiles.addWidget(tile, 1)
        tile, col = self._tile("채팅창 영역")
        self.region_state = label("위치 조정 대기", "value")
        self.btn_region = button("영역 다시 맞추기", "link")
        self.btn_region.clicked.connect(lambda: self.btn_lock.click())
        self.btn_region.hide()
        col.addWidget(self.region_state)
        col.addWidget(self.btn_region, 0, Qt.AlignLeft)
        tiles.addWidget(tile, 1)
        tile, col = self._tile("필터 강도")
        segments = QHBoxLayout()
        segments.setSpacing(6)
        self.strength_buttons = QButtonGroup(self)
        for index, (caption, _) in enumerate(STRENGTHS):
            segment = button(caption, "segment")
            segment.setCheckable(True)
            self.strength_buttons.addButton(segment, index)
            segments.addWidget(segment)
        segments.addStretch()
        col.addLayout(segments)
        col.addWidget(label("시스템 메시지는 항상 원문 표시", "caption"))
        tiles.addWidget(tile, 1)
        self.set_overlay_state(False, True)

        self.live_card, live_layout = card("이번 게임 처리 내역")
        self.game_label = label("게임 중 · 채팅은 오버레이에서 확인하세요.", "muted")
        self.live = QListWidget()
        live_layout.addWidget(self.game_label)
        live_layout.addWidget(self.live)
        home.addWidget(self.live_card)

        recent = QVBoxLayout()
        recent.setSpacing(8)
        recent.addWidget(label("최근 게임", "section"))
        table = QFrame()
        table.setObjectName("table")
        self.history_layout = QVBoxLayout(table)
        self.history_layout.setContentsMargins(1, 1, 1, 1)
        self.history_layout.setSpacing(0)
        self.history_layout.addWidget(self._table_row(["게임", "신고 대상", "고소장 초안", ""], head=True))
        self.history_body = QWidget()
        self.history_layout.addWidget(self.history_body)
        recent.addWidget(table)
        home.addLayout(recent)

        preview, content = card("캡처 미리보기")
        # 표시만 켜고 끄는 스위치. 채팅 판독(OCR)과는 무관하다.
        self.preview_toggle = Switch("읽고 있는 영역 보기", checked=True)
        self.preview_toggle.toggled.connect(self._preview_toggled)
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(10)
        toggle_row.addWidget(label("읽고 있는 영역 보기", "label"))
        toggle_row.addWidget(self.preview_toggle)
        toggle_row.addStretch(1)
        self.preview_info = label("위치 잠금 대기", "caption")
        self.preview_image = label("위치 잠금 후 첫 이미지가 표시됩니다.", "muted")
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.preview_image.setMinimumHeight(115)
        content.addLayout(toggle_row)
        content.addWidget(self.preview_info)
        content.addWidget(self.preview_image)
        self.preview_card = preview
        home.addWidget(preview)
        home.addStretch()

    def _tile(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame, col = card()
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        col.setAlignment(Qt.AlignTop)
        col.addWidget(label(title, "caption"))
        return frame, col

    def _table_row(self, cells: list[str | QWidget], head: bool = False) -> QWidget:
        row = styled(QWidget(), "tableHeadRow" if head else "tableRow")
        line = QHBoxLayout(row)
        line.setContentsMargins(16, 10 if head else 12, 16, 10 if head else 12)
        for cell, stretch in zip(cells, (2, 1, 1, 1), strict=True):
            widget = label(cell, "tableHead" if head else "") if isinstance(cell, str) else cell
            widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            line.addWidget(widget, stretch)
        return row

    def set_status(self, title: str, desc: str) -> None:
        self.status_title.setText(title)
        self.status_desc.setText(desc)

    def set_overlay_state(self, armed: bool, editing: bool) -> None:
        """실행 버튼은 목업처럼 실행 전 파란색, 실행 중 흰색. 위치 잠금은 조정 중에만 보인다."""
        self.btn_start.setText("오버레이 종료" if armed else "오버레이 실행")
        restyle(self.btn_start, "secondary" if armed else "primary")
        self.btn_lock.setText("위치 잠금" if editing else "위치 조정")
        self.btn_lock.setVisible(armed and editing)
        self.btn_region.setVisible(armed and not editing)

    # ── 신고 메시지 ───────────────────────────────────────────
    def _build_reports(self, reports: QVBoxLayout) -> None:
        reports.setSpacing(16)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.result_meta = label("게임이 끝나면 자동으로 열립니다", "caption")
        self.result_title = label("신고 메시지", "title")
        titles.addWidget(self.result_meta)
        titles.addWidget(self.result_title)
        head.addLayout(titles, 1)
        self.btn_close_result = button("닫기")
        head.addWidget(self.btn_close_result, 0, Qt.AlignTop)
        reports.addLayout(head)
        self.result_holder = QWidget()
        self.result_layout = QVBoxLayout(self.result_holder)
        self.result_layout.setContentsMargins(0, 0, 0, 0)
        self.result_content = QWidget()
        self.result_layout.addWidget(self.result_content)
        reports.addWidget(self.result_holder)

    def _render_result(self, result: PostGameResult | None) -> None:
        old = self.result_content
        self.result_layout.removeWidget(old)
        old.hide()
        old.deleteLater()
        self.result_content = QWidget()
        self.result_layout.addWidget(self.result_content)
        users: dict[str, list[ReportDraft | None]] = {}
        for draft in result.reports if result else []:
            users.setdefault(target_label(draft), [None, None])[0] = draft
        for draft in result.complaints if result else []:
            users.setdefault(target_label(draft), [None, None])[1] = draft
        self.users = {name: (rep, comp) for name, (rep, comp) in users.items()}
        self.selected = ""
        if result is None:
            self.result_meta.setText("게임이 끝나면 자동으로 열립니다")
            self.result_title.setText("신고 메시지")
        else:
            self.result_meta.setText(f"게임 종료 후 자동으로 열림 · {game_title(result.session_id)}")
            self.result_title.setText(f"나에게 욕설한 유저 {len(self.users)}명")
        if not self.users:
            empty = QVBoxLayout(self.result_content)
            empty.setContentsMargins(0, 0, 0, 0)
            empty.addWidget(
                label(
                    "이번 게임에서 신고할 채팅이 없습니다."
                    if result
                    else "게임이 끝나면 가려졌던 메시지와 신고 메시지가 여기에 표시됩니다.",
                    "muted",
                )
            )
            return
        body = QHBoxLayout(self.result_content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(20)
        side = QWidget()
        side.setFixedWidth(260)
        cards = QVBoxLayout(side)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(8)
        self.user_cards: list[SelectCard] = []
        for speaker, (rep, comp) in self.users.items():
            cards.addWidget(self._user_card(speaker, rep, comp))
        cards.addStretch()
        body.addWidget(side)

        detail = QVBoxLayout()
        detail.setSpacing(14)
        detail.addWidget(heading("원문 기록", "게임 중에는 가려졌던 메시지"))
        self.raw_log = label("", "rawLog")
        self.raw_log.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        detail.addWidget(self.raw_log)
        caption = label("생성된 신고 메시지", "label")
        detail.addWidget(caption)
        self.message = QPlainTextEdit()
        self.message.setReadOnly(True)
        self.message.setMinimumHeight(160)
        caption.setBuddy(self.message)
        detail.addWidget(self.message)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.btn_copy = button("신고 메시지 복사", "primary")
        self.btn_copy.setMinimumHeight(44)
        self.btn_copy.clicked.connect(self.copy_report)
        actions.addWidget(self.btn_copy)
        actions.addWidget(label("게임 내 신고창에 붙여넣기", "caption"))
        actions.addStretch()
        self.btn_complaint = button("고소장 만들기 →", "danger")
        self.btn_complaint.setMinimumHeight(44)
        self.btn_complaint.clicked.connect(lambda: self.open_editor(self.users[self.selected][1]))
        actions.addWidget(self.btn_complaint)
        detail.addLayout(actions)
        body.addLayout(detail, 1)
        self.user_cards[0].click()

    def _user_card(self, speaker: str, rep: ReportDraft | None, comp: ReportDraft | None) -> SelectCard:
        draft = rep or comp
        card_button = SelectCard(f"{speaker} 신고 대상 선택")
        self.user_cards.append(card_button)
        inner = QVBoxLayout(card_button)
        inner.setContentsMargins(14, 12, 14, 12)
        inner.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(label(draft.speaker, "value"), 1)
        top.addWidget(label("수위 높음" if comp else "보통", "badgeHigh" if comp else "badgeNormal"))
        inner.addLayout(top)
        champion = draft.champion or next((m.champion for m in draft.evidence if m.champion), "")
        count = f"욕설 {len(draft.incident_ids)}건"
        inner.addWidget(label(f"{champion} · {count}" if champion else count, "caption"))
        card_button.clicked.connect(lambda: self._select_user(speaker))
        return card_button

    def _select_user(self, speaker: str) -> None:
        self.selected = speaker
        for card_widget in self.user_cards:
            card_widget.setChecked(card_widget.accessibleName() == f"{speaker} 신고 대상 선택")
        rep, comp = self.users[speaker]
        draft = rep or comp
        self.raw_log.setText("\n".join(quote(msg) for msg in draft.evidence) or "저장된 원문이 없습니다.")
        self.message.setPlainText(draft.text)
        self.btn_copy.setText("신고 메시지 복사")
        self.btn_complaint.setVisible(comp is not None)

    def copy_report(self) -> None:
        QApplication.clipboard().setText(self.message.toPlainText())
        self.btn_copy.setText("복사됨 ✓")
        self.notify(f"신고 메시지를 복사했습니다 · {self.selected}")

    # ── 설정 ──────────────────────────────────────────────────
    def _build_settings(self, preferences: QVBoxLayout) -> None:
        preferences.addWidget(label("설정", "title"))
        settings_card, fields = card("플레이어 설정")
        preferences.addWidget(settings_card)
        fields.addWidget(label("내 소환사명", "caption"))
        self.my_name = QLineEdit()
        self.my_name.setPlaceholderText("게임에 표시되는 닉네임")
        fields.addWidget(self.my_name)
        fields.addWidget(label("필터 강도", "caption"))
        checks = QHBoxLayout()
        checks.setSpacing(20)
        self.strength_checks = QButtonGroup(self)  # 한 번에 하나만 체크된다
        for index, (caption, _) in enumerate(STRENGTHS):
            check = QCheckBox(caption)
            check.setCursor(Qt.PointingHandCursor)
            self.strength_checks.addButton(check, index)
            checks.addWidget(check)
        checks.addStretch()
        fields.addLayout(checks)
        self.strength_buttons.idClicked.connect(self._pick_strength)
        self.strength_checks.idClicked.connect(self._pick_strength)
        self.set_strength("normal")
        fields.addWidget(
            label(
                "낮음은 가벼운 혼잣말을 표시하고, 보통은 비속어만 가립니다. 높음은 가벼운 비속어도 줄 전체를 숨깁니다. "
                "시스템 메시지는 모든 강도에서 표시됩니다.",
                "muted",
            )
        )

        self._build_llm_card(preferences)

    def _build_llm_card(self, preferences: QVBoxLayout) -> None:
        ai_card, ai = card("AI 순화·고소장 초안 (선택)")
        preferences.addWidget(ai_card)
        ai.addWidget(label("Gemini API 키", "caption"))
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self.llm_key = QLineEdit()
        self.llm_key.setEchoMode(QLineEdit.Password)
        self.llm_key.setAccessibleName("Gemini API 키")
        self.btn_key_show = button("보기")
        self.btn_key_show.setCheckable(True)
        self.btn_key_show.toggled.connect(self._toggle_key)
        key_row.addWidget(self.llm_key, 1)
        key_row.addWidget(self.btn_key_show)
        ai.addLayout(key_row)
        self._fix_width(self.btn_key_show, ("숨기기", "보기"))  # 글자가 바뀌어도 입력칸 폭이 흔들리지 않게
        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.btn_llm_save = button("저장", "primary")
        self.btn_llm_clear = button("지우기", "link")
        self.llm_status = label("", "muted")
        actions.addWidget(self.btn_llm_save)
        actions.addWidget(self.btn_llm_clear)
        actions.addWidget(self.llm_status, 1)
        ai.addLayout(actions)
        ai.addWidget(
            label(
                "키는 이 PC의 사용자 폴더에만 저장되고 화면·로그에 전체가 표시되지 않습니다. 모델은 앱이 정해 둔 것을 씁니다. "
                "비워 두면 외부 AI 없이 로컬 규칙으로 순화하고 초안을 만듭니다.",
                "muted",
            )
        )
        self.llm_key.textChanged.connect(self._llm_inputs_changed)
        self.btn_llm_save.clicked.connect(self._request_llm_save)
        self.btn_llm_clear.clicked.connect(self.llm_clear_requested.emit)
        self.set_llm_state("")

    def set_llm_state(self, api_key: str) -> None:
        """저장된 키를 보여 준다. 키는 입력칸에 다시 채우지 않고 끝 4자리만 표시한다."""
        self._llm_saved = api_key
        self.llm_key.clear()
        self.btn_key_show.setChecked(False)
        masked = mask_key(api_key)
        self.llm_key.setPlaceholderText(f"저장됨 {masked} · 바꾸려면 새 키 입력" if api_key else "API 키 붙여넣기")
        self.llm_status.setText(f"사용 중 · 키 {masked}" if api_key else "설정 안 됨 · 로컬 규칙만 사용")
        self.btn_llm_clear.setVisible(bool(api_key))
        self._llm_inputs_changed()

    def _llm_inputs_changed(self) -> None:
        api_key = self.llm_key.text().strip()
        self.btn_llm_save.setEnabled(bool(api_key) and api_key != self._llm_saved)

    def _request_llm_save(self) -> None:
        if self.btn_llm_save.isEnabled():
            self.llm_save_requested.emit(self.llm_key.text().strip())

    @staticmethod
    def _fix_width(widget: QPushButton, texts: tuple[str, ...]) -> None:
        """여러 글자 중 가장 넓은 폭으로 고정한다. 마지막 글자가 처음 표시된다."""
        widget.ensurePolished()
        widths = []
        for text in texts:
            widget.setText(text)
            widths.append(widget.sizeHint().width())
        widget.setFixedWidth(max(widths))

    def _toggle_key(self, shown: bool) -> None:
        self.llm_key.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)
        self.btn_key_show.setText("숨기기" if shown else "보기")

    def strength_value(self) -> str:
        return STRENGTHS[max(0, self.strength_checks.checkedId())][1]

    def set_strength(self, value: str) -> None:
        """홈의 알약 버튼과 설정의 체크박스를 같은 값으로 맞춘다. 모르는 값이면 보통."""
        index = next((i for i, (_, v) in enumerate(STRENGTHS) if v == value), 1)
        self.strength_buttons.button(index).setChecked(True)
        self.strength_checks.button(index).setChecked(True)

    def _pick_strength(self, index: int) -> None:
        self.set_strength(STRENGTHS[index][1])
        self.strength_changed.emit(STRENGTHS[index][1])

    # ── 공통 ──────────────────────────────────────────────────
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
    def _preview_toggled(self, shown: bool) -> None:
        self.preview_count = 0
        self.preview_info.setText("캡처 미리보기" if shown else "미리보기 꺼짐 · 채팅은 계속 읽습니다")
        self.preview_image.clear()  # 꺼면 마지막 이미지도 지운다
        if shown:
            self.preview_image.setText("캡처 대기 중")

    def show_preview(self, image: QImage) -> None:
        if not self.preview_toggle.isChecked():
            return
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
        self.game_state.setText(PHASE_TEXT[phase])
        if phase == GamePhase.POST_GAME and session and session.id != self.current_result:
            self._render_result(None)
            self.open_editor(None, navigate=False)
        self.pages.setCurrentWidget(self._page_for[phase])

    def add_incident(self, inc: Incident) -> None:
        self.live.addItem(f"{inc.msg.speaker} · {inc.decision.display_text or '숨김'}")
        if self.live.count() > 200:
            self.live.takeItem(0)

    # ── 최근 게임 기록 ────────────────────────────────────────
    def _load_history(self) -> None:
        if self.history_path is None:
            self._refresh_history()
            return
        try:
            saved = self.history_format.validate_json(self.history_path.read_bytes())
        except FileNotFoundError:
            self._refresh_history()
            return
        except (OSError, ValidationError):
            self._refresh_history()
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
        old = self.history_body
        self.history_layout.removeWidget(old)
        old.hide()
        old.deleteLater()
        self.history_body = QWidget()
        rows = QVBoxLayout(self.history_body)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        self.history_layout.addWidget(self.history_body)
        if not self.results:
            rows.addWidget(self._table_row(["완료된 게임이 없습니다.", "–", "–", label("기록 없음", "caption")]))
            return
        for key in reversed(self.results):
            result = self.results[key]
            if result.reports or result.complaints:
                action = button("신고 메시지 보기 →", "link")
                action.setStyleSheet("font-size:13px;font-weight:500;")
                action.setAccessibleName(f"{game_title(key)} 신고 메시지 보기")
                action.clicked.connect(lambda _, k=key: self.open_result(k))
            else:
                action = label("기록 없음", "caption")
            reports = f"{len(result.reports)}명" if result.reports else "–"
            complaints = f"{len(result.complaints)}건" if result.complaints else "–"
            rows.addWidget(self._table_row([game_title(key), reports, complaints, action]))

    def open_result(self, session_id: str) -> None:
        result = self.results[session_id]
        self.current_result = session_id
        self._render_result(result)
        self.open_editor(result.complaints[0] if result.complaints else None, navigate=False)
        self.pages.setCurrentIndex(1)

    # ── 고소장 ────────────────────────────────────────────────
    def open_editor(self, draft: ReportDraft | None, navigate: bool = True) -> None:
        if self.editor.draft is not draft:
            old = self.editor
            self.editor_layout.removeWidget(old)
            old.hide()
            old.deleteLater()
            game = game_title(self.current_result) if self.current_result and draft else ""
            self.editor = ComplaintEditor(draft, game)
            self.editor.notice.connect(self.notify)
            self.editor.back.connect(lambda: self.pages.setCurrentIndex(1))
            if draft:
                self.editor.saved.connect(lambda path: self._saved(draft, path))
                self.editor.open_pdf.connect(lambda: self.open_pdf(draft))
            self.editor_layout.addWidget(self.editor)
        if navigate:
            self.pages.setCurrentIndex(2)

    def _saved(self, draft: ReportDraft, path: str) -> None:
        draft.pdf_path = path
        self._save_history()

    def open_pdf(self, draft: ReportDraft) -> None:
        path = resolve_repo_path(draft.pdf_path or "")
        if not draft.pdf_path or not path.is_file():
            self.notify("저장된 PDF를 찾을 수 없습니다. 초안에서 다시 저장하세요.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
            self.notify(
                "저장 폴더에서 PDF를 선택해 다른 앱으로 여세요." if opened else f"PDF를 열 수 없습니다 · {path}"
            )

    def show_engine_error(self, message: str) -> None:
        self.statusBar().showMessage(message)
        self.game_label.setText(f"멈춤 · {message}")
        self.set_status("멈춤", message)
