"""rewrite 계약·실패 경로·개인정보·시간 제한. 실제 API 키나 네트워크를 쓰지 않는다."""

from __future__ import annotations

import copy
import json
import threading
import time

import pytest

from clean_chat.core import modules
from clean_chat.core.schemas import RewriteRequest
from clean_chat.modules.rewrite import backend, impl
from helpers import check_module, fixture_pairs


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(backend, "options", lambda: {"LLM_BACKEND": "rule", "LLM_MODEL": "test"})
    monkeypatch.setattr(backend, "_SLOT", threading.BoundedSemaphore(1))


def request(text="야 정글 ㅂㅅ아 용 먼저 치라고", spans=None):
    data = fixture_pairs("rewrite")[0][0].model_dump()
    data["message"].update(text=text, text_norm=text)
    data["analysis"]["feedback_spans"] = ["용 먼저 치라고"] if spans is None else spans
    return RewriteRequest.model_validate(data)


def api(monkeypatch, output):
    monkeypatch.setattr(
        backend, "options", lambda: {"LLM_BACKEND": "api", "LLM_API_KEY": "test-secret", "LLM_MODEL": "test"}
    )
    monkeypatch.setattr(backend, "complete", lambda *args: output)


def test_rewrite_fixtures():
    check_module("rewrite", strict=False)
    for req, expected in fixture_pairs("rewrite"):
        result = modules.call("rewrite", req)
        assert result.rewritten == expected.rewritten
        assert result.msg_id == expected.msg_id
        assert result.backend == "rule"


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        ("와드 좀 박아", "와드 설치 부탁해요"),
        ("빼라고", "뒤로 빠져 주세요"),
        ("들어가지 마", "들어가지 말아 주세요"),
        ("용 치지 말라고", "용 치지 말아 주세요"),
    ],
)
def test_rule_preserves_feedback_and_negation(span, expected):
    assert impl.run(request(span, [span])).rewritten == expected


@pytest.mark.parametrize("spans", [[], [""], ["바론 쳐"], ["용 먼저 치라고", "용 먼저 치라고 바론"], ["ㅂㅅ"]])
def test_empty_invented_or_abusive_spans_are_rejected(spans):
    assert impl.run(request(spans=spans)).rewritten is None


def test_unknown_feedback_is_not_invented():
    assert impl.run(request("상황을 좀 봐", ["상황을 좀 봐"])).rewritten is None


def test_invalid_analysis_does_not_call_api(monkeypatch):
    api(monkeypatch, "용 먼저 치자")
    req = request()
    req.analysis.level = 1
    assert impl.run(req).rewritten is None
    req.analysis.level = 2
    req.analysis.msg_id = "different"
    assert impl.run(req).rewritten is None


def test_run_does_not_mutate_evidence():
    req = request()
    before = copy.deepcopy(req.model_dump())
    impl.run(req)
    assert req.model_dump() == before


def test_api_success_cleaning_and_backend(monkeypatch):
    api(monkeypatch, "순화 문장: “용 먼저 치자”")
    result = impl.run(request())
    assert result.rewritten == "용 먼저 치자"
    assert result.backend == "api"


@pytest.mark.parametrize(
    "generated",
    [
        "용 먼저 치자 병신",
        "용 먼저 치자 ㅂ ㅅ",
        "용 먼저 치자 시\u200b발",
        "용 먼저 치자 f.u.c.k",
        "바론 먼저 치자",
        "용 3번 치자",
        "용 먼저 치자. 와드 설치하자",
        "용 먼저 치지 말자",
        "용 먼저 쳐",
        "",
        "<script>용 먼저 치자</script>",
        "용 먼저 치자: 설명",
        "불꽃남자 용 먼저 치자",
    ],
)
def test_unsafe_or_invented_api_output_is_null(monkeypatch, generated):
    api(monkeypatch, generated)
    result = impl.run(request())
    assert result.rewritten is None
    assert result.backend == "api"


def test_api_cannot_restore_unselected_context(monkeypatch):
    api(monkeypatch, "바론 먼저 치자")
    assert impl.run(request("바론도 치고 용 먼저 치라고", ["용 먼저 치라고"])).rewritten is None


def test_negative_feedback_cannot_become_positive(monkeypatch):
    api(monkeypatch, "용 먼저 치자")
    assert impl.run(request("용 치지 말라고", ["용 치지 말라고"])).rewritten is None


def test_known_names_are_redacted_before_network(monkeypatch):
    api(monkeypatch, "용 먼저 치자")
    prompts = []
    monkeypatch.setattr(backend, "complete", lambda prompt, *_: prompts.append(prompt) or "용 먼저 치자")
    req = request("불꽃남자야 초코우유한테 용 먼저 치라고", ["용 먼저 치라고"])
    impl.run(req)
    payload = json.loads(prompts[0])
    assert set(payload) == {"text", "feedback_spans"}
    assert "불꽃남자" not in prompts[0] and "초코우유" not in prompts[0]
    assert "speaker" not in prompts[0] and req.message.raw not in prompts[0]


def test_name_inside_feedback_is_not_sent(monkeypatch):
    api(monkeypatch, "용 먼저 치자")
    monkeypatch.setattr(backend, "complete", lambda *_: pytest.fail("닉네임을 전송하면 안 됨"))
    assert impl.run(request("초코우유 용 먼저 치라고", ["초코우유 용 먼저 치라고"])).rewritten is None


@pytest.mark.parametrize("output", [None])
def test_failed_api_uses_known_rule(monkeypatch, output):
    api(monkeypatch, output)
    result = impl.run(request())
    assert result.rewritten == "용 먼저 치자" and result.backend == "rule"


def test_unsupported_backend_is_safe(monkeypatch):
    monkeypatch.setattr(backend, "options", lambda: {"LLM_BACKEND": "local"})
    assert impl.run(request()).rewritten is None


def test_env_file_and_environment_precedence(monkeypatch, tmp_path):
    # autouse의 가짜 options 대신 원래 함수를 아래 별도 참조로 사용한다.
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    (tmp_path / ".env").write_text('LLM_API_KEY="file-key" # 주석\nLLM_MODEL=file-model\n', encoding="utf-8")
    for key in ("LLM_API_KEY", "GEMINI_API_KEY", "LLM_MODEL", "LLM_BACKEND"):
        monkeypatch.delenv(key, raising=False)
    assert REAL_OPTIONS()["LLM_API_KEY"] == "file-key"
    monkeypatch.setenv("LLM_API_KEY", "environment-key")
    assert REAL_OPTIONS()["LLM_API_KEY"] == "environment-key"
    monkeypatch.setenv("LLM_API_KEY", "")
    assert REAL_OPTIONS()["LLM_API_KEY"] == ""


REAL_OPTIONS = backend.options


def response(content="용 먼저 치자", finish="stop"):
    return {
        "choices": [
            {"finish_reason": finish, "message": {"content": json.dumps({"rewritten": content}, ensure_ascii=False)}}
        ]
    }


def test_litellm_gemini_contract(monkeypatch):
    captured = []

    def completion_fake(**kwargs):
        captured.append(kwargs)
        return response()

    monkeypatch.setattr(backend, "_completion", completion_fake)
    assert backend._request('{"text":"용 먼저 치라고"}', "test-key", "gemini/test-model", 0.5) == "용 먼저 치자"
    (data,) = captured
    assert data["model"] == "gemini/test-model"
    assert data["api_key"] == "test-key"
    assert data["timeout"] == 0.5 and data["num_retries"] == 0
    assert data["response_format"] == {"type": "json_object"}
    assert json.loads(data["messages"][1]["content"]) == {"text": "용 먼저 치라고"}


@pytest.mark.parametrize(
    "body",
    [
        {},
        response(finish="length"),
        response(None),
        {"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": "x" * 17000}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": "[]"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": '{"rewritten": 4}'}}]},
    ],
)
def test_bad_litellm_response_does_not_crash(monkeypatch, body):
    monkeypatch.setattr(backend, "_completion", lambda **_kwargs: body)
    assert backend.complete("test", 0.2, {"LLM_API_KEY": "test", "LLM_MODEL": "gemini/test"}) is None


@pytest.mark.parametrize("error", [TimeoutError(), ConnectionError("offline"), ValueError("bad")])
def test_network_failure_is_safe(monkeypatch, error):
    def fail(*_):
        raise error

    monkeypatch.setattr(backend, "_request", fail)
    assert backend.complete("test", 0.2, {"LLM_API_KEY": "test", "LLM_MODEL": "test"}) is None


def test_deadline_and_busy_worker(monkeypatch):
    release = threading.Event()
    entered = threading.Event()

    def hang(*_):
        entered.set()
        release.wait(2)
        return "용 먼저 치자"

    monkeypatch.setattr(backend, "_request", hang)
    config = {"LLM_API_KEY": "test", "LLM_MODEL": "test"}
    try:
        started = time.monotonic()
        assert backend.complete("test", 0.05, config) is None
        assert entered.is_set()
        assert time.monotonic() - started < 0.5
        started = time.monotonic()
        assert backend.complete("test", 0.5, config) is None
        assert time.monotonic() - started < 0.2
    finally:
        release.set()


def test_no_key_never_calls_network(monkeypatch):
    monkeypatch.setattr(backend, "_request", lambda *_: pytest.fail("키 없이 호출하면 안 됨"))
    assert backend.complete("test", 0.1, {"LLM_MODEL": "test"}) is None


def test_simulator_worker_returns_ok(monkeypatch, tmp_path):
    from clean_chat.sim.worker import main

    inp, out = tmp_path / "input.json", tmp_path / "output.json"
    inp.write_text(request().model_dump_json(), encoding="utf-8")
    monkeypatch.delenv("CLEAN_CHAT_SIM_TARGET", raising=False)
    assert main(["rewrite", str(inp), str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert data["output"]["rewritten"] == "용 먼저 치자"
    assert data["durationMs"] < 3000


def test_only_selected_feedback_goes_to_api(monkeypatch):
    api(monkeypatch, "용 먼저 치자")
    prompts = []
    monkeypatch.setattr(backend, "complete", lambda prompt, *_: prompts.append(prompt) or "용 먼저 치자")
    impl.run(request("달빛고양이한테 비밀 얘기하고 바론도 치고 용 먼저 치라고", ["용 먼저 치라고"]))
    assert json.loads(prompts[0]) == {"text": "용 먼저 치라고", "feedback_spans": ["용 먼저 치라고"]}


def test_api_cannot_drop_feedback_objective(monkeypatch):
    api(monkeypatch, "잘하자")
    assert impl.run(request()).rewritten is None


def test_full_run_returns_before_three_seconds(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(backend, "options", lambda: {"LLM_BACKEND": "api", "LLM_API_KEY": "test", "LLM_MODEL": "test"})
    monkeypatch.setattr(backend, "_request", lambda *_: release.wait(5) and "용 먼저 치자")
    try:
        started = time.monotonic()
        result = impl.run(request())
        assert time.monotonic() - started < 3
        assert result.rewritten == "용 먼저 치자" and result.backend == "rule"
    finally:
        release.set()


def test_simulator_subprocess_with_simple_input(monkeypatch, tmp_path):
    from clean_chat.sim.server import run_module

    monkeypatch.setenv("LLM_BACKEND", "rule")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("PYTHONUTF8", "1")
    monkeypatch.delenv("CLEAN_CHAT_SIM_TARGET", raising=False)
    events = []
    run_module(
        "rewrite",
        {"simple": {"text": "야 정글 ㅂㅅ아 용 먼저 치라고", "feedback": "용 먼저 치라고"}},
        events.append,
        uploads_dir=tmp_path,
    )
    (result,) = [event for event in events if event["type"] == "result"]
    assert result["status"] == "ok"
    assert result["output"]["rewritten"] == "용 먼저 치자"
    assert result["durationMs"] < 3000


def test_model_not_ready_never_calls_sdk(monkeypatch, caplog):
    monkeypatch.setattr(backend, "_completion", lambda **_: pytest.fail("모델 없이 호출하면 안 됨"))
    with caplog.at_level("INFO"):
        assert backend.complete("test", 0.1, {"LLM_API_KEY": "test", "LLM_MODEL": ""}) is None
    assert "키/모델이 준비되지" in caplog.text


def test_gemini_key_alias_and_model_normalization(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    for key in ("LLM_API_KEY", "GEMINI_API_KEY", "LLM_MODEL", "LLM_BACKEND"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text(
        "GEMINI_API_KEY=gemini-key\nLLM_API_KEY=legacy-key\nLLM_MODEL=team-model\n", encoding="utf-8"
    )
    assert REAL_OPTIONS()["LLM_API_KEY"] == "gemini-key"
    assert REAL_OPTIONS()["LLM_MODEL"] == "gemini/team-model"
    monkeypatch.setenv("GEMINI_API_KEY", "environment-gemini-key")
    monkeypatch.setenv("LLM_MODEL", "gemini/team-model-2")
    assert REAL_OPTIONS()["LLM_API_KEY"] == "environment-gemini-key"
    assert REAL_OPTIONS()["LLM_MODEL"] == "gemini/team-model-2"


def test_no_default_model_before_team_decides(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    for key in ("LLM_API_KEY", "GEMINI_API_KEY", "LLM_MODEL", "LLM_BACKEND"):
        monkeypatch.delenv(key, raising=False)
    assert REAL_OPTIONS()["LLM_MODEL"] == ""


def test_other_provider_is_not_called(monkeypatch):
    monkeypatch.setattr(backend, "_completion", lambda **_: pytest.fail("Gemini 외 제공자 호출 금지"))
    assert backend._request("test", "test", "openai/test", 0.2) is None


def test_rule_and_null_reasons_are_visible(monkeypatch, caplog):
    with caplog.at_level("INFO"):
        assert impl.run(request()).backend == "rule"
        assert impl.run(request("야 뭐하냐고", ["야 뭐하냐고"])).rewritten is None
    assert "AI 생성이 아닌" in caplog.text
    assert "규칙에 없는 표현" in caplog.text


def test_real_litellm_mock_response_without_key(monkeypatch):
    import importlib.util
    import os
    import subprocess
    import sys

    if importlib.util.find_spec("litellm") is None:
        pytest.skip("선택 의존성: uv sync --extra rewrite")
    env = dict(os.environ, LITELLM_LOCAL_MODEL_COST_MAP="True", PYTHONUTF8="1")
    for key in ("GEMINI_API_KEY", "LLM_API_KEY", "GOOGLE_API_KEY"):
        env.pop(key, None)
    script = """
import json, logging
logging.basicConfig(level=logging.WARNING)
from clean_chat.modules.rewrite import backend
result = backend._completion(model='gemini/gemini-2.5-flash', messages=[{'role':'user','content':'test'}], mock_response='{"rewritten":"ok"}')
assert json.loads(result.choices[0].message.content)['rewritten'] == 'ok'
"""
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr


def test_prepare_requires_model_and_key(monkeypatch):
    monkeypatch.setattr(backend, "_sdk", lambda: pytest.fail("설정 없이 로딩하면 안 됨"))
    backend.prepare()


def test_prepare_loads_sdk_without_completion(monkeypatch):
    calls = []
    monkeypatch.setattr(
        backend, "options", lambda: {"LLM_BACKEND": "api", "LLM_API_KEY": "test", "LLM_MODEL": "gemini/test"}
    )
    monkeypatch.setattr(backend, "_sdk", lambda: calls.append(True))
    backend.prepare()
    assert calls == [True]


@pytest.mark.parametrize(
    ("feedback", "generated"),
    [
        ("미니맵 좀 보라고", "미니맵을 조금 더 신경 써주시면 감사하겠습니다."),
        ("혼자 들어가지 말라고", "무리하게 혼자 들어가는 것은 자제해 주세요."),
        ("용 먼저 치라고", "용 먼저 쳐 주시겠어요?"),
    ],
)
def test_polite_live_response_regressions(monkeypatch, feedback, generated):
    api(monkeypatch, generated)
    result = impl.run(request("야 ㅂㅅ아 " + feedback, [feedback]))
    assert result.rewritten == generated
    assert result.backend == "api"
