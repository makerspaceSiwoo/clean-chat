"""[뼈대 · ui 담당] Engine(백그라운드 스레드) 결과 → Qt 메인 스레드로 전달하는 다리.

Qt 규칙: 화면은 메인 스레드에서만 바꿀 수 있다 → 콜백을 Signal로 바꿔서 넘긴다.
"""

from PySide6.QtCore import QObject, Signal

from clean_chat.core.engine import Engine
from clean_chat.core.schemas import Incident


class EngineBridge(QObject):
    incident = Signal(object)  # Incident

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        engine.subscribe(self._on_incident)  # 백그라운드 스레드에서 호출됨

    def _on_incident(self, inc: Incident) -> None:
        self.incident.emit(inc)  # Qt가 메인 스레드로 안전하게 전달
