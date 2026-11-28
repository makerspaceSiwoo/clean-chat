"""첫 실행 준비(core/setup.py, ui/setup.py): Gemini API 키 필수 입력과 analyze 모델 내려받기."""

import os
import time
from types import SimpleNamespace

import pytest

from clean_chat.core import setup
from clean_chat.core.config import USER_ENV_KEYS, current_llm_key, settings


@pytest.fixture
def no_llm_key(tmp_path, monkeypatch):
    """키가 없는 PC. 테스트가 저장한 키는 끝나면 환경 변수에서 지운다."""
    for key in USER_ENV_KEYS:
        monkeypatch.setenv(key, "")
    monkeypatch.setattr(settings, "llm_env", tmp_path / ".env")
    monkeypatch.delenv(setup.SKIP_ENV, raising=False)
    return tmp_path / ".env"


def test_setup_is_needed_until_key_and_model_are_ready(no_llm_key, monkeypatch):
    missing = ["classifier"]
    monkeypatch.setattr(setup, "runtime_ready", lambda: True)
    monkeypatch.setattr(setup, "missing_models", lambda: missing)
    assert setup.needed() and not setup.models_ready()  # 키도 모델도 없음
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123456")
    assert setup.needed()  # 키만 있음 → 모델을 받아야 한다
    missing.clear()
    assert not setup.needed() and setup.models_ready()
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert setup.needed()  # 모델만 있음 → 키를 받아야 한다
    monkeypatch.setenv(setup.SKIP_ENV, "1")
    assert not setup.needed()  # CI 실행 확인용


def test_setup_without_model_packages_only_asks_for_key(no_llm_key, monkeypatch):
    """analyze extra 가 없는 개발 환경에서는 모델을 돌릴 수 없어 키만 확인한다."""
    monkeypatch.setattr(setup, "runtime_ready", lambda: False)
    monkeypatch.setattr(setup, "missing_models", lambda: pytest.fail("패키지 없이 모델을 확인함"))
    assert setup.needed()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123456")
    assert not setup.needed() and not setup.models_ready()


def test_weights_missing_follows_model_folder(tmp_path, monkeypatch):
    from clean_chat.modules.analyze import model, weights

    monkeypatch.setenv(model.ENV_VAR, str(tmp_path / "classifier"))
    assert weights.folder("classifier") == tmp_path / "classifier"
    assert weights.missing(["classifier"]) == ["classifier"]
    (tmp_path / "classifier").mkdir()
    for name in weights.FILES[:-1]:
        (tmp_path / "classifier" / name).write_text("x")
    assert weights.missing(["classifier"]) == ["classifier"]  # 파일 하나가 모자람
    (tmp_path / "classifier" / weights.FILES[-1]).write_text("x")
    assert weights.missing(["classifier"]) == []
    monkeypatch.setattr(setup, "APP_MODELS", ("classifier",))
    assert setup.downloaded_bytes() == len(weights.FILES)


def _dialog(ops):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from clean_chat.ui.setup import SetupDialog

    qt = QApplication.instance() or QApplication([])
    return qt, SetupDialog(ops)


def _ops(**changes):
    base = dict(
        runtime_ready=lambda: True,
        missing_models=lambda: [],
        expected_bytes=lambda: 0,
        downloaded_bytes=lambda: 0,
        download_models=lambda: None,
        INSTALL_HINT=setup.INSTALL_HINT,
    )
    return SimpleNamespace(**(base | changes))


def test_dialog_requires_key_before_start(no_llm_key):
    _qt, dialog = _dialog(_ops())
    assert dialog.model_state == "ready" and not dialog.btn_start.isEnabled()  # 모델이 있어도 키가 없으면 시작 불가
    dialog.key.setText("bad key")
    dialog.btn_start.click()
    assert not dialog.result() and dialog.key.property("invalid") is True  # 공백이 든 키는 저장하지 않는다
    dialog.key.setText("test-key-123456")
    assert dialog.btn_start.isEnabled()
    dialog.btn_start.click()
    assert dialog.result() and current_llm_key(no_llm_key) == "test-key-123456"
    assert "test-key-123456" in no_llm_key.read_text(encoding="utf-8")


def test_dialog_downloads_missing_model_then_allows_start(no_llm_key, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123456")
    missing, calls = ["classifier"], []

    def download():
        calls.append("download")
        if len(calls) == 1:
            raise OSError("연결 끊김")
        missing.clear()

    qt, dialog = _dialog(
        _ops(missing_models=lambda: list(missing), download_models=download, expected_bytes=lambda: 10)
    )

    def wait(state):
        deadline = time.monotonic() + 5
        while dialog.model_state != state and time.monotonic() < deadline:
            qt.processEvents()
            time.sleep(0.01)
        assert dialog.model_state == state

    wait("failed")  # 처음에는 자동으로 받기 시작했다가 실패
    assert not dialog.btn_start.isEnabled() and not dialog.btn_retry.isHidden()
    assert "연결 끊김" in dialog.model_status.text()
    dialog.btn_retry.click()
    wait("ready")
    assert calls == ["download", "download"] and dialog.btn_start.isEnabled() and dialog.btn_retry.isHidden()


def test_dialog_explains_missing_model_packages(no_llm_key, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123456")
    _qt, dialog = _dialog(_ops(runtime_ready=lambda: False))
    assert dialog.model_state == "unavailable" and dialog.btn_start.isEnabled()
    assert "--extra analyze" in dialog.model_status.text()


def test_only_one_app_instance_runs(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QLockFile

    from clean_chat.ui import app

    path = tmp_path / "store" / "app.lock"
    assert app.single_instance(path)  # 첫 실행
    other = QLockFile(str(path))  # 두 번째로 뜬 앱
    other.setStaleLockTime(0)
    assert not other.tryLock(0)
    app._instance_lock.unlock()
    assert other.tryLock(0)  # 앞의 앱이 끝나면 다시 실행할 수 있다
    other.unlock()


def test_built_app_refuses_interpreter_style_arguments():
    """설치 파일이 `-c ...` 로 다시 불려도(보조 프로세스) 앱 창을 띄우지 않는다."""
    from clean_chat import desktop

    assert desktop.unexpected_args(["--demo"]) == [] and desktop.unexpected_args(["-psn_0_12345", "--check"]) == []
    assert desktop.unexpected_args(["-B", "-c", "from multiprocessing.resource_tracker import main;main(5)"])
