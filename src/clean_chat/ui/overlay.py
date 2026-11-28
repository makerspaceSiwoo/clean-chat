"""게임 채팅 전체를 덮는 불투명 오버레이. 잠그면 클릭이 게임으로 통과한다."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from clean_chat.core.schemas import Action, Incident, Level, Region


class OverlayWindow(QWidget):
    def __init__(self, on_submit: Callable[[str], None]) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Clean Chat 오버레이")
        self.setObjectName("chatOverlay")
        self.setStyleSheet(
            "#chatOverlay {background: #151923; color: white;} "
            "QListWidget {background: #151923; color: white; border: 0;} QLabel {color: white;}"
        )
        self.on_submit = on_submit
        self.setMinimumSize(140, 64)
        self.editing = True
        self.drag = None
        self.setMouseTracking(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self.handle = QLabel("드래그로 이동 · 가장자리로 크기 조절")
        self.handle.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.chat = QListWidget()
        self.chat.setWordWrap(True)
        self.chat.setFocusPolicy(Qt.NoFocus)
        self.notice = QLabel()
        self.input = QLineEdit(placeholderText="채팅 입력 → 필터 후 복사")
        for widget in (self.handle, self.chat, self.notice, self.input):
            layout.addWidget(widget)
        self.notice.hide()

    def set_editing(self, editing: bool) -> None:
        self.editing = editing
        self.drag = None
        self.handle.setVisible(editing)
        self.input.setVisible(editing)
        self.setWindowFlag(Qt.WindowTransparentForInput, not editing)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, not editing)
        self.show()
        if QApplication.platformName() == "cocoa":
            from clean_chat.ui.window_bounds import join_fullscreen_spaces

            join_fullscreen_spaces(int(self.winId()))

    def _edges(self, point):
        return (point.x() < 8, point.y() < 6, point.x() >= self.width() - 8, point.y() >= self.height() - 6)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.editing and event.button() == Qt.LeftButton:
            self.drag = (event.globalPosition().toPoint(), self.geometry(), self._edges(event.position()))
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        left, top, right, bottom = self._edges(event.position())
        if not self.drag:
            cursor = Qt.SizeAllCursor
            if (left and top) or (right and bottom):
                cursor = Qt.SizeFDiagCursor
            elif (left and bottom) or (right and top):
                cursor = Qt.SizeBDiagCursor
            elif left or right:
                cursor = Qt.SizeHorCursor
            elif top or bottom:
                cursor = Qt.SizeVerCursor
            self.setCursor(cursor)
            return
        origin, rect, edges = self.drag
        delta = event.globalPosition().toPoint() - origin
        bounds = rect.adjusted(0, 0, 0, 0)
        left, top, right, bottom = edges
        if left:
            bounds.setLeft(min(rect.left() + delta.x(), rect.right() - self.minimumWidth() + 1))
        if top:
            bounds.setTop(min(rect.top() + delta.y(), rect.bottom() - self.minimumHeight() + 1))
        if right:
            bounds.setWidth(max(self.minimumWidth(), rect.width() + delta.x()))
        if bottom:
            bounds.setHeight(max(self.minimumHeight(), rect.height() + delta.y()))
        if not any(edges):
            bounds.translate(delta)
        self.setGeometry(bounds)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.drag = None

    def append_row(self, order: int, text: str) -> None:
        # 늦게 도착한 순화 결과도 원래 콜 순서에 끼워 넣는다.
        index = self.chat.count()
        while index and self.chat.item(index - 1).data(Qt.UserRole) > order:
            index -= 1
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, order)
        self.chat.insertItem(index, item)
        if self.chat.count() > 100:
            self.chat.takeItem(0)
        self.chat.scrollToBottom()

    def show_incident(self, inc: Incident) -> None:
        if inc.decision.display_text:
            self.append_row(0, f"{inc.msg.speaker}: {inc.decision.display_text}")

    def submit_input(self) -> None:
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.on_submit(text)

    def apply_outgoing(self, inc: Incident | None) -> None:
        if not inc:
            return
        if inc.decision.action == Action.BLOCK:
            # L1(욕설뿐인 혼잣말)은 욕설을 빼면 남는 말이 없어서 복사할 것이 없다. L2 이상은 차단.
            mild = inc.analysis.level == Level.L1_MILD
            self.show_error("욕설을 빼면 보낼 내용이 없습니다." if mild else "전송이 차단되었습니다.")
        elif text := inc.decision.display_text:
            QApplication.clipboard().setText(text)
            self.show_error("복사했습니다. 게임에 직접 붙여넣으세요.")

    def show_error(self, message: str) -> None:
        self.notice.setText(message)
        self.notice.show()

    def clear_chat(self) -> None:
        self.chat.clear()
        self.notice.hide()
        self.input.clear()

    def region(self) -> Region:
        rect = self.geometry()
        return Region(x=rect.x(), y=rect.y(), w=rect.width(), h=rect.height())
