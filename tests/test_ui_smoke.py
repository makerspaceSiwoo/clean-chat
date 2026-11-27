"""UI 조립 연기 테스트 (화면 없이). PySide6 가 없으면 skip: uv sync --extra ui"""

import os
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from clean_chat.core.pipeline import Pipelines  # noqa: E402
from clean_chat.core.schemas import GamePhase  # noqa: E402
from clean_chat.core.sources import DemoLineSource  # noqa: E402
from clean_chat.session.fake import FakePhaseDetector  # noqa: E402
from helpers import SCENARIO, fixture_modules  # noqa: E402


def test_app_follows_game_phases():
    from clean_chat.ui.app import App

    detector = FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl")
    app = App(Pipelines(fixture_modules()), DemoLineSource(SCENARIO / "lines.jsonl", delay_sec=0), detector)
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


def test_settings_page_saves_and_clears_llm_key(tmp_path, monkeypatch):
    from clean_chat.core.config import USER_ENV_KEYS, read_user_env, settings
    from clean_chat.ui.app import App

    for key in USER_ENV_KEYS:  # 테스트가 끝나면 원래 환경 변수로 되돌린다.
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    env_file = tmp_path / ".env"
    monkeypatch.setattr(settings, "llm_env", env_file)
    detector = FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl")
    app = App(Pipelines(fixture_modules()), DemoLineSource(SCENARIO / "lines.jsonl", delay_sec=0), detector)
    client = app.client
    assert client.llm_status.text() == "설정 안 됨 · 로컬 규칙만 사용"
    assert not client.btn_llm_save.isEnabled() and client.btn_llm_clear.isHidden()
    client.llm_model.setText("gemini-2.5-flash")
    client.llm_key.setText("test-key-abcd1234")
    assert client.llm_key.echoMode() == client.llm_key.EchoMode.Password
    client.btn_key_show.click()
    assert client.llm_key.echoMode() == client.llm_key.EchoMode.Normal and client.btn_key_show.text() == "숨기기"
    client.btn_llm_save.click()
    assert read_user_env(env_file)["LLM_API_KEY"] == "test-key-abcd1234"
    assert os.environ["LLM_MODEL"] == "gemini/gemini-2.5-flash"
    # 저장 뒤에는 키를 입력칸에 다시 채우지 않고 끝 4자리만 보여 준다.
    assert client.llm_key.text() == "" and client.llm_key.echoMode() == client.llm_key.EchoMode.Password
    assert client.llm_status.text() == "사용 중 · gemini/gemini-2.5-flash · 키 ••••1234"
    assert "test-key" not in client.llm_status.text() + client.llm_key.placeholderText()
    assert not client.btn_llm_save.isEnabled() and not client.btn_llm_clear.isHidden()
    client.llm_model.setText("gemini/gemini-2.5-pro")  # 모델만 바꾸면 저장된 키를 그대로 쓴다.
    client.btn_llm_save.click()
    assert read_user_env(env_file)["LLM_MODEL"] == "gemini/gemini-2.5-pro"
    assert read_user_env(env_file)["LLM_API_KEY"] == "test-key-abcd1234"
    client.btn_llm_clear.click()
    assert not env_file.exists() and "LLM_API_KEY" not in os.environ
    assert client.llm_status.text() == "설정 안 됨 · 로컬 규칙만 사용" and "지웠습니다" in client.toast.text()
    client.close()
    app.overlay.close()
