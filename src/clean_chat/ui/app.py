"""[뼈대 · ui 담당] 앱 조립: QApplication + Engine + 창 2개 연결.  `uv run clean-chat app ...` 이 호출."""

import sys

from PySide6.QtWidgets import QApplication

from clean_chat.core.engine import Engine
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.schemas import Incident
from clean_chat.core.sources import FrameSource, LineSource, PhaseDetector
from clean_chat.ui import win32
from clean_chat.ui.bridge import EngineBridge
from clean_chat.ui.client import ClientWindow
from clean_chat.ui.overlay import OverlayWindow


def run_app(pipelines: Pipelines, source: LineSource | FrameSource, detector: PhaseDetector) -> int:
    qt = QApplication(sys.argv)
    engine = Engine(pipelines, source, detector)
    bridge = EngineBridge(engine)
    client = ClientWindow()

    def on_self_input(text: str) -> Incident:
        return pipelines.outgoing.submit(text)  # 흐름 B (동기 요청-응답)

    overlay = OverlayWindow(on_self_input)
    bridge.incident.connect(client.add_incident)
    bridge.incident.connect(overlay.show_incident)
    try:
        win32.exclude_from_capture(overlay)
    except NotImplementedError:
        print("⚠️ 캡처 제외 미구현 (OPEN-02)")
    client.show()
    overlay.resize(420, 260)
    overlay.show()
    engine.start()  # TODO: 클라이언트의 '감시 시작' 버튼으로 옮기기
    code = qt.exec()
    engine.stop()
    return code
