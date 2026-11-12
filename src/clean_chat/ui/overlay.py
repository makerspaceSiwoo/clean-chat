"""[뼈대 · WP7] 오버레이 창 (SPEC 3-2): 게임 채팅창을 가리고 필터된 채팅 표시 + 내 채팅 입력

- 게임 중(IN_GAME)에만 보인다. 표시/숨김은 app.py 가 단계 신호로 정한다.
- Decision.display_text 만 보여 주고 **판단하지 않는다** (MVP: 화면은 보여 주기만).
- Windows: win32.exclude_from_capture(self) 로 캡처 제외 (ADR-0003)
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QVBoxLayout, QWidget

from clean_chat.core.schemas import Incident, Region


class OverlayWindow(QWidget):
    def __init__(self, on_submit: Callable[[str], None]) -> None:
        """on_submit: 입력 문장을 흐름 B 로 보내는 함수 (app.py 가 OutgoingRunner.submit 을 넘김)."""
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.on_submit = on_submit
        lay = QVBoxLayout(self)
        self.chat = QListWidget()  # 필터된 채팅 목록
        self.notice = QLabel("")  # 복사됨 / 전송 차단 안내
        self.input = QLineEdit(placeholderText="채팅 입력 → 필터 후 클립보드 복사")
        lay.addWidget(self.chat)
        lay.addWidget(self.notice)
        lay.addWidget(self.input)

    def show_incident(self, inc: Incident) -> None:
        """흐름 A 결과 1건을 채팅 목록에 추가한다.

        입력: Incident → 화면: "화자: display_text" 한 줄
        예) show_rewritten "용 먼저 치자" → "원딜러: 용 먼저 치자" / hide → 아무것도 추가하지 않음
        주의: display_text 가 None 이면 표시하지 않는다. 판단하지 않고 Decision 만 따른다. 오래된 줄은 위에서 지운다.
        """
        raise NotImplementedError("ui 담당: show_incident")

    def submit_input(self) -> None:
        """입력칸 Enter: 텍스트를 읽고 비운 뒤 on_submit(text) 호출. 빈 문장은 무시. 처리 중 표시(notice)."""
        raise NotImplementedError("ui 담당: submit_input")

    def apply_outgoing(self, inc: Incident) -> None:
        """흐름 B 결과 반영 (ADR-0006: 가상 키 입력 없이 클립보드만).

        copy / copy_masked / copy_rewritten → display_text 를 클립보드에 복사 + "복사됨, 게임 채팅창에 붙여넣으세요"
        block → 클립보드는 그대로 두고 "이 문장은 보낼 수 없어요"
        예) "아 정글 ㅂㅅ 왜 안 와" → copy_rewritten "정글 합류 부탁해요" 복사
        """
        raise NotImplementedError("ui 담당: apply_outgoing")

    def show_error(self, message: str) -> None:
        """흐름 B 실패 안내 (예: "필터 처리 실패 — 다시 시도해 주세요")."""
        raise NotImplementedError("ui 담당: show_error")

    def clear_chat(self) -> None:
        """새 게임이 시작되면 이전 게임 채팅 목록을 비운다."""
        raise NotImplementedError("ui 담당: clear_chat")

    def start_calibration(self) -> None:
        """보정 모드: 드래그로 위치·크기를 맞춘다 → 끝나면 region() 을 설정에 저장 (capture 영역과 같은 값)."""
        raise NotImplementedError("ui 담당: start_calibration")

    def region(self) -> Region:
        """지금 오버레이 위치·크기 → Region (캡처 영역으로 씀)."""
        g = self.geometry()
        return Region(x=g.x(), y=g.y(), w=g.width(), h=g.height())
