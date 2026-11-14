"""로컬 모듈 시뮬레이터 (`uv run sim`, ADR-0019): 간단 입력 변환, 하위 프로세스 실행·콘솔 스트림, HTTP."""

import base64
import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from clean_chat.core.modules import MODULE_NAMES, MODULES
from clean_chat.sim import inputs
from clean_chat.sim.server import ClientGone, make_server, module_list, resolve_input, run_module
from helpers import fixture_pairs

TESTS = Path(__file__).parent


def _run(name: str, body, monkeypatch=None, target: str | None = None, timeout: float | None = None, tmp=None):
    if target:
        monkeypatch.setenv("CLEAN_CHAT_SIM_TARGET", f"sim_fakes:{target}")
        monkeypatch.setenv("PYTHONPATH", str(TESTS))
    events: list[dict] = []
    run_module(name, body, events.append, uploads_dir=tmp, timeout=timeout)
    logs = [e for e in events if e["type"] == "log"]
    assert {e["type"] for e in events} <= {"log", "ping", "result"}
    (result,) = [e for e in events if e["type"] == "result"]
    assert events[-1] is result  # 결과는 항상 마지막
    return logs, result


def _text(logs) -> str:
    return "\n".join(e["text"] for e in logs)


# ── 간단 입력 ──
@pytest.mark.parametrize("name", ["parse", "analyze", "rewrite"])
def test_simple_inputs_validate(name):
    simple = {f["key"]: f.get("default", "") for f in inputs.FORMS[name]}
    data = inputs.build(name, simple)
    MODULES[name].input_model.model_validate(data)


def test_simple_parse_self_input_and_ocr_image():
    data = inputs.build("parse", {"text": "아 정글 ㅂㅅ 왜 안 와", "self_input": True})
    assert data["line"]["source"] == "self_input"
    frame = inputs.build("ocr", {}, image_path="/tmp/a.png")
    assert frame["image_path"] == "/tmp/a.png"


@pytest.mark.parametrize(("name", "simple"), [("parse", {"text": "  "}), ("ocr", {}), ("report", {"text": "x"})])
def test_simple_input_errors(name, simple):
    with pytest.raises(inputs.SimpleInputError):
        inputs.build(name, simple)


def test_image_saved_safely_and_only_for_image_modules(tmp_path):
    img = {"name": "../../evil name.png", "base64": base64.b64encode(b"PNG").decode()}
    data = resolve_input("ocr", {"simple": {}, "image": img}, tmp_path)
    assert data["image_path"] == str(tmp_path / "evil_name.png")
    assert (tmp_path / "evil_name.png").read_bytes() == b"PNG"
    with pytest.raises(inputs.SimpleInputError):
        resolve_input("parse", {"simple": {"text": "x"}, "image": img}, tmp_path)


# ── 실행 (하위 프로세스) ──
def test_unimplemented_module_streams_steps_and_not_implemented():
    logs, result = _run("parse", {"simple": {"text": "[팀] 원딜러 (징크스): ㅎㅇ"}})
    assert result["status"] == "not_implemented" and "parse" in result["error"]
    text = _text(logs)
    assert "입력 검증" in text and "run() 실행" in text and "구현이 아직 없습니다" in text
    assert result["input"]["line"]["text"] == "[팀] 원딜러 (징크스): ㅎㅇ"  # 변환된 입력도 돌려줌


def test_ok_shows_prints_logs_and_output(monkeypatch):
    req = fixture_pairs("parse")[0][0].model_dump(mode="json")
    logs, result = _run("parse", {"input": req}, monkeypatch, target="ok")
    assert result["status"] == "ok"
    assert result["output"] == {"line_id": req["line"]["id"], "message": None}
    text = _text(logs)
    assert "디버그 출력: 줄 분해 시작" in text and "로그도 콘솔로" in text and "출력 형식 OK" in text
    assert any(e["stream"] == "stderr" for e in logs)  # logging 은 stderr


def test_exception_shows_traceback(monkeypatch):
    req = fixture_pairs("parse")[0][0].model_dump(mode="json")
    logs, result = _run("parse", {"input": req}, monkeypatch, target="boom")
    assert result["status"] == "error" and "일부러 낸 오류" in result["error"]
    assert "Traceback" in _text(logs) and "곧 터짐" in _text(logs)


def test_wrong_output_type_is_error(monkeypatch):
    req = fixture_pairs("parse")[0][0].model_dump(mode="json")
    _logs, result = _run("parse", {"input": req}, monkeypatch, target="wrong_type")
    assert result["status"] == "error"


def test_invalid_json_input():
    logs, result = _run("parse", {"input": {"line": "줄"}})
    assert result["status"] == "invalid_input" and "ParseRequest" in result["error"]


def test_timeout_kills_process(monkeypatch):
    req = fixture_pairs("parse")[0][0].model_dump(mode="json")
    logs, result = _run("parse", {"input": req}, monkeypatch, target="slow", timeout=3)
    assert result["status"] == "timeout"
    assert "오래 걸림" in _text(logs)


def test_client_gone_while_module_is_silent_stops_process(monkeypatch):
    """출력 없이 오래 도는 모듈도 중지 버튼(연결 끊김)을 1초 안팎에 알아채고 끝낸다 (ping)."""
    monkeypatch.setenv("CLEAN_CHAT_SIM_TARGET", "sim_fakes:slow")
    monkeypatch.setenv("PYTHONPATH", str(TESTS))
    req = fixture_pairs("parse")[0][0].model_dump(mode="json")
    seen = []

    def emit(event):
        seen.append(event["type"])
        if event["type"] == "ping":  # 모듈은 sleep 중 (출력 없음) → 이때 브라우저가 끊김
            raise ClientGone

    t0 = time.monotonic()
    with pytest.raises(ClientGone):
        run_module("parse", {"input": req}, emit, timeout=20)
    assert time.monotonic() - t0 < 10 and "ping" in seen


def test_unknown_module():
    _logs, result = _run("classify", {"input": {}})
    assert result["status"] == "invalid_input"


# ── 화면 · HTTP ──
def test_module_list_has_forms_and_examples():
    items = module_list()
    assert [m["name"] for m in items] == list(MODULE_NAMES)
    for m in items:
        assert m["examples"] and m["schema"]["title"] == m["inputModel"]
    assert next(m for m in items if m["name"] == "ocr")["form"][0]["type"] == "image"


def test_http_static_api_and_stream():
    httpd = make_server(0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/", timeout=5) as r:
            assert "모듈 시뮬레이터" in r.read().decode()
        for path in ("/app.js", "/style.css"):
            with urllib.request.urlopen(base + path, timeout=5) as r:
                assert r.status == 200
        with urllib.request.urlopen(f"{base}/api/modules", timeout=5) as r:
            assert len(json.loads(r.read())) == 5
        body = json.dumps({"simple": {"text": "[팀] 원딜러 (징크스): ㅎㅇ"}}).encode()
        req = urllib.request.Request(f"{base}/api/modules/parse/run", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            assert r.headers["Content-Type"].startswith("application/x-ndjson")
            events = [json.loads(line) for line in r.read().decode().splitlines() if line.strip()]
        assert events[0]["type"] == "log" and events[-1]["type"] == "result"
        assert events[-1]["status"] == "not_implemented"
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/../pyproject.toml", timeout=5)
        assert e.value.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()
