"""모듈 내부의 로컬 작업자. LiteLLM을 한 번 준비하고 반복 요청에 재사용한다."""

from __future__ import annotations

import hmac
import io
import json
import logging
import os
import queue
import threading
import time
from contextlib import redirect_stderr, redirect_stdout, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from clean_chat.modules.rewrite import backend, client


class WorkerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str):
        super().__init__(("127.0.0.1", 0), Handler)
        self.token = token
        self.ready = threading.Event()
        self.setup_error = None
        self.stop_requested = False
        self.last_activity = time.monotonic()
        self.worker_version = client.version()
        self.timeout = 1
        self.tasks = queue.Queue(maxsize=1)
        self.api_slot = threading.BoundedSemaphore(1)
        self.run_slot = threading.BoundedSemaphore(1)


class Handler(BaseHTTPRequestHandler):
    server: WorkerServer

    def log_message(self, *_args) -> None:
        pass  # 프롬프트·인증 헤더를 로그에 남기지 않는다.

    def _authorized(self) -> bool:
        valid = hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + self.server.token)
        if not valid:
            self.send_error(403)
        return valid

    def _send(self, data: dict, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        with suppress(OSError):
            self.wfile.write(raw)

    def do_GET(self) -> None:
        if not self._authorized():
            return
        self.server.last_activity = time.monotonic()
        self._send(
            {
                "ready": self.server.ready.is_set(),
                "version": self.server.worker_version,
                "setup_error": self.server.setup_error,
            }
        )

    def do_POST(self) -> None:
        if not self._authorized():
            return
        self.server.last_activity = time.monotonic()
        if self.path == "/shutdown":
            self.server.stop_requested = True
            self._send({"status": "stopping"})
            return
        if self.path == "/run":
            self._run_module()
            return
        if self.path != "/generate":
            self._send({"status": "not_found"}, 404)
            return
        if not self.server.ready.is_set():
            self._send({"status": "preparing", "rewritten": None})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("length")
            self.connection.settimeout(3)
            data = json.loads(self.rfile.read(length))
            prompt = data["prompt"]
            timeout = float(data["timeout"])
            if not isinstance(prompt, str) or not 0 < timeout <= 3:
                raise ValueError("input")
        except (OSError, ValueError, TypeError, KeyError):
            self._send({"status": "invalid_input", "rewritten": None}, 400)
            return
        # 외부 API 키는 로컬 .env에서 읽고 RPC 메시지에는 포함하지 않는다.
        if not self.server.api_slot.acquire(blocking=False):
            self._send({"status": "busy", "rewritten": None})
            return
        reply = queue.Queue(maxsize=1)
        self.server.tasks.put((prompt, reply))
        try:
            result = reply.get(timeout=min(timeout, 2.5))
        except queue.Empty:
            result = {"status": "timeout", "rewritten": None}
        self._send(result)

    def _run_module(self) -> None:
        # 이 작업자는 rewrite 전용이다. 다른 모듈의 stdout이나 상태를 공유하지 않는다.
        if not self.server.run_slot.acquire(blocking=False):
            self._send({"status": "error", "error": "rewrite가 이미 실행 중입니다."})
            return
        console = io.StringIO()
        handler = logging.StreamHandler(console)
        logger = logging.getLogger("clean_chat.modules.rewrite")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("input too large")
            self.connection.settimeout(3)
            data = json.loads(self.rfile.read(length))
            from clean_chat.core.schemas import RewriteRequest
            from clean_chat.modules.rewrite import impl

            req = RewriteRequest.model_validate(data["input"])
            with redirect_stdout(console), redirect_stderr(console):
                output = impl.run(req)
            self._send({"status": "ok", "output": output.model_dump(mode="json"), "logs": console.getvalue()[-12000:]})
        except Exception as error:
            # 상세 외부 오류 본문 대신 오류 종류만 반환한다. 키를 노출하지 않는다.
            self._send({"status": "error", "error": type(error).__name__, "logs": console.getvalue()[-12000:]})
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)
            self.server.run_slot.release()


def work(server: WorkerServer) -> None:
    """SDK와 API 클라이언트를 같은 작업 스레드에서 계속 재사용한다."""
    try:
        backend._sdk()
        server.ready.set()
    except Exception as error:
        server.setup_error = type(error).__name__
        logging.getLogger("clean_chat.modules.rewrite.backend").warning("[준비 실패] Gemini SDK %s", server.setup_error)
        return
    while not server.stop_requested:
        try:
            prompt, reply = server.tasks.get(timeout=1)
        except queue.Empty:
            continue
        try:
            started = time.monotonic()
            config = backend.options()
            result = backend._request(prompt, config["LLM_API_KEY"], config["LLM_MODEL"], 10)
            logging.warning(
                "Gemini completed seconds=%.3f has_result=%s", time.monotonic() - started, result is not None
            )
            reply.put({"status": "ok" if result is not None else "failed", "rewritten": result})
        except Exception as error:
            logging.getLogger("clean_chat.modules.rewrite.backend").warning(
                "[API 실패] %s (키/오류 본문은 출력하지 않음)", type(error).__name__
            )
            reply.put({"status": "failed", "rewritten": None})
        finally:
            server.api_slot.release()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.pop("CLEAN_CHAT_REWRITE_SERVICE_TOKEN", "")
    if len(token) != 64:
        raise SystemExit("service authentication is required")
    server = WorkerServer(token)
    client.STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = {"port": server.server_port, "token": token, "version": server.worker_version, "pid": os.getpid()}
    temp = client.state_path().with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(state, stream)
    os.replace(temp, client.state_path())
    (client.STATE_DIR / "rewrite-service.lock").unlink(missing_ok=True)

    threading.Thread(target=work, args=(server,), name="rewrite-gemini", daemon=True).start()
    try:
        # 사용하지 않으면 15분 후 종료. 실행 중인 앱이 정기적으로 사용하면 재사용된다.
        while not server.stop_requested and time.monotonic() - server.last_activity < 900:
            server.handle_request()
    finally:
        server.server_close()
        current = client._read_state()
        if current and current.get("token") == token:
            client.state_path().unlink(missing_ok=True)


if __name__ == "__main__":
    main()
