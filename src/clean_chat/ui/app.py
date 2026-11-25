"""클라이언트·오버레이·엔진을 연결한다. 화면 변경은 Qt 이벤트 루프에서 처리한다."""

import sys

from PySide6.QtCore import QObject, QSettings, Slot
from PySide6.QtWidgets import QApplication

from clean_chat.core.config import settings
from clean_chat.core.engine import Engine
from clean_chat.core.grabber import ScreenGrabber
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.schemas import GamePhase, GameSession
from clean_chat.core.sources import FrameSource, LineSource, PhaseDetector
from clean_chat.ui.bridge import EngineBridge, OutgoingRunner
from clean_chat.ui.client import ClientWindow
from clean_chat.ui.overlay import OverlayWindow


class App(QObject):
    def __init__(self, pipelines: Pipelines, source: LineSource | FrameSource, detector: PhaseDetector) -> None:
        qt = QApplication.instance() or QApplication(sys.argv)
        super().__init__()
        self.qt = qt
        self.engine = Engine(pipelines, source, detector)
        self.bridge = EngineBridge(self.engine)
        self.outgoing = OutgoingRunner(pipelines.outgoing)
        self.client = ClientWindow()
        self.overlay = OverlayWindow(on_submit=self.outgoing.submit)
        self.preferences = QSettings("CleanChat", "Desktop")
        self.client.my_name.setText(self.preferences.value("player/name", settings.my_name, type=str))
        self.sampler = None
        self.armed = False
        self.session_started = False
        self.failure = ""
        if isinstance(source, ScreenGrabber):
            from clean_chat.ui.capture import WindowSampler

            self.sampler = WindowSampler(source, self.overlay)
            self.sampler.preview.connect(self.client.show_preview)
            self.sampler.permission_needed.connect(self.client.show_capture_settings)
            self.sampler.status.connect(self._status)
            self.sampler.failed.connect(self.capture_failed)
            self.sampler.ended.connect(self.stop)
            self.client.btn_start.clicked.connect(self.toggle)
            self.client.btn_lock.clicked.connect(self.toggle_editing)
            self.bridge.row.connect(self.show_row)
        else:
            self.client.preview_only.hide()
            self.client.btn_start.hide()
            self.client.btn_lock.hide()
            self.bridge.incident.connect(self.overlay.show_incident)
        self.bridge.phase.connect(self.on_phase)
        self.bridge.incident.connect(self.client.add_incident)
        self.bridge.result.connect(self.client.show_result)
        self.bridge.error.connect(self.on_error)
        self.overlay.input.returnPressed.connect(self.overlay.submit_input)
        self.outgoing.done.connect(self.overlay.apply_outgoing)
        self.outgoing.failed.connect(self.overlay.show_error)
        self.client.btn_copy_report.clicked.connect(self.client.copy_selected_report)
        self.client.btn_open_complaint.clicked.connect(self.client.open_selected_complaint)
        self.client.btn_close_result.clicked.connect(self.engine.dismiss_result)
        self.qt.aboutToQuit.connect(self.shutdown)

    @Slot(str)
    def _status(self, text: str) -> None:
        if not self.failure:
            self.client.statusBar().showMessage(text)
            if self.armed and self.sampler and self.sampler.preview_only and not self.client.preview_count:
                self.client.preview_image.setText(text)

    @Slot(str)
    def capture_failed(self, text: str) -> None:
        # 실패해도 사용자가 중지하기 전에는 원문 가림막을 유지한다.
        self.failure = text
        self.client.show_engine_error(text)
        self.overlay.show_error("감시 중단 · 클라이언트에서 상태를 확인하세요.")

    @Slot(str)
    def on_error(self, text: str) -> None:
        if self.sampler and self.engine.error:
            self.sampler.stop()
            self.capture_failed(text)
            self.client.btn_lock.setEnabled(False)
        self.client.show_engine_error(text)

    @Slot(int, int, str)
    def show_row(self, generation: int, order: int, text: str) -> None:
        if self.armed and self.sampler.source.generation == generation:
            self.overlay.append_row(order, text)

    @Slot()
    def toggle(self) -> None:
        if self.armed:
            self.stop()
            return
        if self.engine.phase == GamePhase.POST_GAME and not self.engine.dismiss_result():
            return
        settings.my_name = self.client.my_name.text().strip() or "나"
        self.preferences.setValue("player/name", settings.my_name)
        self.sampler.preview_only = self.client.preview_only.isChecked()
        self.client.preview_only.setEnabled(False)
        if self.sampler.preview_only:
            self.client.pages.setCurrentWidget(self.client.preview_page)
        self.armed = True
        self.failure = ""
        self.overlay.clear_chat()
        self.client.live.clear()
        self.client.btn_start.setText("중지")
        self.client.btn_lock.setEnabled(True)
        self.set_editing(True)

    @Slot()
    def toggle_editing(self) -> None:
        if self.armed:
            self.set_editing(not self.overlay.editing)

    def set_editing(self, editing: bool) -> None:
        if editing:
            self.sampler.pause()
            self.failure = ""
        self.overlay.set_editing(editing)
        self.client.btn_lock.setText("위치 잠금" if editing else "위치 조정")
        if editing:
            self._status("위치 조정 중 · 위치 잠금을 누르면 캡처를 시작합니다.")
        else:
            self.preferences.setValue("overlay/geometry", self.overlay.saveGeometry())
            self.sampler.start()

    @Slot()
    def stop(self) -> None:
        self.armed = False
        if self.sampler:
            self.session_started |= self.sampler.source.running
            self.sampler.stop()
            self.client.preview_only.setEnabled(True)
            if self.sampler.preview_only:
                self.client.show_phase(self.engine.phase, None)
        self.overlay.hide()
        self.client.btn_start.setText("Clean Chat 시작")
        self.client.btn_start.setEnabled(not self.session_started and self.engine.error is None)
        self.client.btn_lock.setEnabled(False)
        self._status("감시 중지")

    @Slot(object, object)
    def on_phase(self, phase: GamePhase, session: GameSession | None) -> None:
        self.client.show_phase(phase, session)
        if not self.sampler:
            self.overlay.setVisible(phase == GamePhase.IN_GAME)
            if phase == GamePhase.IN_GAME:
                self.overlay.clear_chat()
        elif phase == GamePhase.IN_GAME:
            self.session_started = True
        elif phase == GamePhase.POST_GAME:
            self.session_started = False
            if not self.failure:
                self.stop()

    def show(self) -> None:
        self.client.show_phase(GamePhase.IDLE, None)
        self.client.show()
        self.overlay.resize(460, 160)
        geometry = self.preferences.value("overlay/geometry")
        if geometry is not None:
            self.overlay.restoreGeometry(geometry)
        else:
            screen = self.client.screen().availableGeometry()
            self.overlay.move(screen.x() + 20, screen.bottom() - self.overlay.height() - 40)

    @Slot()
    def shutdown(self) -> None:
        if self.sampler:
            self.sampler.stop()
        self.engine.stop()


def run_app(pipelines: Pipelines, source: LineSource | FrameSource, detector: PhaseDetector) -> int:
    app = App(pipelines, source, detector)
    app.show()
    app.engine.start()
    try:
        return app.qt.exec()
    finally:
        app.shutdown()
