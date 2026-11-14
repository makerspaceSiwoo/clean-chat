"""로컬 모듈 실행 서버 (구성, 리드 소유). 웹 시뮬레이터가 실제 모듈 함수를 부를 때 쓴다 (ADR-0017).

  uv run clean-chat serve                # http://localhost:8765
  POST /modules/<이름>/run   본문 {"input": {...}, "image": {"name": "a.png", "base64": "..."}?}
    200 {"output": {...}}                        모듈 실행 성공
    501 {"output": null, "error": "..."}         모듈 구현이 아직 없음 (NotImplementedError)
    422 {"output": null, "error": "..."}         입력 형식이 계약과 다름
    500 {"output": null, "error": "..."}         모듈 실행 중 예외
  GET  /modules              모듈 목록 [{name, title, path}]

표준 라이브러리 http.server 만 쓴다 (새 패키지 없음). 로컬 개발 전용: 127.0.0.1 에만 열고, CORS 는 localhost 만 허용.
첨부 이미지는 .clean-chat/uploads/ 에 저장하고 입력의 image_path 를 그 경로로 바꾼다 (git 제외).
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from clean_chat.core import modules
from clean_chat.core.config import settings

ROUTE = re.compile(r"^/modules/([a-z_]+)/run/?$")
LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
MAX_BODY = 20 * 1024 * 1024  # 20MB (이미지 base64 포함)
IMAGE_FIELD = "image_path"  # 첨부 이미지를 넣을 입력 필드 (ocr 의 Frame.image_path)


class RunError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def save_upload(image: dict[str, Any], uploads_dir: Path) -> Path:
    """{"name", "base64"} → uploads_dir/<안전한 이름> 저장. 경로 조작(../)을 막으려고 파일 이름만 쓴다."""
    name = Path(str(image.get("name") or "upload.png")).name
    name = re.sub(r"[^\w.\-가-힣]", "_", name) or "upload.png"
    try:
        data = base64.b64decode(str(image.get("base64") or ""), validate=True)
    except (binascii.Error, ValueError) as e:
        raise RunError(HTTPStatus.UNPROCESSABLE_ENTITY, f"이미지 base64 를 읽을 수 없습니다: {e}") from e
    uploads_dir.mkdir(parents=True, exist_ok=True)
    path = uploads_dir / name
    path.write_bytes(data)
    return path


def run_module(name: str, body: Any, uploads_dir: Path | None = None) -> dict[str, Any]:
    """요청 본문 → 모듈 실행 → {"output": ...}. 실패는 RunError(상태 코드, 안내 문장)."""
    if name not in modules.MODULES:
        raise RunError(HTTPStatus.NOT_FOUND, f"모르는 모듈: {name} (있는 모듈: {', '.join(modules.MODULE_NAMES)})")
    if not isinstance(body, dict) or not isinstance(body.get("input"), dict):
        raise RunError(HTTPStatus.UNPROCESSABLE_ENTITY, '본문은 {"input": {...}} 형식이어야 합니다')
    data = dict(body["input"])
    if isinstance(body.get("image"), dict):
        data[IMAGE_FIELD] = str(save_upload(body["image"], uploads_dir or settings.uploads_dir))
    try:
        out = modules.call(name, data)
    except ValidationError as e:
        raise RunError(HTTPStatus.UNPROCESSABLE_ENTITY, f"입력이 계약과 다릅니다:\n{e}") from e
    except modules.ModuleNotImplemented as e:
        raise RunError(HTTPStatus.NOT_IMPLEMENTED, str(e)) from e
    except Exception as e:  # 모듈 안의 오류를 그대로 보여 준다 (디버그용 로컬 서버)
        traceback.print_exc()
        raise RunError(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(e).__name__}: {e}") from e
    return {"output": out.model_dump(mode="json")}


class Handler(BaseHTTPRequestHandler):
    server_version = "clean-chat/1"

    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if LOCAL_ORIGIN.match(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, status: HTTPStatus, payload: Any) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:  # noqa: N802 (http.server 규칙)
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path.rstrip("/") != "/modules":
            self._send(HTTPStatus.NOT_FOUND, {"error": "GET /modules 만 있습니다"})
            return
        items = [{"name": m.name, "title": m.title, "path": m.path} for m in modules.MODULES.values()]
        self._send(HTTPStatus.OK, items)

    def do_POST(self) -> None:  # noqa: N802
        match = ROUTE.match(urlparse(self.path).path)
        if match is None:
            self._send(HTTPStatus.NOT_FOUND, {"output": None, "error": "POST /modules/<이름>/run 만 있습니다"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise RunError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"본문이 너무 큽니다 (최대 {MAX_BODY // 2**20}MB)")
            try:
                body = json.loads(self.rfile.read(length) or b"null")
            except json.JSONDecodeError as e:
                raise RunError(HTTPStatus.UNPROCESSABLE_ENTITY, f"JSON 이 아닙니다: {e}") from e
            self._send(HTTPStatus.OK, run_module(match.group(1), body))
        except RunError as e:
            self._send(e.status, {"output": None, "error": str(e)})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        print(f"[serve] {self.address_string()} {format % args}", file=sys.stderr)


def serve(port: int | None = None, host: str = "127.0.0.1") -> None:
    port = port or settings.server_port
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"✅ 모듈 실행 서버: http://localhost:{port}  (시뮬레이터: cd simulator && npm run dev, Ctrl+C 로 종료)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
