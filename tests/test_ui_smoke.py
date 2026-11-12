"""UI 조립 연기 테스트 (화면 없이). PySide6 가 없으면 skip: uv sync --extra ui"""

import os
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from clean_chat.core.config import FIXTURES  # noqa: E402
from clean_chat.core.pipeline import Pipelines  # noqa: E402
from clean_chat.core.schemas import GamePhase  # noqa: E402
from clean_chat.core.sources import DemoLineSource  # noqa: E402
from clean_chat.session.fake import FakePhaseDetector  # noqa: E402

SCENARIO = FIXTURES / "scenario"


def test_app_follows_game_phases():
    from clean_chat.ui.app import App

    detector = FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl")
    app = App(Pipelines(), DemoLineSource(SCENARIO / "lines.jsonl", delay_sec=0), detector)
    seen: list[GamePhase] = []
    results = []
    app.bridge.phase.connect(lambda phase, _s: seen.append(phase))
    app.bridge.result.connect(results.append)
    app.show()
    app.engine.start()
    deadline = time.monotonic() + 10
    while not results and time.monotonic() < deadline:
        app.qt.processEvents()
        time.sleep(0.01)
    app.engine.stop()

    assert seen == [GamePhase.IN_GAME, GamePhase.POST_GAME]
    assert len(results[0].reports) == 2
    assert app.client.pages.currentWidget() is app.client._page_for[GamePhase.POST_GAME]
    assert not app.overlay.isVisible()  # 게임이 끝나면 오버레이 숨김

    app.client.btn_close_result.click()  # 결과 화면 닫기 → 대기
    for _ in range(50):
        app.qt.processEvents()
    assert app.engine.phase == GamePhase.IDLE
    assert app.client.pages.currentWidget() is app.client._page_for[GamePhase.IDLE]
