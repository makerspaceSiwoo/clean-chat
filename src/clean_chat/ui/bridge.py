"""[동작 · ui] 백그라운드 스레드 결과 → Qt 메인 스레드로 전달하는 다리 (패턴: Observer → Qt Signal).

Qt 규칙: 화면은 메인 스레드에서만 바꿀 수 있다 → 콜백을 Signal로 바꿔서 넘긴다.
- EngineBridge: Engine(흐름 A, 단계, 게임 결과) 콜백 → Signal
- OutgoingRunner: 흐름 B(내 입력)를 작업 스레드에서 실행하고 결과를 Signal 로 돌려준다
  (rewrite LLM 이 최대 3초 걸려도 오버레이가 멈추지 않게. 호출 방식은 여전히 요청 1개 → 결과 1개)
"""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from clean_chat.core.engine import Engine
from clean_chat.core.pipeline import OutgoingPipeline


class EngineBridge(QObject):
    incident = Signal(object)  # Incident (흐름 A 결과 1건)
    phase = Signal(object, object)  # GamePhase, GameSession | None
    result = Signal(object)  # PostGameResult (게임 종료 배치 처리 결과)
    error = Signal(str)  # 엔진이 시작하지 못함 (Stage 준비 실패 등)

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        engine.subscribe(self.incident.emit)  # 백그라운드 스레드에서 호출됨 → Qt가 메인 스레드로 전달
        engine.on_phase(self.phase.emit)
        engine.on_result(self.result.emit)
        engine.on_error(self.error.emit)


class OutgoingRunner(QObject):
    done = Signal(object)  # Incident (흐름 B 결과)
    failed = Signal(str)

    def __init__(self, outgoing: OutgoingPipeline) -> None:
        super().__init__()
        self.outgoing = outgoing
        self.pool = QThreadPool.globalInstance()

    def submit(self, text: str) -> None:
        self.pool.start(_OutgoingJob(self, text))


class _OutgoingJob(QRunnable):
    def __init__(self, runner: OutgoingRunner, text: str) -> None:
        super().__init__()
        self.runner, self.text = runner, text

    def run(self) -> None:
        try:
            self.runner.done.emit(self.runner.outgoing.submit(self.text))
        except Exception as e:  # 흐름 B 실패가 앱을 멈추지 않게
            self.runner.failed.emit(f"{type(e).__name__}: {e}")
