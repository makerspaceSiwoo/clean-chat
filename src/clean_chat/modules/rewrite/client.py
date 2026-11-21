"""짧게 실행되는 모듈 프로세스가 준비된 로컬 Gemini 작업자를 재사용한다."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from clean_chat.core.config import ROOT

_LOG = logging.getLogger(__name__)
STATE_DIR = ROOT / ".clean-chat"
# 로컬 연결에서 시스템 프록시로 프롬프트/토큰을 보내지 않는다.
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def version() -> str:
    folder = Path(__file__).parent
    return hashlib.sha256(
        b"".join(
            (folder / name).read_bytes() for name in ("backend.py", "client.py", "service.py", "impl.py", "tracing.py")
        )
    ).hexdigest()


def state_path() -> Path:
    return STATE_DIR / "rewrite-service.json"


def _read_state() -> dict[str, Any] | None:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
        if not isinstance(data.get("port"), int) or not 0 < data["port"] < 65536:
            return None
        token = data.get("token", "")
        if not isinstance(token, str) or len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
            return None
        return data
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _rpc(state: dict[str, Any], path: str, body: dict | None, timeout: float) -> dict:
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{state['port']}{path}",
        data=payload,
        headers={"Authorization": "Bearer " + state["token"], "Content-Type": "application/json"},
    )
    with _LOCAL.open(req, timeout=max(0.01, timeout)) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("local response too large")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("invalid local response")
    return result


def _start() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = STATE_DIR / "rewrite-service.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        # 첫 프로세스가 descriptor를 쓰는 중이면 중복 실행하지 않는다.
        try:
            if time.time() - lock.stat().st_mtime > 180:
                lock.unlink(missing_ok=True)
        except OSError:
            pass
        return
    os.close(fd)
    try:
        env = dict(os.environ, PYTHONUTF8="1", LITELLM_LOCAL_MODEL_COST_MAP="True")
        token = secrets.token_hex(32)
        env["CLEAN_CHAT_REWRITE_SERVICE_TOKEN"] = token
        with (STATE_DIR / "rewrite-service.log").open("a", encoding="utf-8") as log:
            subprocess.Popen(
                [sys.executable, "-u", "-m", "clean_chat.modules.rewrite.service"],
                cwd=ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                start_new_session=os.name != "nt",
            )
    except Exception:
        lock.unlink(missing_ok=True)
        raise


def ensure_started() -> tuple[dict[str, Any] | None, bool]:
    """SDK 초기화를 기다리지 않는다. 최초 준비는 별도 프로세스에서 진행된다."""
    state = _read_state()
    if state:
        try:
            health = _rpc(state, "/health", None, 0.5)
            if health.get("version") == version():
                if health.get("setup_error"):
                    _LOG.warning("[준비 실패] Gemini 작업자 SDK 설치 확인 필요 (%s)", health["setup_error"])
                return state, bool(health.get("ready"))
            _rpc(state, "/shutdown", {}, 0.5)
        except (OSError, ValueError) as error:
            # SDK 로딩으로 잠시 바쁘다고 작업자를 중복 시작하면 더 느려진다.
            reason = getattr(error, "reason", error)
            if isinstance(reason, TimeoutError):
                return state, False
    _start()
    return None, False


def generate(prompt: str, timeout_sec: float, config: dict[str, str]) -> str | None:
    """준비된 로컬 작업자에게만 요청한다. SDK import를 요청 경로에서 하지 않는다."""
    if not config.get("LLM_API_KEY") or not config.get("LLM_MODEL"):
        _LOG.info("[rewrite] Gemini 키/모델 미설정. 규칙 대체를 시도합니다.")
        return None
    started = time.monotonic()
    try:
        state, ready = ensure_started()
        if not ready or state is None:
            _LOG.info(
                "[rewrite] Gemini 연결 최초 준비 중입니다. 잠시 후 다시 실행하세요. 입력을 기다리게 하지 않습니다."
            )
            return None
        remaining = timeout_sec - (time.monotonic() - started)
        if remaining <= 0:
            return None
        result = _rpc(state, "/generate", {"prompt": prompt, "timeout": max(0.01, remaining - 0.1)}, remaining)
        if time.monotonic() - started > timeout_sec:
            return None
        value = result.get("rewritten")
        if value is None:
            _LOG.info("[rewrite] Gemini 결과 없음(%s). 규칙 대체를 시도합니다.", result.get("status", "failed"))
        return value if isinstance(value, str) else None
    except (OSError, ValueError):
        _LOG.info("[rewrite] Gemini 연결/시간 제한으로 결과를 받지 못했습니다. 규칙 대체를 시도합니다.")
        return None


def simulate(data: dict, emit, result) -> None:
    """시뮬레이터에서 매번 Python을 띄우지 않고 준비된 rewrite 실행기를 재사용한다."""
    from clean_chat.core.schemas import RewriteRequest

    try:
        req = RewriteRequest.model_validate(data)
    except ValueError:
        return result("invalid_input", error="입력이 RewriteRequest 형식과 다릅니다.", data=data)
    emit({"type": "log", "stream": "system", "text": "▶ Gemini rewrite 실행기 재사용 (반복 SDK/Python 초기화 없음)"})
    from clean_chat.modules.rewrite import backend

    config = backend.options()
    if config["LLM_BACKEND"] != "api" or not config.get("LLM_API_KEY") or not config.get("LLM_MODEL"):
        from clean_chat.modules.rewrite import impl

        output = impl.run(req)
        return result("ok", output=output.model_dump(mode="json"), data=data)
    try:
        state, ready = ensure_started()
        if state and ready:
            response = _rpc(state, "/run", {"input": req.model_dump(mode="json")}, 3.5)
            for line in response.get("logs", "").splitlines():
                emit({"type": "log", "stream": "stdout", "text": line})
            return result(
                response.get("status", "error"), output=response.get("output"), error=response.get("error"), data=data
            )
        # 준비가 안 된 경우 기다리는 대신 일반 규칙/None으로 안전하게 반환한다.
        emit(
            {
                "type": "log",
                "stream": "system",
                "text": "Gemini 최초 연결 준비 중입니다. 잠시 후 다시 실행하세요. 이번에는 예비 규칙만 사용합니다.",
            }
        )
        from clean_chat.modules.rewrite import impl

        output = impl.run(req)
        return result("ok", output=output.model_dump(mode="json"), data=data)
    except (OSError, ValueError):
        emit({"type": "log", "stream": "system", "text": "Gemini 연결 또는 시간 제한으로 결과를 받지 못했습니다."})
        return result("ok", output={"msg_id": req.message.id, "rewritten": None, "backend": "api"}, data=data)
