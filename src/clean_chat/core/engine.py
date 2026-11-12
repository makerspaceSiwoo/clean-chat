"""백그라운드 실행기: 소스 → 파이프라인 → 구독자(UI/콘솔/저장소).

UI 스레드를 막지 않도록 별도 스레드에서 돈다. UI는 subscribe()로 결과를 받는다.
(웹 비유: Web Worker가 처리하고 postMessage로 화면에 전달)
Qt에서는 ui/bridge.py 가 이 콜백을 Qt signal로 바꿔 메인 스레드로 넘긴다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from clean_chat.core.pipeline import Pipelines
from clean_chat.core.schemas import Incident
from clean_chat.core.sources import FrameSource, LineSource

Listener = Callable[[Incident], None]


class Engine:
    def __init__(self, pipelines: Pipelines, source: LineSource | FrameSource) -> None:
        self.pipelines, self.source = pipelines, source
        self._listeners: list[Listener] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def subscribe(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def _emit(self, inc: Incident) -> None:
        for fn in self._listeners:
            fn(inc)

    def _loop(self) -> None:
        self.pipelines.setup()
        try:
            if hasattr(self.source, "frames"):
                for frame in self.source.frames():
                    if self._stop.is_set():
                        break
                    for inc in self.pipelines.incoming.process_frame(frame):
                        self._emit(inc)
            else:
                for line in self.source.lines():
                    if self._stop.is_set():
                        break
                    if inc := self.pipelines.incoming.process_line(line):
                        self._emit(inc)
        finally:
            self.pipelines.close()

    def start(self, block: bool = False) -> None:
        if block:
            self._loop()
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
