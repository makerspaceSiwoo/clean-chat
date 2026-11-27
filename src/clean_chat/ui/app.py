"""클라이언트·오버레이·엔진을 연결한다. 화면 변경은 Qt 이벤트 루프에서 처리한다."""

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Slot
from PySide6.QtWidgets import QApplication

from clean_chat.core.config import clear_llm_settings, current_llm_key, save_llm_settings, settings
from clean_chat.core.engine import Engine
from clean_chat.core.grabber import ScreenGrabber
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.schemas import GamePhase, GameSession
from clean_chat.core.sources import FrameSource, LineSource, PhaseDetector
from clean_chat.ui.bridge import EngineBridge, OutgoingRunner
from clean_chat.ui.client import ClientWindow
from clean_chat.ui.overlay import OverlayWindow


class App(QObject):
    def __init__(
        self,
        pipelines: Pipelines,
        source: LineSource | FrameSource,
        detector: PhaseDetector,
        history_path: Path | None = None,
    ) -> None:
        qt = QApplication.instance() or QApplication(sys.argv)
        super().__init__()
        self.qt = qt
        self.engine = Engine(pipelines, source, detector)
        self.bridge = EngineBridge(self.engine)
        self.outgoing = OutgoingRunner(pipelines.outgoing)
        self.client = ClientWindow(history_path)
        self.overlay = OverlayWindow(on_submit=self.outgoing.submit)
        self.preferences = QSettings("CleanChat", "Desktop")
        settings.my_name = self.preferences.value("player/name", settings.my_name, type=str)
        self.client.my_name.setText(settings.my_name)
        level = self.preferences.value("filter/strength", "normal", type=str)
        self.client.set_strength(level)
        settings.filter_strength = self.client.strength_value()
        self.client.strength_changed.connect(self.set_strength)
        self.client.my_name.editingFinished.connect(self.save_name)
        self.client.set_llm_state(current_llm_key(settings.llm_env))
        self.client.llm_save_requested.connect(self.save_llm)
        self.client.llm_clear_requested.connect(self.clear_llm)
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
            self.client.game_caption.setText("오버레이를 실행하고 위치를 잠그면 게임 창을 찾아 감시")
        else:
            self.client.preview_card.hide()
            self.client.btn_start.hide()
            self.client.btn_lock.hide()
            self.client.region_state.setText("데모 · 고정 위치")
            self.bridge.incident.connect(self.overlay.show_incident)
        self.bridge.phase.connect(self.on_phase)
        self.bridge.incident.connect(self.client.add_incident)
        self.bridge.result.connect(self.client.show_result)
        self.bridge.error.connect(self.on_error)
        self.overlay.input.returnPressed.connect(self.overlay.submit_input)
        self.outgoing.done.connect(self.overlay.apply_outgoing)
        self.outgoing.failed.connect(self.overlay.show_error)
        self.client.btn_close_result.clicked.connect(self.close_result)
        self.qt.aboutToQuit.connect(self.shutdown)
        self._refresh_status()

    @Slot()
    def save_name(self) -> None:
        settings.my_name = self.client.my_name.text().strip() or "나"
        self.preferences.setValue("player/name", settings.my_name)

    @Slot(str)
    def save_llm(self, api_key: str) -> None:
        try:
            save_llm_settings(api_key, settings.llm_env)
        except (OSError, ValueError) as exc:
            self.client.notify(f"AI 설정을 저장하지 못했습니다 · {exc}")
            return
        self.client.set_llm_state(current_llm_key(settings.llm_env))
        self.client.notify("AI 설정을 저장했습니다 · 바로 적용됩니다")

    @Slot()
    def clear_llm(self) -> None:
        try:
            clear_llm_settings(settings.llm_env)
        except OSError as exc:
            self.client.notify(f"AI 설정을 지우지 못했습니다 · {exc}")
            return
        self.client.set_llm_state(current_llm_key(settings.llm_env))
        self.client.notify("AI 설정을 지웠습니다 · 로컬 규칙만 사용합니다")

    @Slot()
    def set_strength(self) -> None:
        settings.filter_strength = self.client.strength_value()
        self.preferences.setValue("filter/strength", settings.filter_strength)

    @Slot()
    def close_result(self) -> None:
        if self.engine.phase == GamePhase.POST_GAME:
            self.engine.dismiss_result()
        else:
            self.client.pages.setCurrentIndex(0)

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
        self._refresh_status()

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
        self.save_name()
        self.sampler.preview_only = self.client.preview_only.isChecked()
        self.client.preview_only.setEnabled(False)
        if self.sampler.preview_only:
            self.client.pages.setCurrentWidget(self.client.preview_page)
        self.armed = True
        self.failure = ""
        self.overlay.clear_chat()
        self.client.live.clear()
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
        rect = self.overlay.geometry()
        state = "위치 조정 중" if editing else "맞춤 완료"
        self.client.region_state.setText(f"{state} · {rect.width()} × {rect.height()}")
        if editing:
            self._status("위치 조정 중 · 위치 잠금을 누르면 캡처를 시작합니다.")
        else:
            self.preferences.setValue("overlay/geometry", self.overlay.saveGeometry())
            self.sampler.start()
        self._refresh_status()

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
        self.client.region_state.setText("위치 조정 대기")
        self.client.btn_start.setEnabled(not self.session_started and self.engine.error is None)
        self.client.btn_lock.setEnabled(False)
        self._status("감시 중지")
        self._refresh_status()

    def _refresh_status(self) -> None:
        """홈의 '오버레이 채팅창' 카드 문구와 실행·잠금 버튼 모양을 지금 상태에 맞춘다."""
        c = self.client
        if not self.sampler:
            text = {
                GamePhase.IDLE: (
                    "데모 · 게임 대기",
                    "게임이 시작되면 채팅창 위에 오버레이가 뜨고, 끝나면 자동으로 닫힙니다.",
                ),
                GamePhase.IN_GAME: ("데모 · 게임 중", "시나리오 채팅을 필터링해 오버레이에 표시하고 있습니다."),
                GamePhase.POST_GAME: ("데모 · 게임 종료", "신고 메시지 화면에서 결과를 확인하세요."),
            }
            c.set_status(*text[self.engine.phase])
            return
        if self.failure:
            c.set_status("멈춤", f"{self.failure} · 오버레이를 종료한 뒤 다시 실행하세요.")
        elif not self.armed:
            c.set_status("중지됨", "오버레이를 실행하면 채팅창을 가리고, 위치를 잠그면 채팅 필터가 동작합니다.")
        elif self.overlay.editing:
            c.set_status(
                "실행 중 · 위치 조정",
                "오버레이를 드래그하고 가장자리로 크기를 맞춰 채팅 5~6줄을 모두 가린 뒤 위치 잠금을 누르세요.",
            )
        elif self.sampler.preview_only:
            c.set_status("실행 중 · 화면 미리보기", "OCR 없이 오버레이 아래 화면을 0.2초마다 확인합니다.")
        elif self.engine.phase == GamePhase.IN_GAME:
            c.set_status(
                "실행 중 · 게임 중", "채팅을 읽어 필터링하고 있습니다. 게임이 끝나면 오버레이가 자동으로 닫힙니다."
            )
        else:
            c.set_status(
                "실행 중 · 게임 대기",
                "게임이 시작되면 채팅창 위에 오버레이가 뜨고, 게임이 끝나면 자동으로 닫힙니다.",
            )
        c.set_overlay_state(self.armed, self.overlay.editing)

    @Slot(object, object)
    def on_phase(self, phase: GamePhase, session: GameSession | None) -> None:
        self.client.show_phase(phase, session)
        self._refresh_status()
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
    app = App(pipelines, source, detector, history_path=settings.store_dir / "recent-results.json")
    app.show()
    app.engine.start()
    try:
        return app.qt.exec()
    finally:
        app.shutdown()
