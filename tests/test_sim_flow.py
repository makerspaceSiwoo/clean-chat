"""전체 흐름 시뮬레이션 (`uv run sim flow`): 캡처 이미지 → ocr → parse → analyze → rewrite → 정책 → report.

모듈이 구현되기 전에도 끝까지 돌도록 가정 응답(sim/fallback.py)으로 대신하는지, 구현된 모듈은 실제로 부르는지 본다.
결과 내용 검사는 모든 모듈을 가정 응답으로 강제한 상태에서만 한다 (실제 모듈이 들어와도 테스트가 깨지지 않게).
"""

import base64
import json
import threading
import urllib.request

import pytest

from clean_chat.core import modules
from clean_chat.core.schemas import ParseRequest, RawLine, Source
from clean_chat.sim import fallback, flow_api
from clean_chat.sim.flow import FlowRequest, FlowStopped, run_flow
from clean_chat.sim.server import make_server


def _not_implemented(item):
    raise NotImplementedError("테스트: 구현 전")


@pytest.fixture
def all_fallback(monkeypatch):
    """실제 모듈이 있어도 전부 구현 전으로 보이게 → 가정 응답만으로 흐름 확인."""
    monkeypatch.setattr(modules, "load", lambda name: _not_implemented)


def _sample(sample_id: str) -> dict:
    return next(s for s in flow_api.samples() if s["id"] == sample_id)


def _run(sample_id: str, **kw) -> list[dict]:
    s = _sample(sample_id)
    events: list[dict] = []
    req = FlowRequest(image_path=s["image"], ocr_text="\n".join(s["lines"]), **kw)
    run_flow(req, events.append)
    return events


def _incidents(events):
    return [e["incident"] for e in events if e["event"] == "incident"]


def _post_game(events):
    return next(e["result"] for e in events if e["event"] == "post_game")


# ── 가정 응답 ──
def test_fallback_parse_chat_system_and_self_input():
    def parse(text, source=Source.OCR):
        return fallback.parse(ParseRequest(line=RawLine(id="x", ts=0, text=text, source=source), my_name="나"))

    msg = parse("[03:43] [전체] 감자튀김 (룰루): ㅂㅅ같이 하네").message
    assert (msg.speaker, msg.champion, msg.channel, msg.text) == ("감자튀김", "룰루", "all", "ㅂㅅ같이 하네")
    assert parse("[03:43] 불꽃남자 (징크스): 미드 차이 ㅋ").message.channel == "team"  # [전체] 없으면 팀
    assert parse("[03:46] 불꽃남자 (징크스)님이 연속 킬을 차단했습니다! (총 처치 보상: 600골드)").message is None
    assert parse("[04:16] 초코우유 (리신)님이 전설적입니다!").message is None
    me = parse("용 먼저 치자", Source.SELF_INPUT).message
    assert me.is_me and me.speaker == "나"


# ── 흐름 (모두 가정 응답) ──
def test_clean_sample_shows_everything_and_reports_nothing(all_fallback):
    events = _run("clean")
    incs = _incidents(events)
    assert incs and all(i["decision"]["action"] == "show" for i in incs)
    assert _post_game(events) == {"session_id": _post_game(events)["session_id"], "reports": [], "complaints": []}
    calls = [e for e in events if e["event"] == "call"]
    assert {c["mode"] for c in calls} == {"fallback"}
    assert not [c for c in calls if c["module"] in ("rewrite", "report")]  # 조건이 안 맞으면 부르지 않음


def test_abusive_sample_masks_hides_and_reports(all_fallback):
    events = _run("abusive")
    actions = {i["msg"]["text"]: i["decision"]["action"] for i in _incidents(events)}
    assert actions["ㅂㅅ같이 하네 kkkk ^^; omw ㅇㅇㅇ"] == "show_masked"
    assert actions["ZZZZZZZZ 넌 그냥 탈주해 ♡♡♡"] == "hide"
    assert {r["speaker"] for r in _post_game(events)["reports"]} == {"별빛라면", "불꽃남자"}
    assert events[-1] == {"event": "done", "summary": events[-1]["summary"]}


def test_blame_feedback_sample_rewrites(all_fallback):
    events = _run("blame_feedback")
    rewritten = [i for i in _incidents(events) if i["decision"]["action"] == "show_rewritten"]
    assert [i["decision"]["display_text"] for i in rewritten] == ["용 앞 시야 없어요"]
    assert any(e["event"] == "call" and e["module"] == "rewrite" for e in events)


def test_l3_line_makes_complaint(all_fallback):
    events: list[dict] = []
    run_flow(FlowRequest(image_path="x.png", ocr_text="[01:00] [전체] 얼음땡 (다리우스): 서폿 니애미"), events.append)
    (complaint,) = _post_game(events)["complaints"]
    assert complaint["kind"] == "complaint" and complaint["speaker"] == "얼음땡"


def test_without_fallback_stops_at_first_missing_module(all_fallback):
    with pytest.raises(FlowStopped, match=r"\[ocr\]"):
        _run("abusive", use_fallback=False)


def test_implemented_module_is_called_for_real(monkeypatch):
    real = {"parse": fallback.parse}  # parse 만 "구현됨"
    monkeypatch.setattr(modules, "load", lambda name: real.get(name, _not_implemented))
    events = _run("abusive")
    modes = {(e["module"], e["mode"]) for e in events if e["event"] == "call"}
    assert ("parse", "real") in modes and ("parse", "fallback") not in modes
    assert ("analyze", "fallback") in modes


def test_module_error_falls_back_per_call(monkeypatch, capsys):
    def broken(item):
        raise ValueError("모듈 안 오류")

    monkeypatch.setattr(modules, "load", lambda name: broken)
    events = _run("clean")
    ocr = next(e for e in events if e["event"] == "call")
    assert ocr["mode"] == "fallback" and "ValueError" in ocr["reason"]
    assert "모듈 안 오류" in capsys.readouterr().err  # traceback 은 디버깅 콘솔로


# ── 서버 (새 프로세스 + HTTP) ──
def test_run_flow_request_streams_steps_in_subprocess(tmp_path):
    events: list[dict] = []
    flow_api.run_flow_request(
        {"sample": "abusive", "ocrText": "\n".join(_sample("abusive")["lines"])}, events.append, tmp_path
    )
    assert events[-1]["type"] == "result" and events[-1]["status"] == "ok"
    kinds = [e.get("event") for e in events if e["type"] == "flow"]
    assert kinds[:2] == ["start", "phase"] and "post_game" in kinds and kinds[-1] == "done"
    assert isinstance(events[1]["pid"], int)  # 매번 새 프로세스


def test_run_flow_request_input_errors(tmp_path):
    for body in ({"sample": "nope"}, {}, [1]):
        events: list[dict] = []
        flow_api.run_flow_request(body, events.append, tmp_path)
        assert events == [events[0]] and events[0]["status"] == "invalid_input"


def test_uploaded_image_is_saved(tmp_path):
    img = {"name": "../캡처.png", "base64": base64.b64encode(b"PNG").decode()}
    req = flow_api.resolve_request({"image": img, "ocrText": "a"}, tmp_path)
    assert req.image_path == str(tmp_path / "캡처.png") and req.ocr_text == "a"


def test_http_flow_page_samples_and_images():
    httpd = make_server(0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/flow", timeout=5) as r:
            assert "전체 흐름" in r.read().decode()
        for path in ("/flow.js", "/flow.css"):
            with urllib.request.urlopen(base + path, timeout=5) as r:
                assert r.status == 200
        with urllib.request.urlopen(f"{base}/api/flow/samples", timeout=5) as r:
            info = json.loads(r.read())
        assert {s["id"] for s in info["samples"]} == {"clean", "abusive", "blame_feedback"}
        assert any(p["is_me"] for p in info["players"])
        with urllib.request.urlopen(base + info["samples"][0]["imageUrl"], timeout=5) as r:
            assert r.headers["Content-Type"] == "image/png" and r.read()[:4] == b"\x89PNG"
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/api/flow/samples/nope.png", timeout=5)
        assert e.value.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_missing_package_error_hints_extra(monkeypatch):
    def needs_pkg(item):
        raise ModuleNotFoundError("No module named 'reportlab'")

    monkeypatch.setattr(modules, "load", lambda name: needs_pkg)
    ocr = next(e for e in _run("clean") if e["event"] == "call")
    assert "uv run --extra ocr sim flow" in ocr["reason"]


def test_steps_stream_in_order_one_line_at_a_time(all_fallback):
    events = _run("abusive")
    kinds = [(e["event"], e.get("module")) for e in events if e["event"] in ("call_start", "call", "incident")]
    # 모든 호출은 call_start → call 짝으로, 다른 호출과 겹치지 않는다
    calls = [k for k in kinds if k[0] != "incident"]
    assert calls[0::2] == [("call_start", m) for _, m in calls[1::2]]
    assert [m for _, m in calls[1::2]] == [m for _, m in calls[0::2]]
    # 줄 하나가 끝나면 바로 incident 가 나온다 (모든 줄을 다 처리한 뒤 한꺼번에가 아니라)
    first_incident = kinds.index(("incident", None))
    assert ("call_start", "parse") in kinds[first_incident:]


def test_step_delay_pauses_between_calls(all_fallback):
    import time

    started = time.perf_counter()
    events = _run("clean", step_delay_ms=20)
    n_calls = sum(e["event"] == "call" for e in events)
    assert time.perf_counter() - started >= n_calls * 0.02
    assert all(e["ms"] < 1000 for e in events if e["event"] == "call")  # 멈춤은 계산 시간(ms)에 넣지 않는다
