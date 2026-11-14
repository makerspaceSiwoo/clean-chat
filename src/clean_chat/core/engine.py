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
from clean_chat.core.modules import ModuleNotImplemented
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
        self.batch = PostGameBatch(pipelines.modules)
        self._incident_listeners: list[IncidentListener] = []
        self._phase_listeners: list[PhaseListener] = []
        self._result_listeners: list[ResultListener] = []
        self._error_listeners: list[Callable[[str], None]] = []
        self.error: ModuleNotImplemented | None = None  # 구현 없는 모듈을 만나 멈췄으면 그 원인
        self._stop = threading.Event()
        self._capture_stop = threading.Event()
        self._batch_running = threading.Event()  # 게임 종료 배치 중에는 결과 화면을 닫을 수 없음
        self._players_ready = False  # 플레이어 명단을 받았는지 (게임 로딩 중에는 빈 목록이라 다시 물어봄)
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

    def on_error(self, fn: Callable[[str], None]) -> None:
        """구현이 없는 모듈을 만나 엔진이 멈출 때, 사람이 읽을 안내 문장으로 호출"""
        self._error_listeners.append(fn)

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
        try:
            self.detector.stop()
        except Exception:  # 감지기 정리 실패가 앱 종료를 막지 않게 (예: 미구현 LCU 감지기)
            print("⚠️ 단계 감지기 정리 실패:", file=sys.stderr)
            traceback.print_exc()

    def dismiss_result(self) -> bool:
        """사용자가 '이번 게임 결과' 화면을 닫음 → 대기(IDLE).

        신고 문구·고소장을 만드는 중이면 닫지 않고 False (결과가 대기 화면에 늦게 도착하는 것을 막음).
        """
        if self._batch_running.is_set():
            return False
        if self.machine.dismiss():
            self._emit_phase(GamePhase.IDLE, None)
            return True
        return False

    # ── 내부 ──
    def _loop(self) -> None:
        try:
            for event in self.detector.events():
                if self._stop.is_set():
                    break
                try:
                    self._on_phase_event(event)
                except ModuleNotImplemented as e:
                    self._fail(e)
                    break
                except Exception:  # 한 번의 실패로 단계 감지 전체가 멈추지 않게
                    print(f"⚠️ 단계 처리 실패 ({event.phase}):", file=sys.stderr)
                    traceback.print_exc()
                if self.error is not None:
                    break
        finally:
            self._stop_capture(drain=False)

    def _fail(self, error: ModuleNotImplemented) -> None:
        """구현 없는 모듈을 만남 → 원인을 알리고 엔진을 멈춘다 (Mock 으로 대신하지 않음, ADR-0017)."""
        if self.error is not None:
            return
        self.error = error
        print(f"⏳ {error}", file=sys.stderr)
        for fn in self._error_listeners:
            fn(str(error))
        self.stop()

    def _on_phase_event(self, event: PhaseEvent) -> None:
        target = self.machine.peek(event)
        if target == GamePhase.POST_GAME:
            # 단계를 바꾸기 전에: 결과 화면 닫기를 막고(배치가 끝날 때까지), 캡처를 끝낸다
            # → 남은 줄까지 이번 세션에 기록됨 (재생 소스는 끝까지 처리)
            self._batch_running.set()
            self._stop_capture(drain=bool(getattr(self.source, "finite", False)))
            if self.error is not None:  # 캡처 중 구현 없는 모듈을 만나 멈춤 → 배치도 하지 않는다
                self._batch_running.clear()
                return
        try:
            phase = self.machine.handle(event)  # 유예 시간 계산 때문에 target 이 없어도 항상 적용
        finally:
            if self.machine.phase != GamePhase.POST_GAME:
                self._batch_running.clear()
        if phase is None:
            return
        if phase == GamePhase.IN_GAME:
            self._players_ready = False
            self._refresh_players()
            self._emit_phase(phase, self.machine.session)
            self._start_capture()
        elif phase == GamePhase.POST_GAME:
            session = self.machine.session
            try:
                self._emit_phase(phase, session)
                if session is not None:
                    self._finish_game(session)
            finally:
                self._batch_running.clear()

    def _finish_game(self, session: GameSession) -> None:
        """세션 저장 → 배치 처리 → 결과 발행. 실패해도 빈 결과를 발행해서 UI 가 결과 화면에 멈추지 않게 한다."""
        try:
            self.repository.save(session)
        except Exception:
            print("⚠️ 세션 저장 실패:", file=sys.stderr)
            traceback.print_exc()
        try:
            result = self.batch.run(session)
        except ModuleNotImplemented as e:
            self._fail(e)
            result = PostGameResult(session_id=session.id)
        except Exception:
            print("⚠️ 신고 문구·고소장 생성 실패:", file=sys.stderr)
            traceback.print_exc()
            result = PostGameResult(session_id=session.id)
        for fn in self._result_listeners:
            fn(result)

    def _refresh_players(self) -> None:
        """플레이어 명단 갱신. 게임 로딩 중에는 Live Client Data API 가 빈 목록이라, 받을 때까지 캡처 주기마다 다시 묻는다."""
        if self._players_ready:
            return
        try:
            players = self.detector.players()
        except Exception:
            players = []
        if players:
            self._players_ready = True
            self.pipelines.set_players(players)
            self.machine.set_players(players)

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
        except ModuleNotImplemented as e:
            self._fail(e)
        except Exception:  # 캡처 스레드가 조용히 죽지 않게 원인을 남긴다 (앱은 계속 돈다)
            print("⚠️ 흐름 A(캡처) 중단:", file=sys.stderr)
            traceback.print_exc()

    def _capture(self) -> None:
        incoming = self.pipelines.incoming
        if hasattr(self.source, "frames"):
            for frame in self.source.frames():
                if self._capture_stop.is_set():
                    return
                self._refresh_players()
                for inc in incoming.process_frame(frame):
                    self._emit_incident(inc)
        else:
            for line in self.source.lines():
                if self._capture_stop.is_set():
                    return
                self._refresh_players()
                if inc := incoming.process_line(line):
                    self._emit_incident(inc)

    def _emit_incident(self, inc: Incident) -> None:
        self.machine.record(inc)
        for fn in self._incident_listeners:
            fn(inc)

    def _emit_phase(self, phase: GamePhase, session: GameSession | None) -> None:
        for fn in self._phase_listeners:
            fn(phase, session)
