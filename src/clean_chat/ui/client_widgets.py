"""클라이언트 전용 라이트 테마와 공통 위젯. 색·크기는 클라이언트 목업(와이어프레임)을 따른다."""

import tempfile
from html import escape
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QKeyEvent, QKeySequence, QMouseEvent, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

ACCENT = "#2457D6"
MUTED = "#5B636E"
DANGER = "#B4441A"

STYLE = """
QMainWindow, QWidget {background:#FFFFFF;color:#1A1D21;font-size:14px;}
QWidget#rail {background:#F7F8FA;border-right:1px solid #DDE1E6;}
QLabel, QCheckBox {background:transparent;}
QCheckBox {spacing:6px;}
QCheckBox::indicator {width:14px;height:14px;border:1px solid #8A919B;border-radius:3px;background:white;}
QCheckBox::indicator:checked {background:#2457D6;border:1px solid #2457D6;image:url(CHECK_SVG);}
QLabel#title {font-weight:700;font-size:22px;}
QLabel#section {font-weight:700;font-size:15px;}
QLabel#label {font-weight:700;font-size:13px;}
QLabel#status {font-weight:700;font-size:20px;}
QLabel#value {font-weight:700;font-size:15px;}
QLabel#muted {color:#5B636E;font-size:13px;}
QLabel#caption {color:#5B636E;font-size:12px;}
QLabel#error {color:#B4441A;font-size:12px;font-weight:700;}
QLabel#hash {color:#5B636E;font-size:18px;font-weight:700;}
QLabel#rawLog {background:#F7F8FA;border:1px solid #DDE1E6;border-radius:8px;padding:12px 14px;
  font-family:Menlo,Consolas,monospace;font-size:13px;}
QLabel#badgeHigh {background:#FCE9E2;color:#B4441A;border-radius:9px;padding:2px 8px;font-size:11px;font-weight:700;}
QLabel#badgeNormal {background:#FFF3D6;color:#7A5300;border-radius:9px;padding:2px 8px;font-size:11px;font-weight:700;}
QLabel#warnTitle {color:#8F3412;font-size:15px;font-weight:700;}
QLabel#warnBody {color:#3F2A20;font-size:12px;}
QLabel#warnNo {color:#B4441A;font-weight:700;font-size:13px;}
QLabel#warnItem {font-size:13px;}
QLabel#tableHead {color:#5B636E;font-size:12px;}
QLabel#paperLabel {color:#5B636E;font-size:12px;}
QLabel#toast {background:#ecf6f0;color:#184832;border:1px solid #93bcaa;border-radius:8px;padding:10px 14px;}
QFrame#card {background:white;border:1px solid #DDE1E6;border-radius:10px;}
QFrame#hero {background:white;border:1px solid #C9CED6;border-radius:10px;}
QFrame#warning {background:#FDF3EE;border:1px solid #E8A27F;border-radius:10px;}
QFrame#warnRule {background:#F0C9B5;border:0;}
QFrame#table {background:white;border:1px solid #DDE1E6;border-radius:10px;}
QWidget#tableHeadRow {background:#F7F8FA;border-bottom:1px solid #DDE1E6;}
QWidget#tableRow {background:white;border-bottom:1px solid #EEF0F3;}
QFrame#chip {background:white;border:1px solid #C9CED6;border-radius:12px;}
QFrame#chip[on="true"] {background:#F3F6FD;border:1px solid #2457D6;}
QFrame#chip[on="true"]:disabled {background:#F3F6FD;border:1px solid #2457D6;}
QWidget#popoverWindow {background:transparent;}
QFrame#popover {background:#1A1D21;border-radius:12px;}
QFrame#popover QLabel {color:white;font-size:12px;}
QFrame#popover QLabel#popTitle {font-size:14px;font-weight:700;}
QFrame#popover QLabel#popLaw {color:#A9B1BC;font-size:11px;}
QPushButton {background:white;border:1px solid #C9CED6;border-radius:8px;padding:0 16px;min-height:36px;}
QPushButton:hover {background:#F3F6FD;border-color:#8A919B;}
QPushButton:focus {border:1px solid #2457D6;}
QPushButton#primary {background:#2457D6;color:white;border-color:#2457D6;font-weight:700;}
QPushButton#primary:hover {background:#1A3FA0;border-color:#1A3FA0;}
QPushButton#secondary {background:white;color:#1A1D21;border:1px solid #8A919B;font-weight:700;}
QPushButton#danger {background:white;color:#B4441A;border:1px solid #B4441A;font-weight:700;}
QPushButton#danger:hover {background:#FDF3EE;}
QPushButton[size="large"] {min-height:48px;min-width:160px;padding:0 22px;font-size:15px;}
QPushButton:disabled, QPushButton#primary:disabled, QPushButton#secondary:disabled
  {background:#EEF0F3;color:#5B636E;border:1px solid #C9CED6;}
QPushButton#link {border:0;background:transparent;color:#2457D6;padding:0;min-height:0;text-align:left;font-size:12px;}
QPushButton#link:hover {color:#1A3FA0;text-decoration:underline;}
QPushButton#nav {text-align:left;border:0;border-radius:6px;background:transparent;padding:10px 12px;min-height:0;}
QPushButton#nav:hover {background:#EEF0F3;}
QPushButton#nav:checked {background:#E3EAFB;color:#2457D6;font-weight:700;}
QPushButton#segment {border:1px solid #C9CED6;border-radius:11px;padding:4px 10px;min-height:0;font-size:12px;}
QPushButton#segment:checked {background:#2457D6;color:white;border-color:#2457D6;}
QFrame#userCard {border:1px solid #DDE1E6;border-radius:8px;background:white;}
QFrame#userCard[on="true"] {border:2px solid #2457D6;background:#F3F6FD;}
QFrame#userCard:focus {border:2px solid #8A919B;}
QFrame#userCard[on="true"]:focus {border:2px solid #2457D6;}
QPushButton#info {border:0;background:transparent;border-radius:11px;padding:0;min-height:0;}
QPushButton#info:hover {background:#E3EAFB;}
QPushButton#popClose {border:0;background:transparent;color:#C9CED6;font-size:16px;padding:0;min-height:0;}
QLineEdit {background:white;border:1px solid #C9CED6;border-radius:6px;padding:0 12px;min-height:38px;
  selection-background-color:#2457D6;selection-color:white;}
QLineEdit[invalid="true"] {border:2px solid #B4441A;}
QPlainTextEdit, QListWidget, QTextBrowser, QComboBox {background:white;color:#1A1D21;border:1px solid #C9CED6;
  border-radius:8px;padding:6px;selection-background-color:#2457D6;selection-color:white;}
QPlainTextEdit {padding:8px 10px;font-size:13px;}
QTextBrowser#paper {background:white;border:1px solid #C9CED6;border-radius:0;padding:20px 18px;}
QScrollArea {border:0;} QStatusBar {color:#5B636E;background:#F7F8FA;}
"""


def _check_mark() -> str:
    """체크박스의 흰 체크 표시. Qt 스타일시트 image 는 파일 경로만 받아서 임시 폴더에 한 번 쓴다."""
    path = Path(tempfile.gettempdir()) / "clean-chat-check.svg"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
        '<path d="M3 7.2 5.8 10 11 4" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )
    try:
        if not path.is_file() or path.read_text() != svg:
            path.write_text(svg)
    except OSError:
        return ""
    return path.as_posix()


STYLE = STYLE.replace("image:url(CHECK_SVG);", f"image:url({_check_mark()});" if _check_mark() else "")


def label(text: str, role: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    widget.setObjectName(role)
    return widget


def rich(html: str, role: str = "") -> QLabel:
    widget = QLabel(html)
    widget.setTextFormat(Qt.RichText)
    widget.setWordWrap(True)
    widget.setObjectName(role)
    return widget


def heading(title: str, note: str = "") -> QLabel:
    """목업의 '원문 기록 · 게임 중에는 가려졌던 메시지'처럼 굵은 제목 + 흐린 설명 한 줄."""
    extra = f"<span style='font-weight:400;color:{MUTED}'> · {escape(note)}</span>" if note else ""
    return rich(f"<b>{escape(title)}</b>{extra}", "label")


def restyle(widget: QWidget, role: str | None = None, **props: object) -> None:
    """objectName·동적 속성을 바꾼 뒤 스타일시트를 다시 적용한다."""
    if role is not None:
        widget.setObjectName(role)
    for key, value in props.items():
        widget.setProperty(key, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def button(text: str, role: str = "", large: bool = False) -> QPushButton:
    widget = QPushButton(text)
    widget.setObjectName(role)
    widget.setCursor(Qt.PointingHandCursor)
    if large:
        widget.setProperty("size", "large")
    return widget


def card(title: str = "", role: str = "card") -> tuple[QFrame, QVBoxLayout]:
    widget = QFrame()
    widget.setObjectName(role)
    widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(6)
    if title:
        layout.addWidget(label(title, "section"))
    return widget, layout


def scroll_page(margins: tuple[int, int, int, int] = (32, 28, 32, 28)) -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(*margins)
    layout.setAlignment(Qt.AlignTop)
    layout.setSpacing(20)
    scroll.setWidget(body)
    return scroll, layout


def stroke_icon(paths: str, color: str = "#395777", size: int = 24) -> QIcon:
    pixmap = QPixmap()
    pixmap.loadFromData(
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size * 2}" height="{size * 2}" viewBox="0 0 {size} {size}">'
            f'<g fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
            f"{paths}</g></svg>"
        ).encode(),
        "SVG",
    )
    return QIcon(pixmap)


INFO_ICON = (
    '<circle cx="8" cy="8" r="6.5"/><path d="M8 7.2v4"/><circle cx="8" cy="4.9" r="0.6" fill="{c}" stroke="none"/>'
)
WARN_ICON = (
    '<path d="M9 2 L16.5 15.5 H1.5 Z"/><path d="M9 7v4"/><circle cx="9" cy="13.2" r="0.7" fill="{c}" stroke="none"/>'
)


def warn_icon() -> QLabel:
    widget = QLabel()
    widget.setPixmap(stroke_icon(WARN_ICON.format(c=DANGER), DANGER, 18).pixmap(18, 18))
    widget.setFixedSize(18, 18)
    return widget


def pop_text(html: str, role: str = "") -> QLabel:
    """팝오버 본문. 줄 간격을 넉넉하게(160%) 잡아 촘촘해 보이지 않게 한다."""
    return rich(f"<p style='margin:0;line-height:160%'>{html}</p>", role)


def info_button(title: str, body: str | list[QLabel], color: str = MUTED) -> QPushButton:
    """(i) 아이콘을 누르면 어두운 설명 팝오버를 연다. body 는 본문 문자열 또는 미리 만든 라벨 목록."""
    btn = QPushButton()
    btn.setObjectName("info")
    btn.setIcon(stroke_icon(INFO_ICON.format(c=color), color, 16))
    btn.setIconSize(QSize(16, 16))
    btn.setFixedSize(24, 24)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setAccessibleName(f"{title} 설명 보기")
    btn.setToolTip(f"{title} 설명")
    # 창은 투명하게 두고 안쪽 프레임만 둥글게 칠해야 모서리가 각지지 않는다.
    popup = QWidget(btn, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    popup.setObjectName("popoverWindow")
    popup.setAttribute(Qt.WA_TranslucentBackground)
    popup.setStyleSheet(STYLE)
    outer = QVBoxLayout(popup)
    outer.setContentsMargins(0, 0, 0, 0)
    panel = QFrame()
    panel.setObjectName("popover")
    outer.addWidget(panel)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(20, 16, 20, 18)
    layout.setSpacing(10)
    width, pad = 340, 20
    head = QHBoxLayout()
    head.setSpacing(12)
    caption = label(title, "popTitle")
    caption.setFixedWidth(width - 2 * pad - 12 - 24)
    head.addWidget(caption, 1)
    close = QPushButton("×")
    close.setObjectName("popClose")
    close.setFixedSize(24, 24)
    close.setAccessibleName("닫기")
    close.clicked.connect(popup.close)
    head.addWidget(close, 0, Qt.AlignTop)
    layout.addLayout(head)
    for line in [pop_text(escape(body))] if isinstance(body, str) else body:
        # 줄바꿈 높이를 실제 너비로 계산하게 해 문단 사이가 들쭉날쭉 벌어지지 않게 한다.
        line.setFixedWidth(width - 2 * pad)
        line.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        layout.addWidget(line)
    popup.setFixedWidth(width)
    QShortcut(QKeySequence(Qt.Key_Escape), popup, activated=popup.close)

    def show_popup() -> None:
        point = btn.mapToGlobal(btn.rect().bottomLeft())
        screen = QGuiApplication.screenAt(point) or btn.screen()
        bounds = screen.availableGeometry()
        popup.adjustSize()
        x = max(bounds.left(), min(point.x(), bounds.right() - popup.width() + 1))
        y = point.y() + 6
        if y + popup.height() > bounds.bottom():
            y = point.y() - btn.height() - popup.height()
        popup.move(x, max(bounds.top(), y))
        popup.show()
        close.setFocus()

    btn.clicked.connect(show_popup)
    btn.popup = popup
    return btn


class SelectCard(QFrame):
    """목업의 신고 대상 카드. 누르거나 Space/Enter 로 선택한다 (선택 상태는 on 속성)."""

    clicked = Signal()

    def __init__(self, accessible_name: str) -> None:
        super().__init__()
        self.setObjectName("userCard")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(accessible_name)
        self.setChecked(False)

    def isChecked(self) -> bool:  # noqa: N802 (QAbstractButton 과 같은 이름)
        return self.property("on") == "true"

    def setChecked(self, on: bool) -> None:  # noqa: N802
        restyle(self, on="true" if on else "false")

    def click(self) -> None:
        self.clicked.emit()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.click()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.click()
        else:
            super().keyPressEvent(event)


class FlowLayout(QLayout):
    """목업의 flex-wrap 처럼 폭이 모자라면 다음 줄로 넘기는 레이아웃."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802 (Qt 이름)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._place(QRect(0, 0, width, 0), move=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._place(rect, move=True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _place(self, rect: QRect, move: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x, y, line = rect.x(), y + line + self._spacing, 0
            if move:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line = max(line, hint.height())
        return y + line - rect.y()
