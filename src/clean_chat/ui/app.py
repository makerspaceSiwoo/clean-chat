"""[동작 · ui] 앱 조립: QApplication + Engine + 창 2개 연결.  `uv run clean-chat app ...` 이 호출.

연결 (패턴: 이벤트 발행·구독 + MVP 에 가까운 구조 — 창은 보여 주기만, 판단은 모듈·정책표)
  Engine 단계 신호  → 클라이언트 화면 전환 + 오버레이 표시(IN_GAME)/숨김(그 외)
  Engine 흐름 A     → 오버레이 채팅 목록 + 클라이언트 실시간 내역
  Engine 게임 결과   → 클라이언트 '이번 게임 결과' 화면
  오버레이 입력      → OutgoingRunner(작업 스레드에서 흐름 B) → 오버레이 결과 반영(클립보드/차단)
  결과 화면 '닫기'   → engine.dismiss_result() → IDLE
아직 구현되지 않은 화면 메서드(NotImplementedError)는 앱을 멈추지 않고 한 번만 안내한다.
"""

import functools
import sys
from collections.abc import Callable

from PySide6.QtWidgets import QApplication

from clean_chat.core.engine import Engine
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.schemas import GamePhase, GameSession
from clean_chat.core.sources import FrameSource, LineSource, PhaseDetector
from clean_chat.ui import win32
from clean_chat.ui.bridge import EngineBridge, OutgoingRunner
from clean_chat.ui.client import ClientWindow
from clean_chat.ui.overlay import OverlayWindow

_warned: set[str] = set()


def guard(fn: Callable) -> Callable:
    """미구현 화면 메서드를 Qt 슬롯에 연결해도 앱이 멈추지 않게 감싼다 (구현하면 그대로 동작)."""

    @functools.wraps(fn)
    def wrapper(*args):
        try:
            return fn(*args)
        except NotImplementedError as e:
            key = getattr(fn, "__qualname__", str(fn))
            if key not in _warned:
                _warned.add(key)
                print(f"⏳ 화면 미구현: {e}", file=sys.stderr)
            return None

    return wrapper


class App:
    """조립된 앱 (테스트에서도 같은 조립을 쓴다)."""

    def __init__(self, pipelines: Pipelines, source: LineSource | FrameSource, detector: PhaseDetector) -> None:
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.engine = Engine(pipelines, source, detector)
        self.bridge = EngineBridge(self.engine)
        self.outgoing = OutgoingRunner(pipelines.outgoing)
        self.client = ClientWindow()
        self.overlay = OverlayWindow(on_submit=self.outgoing.submit)
        self._connect()

    def _connect(self) -> None:
        client, overlay = self.client, self.overlay
        self.bridge.phase.connect(self.on_phase)
        self.bridge.incident.connect(guard(overlay.show_incident))
        self.bridge.incident.connect(guard(client.add_incident))
        self.bridge.result.connect(guard(client.show_result))
        self.bridge.error.connect(guard(client.show_engine_error))
        overlay.input.returnPressed.connect(guard(overlay.submit_input))
        self.outgoing.done.connect(guard(overlay.apply_outgoing))
        self.outgoing.failed.connect(guard(overlay.show_error))
        client.btn_copy_report.clicked.connect(guard(client.copy_selected_report))
        client.btn_open_complaint.clicked.connect(guard(client.open_selected_complaint))
        client.btn_close_result.clicked.connect(self.engine.dismiss_result)

    def on_phase(self, phase: GamePhase, session: GameSession | None) -> None:
        """단계 → 클라이언트 화면 전환, 오버레이는 게임 중에만 보임"""
        self.client.show_phase(phase, session)
        self.overlay.setVisible(phase == GamePhase.IN_GAME)
        if phase == GamePhase.IN_GAME:
            guard(self.overlay.clear_chat)()

    def show(self) -> None:
        try:
            win32.exclude_from_capture(self.overlay)
        except NotImplementedError:
            print("⚠️ 캡처 제외 미구현 (OPEN-02)", file=sys.stderr)
        self.client.show_phase(GamePhase.IDLE, None)
        self.client.show()
        self.overlay.resize(420, 260)
        self.overlay.hide()  # 게임이 시작되면(IN_GAME) 보인다


def run_app(pipelines: Pipelines, source: LineSource | FrameSource, detector: PhaseDetector) -> int:
    app = App(pipelines, source, detector)
    app.show()
    app.engine.start()  # 단계 감지기를 켠다. 채팅 캡처는 게임 중에만 돈다
    code = app.qt.exec()
    app.engine.stop()
    return code
