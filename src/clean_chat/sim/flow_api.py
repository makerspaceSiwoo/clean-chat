"""전체 흐름 화면의 서버 쪽 (`uv run sim flow` → http://localhost:8765/flow). server.py 가 주소만 넘겨준다.

GET  /api/flow/samples           예시 캡처 이미지 목록 (fixtures/flow/samples.jsonl) + 명단
GET  /api/flow/samples/<id>.png  예시 이미지
GET  /api/flow/logs              단계별 실패 모니터링: 최근 실행의 단계별 합계 + 최근 실패 (sim/flow_log.py)
POST /api/flow/run               {"sample": id} 또는 {"image": {"name","base64"}}, "ocrText", "useFallback"
                                 → NDJSON 스트림: {"type":"log"} / {"type":"flow", ...단계 이벤트} / {"type":"ping"}
                                   마지막에 {"type":"result","status":"ok|stopped|error|timeout","error","durationMs"}
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clean_chat.core.config import ROOT, settings
from clean_chat.sim import flow_log
from clean_chat.sim.flow import FLOW_DIR, MARKER, FlowRequest, default_players

Emit = Callable[[dict[str, Any]], None]


class FlowInputError(ValueError):
    """요청 본문이 잘못됨 (예시 id 없음, 이미지 없음)."""


def samples() -> list[dict[str, Any]]:
    path = FLOW_DIR / "samples.jsonl"
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [{**s, "imageUrl": f"/api/flow/samples/{s['id']}.png"} for s in items]


def sample_info() -> dict[str, Any]:
    return {"samples": samples(), "players": [p.model_dump(mode="json") for p in default_players()]}


def logs() -> dict[str, Any]:
    return flow_log.summary()


def sample_image(sample_id: str) -> bytes | None:
    """예시 id → PNG 바이트. 모르는 id 면 None (경로를 직접 받지 않아서 ../ 같은 경로 조작이 없다)."""
    for s in samples():
        if s["id"] == sample_id:
            return (ROOT / s["image"]).read_bytes()
    return None


def resolve_request(body: Any, uploads_dir: Path) -> FlowRequest:
    from clean_chat.sim.server import save_upload  # server 가 이 파일을 import 하므로 여기서 늦게 가져온다

    if not isinstance(body, dict):
        raise FlowInputError("본문은 JSON 객체여야 합니다")
    sample_id = body.get("sample")
    if isinstance(body.get("image"), dict):
        image_path = str(save_upload(body["image"], uploads_dir))
    elif sample_id:
        found = next((s for s in samples() if s["id"] == sample_id), None)
        if found is None:
            raise FlowInputError(f"모르는 예시: {sample_id}")
        image_path = str(ROOT / found["image"])
    else:
        raise FlowInputError("예시 이미지를 고르거나 이미지를 첨부하세요")
    return FlowRequest(
        image_path=image_path,
        ocr_text=str(body.get("ocrText") or ""),
        use_fallback=bool(body.get("useFallback", True)),
        step_delay_ms=max(0, min(3000, int(body.get("stepDelayMs") or 0))),
        sample_id=sample_id if isinstance(sample_id, str) else None,
    )


def _pump(stream, kind: str, q: queue.Queue) -> None:
    for line in iter(stream.readline, ""):
        q.put((kind, line.rstrip("\n")))
    q.put((kind, None))


def run_flow_request(body: Any, emit: Emit, uploads_dir: Path | None = None, timeout: float | None = None) -> None:
    """새 프로세스로 흐름 1번 실행. 단계 이벤트는 {"type":"flow"}, 나머지 출력은 콘솔 줄로 실시간 전달."""
    started = time.perf_counter()
    limit = timeout or settings.sim_timeout_sec

    def result(status: str, error: str | None = None) -> None:
        ms = round((time.perf_counter() - started) * 1000)
        emit({"type": "result", "status": status, "error": error, "durationMs": ms})

    try:
        req = resolve_request(body, uploads_dir or settings.uploads_dir)
    except Exception as e:  # 예시 없음, 이미지 깨짐
        return result("invalid_input", str(e))
    emit({"type": "log", "stream": "system", "text": "$ python -m clean_chat.sim.flow  (새 프로세스)"})

    stopped: str | None = None
    with tempfile.TemporaryDirectory(prefix="clean-chat-flow-") as tmp:
        inp = Path(tmp) / "input.json"
        inp.write_text(req.model_dump_json(), encoding="utf-8")
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "clean_chat.sim.flow", str(inp)],
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
        deadline, open_streams, last_emit = time.monotonic() + limit, 2, time.monotonic()
        try:
            while open_streams:
                left = deadline - time.monotonic()
                if left <= 0:
                    proc.kill()
                    proc.wait()
                    return result("timeout", f"{limit:.0f}초가 지나 실행을 멈췄습니다")
                try:
                    kind, line = q.get(timeout=min(left, 0.5))
                except queue.Empty:
                    if time.monotonic() - last_emit >= 1.0:  # 브라우저가 끊겼는지(중지 버튼) 알아내려고
                        emit({"type": "ping"})
                        last_emit = time.monotonic()
                    continue
                if line is None:
                    open_streams -= 1
                    continue
                last_emit = time.monotonic()
                if kind == "stdout" and line.startswith(MARKER):
                    event = json.loads(line[len(MARKER) :])
                    if event.get("event") == "stopped":
                        stopped = event.get("error") or "멈췄습니다"
                    emit({"type": "flow", **event})
                else:
                    emit({"type": "log", "stream": kind, "text": line})
            code = proc.wait()
        except BaseException:  # ClientGone(중지 버튼) 등 → 프로세스를 끝내고 다시 던짐
            proc.kill()
            proc.wait()
            raise
    if stopped:
        return result("stopped", stopped)
    if code != 0:
        return result("error", f"프로세스가 종료 코드 {code} 로 끝났습니다")
    result("ok")
