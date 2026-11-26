"""클라이언트 전용 라이트 테마와 공통 위젯."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

STYLE = """
QMainWindow, QWidget {background:#f5f7fa;color:#222e40;font-size:14px;}
QWidget#rail, QWidget#bar, QFrame#card, QFrame#popup {background:white;}
QWidget#rail {border-right:1px solid #dbe2ea;}
QWidget#bar {border-bottom:1px solid #dbe2ea;}
QLabel,QCheckBox {background:transparent;}
QLabel#brand {font-weight:700;font-size:21px;color:#204779;}
QLabel#title {font-weight:700;font-size:27px;}
QLabel#section {font-weight:650;font-size:16px;}
QLabel#muted {color:#52657a;font-size:13px;}
QLabel#charge {color:#204b9d;background:#edf3ff;border-radius:6px;padding:4px 8px;}
QFrame#card,QFrame#popup {border:1px solid #d5dfe9;border-radius:10px;}
QFrame#hero {background:#eef4ff;border:1px solid #c5d7f6;border-radius:10px;}
QFrame#warning {background:#fffbf1;border:1px solid #e9d7ac;border-radius:10px;}
QFrame#preview {background:#e9eef4;border:1px solid #d4deea;border-radius:11px;}
QLabel#breadcrumb {background:white;border-bottom:1px solid #dbe2ea;color:#58687b;}
QLabel#original {background:#f3f7fc;padding:12px;border-radius:7px;}
QPushButton#segment {padding:3px 7px;font-size:12px;} QPushButton#segment:checked {background:#e8effd;color:#2458bd;border-color:#a2b9e6;}
QPushButton {background:white;border:1px solid #bdcbdc;border-radius:6px;padding:5px 11px;}
QPushButton:hover {background:#edf3ff;border-color:#86a4d8;}
QPushButton:focus {border:1px solid #3469c6;}
QPushButton#primary {background:#2458bd;color:white;border-color:#2458bd;font-weight:650;}
QPushButton:disabled,QPushButton#primary:disabled {background:#e4e9f0;color:#697789;border-color:#d4dce7;}
QPushButton#nav {text-align:left;border:0;background:transparent;padding:10px 13px;}
QPushButton#nav:checked {background:#e8effd;color:#174fae;font-weight:650;}
QPushButton#toggle {text-align:left;border:0;background:transparent;font-weight:650;}
QPushButton#info {border-radius:10px;padding:0;color:#2458bd;}
QLineEdit,QListWidget,QTextBrowser,QComboBox {background:white;color:#222e40;border:1px solid #cad5e2;border-radius:6px;padding:5px;selection-background-color:#2458bd;selection-color:white;}
QTextBrowser#paper {background:#fffefa;padding:14px;}
QScrollArea {border:0;} QStatusBar {color:#40536a;background:#f5f7fa;}
QLabel#toast {background:#ecf6f0;color:#184832;border:1px solid #93bcaa;border-radius:8px;padding:10px 14px;}
"""


def label(text: str, role: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    widget.setObjectName(role)
    return widget


def card(title: str, role: str = "card") -> tuple[QFrame, QVBoxLayout]:
    widget = QFrame()
    widget.setObjectName(role)
    widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(16, 13, 16, 13)
    layout.setSpacing(8)
    layout.addWidget(label(title, "section"))
    return widget, layout


def scroll_page() -> tuple[QScrollArea, QSizePolicy, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(22, 16, 22, 16)
    layout.setAlignment(Qt.AlignTop)
    layout.setSpacing(12)
    scroll.setWidget(body)
    return scroll, layout


def info_button(title: str, help_text: str) -> QPushButton:
    button = QPushButton("ⓘ")
    button.setObjectName("info")
    button.setFixedSize(22, 22)
    button.setAccessibleName(f"{title} 설명")
    popup = QFrame(button, Qt.Popup)
    popup.setObjectName("popup")
    popup.setStyleSheet(STYLE)
    layout = QVBoxLayout(popup)
    head = QHBoxLayout()
    head.addWidget(label(title, "section"), 1)
    close = QPushButton("×")
    close.setAccessibleName("설명 닫기")
    close.clicked.connect(popup.close)
    head.addWidget(close)
    layout.addLayout(head)
    layout.addWidget(label(help_text))
    popup.setFixedWidth(275)
    QShortcut(QKeySequence(Qt.Key_Escape), popup, activated=popup.close)

    def show_popup() -> None:
        point = button.mapToGlobal(button.rect().bottomLeft())
        screen = QGuiApplication.screenAt(point) or button.screen()
        bounds = screen.availableGeometry()
        popup.adjustSize()
        x = max(bounds.left(), min(point.x(), bounds.right() - popup.width() + 1))
        y = point.y() + 4
        if y + popup.height() > bounds.bottom():
            y = point.y() - button.height() - popup.height()
        popup.move(x, max(bounds.top(), y))
        popup.show()
        close.setFocus()

    button.clicked.connect(show_popup)
    return button


def client_icon(name: str) -> QIcon:
    paths = {
        "brand": '<path fill="#2458bd" stroke="none" d="M12 1 22 5l-1 10q-2 5-9 8-7-3-9-8L2 5z"/><path stroke="white" d="m7 12 3 3 7-7"/>',
        "home": '<path d="m2 11 10-8 10 8M5 10v11h5v-7h4v7h5V10"/>',
        "reports": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
        "complaint": '<path d="M5 2h9l5 5v15H5zM14 2v6h5M8 12h8M8 16h6"/>',
        "settings": '<path d="M3 6h18M3 12h18M3 18h18"/><path stroke-width="4" d="M8 4v4m8 2v4m-6 2v4"/>',
        "clipboard": '<rect x="5" y="5" width="14" height="16" rx="2"/><rect fill="white" x="9" y="3" width="6" height="4" rx="1"/>',
    }
    pixmap = QPixmap()
    pixmap.loadFromData(
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24">'
            f'<g fill="none" stroke="#395777" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{paths[name]}</g></svg>'
        ).encode(),
        "SVG",
    )
    return QIcon(pixmap)


def overlay_diagram() -> QLabel:
    diagram = QLabel()
    pixmap = QPixmap()
    pixmap.loadFromData(
        b"""<svg xmlns="http://www.w3.org/2000/svg" width="156" height="96" viewBox="0 0 156 96">
        <defs><pattern id="stripe" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
        <rect width="12" height="12" fill="#d8e6ef"/><rect width="2" height="12" fill="#cbdde9"/></pattern></defs>
        <rect x="1" y="1" rx="5" width="154" height="94" fill="url(#stripe)" stroke="#9fb8d9" stroke-width="2"/>
        <rect x="10" y="51" width="72" height="34" rx="2" fill="white" stroke="#8da8c7"/>
        <path d="M17 58h54m-54 6h45m-45 6h51m-51 6h40" stroke="#a6b7c9" stroke-width="2.5"/></svg>""",
        "SVG",
    )
    diagram.setPixmap(pixmap)
    return diagram
