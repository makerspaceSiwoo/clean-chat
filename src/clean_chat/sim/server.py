"""로컬 시뮬레이터 서버 (`uv run sim`). 화면(static/)과 모듈 실행 API 를 함께 제공한다. 표준 라이브러리만 쓴다.

  GET  /                       화면 (static/index.html)
  GET  /api/modules            모듈 5개: 이름·제목·설명·간단 입력 칸·예시 입력(fixtures)·입력 JSON Schema
  POST /api/modules/<이름>/run  {"input": {...}} 또는 {"simple": {...}}, 선택 {"image": {"name", "base64"}}
                               → NDJSON 스트림: {"type":"log","stream":"stdout|stderr|system","text"}, {"type":"ping"}(1초마다) ... 마지막에
                                 {"type":"result","status","output","error","input","durationMs"}

로컬 개발 전용: 127.0.0.1 에만 연다. 실행마다 새 프로세스(worker.py)라서 모듈 코드를 고치면 바로 반영된다.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from clean_chat.core import modules
from clean_chat.core.config import FIXTURES, settings
from clean_chat.core.jsonl import read_jsonl
from clean_chat.sim import inputs

STATIC = Path(__file__).parent / "static"
STATIC_FILES = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css"}
ROUTE = re.compile(r"^/api/modules/([a-z_]+)/run/?$")
MAX_BODY = 20 * 1024 * 1024  # 20MB (이미지 base64 포함)
IMAGE_FIELD = "image_path"  # 첨부 이미지를 넣을 입력 필드 (ocr 의 Frame.image_path)
PORT = 8765

Emit = Callable[[dict[str, Any]], None]


class ClientGone(Exception):
    """브라우저가 연결을 끊음 (중지 버튼, 창 닫기) → 실행 중인 프로세스를 끝낸다."""


# ── 모듈 목록 ─────────────────────────────────────────────
def _label(item: dict[str, Any], i: int) -> str:
    msg = item.get("line") or item.get("message") or {}
    text = (
        msg.get("text")
        or item.get("image_path")
        or (f"{item.get('kind', '')} · 대상 {item['speaker']}" if item.get("speaker") else "")
    )
    ident = item.get("id") or msg.get("id") or (item.get("session") or {}).get("id")
    return " · ".join(str(x) for x in (f"#{i + 1}", ident, text) if x)


def module_list() -> list[dict[str, Any]]:
    out = []
    for spec in modules.MODULES.values():
        path = FIXTURES / spec.name / "input.jsonl"
        examples = [x.model_dump(mode="json") for x in read_jsonl(path, spec.input_model)] if path.exists() else []
        out.append(
            {
                "name": spec.name,
                "number": spec.number,
                "title": spec.title,
                "description": inputs.DESCRIPTIONS[spec.name],
                "path": spec.path,
                "inputModel": spec.input_model.__name__,
                "outputModel": spec.output_model.__name__,
                "form": inputs.FORMS[spec.name],
                "examples": [{"label": _label(x, i), "input": x} for i, x in enumerate(examples)],
                "schema": spec.input_model.model_json_schema(),
            }
        )
    return out


# ── 실행 ──────────────────────────────────────────────────
def save_upload(image: dict[str, Any], uploads_dir: Path) -> Path:
    """{"name", "base64"} → uploads_dir/<안전한 이름>. 경로 조작(../)을 막으려고 파일 이름만 쓴다."""
    name = Path(str(image.get("name") or "upload.png")).name
    name = re.sub(r"[^\w.\-가-힣]", "_", name) or "upload.png"
    try:
        data = base64.b64decode(str(image.get("base64") or ""), validate=True)
    except (binascii.Error, ValueError) as e:
        raise inputs.SimpleInputError(f"이미지를 읽을 수 없습니다: {e}") from e
    uploads_dir.mkdir(parents=True, exist_ok=True)
    path = uploads_dir / name
    path.write_bytes(data)
    return path


def resolve_input(name: str, body: Any, uploads_dir: Path) -> dict[str, Any]:
    """요청 본문 → 모듈 입력 JSON. 간단 입력이면 변환, 이미지가 있으면 저장 후 image_path 를 바꾼다."""
    if not isinstance(body, dict):
        raise inputs.SimpleInputError('본문은 {"input": {...}} 또는 {"simple": {...}} 이어야 합니다')
    image = body.get("image") if isinstance(body.get("image"), dict) else None
    if image is not None and IMAGE_FIELD not in modules.MODULES[name].input_model.model_fields:
        raise inputs.SimpleInputError(f"'{name}' 모듈 입력에는 이미지가 없습니다")
    image_path = str(save_upload(image, uploads_dir)) if image is not None else None
    if isinstance(body.get("simple"), dict):
        return inputs.build(name, body["simple"], image_path)
    if not isinstance(body.get("input"), dict):
        raise inputs.SimpleInputError("입력 JSON 이 객체가 아닙니다")
    data = dict(body["input"])
    if image_path is not None:
        data[IMAGE_FIELD] = image_path
    return data


def _pump(stream, kind: str, q: queue.Queue) -> None:
    for line in iter(stream.readline, ""):
        q.put((kind, line.rstrip("\n")))
    q.put((kind, None))


def run_module(name: str, body: Any, emit: Emit, uploads_dir: Path | None = None, timeout: float | None = None) -> None:
    """모듈 1번 실행: 콘솔 줄은 emit({"type":"log"}) 로 실시간, 마지막에 emit({"type":"result"})."""
    started = time.perf_counter()

    def result(status: str, output: Any = None, error: str | None = None, data: Any = None) -> None:
        ms = round((time.perf_counter() - started) * 1000)
        emit({"type": "result", "status": status, "output": output, "error": error, "input": data, "durationMs": ms})

    if name not in modules.MODULES:
        return result("invalid_input", error=f"모르는 모듈: {name} (있는 모듈: {', '.join(modules.MODULE_NAMES)})")
    try:
        data = resolve_input(name, body, uploads_dir or settings.uploads_dir)
    except Exception as e:  # 간단 입력 비어 있음, 이미지 깨짐, 형식 오류
        return result("invalid_input", error=str(e))
    emit({"type": "log", "stream": "system", "text": f"$ python -m clean_chat.sim.worker {name}  (새 프로세스)"})

    with tempfile.TemporaryDirectory(prefix="clean-chat-sim-") as tmp:
        inp, out = Path(tmp) / "input.json", Path(tmp) / "result.json"
        inp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "clean_chat.sim.worker", name, str(inp), str(out)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        q: queue.Queue = queue.Queue()
        for stream, kind in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
            threading.Thread(target=_pump, args=(stream, kind, q), daemon=True).start()
        deadline = time.monotonic() + (timeout or settings.sim_timeout_sec)
        open_streams = 2
        last_emit = time.monotonic()
        try:
            while open_streams:
                left = deadline - time.monotonic()
                if left <= 0:
                    proc.kill()
                    proc.wait()
                    return result(
                        "timeout",
                        error=f"{timeout or settings.sim_timeout_sec:.0f}초가 지나 실행을 멈췄습니다",
                        data=data,
                    )
                try:
                    kind, line = q.get(timeout=min(left, 0.5))
                except queue.Empty:
                    # 출력이 없는 동안에도 1초마다 신호를 보내 브라우저가 끊겼는지(중지 버튼) 알아낸다
                    if time.monotonic() - last_emit >= 1.0:
                        emit({"type": "ping"})
                        last_emit = time.monotonic()
                    continue
                if line is None:
                    open_streams -= 1
                else:
                    emit({"type": "log", "stream": kind, "text": line})
                    last_emit = time.monotonic()
            code = proc.wait()
        except ClientGone:
            proc.kill()
            proc.wait()
            raise
        if not out.exists():
            return result("error", error=f"프로세스가 결과 없이 끝났습니다 (종료 코드 {code})", data=data)
        r = json.loads(out.read_text(encoding="utf-8"))
        result(r["status"], r.get("output"), r.get("error"), data)


# ── HTTP ─────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "clean-chat-sim/1"

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, payload: Any) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 (http.server 규칙)
        path = urlparse(self.path).path
        if path in STATIC_FILES:
            f = STATIC / STATIC_FILES[path]
            self._send(HTTPStatus.OK, f.read_bytes(), CONTENT_TYPES[f.suffix])
        elif path.rstrip("/") == "/api/modules":
            self._json(HTTPStatus.OK, module_list())
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "없는 주소"})

    def do_POST(self) -> None:  # noqa: N802
        match = ROUTE.match(urlparse(self.path).path)
        if match is None:
            return self._json(HTTPStatus.NOT_FOUND, {"error": "POST /api/modules/<이름>/run 만 있습니다"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "본문이 너무 큽니다 (최대 20MB)"})
        try:
            body = json.loads(self.rfile.read(length) or b"null")
        except json.JSONDecodeError as e:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": f"JSON 이 아닙니다: {e}"})
        # 스트리밍: 길이를 모르므로 Content-Length 없이 보내고 연결을 닫는다 (HTTP/1.0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def emit(event: dict[str, Any]) -> None:
            try:
                self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError) as e:
                raise ClientGone from e

        try:
            run_module(match.group(1), body, emit)
        except ClientGone:
            print("[sim] 브라우저가 연결을 끊어 실행을 멈췄습니다", file=sys.stderr)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if "/api/modules/" in str(args[0] if args else ""):
            print(f"[sim] {format % args}", file=sys.stderr)


def make_server(port: int = PORT) -> ThreadingHTTPServer:
    """127.0.0.1:port 에 연다. 이미 쓰는 중이면 다음 포트(최대 +20)를 쓴다."""
    for p in range(port, port + 21):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), Handler)
        except OSError:
            continue
    raise OSError(f"{port}~{port + 20} 포트를 모두 쓰는 중입니다")


def serve(module: str | None = None, open_browser: bool = True) -> None:
    httpd = make_server()
    url = f"http://localhost:{httpd.server_address[1]}/" + (f"#{module}" if module else "")
    print(f"✅ 모듈 시뮬레이터: {url}")
    print("   브라우저에서 모듈을 골라 실행하세요. 끝내려면 Ctrl+C")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n시뮬레이터를 끝냈습니다.")
    finally:
        httpd.server_close()
