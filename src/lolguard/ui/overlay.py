"""[뼈대 · ui 담당] 오버레이 창 (SPEC 3-2): 게임 채팅창을 가리고 필터된 채팅 표시 + 내 채팅 입력

구성:
  - 투명·테두리 없음·항상 위 (Mac에서도 화면 개발 가능)
  - 보정 모드: 드래그로 위치·크기 조정 → Region 저장 (capture 영역과 같은 값)
  - 채팅 목록: Decision.display_text 만 표시 (HIDE/BLOCK 은 표시 안 함)
  - 입력칸: Enter → on_self_input 콜백 → 결과를 클립보드에 복사 + 안내 (ADR-0006)
  - Windows: win32.exclude_from_capture(self) 로 캡처 제외 (ADR-0003)
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QListWidget, QVBoxLayout, QWidget

from lolguard.core.schemas import Incident, Region


class OverlayWindow(QWidget):
    def __init__(self, on_self_input: Callable[[str], Incident | None]) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.on_self_input = on_self_input
        lay = QVBoxLayout(self)
        self.chat = QListWidget()
        self.input = QLineEdit(placeholderText="채팅 입력 → 필터 후 클립보드 복사")
        lay.addWidget(self.chat)
        lay.addWidget(self.input)
        self.input.returnPressed.connect(self._submit)
        # TODO: 반투명 배경 스타일, 보정 모드(드래그/리사이즈), 클릭 통과 영역

    def show_incident(self, inc: Incident) -> None:
        if inc.decision.display_text is not None and not inc.msg.is_me:
            self.chat.addItem(f"{inc.msg.speaker or ''}: {inc.decision.display_text}")

    def _submit(self) -> None:
        text = self.input.text().strip()
        self.input.clear()
        inc = self.on_self_input(text) if text else None
        # TODO: inc.decision.action 이 copy* 면 클립보드 복사 + 안내, block 이면 경고 표시
        _ = inc

    def region(self) -> Region:
        g = self.geometry()
        return Region(x=g.x(), y=g.y(), w=g.width(), h=g.height())
