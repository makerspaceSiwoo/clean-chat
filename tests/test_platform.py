import io
import sys

from clean_chat.core.platform import use_utf8_console


def test_use_utf8_console_prints_korean_on_cp1252(monkeypatch):
    """Windows CI 콘솔(cp1252)처럼 한글을 못 찍는 출력에서도 멈추지 않아야 한다."""
    buf = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(buf, encoding="cp1252"))
    use_utf8_console()
    print("한글 ✅")
    sys.stdout.flush()
    assert buf.getvalue().decode("utf-8").strip() == "한글 ✅"


def test_load_user_env_reads_only_llm_keys_and_keeps_existing(tmp_path):
    from clean_chat.core.config import load_user_env

    env_file = tmp_path / ".env"
    env_file.write_text(
        '# 주석\nexport LLM_MODEL="gemini/flash"\nGEMINI_API_KEY=abc # 메모\nLLM_BACKEND=rule\nOTHER=x\n',
        encoding="utf-8",
    )
    environ = {"LLM_BACKEND": "api"}
    load_user_env(env_file, environ)
    assert environ == {"LLM_BACKEND": "api", "LLM_MODEL": "gemini/flash", "GEMINI_API_KEY": "abc"}
    load_user_env(tmp_path / "missing.env", environ)


def test_llm_settings_save_and_clear_keep_other_lines(tmp_path):
    import os
    import stat

    import pytest

    from clean_chat.core.config import clear_llm_settings, current_llm_key, read_user_env, save_llm_settings

    env_file = tmp_path / "Clean Chat" / ".env"
    environ: dict[str, str] = {"GEMINI_API_KEY": "old-key"}
    with pytest.raises(ValueError):
        save_llm_settings("", env_file, environ)
    with pytest.raises(ValueError):
        save_llm_settings("has space", env_file, environ)
    save_llm_settings("test-key-1234", env_file, environ)
    # 키만 저장한다. 모델은 rewrite·report가 각자 기본값을 쓴다.
    assert read_user_env(env_file) == {"LLM_BACKEND": "api", "LLM_API_KEY": "test-key-1234"}
    assert environ["GEMINI_API_KEY"] == environ["LLM_API_KEY"] == "test-key-1234"
    assert current_llm_key(env_file, {}) == "test-key-1234"
    if os.name == "posix":
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    env_file.write_text(
        "# 메모\nOTHER=1\nLLM_MODEL=gemini/old\n" + env_file.read_text(encoding="utf-8"), encoding="utf-8"
    )
    clear_llm_settings(env_file, environ)
    assert environ == {} and env_file.read_text(encoding="utf-8") == "# 메모\nOTHER=1\n"
    env_file.write_text("", encoding="utf-8")
    save_llm_settings("test-key-1234", env_file, {})
    clear_llm_settings(env_file, {})
    assert not env_file.exists()


def test_desktop_entry_excludes_simulator():
    """설치 파일의 진입점(clean_chat.desktop)은 개발용 시뮬레이터를 불러오지 않고, 빌드도 시뮬레이터를 뺀다."""
    import subprocess
    import sys
    from pathlib import Path

    code = "import sys, clean_chat.desktop; print(any(m.startswith('clean_chat.sim') for m in sys.modules))"
    loaded = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert loaded.stdout.strip() == "False"
    build = (Path(__file__).resolve().parents[1] / "scripts" / "build_desktop.py").read_text(encoding="utf-8")
    assert '"clean_chat.sim"' in build and "--exclude-module" in build
    # 분류 모델은 ONNX 로 돌려서 torch·transformers 는 빌드에서 뺀다 (약 1GB). 진입점은 그래도 multiprocessing
    # 보조 프로세스를 맨 먼저 가로챈다 (tqdm 등이 만들면 앱 창이 또 뜬다).
    assert 'TRAINING_ONLY = ("torch", "transformers"' in build and "for module in TRAINING_ONLY" in build
    entry = (Path(__file__).resolve().parents[1] / "src" / "clean_chat" / "desktop.py").read_text(encoding="utf-8")
    body = entry[entry.index("def app()") :]
    assert body.index("multiprocessing.freeze_support()") < body.index("use_utf8_console()")
    assert '"desktop.py"' in build and '"__main__.py"' not in build


def test_windowed_app_without_console_gets_log_streams(tmp_path, monkeypatch):
    """Windows 설치 파일(콘솔 없는 창 앱)은 sys.stdout·sys.stderr 가 None 이다. 진행 막대(tqdm)가 쓰다 죽지 않게
    logs/console.log 로 돌린다 ("'NoneType' object has no attribute 'write'" 로 모델 내려받기 실패)."""
    import sys

    from clean_chat import desktop
    from clean_chat.core.config import settings

    monkeypatch.setattr(settings, "store_dir", tmp_path)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    desktop.ensure_std_streams()
    try:
        assert sys.stdout is sys.stderr is not None
        print("진행 막대", file=sys.stderr)
        sys.stderr.flush()
        assert "진행 막대" in (tmp_path / "logs" / "console.log").read_text(encoding="utf-8")
    finally:
        sys.stderr.close()


def test_terminal_streams_are_left_alone(monkeypatch):
    import io
    import sys

    from clean_chat import desktop

    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    desktop.ensure_std_streams()
    assert sys.stdout is out and sys.stderr is err
