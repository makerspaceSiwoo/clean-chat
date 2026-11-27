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
