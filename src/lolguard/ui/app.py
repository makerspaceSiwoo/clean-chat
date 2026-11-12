"""[뼈대 · ui 담당] 앱 조립: QApplication + Engine + 창 2개 연결.  `uv run lolguard app ...` 이 호출."""

import sys

from PySide6.QtWidgets import QApplication

from lolguard.core.engine import Engine
from lolguard.core.pipeline import Pipeline
from lolguard.core.schemas import Incident, RawLine, Source
from lolguard.core.sources import FrameSource, LineSource
from lolguard.ui import win32
from lolguard.ui.bridge import EngineBridge
from lolguard.ui.client import ClientWindow
from lolguard.ui.overlay import OverlayWindow


def run_app(pipeline: Pipeline, source: LineSource | FrameSource) -> int:
    qt = QApplication(sys.argv)
    engine = Engine(pipeline, source)
    bridge = EngineBridge(engine)
    client = ClientWindow()

    def on_self_input(text: str) -> Incident | None:
        import time
        import uuid

        line = RawLine(id=f"self-{uuid.uuid4().hex[:8]}", ts=time.time(), text=text, source=Source.SELF_INPUT)
        return pipeline.process_line(line)

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
