"""Engine 이 실제 게임에서 만날 상황에 버티는지 (리뷰 지적 회귀 테스트)."""

import threading

from clean_chat.core.config import FIXTURES
from clean_chat.core.engine import Engine
from clean_chat.core.pipeline import Pipelines, SentLog
from clean_chat.core.schemas import GamePhase, Player, PostGameResult
from clean_chat.core.sources import DemoLineSource
from clean_chat.core.stage import read_jsonl
from clean_chat.session.fake import FakePhaseDetector

SCENARIO = FIXTURES / "scenario"


class LoadingDetector(FakePhaseDetector):
    """게임 로딩 중에는 명단이 비어 있다가 몇 번 물어본 뒤 생기는 감지기 (Live Client Data API 흉내)."""

    def __init__(self, empty_times: int) -> None:
        super().__init__(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl")
        self.calls, self.empty_times = 0, empty_times

    def players(self) -> list[Player]:
        self.calls += 1
        return [] if self.calls <= self.empty_times else super().players()


def _engine(detector) -> Engine:
    return Engine(Pipelines(), DemoLineSource(SCENARIO / "lines.jsonl", delay_sec=0), detector)


def test_players_are_polled_until_loading_finishes():
    eng = _engine(LoadingDetector(empty_times=3))
    eng.start(block=True)
    session = eng.repository.load("20251112-125820")
    assert session.players == read_jsonl(SCENARIO / "players.jsonl", Player)


def test_batch_failure_still_emits_result_and_keeps_detecting():
    eng = _engine(FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl"))

    def broken(_session):
        raise RuntimeError("complaint 구현 오류")

    eng.batch.run = broken
    results: list[PostGameResult] = []
    eng.on_result(results.append)
    eng.start(block=True)
    assert results == [PostGameResult(session_id="20251112-125820")]  # 빈 결과라도 와야 UI 가 멈추지 않음
    assert eng.phase == GamePhase.POST_GAME
    assert eng.dismiss_result() is True


def test_cannot_dismiss_while_results_are_being_made():
    eng = _engine(FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl"))
    started, release = threading.Event(), threading.Event()
    real_run = eng.batch.run
    attempts: list[bool] = []

    def slow_run(session):
        started.set()
        release.wait(5)
        return real_run(session)

    eng.batch.run = slow_run
    eng.start()
    assert started.wait(5)
    attempts.append(eng.dismiss_result())  # 배치 중 → 거부
    release.set()
    eng._thread.join(5)
    attempts.append(eng.dismiss_result())  # 결과가 나온 뒤 → 허용
    assert attempts == [False, True]
    assert eng.phase == GamePhase.IDLE


def test_sent_log_forgets_old_entries():
    log = SentLog(window_sec=60)
    for i in range(100):
        log.remember(f"문장 {i}", ts=i * 10.0)
    assert len(log._sent) <= 7
