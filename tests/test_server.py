"""로컬 모듈 실행 서버 (`clean-chat serve`): 시뮬레이터가 실제 함수를 부르는 통로."""

import base64
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from clean_chat.core import modules
from clean_chat.core.server import Handler, RunError, run_module
from helpers import fixture_pairs


def test_unimplemented_module_is_501():
    inp = fixture_pairs("parse")[0][0].model_dump(mode="json")
    with pytest.raises(RunError) as e:
        run_module("parse", {"input": inp})
    assert e.value.status == 501 and "parse" in str(e.value)


def test_bad_input_is_422():
    with pytest.raises(RunError) as e:
        run_module("parse", {"input": {"line": "줄"}})
    assert e.value.status == 422


def test_unknown_module_is_404():
    with pytest.raises(RunError) as e:
        run_module("classify", {"input": {}})
    assert e.value.status == 404


def test_module_exception_is_500(monkeypatch):
    monkeypatch.setattr(modules, "load", lambda _n: lambda _req: 1 / 0)
    with pytest.raises(RunError) as e:
        run_module("parse", {"input": fixture_pairs("parse")[0][0].model_dump(mode="json")})
    assert e.value.status == 500 and "ZeroDivisionError" in str(e.value)


def test_success_returns_output(monkeypatch):
    req, out = fixture_pairs("parse")[0]
    monkeypatch.setattr(modules, "load", lambda _n: lambda _req: out)
    assert run_module("parse", {"input": req.model_dump(mode="json")}) == {"output": out.model_dump(mode="json")}


def test_image_upload_replaces_image_path(monkeypatch, tmp_path):
    frame, out = fixture_pairs("ocr")[0]
    seen = []
    monkeypatch.setattr(modules, "load", lambda _n: lambda f: seen.append(f) or out)
    image = {"name": "../../evil name.png", "base64": base64.b64encode(b"PNGDATA").decode()}
    run_module("ocr", {"input": frame.model_dump(mode="json"), "image": image}, uploads_dir=tmp_path)
    saved = tmp_path / "evil_name.png"  # 경로 조작 없이 uploads 폴더 안에만
    assert saved.read_bytes() == b"PNGDATA"
    assert seen[0].image_path == str(saved)


def test_image_only_for_modules_with_image_field(tmp_path):
    with pytest.raises(RunError) as e:
        run_module("parse", {"input": {}, "image": {"name": "a.png", "base64": "QUJD"}}, uploads_dir=tmp_path)
    assert e.value.status == 422
    assert not list(tmp_path.iterdir())  # 저장하지 않음


def test_http_roundtrip_and_cors():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        body = json.dumps({"input": fixture_pairs("parse")[0][0].model_dump(mode="json")}).encode()
        req = urllib.request.Request(
            f"{base}/modules/parse/run", body, {"Content-Type": "application/json", "Origin": "http://localhost:3100"}
        )
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 501
        assert e.value.headers["Access-Control-Allow-Origin"] == "http://localhost:3100"
        assert json.loads(e.value.read())["output"] is None
        other = urllib.request.Request(f"{base}/modules", headers={"Origin": "https://evil.example"})
        with urllib.request.urlopen(other, timeout=5) as res:
            assert res.headers["Access-Control-Allow-Origin"] is None  # 로컬 외 출처는 허용 안 함
            assert [m["name"] for m in json.loads(res.read())] == list(modules.MODULE_NAMES)
    finally:
        httpd.shutdown()
        httpd.server_close()
