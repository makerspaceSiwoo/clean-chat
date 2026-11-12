"""백그라운드 실행기: 단계 감지기 → 상태 기계 → (게임 중) 흐름 A → 구독자(UI/콘솔/저장소).

패턴: 상태(State) + 이벤트 발행·구독(Observer).
  - 감지기 스레드(엔진 스레드): PhaseEvent 를 받아 GameStateMachine 에 적용
  - 캡처 스레드: IN_GAME 동안만 소스 → IncomingPipeline → Incident 를 세션에 기록하고 발행
  - POST_GAME: 캡처를 멈추고 세션 저장 → PostGameBatch(신고 문구·고소장) → 결과 발행
UI 스레드를 막지 않도록 별도 스레드에서 돈다. UI는 subscribe/on_phase/on_result 로 결과를 받는다.
(웹 비유: Web Worker가 처리하고 postMessage로 화면에 전달. Qt에서는 ui/bridge.py 가 Signal로 바꿈)
"""

from __future__ import annotations

import sys
import threading
import traceback
from collections.abc import Callable

from clean_chat.core.game import GameStateMachine, MemorySessionRepository, PostGameBatch, SessionRepository
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.schemas import GamePhase, GameSession, Incident, PhaseEvent, PostGameResult
from clean_chat.core.sources import FrameSource, LineSource, PhaseDetector

IncidentListener = Callable[[Incident], None]
PhaseListener = Callable[[GamePhase, GameSession | None], None]
ResultListener = Callable[[PostGameResult], None]


class Engine:
    def __init__(
        self,
        pipelines: Pipelines,
        source: LineSource | FrameSource,
        detector: PhaseDetector,
        repository: SessionRepository | None = None,
    ) -> None:
        self.pipelines, self.source, self.detector = pipelines, source, detector
        self.repository = repository or MemorySessionRepository()
        self.machine = GameStateMachine()
        self.batch = PostGameBatch(pipelines.stages)
        self._incident_listeners: list[IncidentListener] = []
        self._phase_listeners: list[PhaseListener] = []
        self._result_listeners: list[ResultListener] = []
        self._stop = threading.Event()
        self._capture_stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._capture_thread: threading.Thread | None = None

    # ── 구독 (Observer) ──
    def subscribe(self, fn: IncidentListener) -> None:
        """흐름 A 결과(Incident) 1건마다 호출 (캡처 스레드)"""
        self._incident_listeners.append(fn)

    def on_phase(self, fn: PhaseListener) -> None:
        """단계가 바뀔 때마다 호출 (엔진 스레드 또는 dismiss 를 부른 스레드)"""
        self._phase_listeners.append(fn)

    def on_result(self, fn: ResultListener) -> None:
        """게임 종료 배치 처리가 끝나면 호출 (엔진 스레드)"""
        self._result_listeners.append(fn)

    @property
    def phase(self) -> GamePhase:
        return self.machine.phase

    # ── 실행 ──
    def start(self, block: bool = False) -> None:
        if block:
            self._loop()
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._capture_stop.set()
        self.detector.stop()

    def dismiss_result(self) -> None:
        """사용자가 '이번 게임 결과' 화면을 닫음 → 대기(IDLE)"""
        if self.machine.dismiss():
            self._emit_phase(GamePhase.IDLE, None)

    # ── 내부 ──
    def _loop(self) -> None:
        self.pipelines.setup()
        try:
            for event in self.detector.events():
                if self._stop.is_set():
                    break
                self._on_phase_event(event)
        finally:
            self._stop_capture(drain=False)
            self.pipelines.close()

    def _on_phase_event(self, event: PhaseEvent) -> None:
        target = self.machine.peek(event)
        if target is None:
            return
        if target == GamePhase.POST_GAME:
            # 단계를 바꾸기 전에 캡처를 끝낸다 → 남은 줄까지 이번 세션에 기록됨 (재생 소스는 끝까지 처리)
            self._stop_capture(drain=bool(getattr(self.source, "finite", False)))
        phase = self.machine.handle(event)
        if phase is None:
            return
        if phase == GamePhase.IN_GAME:
            players = self.detector.players()
            self.pipelines.set_players(players)
            self.machine.set_players(players)
            self._emit_phase(phase, self.machine.session)
            self._start_capture()
        elif phase == GamePhase.POST_GAME:
            session = self.machine.session
            self._emit_phase(phase, session)
            if session is not None:
                self.repository.save(session)
                result = self.batch.run(session)
                for fn in self._result_listeners:
                    fn(result)

    def _start_capture(self) -> None:
        self._capture_stop.clear()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

    def _stop_capture(self, drain: bool) -> None:
        """캡처 스레드 정리. drain=True(끝이 있는 재생 소스)면 남은 줄을 다 처리할 때까지 기다린다."""
        if not drain:
            self._capture_stop.set()
        if self._capture_thread is not None:
            self._capture_thread.join()
            self._capture_thread = None

    def _capture_loop(self) -> None:
        try:
            self._capture()
        except Exception:  # 캡처 스레드가 조용히 죽지 않게 원인을 남긴다 (앱은 계속 돈다)
            print("⚠️ 흐름 A(캡처) 중단:", file=sys.stderr)
            traceback.print_exc()

    def _capture(self) -> None:
        incoming = self.pipelines.incoming
        if hasattr(self.source, "frames"):
            for frame in self.source.frames():
                if self._capture_stop.is_set():
                    return
                for inc in incoming.process_frame(frame):
                    self._emit_incident(inc)
        else:
            for line in self.source.lines():
                if self._capture_stop.is_set():
                    return
                if inc := incoming.process_line(line):
                    self._emit_incident(inc)

    def _emit_incident(self, inc: Incident) -> None:
        self.machine.record(inc)
        for fn in self._incident_listeners:
            fn(inc)

    def _emit_phase(self, phase: GamePhase, session: GameSession | None) -> None:
        for fn in self._phase_listeners:
            fn(phase, session)
