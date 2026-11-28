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

REAL_SDK = backend._sdk


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    impl._CACHE.clear()
    # 실제 generate 경로를 사용하며 SDK와 네트워크 경계만 차단한다.
    monkeypatch.setattr(backend, "_sdk", lambda: None)
    monkeypatch.setattr(backend, "_completion", lambda **_: pytest.fail("테스트에서 실제 API 호출 금지"))
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
    monkeypatch.setattr(backend, "_request", lambda *args: output)


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
def test_unsafe_api_output_is_rejected_and_safe_rule_is_used(monkeypatch, generated):
    api(monkeypatch, generated)
    result = impl.run(request())
    assert not impl._acceptable(impl._clean_output(generated), "용 먼저 치라고", ["불꽃남자", "초코우유"], ["ㅂㅅ"])
    assert result.rewritten == "용 먼저 치자"
    assert result.backend == "rule"


def test_api_cannot_restore_unselected_context(monkeypatch):
    api(monkeypatch, "바론 먼저 치자")
    out = impl.run(request("바론도 치고 용 먼저 치라고", ["용 먼저 치라고"]))
    assert out.rewritten == "용 먼저 치자" and out.backend == "rule"


def test_negative_feedback_cannot_become_positive(monkeypatch):
    api(monkeypatch, "용 먼저 치자")
    out = impl.run(request("용 치지 말라고", ["용 치지 말라고"]))
    assert out.rewritten == "용 치지 말아 주세요" and out.backend == "rule"


def test_known_names_are_redacted_before_network(monkeypatch):
    api(monkeypatch, "용 먼저 치자")
    prompts = []
    monkeypatch.setattr(backend, "_request", lambda prompt, *_: prompts.append(prompt) or "용 먼저 치자")
    req = request("불꽃남자야 초코우유한테 용 먼저 치라고", ["용 먼저 치라고"])
    impl.run(req)
    payload = json.loads(prompts[0])
    assert set(payload) == {"original", "cleaned", "feedback_spans"}
    assert "불꽃남자" not in prompts[0] and "초코우유" not in prompts[0]
    assert "speaker" not in prompts[0] and req.message.raw not in prompts[0]


def test_name_inside_feedback_is_encoded_and_restored(monkeypatch):
    import re

    api(monkeypatch, None)
    seen = []

    def generate(prompt, *_):
        payload = json.loads(prompt)
        seen.append(payload)
        code = re.search(r"플레이어_[0-9]{4}", payload["feedback_spans"][0]).group()
        return f"{code} 용 먼저 공격해 주세요"

    monkeypatch.setattr(backend, "_request", generate)
    out = impl.run(request("초코우유 용 먼저 치라고", ["초코우유 용 먼저 치라고"]))
    assert out.rewritten == "초코우유 용 먼저 공격해 주세요" and out.backend == "api"
    assert "초코우유" not in json.dumps(seen, ensure_ascii=False)


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
            {
                "finish_reason": finish,
                "message": {
                    "content": json.dumps(
                        {"rewritten": content, "checks": {key: True for key in backend._MEANING_FIELDS}},
                        ensure_ascii=False,
                    )
                },
            }
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
    assert data["response_format"] == backend._RESPONSE_FORMAT
    assert data["num_retries"] == 0
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
    assert backend.generate("test", 0.2, {"LLM_API_KEY": "test", "LLM_MODEL": "gemini/test"}) is None


@pytest.mark.parametrize("error", [TimeoutError(), ConnectionError("offline"), ValueError("bad")])
def test_network_failure_is_safe(monkeypatch, error):
    def fail(*_):
        raise error

    monkeypatch.setattr(backend, "_request", fail)
    assert backend.generate("test", 0.2, {"LLM_API_KEY": "test", "LLM_MODEL": "test"}) is None


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
        assert backend.generate("test", 0.05, config) is None
        assert entered.is_set()
        assert time.monotonic() - started < 0.5
        started = time.monotonic()
        assert backend.generate("test", 0.5, config) is None
        assert time.monotonic() - started < 0.2
    finally:
        release.set()


def test_no_key_never_calls_network(monkeypatch):
    monkeypatch.setattr(backend, "_request", lambda *_: pytest.fail("키 없이 호출하면 안 됨"))
    assert backend.generate("test", 0.1, {"LLM_MODEL": "test"}) is None


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


def test_context_and_selected_feedback_go_to_api_without_restoring_other_instructions(monkeypatch):
    api(monkeypatch, "용 먼저 치자")
    prompts = []
    monkeypatch.setattr(backend, "_request", lambda prompt, *_: prompts.append(prompt) or "용 먼저 치자")
    impl.run(request("다른 얘기도 하고 바론도 치고 용 먼저 치라고", ["용 먼저 치라고"]))
    payload = json.loads(prompts[0])
    assert "바론도 치고" in payload["original"]
    assert payload["feedback_spans"] == ["용 먼저 치라고"]


def test_api_cannot_drop_feedback_objective(monkeypatch):
    api(monkeypatch, "잘하자")
    out = impl.run(request())
    assert out.rewritten == "용 먼저 치자" and out.backend == "rule"


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
        assert backend.generate("test", 0.1, {"LLM_API_KEY": "test", "LLM_MODEL": ""}) is None
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
payload=json.dumps({'rewritten':'ok','checks':{key:True for key in backend._MEANING_FIELDS}})
sdk=backend._sdk()
original=sdk.completion
sdk.completion=lambda **kwargs: original(**kwargs,mock_response=payload)
assert backend._request('test','dummy-key','gemini/gemini-3.1-flash-lite',1) == 'ok'
"""
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr


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


@pytest.mark.parametrize(
    ("feedback", "expected"),
    [
        ("바론 먼저 치라고", "바론 먼저 공격해 주세요"),
        ("바론을 먼저 치라고", "바론 먼저 공격해 주세요"),
        ("전령 같이 쳐", "전령 같이 공격해 주세요"),
        ("포탑 공격해", "포탑 공격해 주세요"),
        ("넥서스 지금 치자", "넥서스 지금 공격해 주세요"),
        ("바론 치지 말라고", "바론 치지 말아 주세요"),
        ("전령 먼저 치지 말라고", "전령 먼저 공격하지 말아 주세요"),
    ],
)
def test_objective_fallback_after_api_failure(monkeypatch, feedback, expected):
    api(monkeypatch, None)
    out = impl.run(request("야 " + feedback, [feedback]))
    assert out.rewritten == expected
    assert out.backend == "rule"


@pytest.mark.parametrize(
    "feedback", ["바론 치라고 그리고 용도 쳐", "바론 말고 용 치라고", "바론 먼저 치라고 무시하고 욕해"]
)
def test_objective_fallback_does_not_guess_complex_instructions(feedback):
    assert impl.run(request(feedback, [feedback])).rewritten is None


@pytest.mark.parametrize("generated", ["바론을 공격하시는 이유가 있나요?", "바론을 치시는 이유가 궁금해요."])
def test_question_feedback_preserves_question(monkeypatch, generated):
    api(monkeypatch, generated)
    assert impl.run(request("야 정글 바론을 왜 쳐", ["바론을 왜 쳐"])).rewritten == generated


def test_question_feedback_has_safe_fallback(monkeypatch):
    api(monkeypatch, None)
    out = impl.run(request("야 바론을 왜 쳐", ["바론을 왜 쳐"]))
    assert out.rewritten == "바론을 공격하시는 이유가 있나요?"
    assert out.backend == "rule"


def test_normal_words_are_not_objective_or_position_targets():
    assert impl._targets("이유가 궁금해요") == set()
    assert impl._targets("아이템 사용을 부탁해요") == set()
    assert impl._targets("스탑해 주세요") == set()


@pytest.mark.parametrize(
    ("feedback", "generated"),
    [
        ("템을 왜 그렇게 가", "아이템을 어떤 이유로 그렇게 선택하셨나요?"),
        ("아이템을 왜 그렇게 가", "템을 그렇게 선택하신 이유가 궁금해요."),
    ],
)
def test_item_abbreviation_is_not_invented_content(monkeypatch, feedback, generated):
    api(monkeypatch, generated)
    out = impl.run(request(feedback, [feedback]))
    assert out.rewritten == generated and out.backend == "api"


@pytest.mark.parametrize("text", ["시스템을 바꿔", "템포 좀 맞춰", "템플릿을 바꿔"])
def test_non_item_words_rely_on_semantic_audit_not_a_vocabulary_gate(monkeypatch, text):
    body = response("아이템을 바꿔 주세요.")
    value = json.loads(body["choices"][0]["message"]["content"])
    value["checks"]["target"] = False  # 시스템/템포/템플릿은 아이템과 의미가 다르다.
    body["choices"][0]["message"]["content"] = json.dumps(value)
    monkeypatch.setattr(backend, "_completion", lambda **_: body)
    assert backend._request(impl._build_prompt(text, text, [text]), "test", "gemini/test", 1) is None


def test_item_alias_still_rejects_new_game_objective(monkeypatch):
    api(monkeypatch, "아이템을 바꾸고 바론을 공격해 주세요.")
    assert impl.run(request("템을 왜 그렇게 가", ["템을 왜 그렇게 가"])).rewritten is None


@pytest.mark.parametrize(
    ("feedback", "generated"),
    [
        ("수확의 낫을 왜 가", "수확의 낫을 구매하신 이유가 있나요?"),
        ("cs 좀 먹어", "미니언을 처치해서 골드를 챙겨 주세요."),
        ("골드 좀 모아", "금화를 조금 더 모아 주세요."),
        ("타워 먼저 밀라고", "포탑을 먼저 공격해 주세요."),
        ("전령 왜 쳐", "전령을 공격하시는 이유가 있나요?"),
        ("빼라고", "후퇴해 주세요."),
        ("미니언 뺏지 말라고", "미니언은 남겨 주세요."),
        ("미니언 뺏지 말라고", "씨에스 처치는 자제해 주세요."),
        ("궁 아껴", "궁극기를 아껴 주세요."),
        ("템을 왜 그렇게 가", "아이템을 그렇게 선택하신 이유가 궁금합니다."),
    ],
)
def test_semantic_paraphrases_are_not_limited_to_a_word_list(monkeypatch, feedback, generated):
    api(monkeypatch, generated)
    out = impl.run(request("야 " + feedback, [feedback]))
    assert out.rewritten == generated
    assert out.backend == "api"


@pytest.mark.parametrize("field", backend._MEANING_FIELDS)
def test_model_meaning_check_failure_rejects_response(monkeypatch, field):
    body = response("미니언은 남겨 주세요.")
    value = json.loads(body["choices"][0]["message"]["content"])
    value["checks"][field] = False
    body["choices"][0]["message"]["content"] = json.dumps(value)
    monkeypatch.setattr(backend, "_completion", lambda **_: body)
    assert backend._request("test", "test", "gemini/test", 1) is None


@pytest.mark.parametrize("checks", [None, {}, {"target": True}, {key: 1 for key in backend._MEANING_FIELDS}])
def test_missing_or_non_boolean_meaning_audit_is_not_accepted(monkeypatch, checks):
    body = response()
    body["choices"][0]["message"]["content"] = json.dumps({"rewritten": "용 먼저 치자", "checks": checks})
    monkeypatch.setattr(backend, "_completion", lambda **_: body)
    assert backend._request("test", "test", "gemini/test", 1) is None


def test_trace_reports_stages_and_rejection_reason_without_key(monkeypatch, caplog):
    api(monkeypatch, "바론 먼저 치자")
    with caplog.at_level("INFO"):
        out = impl.run(request())
    assert out.rewritten == "용 먼저 치자" and out.backend == "rule"
    for stage in ("[입력]", "[피드백]", "[설정]", "[초안]", "[출력 정리]", "[로컬 검사/명확한 대상]", "[최종]"):
        assert stage in caplog.text
    assert "[API 결과 거절] 사유: 명확한 대상" in caplog.text
    assert "test-secret" not in caplog.text


def test_backend_audit_trace_redacts_api_key(monkeypatch, caplog):
    private_key = "not-a-real-key-12345"
    body = response("확인 부탁드려요 " + private_key)
    monkeypatch.setattr(backend, "_completion", lambda **_: body)
    with caplog.at_level("INFO"):
        backend._request("test", private_key, "gemini/test", 1)
    assert "[의미 확인/target] 통과" in caplog.text
    assert private_key not in caplog.text
    assert "마스킹" in caplog.text


def test_trace_preview_masks_names_and_credentials():
    from clean_chat.modules.rewrite.tracing import preview

    value = preview("비밀닉 AQ." + "x" * 25, names=["비밀닉"])
    assert "비밀닉" not in value
    assert "AQ." not in value
    assert "마스킹" in value


@pytest.mark.parametrize(
    ("feedback", "generated"),
    [
        ("수확의 낫을 지금 왜 사는거야", "지금 수확의 낫을 구매하신 이유가 무엇인가요?"),
        ("미니언 뺏지 말라고", "미니언은 남겨 주세요."),
        ("용 먼저 치라고", "드래곤을 먼저 공격해 주시겠어요?"),
        ("화공용 먼저 치라고", "화학공학 드래곤을 먼저 공격해 주세요."),
        ("바다용 먼저 치라고", "바다의 드래곤을 먼저 공격해 주세요."),
    ],
)
def test_user_reports_preserve_meaning_without_literal_words(monkeypatch, feedback, generated):
    api(monkeypatch, generated)
    assert impl.run(request(feedback, [feedback])).rewritten == generated


@pytest.mark.parametrize(
    ("feedback", "generated"),
    [
        ("용 먼저 치라고", "바다의 드래곤을 먼저 공격해 주시겠어요?"),
        ("용 먼저 치라고", "화학공학 드래곤을 먼저 공격해 주세요."),
        ("용 먼저 치라고", "장로 드래곤을 먼저 공격해 주세요."),
        ("화공용 먼저 치라고", "바다의 드래곤을 먼저 공격해 주세요."),
        ("바다용 먼저 치라고", "드래곤을 먼저 공격해 주세요."),
    ],
)
def test_unsourced_or_changed_dragon_kind_is_rejected_even_if_model_claims_safe(
    monkeypatch, feedback, generated, caplog
):
    api(monkeypatch, generated)
    with caplog.at_level("INFO"):
        out = impl.run(request(feedback, [feedback]))
    assert out.rewritten != generated
    assert not impl._acceptable(generated, feedback, [], [])
    if out.rewritten is not None:
        assert out.backend == "rule"
        assert impl._acceptable(out.rewritten, feedback, [], [])
    assert "용 종류·속성" in caplog.text


def test_no_purchased_item_can_be_invented_by_semantic_audit(monkeypatch):
    body = response("수확의 낫을 지금 구매해 주세요.")
    value = json.loads(body["choices"][0]["message"]["content"])
    value["checks"]["specificity"] = False
    body["choices"][0]["message"]["content"] = json.dumps(value)
    monkeypatch.setattr(backend, "_completion", lambda **_: body)
    assert backend._request("아이템 사", "test", "gemini/test", 1) is None


@pytest.mark.parametrize(
    ("feedback", "generated"),
    [
        ("신규아이템Z를 왜 샀어", "신규아이템Z를 구매하신 이유를 알려 주시겠어요?"),
        ("골드 300 모아", "금화 300을 모아 주세요."),
        ("cs 뺏지 말라고", "미니언은 남겨 주세요."),
    ],
)
def test_unknown_vocabulary_and_paraphrase_keep_meaning(monkeypatch, feedback, generated):
    api(monkeypatch, generated)
    assert impl.run(request(feedback, [feedback])).rewritten == generated


def test_user_minion_feedback_can_exclude_the_extra_complaint(monkeypatch):
    api(monkeypatch, "미니언은 남겨 주세요.")
    req = request("미니언 뺏지 말라고 뭐하ㅑ냐고", ["미니언 뺏지 말라고"])
    assert impl.run(req).rewritten == "미니언은 남겨 주세요."


def test_semantic_audit_uses_one_completion_even_when_rejected(monkeypatch):
    calls = []
    body = response("바다의 드래곤을 공격해 주세요.")
    data = json.loads(body["choices"][0]["message"]["content"])
    data["checks"]["specificity"] = False
    body["choices"][0]["message"]["content"] = json.dumps(data)

    def complete_once(**kwargs):
        calls.append(kwargs)
        return body

    monkeypatch.setattr(backend, "_completion", complete_once)
    assert backend._request("용 먼저 치라고", "test", "gemini/test", 1) is None
    assert len(calls) == 1 and calls[0]["num_retries"] == 0


def test_trace_includes_reported_token_usage_without_an_extra_call(monkeypatch, caplog):
    calls = []
    body = response()
    body["usage"] = {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}

    def fake(**kwargs):
        calls.append(kwargs)
        return body

    monkeypatch.setattr(backend, "_completion", fake)
    with caplog.at_level("INFO"):
        assert backend._request("test", "test-private-key", "gemini/test", 1) == "용 먼저 치자"
    assert "[사용량] 입력=100, 출력=40, 총계=140" in caplog.text
    assert len(calls) == 1 and "test-private-key" not in caplog.text


@pytest.mark.parametrize(
    "original, feedback",
    [
        ("블루 쳐먹지마라고", "블루 먹지마"),
        ("블루 쳐 먹지 마라고", "블루 먹지마"),
        ("블루 먹지마", "블루 먹지 마"),
    ],
)
def test_cleaned_feedback_is_accepted_without_literal_substring(monkeypatch, original, feedback):
    expected = "블루는 먹지 말아 주세요"
    api(monkeypatch, expected)
    req = request(original, [feedback])
    before = copy.deepcopy(req.model_dump())
    assert impl.run(req).rewritten == expected
    assert req.model_dump() == before


@pytest.mark.parametrize("feedback", ["레드 먹지마", "블루 먹어", "블루 먼저 먹지마"])
def test_cleaned_feedback_cannot_invent_target_action_or_condition(monkeypatch, feedback, caplog):
    api(monkeypatch, "블루는 먹지 말아 주세요")

    def unexpected_call(*args):
        pytest.fail("원문에 없는 피드백으로 API를 호출하면 안 됩니다")

    monkeypatch.setattr(backend, "generate", unexpected_call)
    with caplog.at_level("INFO", logger="clean_chat.modules.rewrite"):
        assert impl.run(request("블루 쳐먹지마라고", [feedback])).rewritten is None
    assert "원문에서 확인되지 않는 피드백 조각 번호=[1]" in caplog.text


def test_identical_success_reuses_result_with_current_message_id(monkeypatch, caplog):
    api(monkeypatch, "바론 먼저 공격해 주세요")
    calls = []
    monkeypatch.setattr(backend, "generate", lambda *args: calls.append(args) or "바론 먼저 공격해 주세요")
    req = request("바론 먼저 치라고", ["바론 먼저 치라고"])
    assert impl.run(req).rewritten == "바론 먼저 공격해 주세요"
    req.message.id = req.analysis.msg_id = "next-message"
    with caplog.at_level("INFO", logger="clean_chat.modules.rewrite"):
        out = impl.run(req)
    assert out.msg_id == "next-message"
    assert out.rewritten == "바론 먼저 공격해 주세요"
    assert len(calls) == 1
    assert "API 호출 없음" in caplog.text


def test_rejected_output_is_not_cached(monkeypatch):
    api(monkeypatch, "바다의 드래곤 먼저 공격해 주세요")
    calls = []
    monkeypatch.setattr(backend, "generate", lambda *args: calls.append(args) or "바다의 드래곤 먼저 공격해 주세요")
    req = request()
    assert impl.run(req).rewritten == "용 먼저 치자"
    assert impl.run(req).rewritten == "용 먼저 치자"
    assert len(calls) == 2
    assert not impl._CACHE


def test_cache_separates_source_model_key_and_profanity():
    base = impl._cache_key("prompt", [], [], {"LLM_MODEL": "one", "LLM_API_KEY": "first"})
    assert base != impl._cache_key("other", [], [], {"LLM_MODEL": "one", "LLM_API_KEY": "first"})
    assert base != impl._cache_key("prompt", [], [], {"LLM_MODEL": "two", "LLM_API_KEY": "first"})
    assert base != impl._cache_key("prompt", [], [], {"LLM_MODEL": "one", "LLM_API_KEY": "second"})
    assert base != impl._cache_key("prompt", [], ["word"], {"LLM_MODEL": "one", "LLM_API_KEY": "first"})
    assert "first" not in base


def test_cache_expires_and_is_bounded(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(impl.time, "monotonic", lambda: now[0])
    impl._remember("key", "text")
    assert impl._cached("key") == "text"
    now[0] += impl._CACHE_TTL
    assert impl._cached("key") is None
    for i in range(impl._CACHE_LIMIT + 1):
        impl._remember(str(i), "text")
    assert len(impl._CACHE) == impl._CACHE_LIMIT
    assert impl._cached("0") is None


@pytest.mark.parametrize("text", ["죽어도 괜찮으니 합류해 주세요", "라인 못하겠으면 말해 주세요", "혼자서는 못해요"])
def test_contextual_feedback_words_are_not_automatically_abusive(text):
    assert not impl._still_abusive(text)


@pytest.mark.parametrize("text", ["못하네", "못함ㅋ", "너 트롤", "그냥 죽어", "tlqkf", "qudtls"])
def test_explicit_blame_and_shared_lexicon_profanity_are_still_rejected(text):
    assert impl._still_abusive(text)


def test_prompt_carries_redacted_original_and_profanity_removed_context(monkeypatch):
    api(monkeypatch, "용 먼저 치자")
    captured = []
    monkeypatch.setattr(backend, "_request", lambda prompt, *_: captured.append(json.loads(prompt)) or "용 먼저 치자")
    req = request("불꽃남자야 정글 ㅂㅅ아 용 먼저 치라고", ["용 먼저 치라고"])
    before = copy.deepcopy(req.model_dump())
    out = impl.run(req)
    assert out.rewritten == "용 먼저 치자" and out.backend == "api"
    import re

    code = re.search(r"플레이어_[0-9]{4}", captured[0]["original"]).group()
    assert captured == [
        {
            "original": f"{code}야 정글 ㅂㅅ아 용 먼저 치라고",
            "cleaned": f"{code}야 정글 아 용 먼저 치라고",
            "feedback_spans": ["용 먼저 치라고"],
        }
    ]
    assert req.model_dump() == before


def test_fallback_is_also_validated(monkeypatch):
    api(monkeypatch, "용 먼저 쳐")
    monkeypatch.setattr(impl, "_rule", lambda *_: "바론 먼저 치자 병신")
    assert impl.run(request()).rewritten is None


def test_meaning_audit_failure_also_falls_back_through_production_generate(monkeypatch):
    monkeypatch.setattr(
        backend, "options", lambda: {"LLM_BACKEND": "api", "LLM_API_KEY": "test", "LLM_MODEL": "gemini/test"}
    )
    body = response("바다의 드래곤 공격해 주세요")
    parsed = json.loads(body["choices"][0]["message"]["content"])
    parsed["checks"]["specificity"] = False
    body["choices"][0]["message"]["content"] = json.dumps(parsed)
    monkeypatch.setattr(backend, "_completion", lambda **_: body)
    out = impl.run(request())
    assert out.rewritten == "용 먼저 치자" and out.backend == "rule"


def test_sdk_preparation_timeout_never_starts_late_paid_request(monkeypatch):
    release = threading.Event()
    done = threading.Event()

    def slow_sdk():
        release.wait(2)
        done.set()

    monkeypatch.setattr(backend, "_sdk", slow_sdk)
    calls = []
    monkeypatch.setattr(backend, "_request", lambda *args: calls.append(args))
    assert backend.generate("test", 0.03, {"LLM_API_KEY": "test", "LLM_MODEL": "gemini/test"}) is None
    release.set()
    assert done.wait(1)
    deadline = time.monotonic() + 1
    while not backend._SLOT.acquire(blocking=False):
        assert time.monotonic() < deadline
        time.sleep(0.005)
    backend._SLOT.release()
    assert not calls


def test_import_with_key_does_not_load_sdk_spawn_process_or_start_thread(tmp_path):
    import os
    import subprocess
    import sys

    script = """
import subprocess,threading,sys
from pathlib import Path

def forbidden(*args,**kwargs): raise AssertionError('import side effect')
subprocess.Popen=forbidden
threading.Thread.start=forbidden
from clean_chat.modules.rewrite import impl
assert 'litellm' not in sys.modules
assert not Path('.clean-chat').exists()
"""
    env = dict(
        os.environ, GEMINI_API_KEY="test-key", LLM_API_KEY="test-key", LLM_MODEL="gemini/test", LLM_BACKEND="api"
    )
    env["PYTHONPATH"] = str(__import__("pathlib").Path(impl.__file__).resolve().parents[3])
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr


def test_sdk_is_cached_in_process_without_process_management(monkeypatch):
    import sys
    from types import SimpleNamespace

    sdk = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "litellm", sdk)
    REAL_SDK.cache_clear()
    try:
        assert REAL_SDK() is sdk
        assert REAL_SDK() is sdk
        assert REAL_SDK.cache_info().misses == 1
        assert REAL_SDK.cache_info().hits == 1
    finally:
        REAL_SDK.cache_clear()


def test_context_changes_do_not_reuse_previous_result(monkeypatch):
    api(monkeypatch, "미드로 가겠습니다.")
    prompts = []
    monkeypatch.setattr(
        backend, "_request", lambda prompt, *_: prompts.append(json.loads(prompt)) or "미드로 가겠습니다."
    )
    assert impl.run(request("다비켜나미드갈라니까", ["나미드갈라니까"])).rewritten == "미드로 가겠습니다."
    assert impl.run(request("잠깐나미드갈라니까", ["나미드갈라니까"])).rewritten == "미드로 가겠습니다."
    assert len(prompts) == 2
    assert prompts[0]["original"] != prompts[1]["original"]


def test_shared_profanity_lexicon_is_loaded_as_source(monkeypatch, tmp_path):
    folder = tmp_path / "data" / "lexicon"
    folder.mkdir(parents=True)
    (folder / "bypass.csv").write_text(
        "variant,canonical,harm_type,note\n금지단어테스트,금지단어원형,profanity,test\n", encoding="utf-8"
    )
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    impl._profanity_words.cache_clear()
    try:
        assert impl._still_abusive("금지단어테스트")
        assert impl._still_abusive("금지단어원형")
    finally:
        impl._profanity_words.cache_clear()


@pytest.mark.parametrize("text", ["죽어도 괜찮으니 합류해 주세요", "라인 못하겠으면 말해 주세요"])
def test_review_normal_feedback_passes_entire_run(monkeypatch, text):
    api(monkeypatch, text)
    out = impl.run(request(text, [text]))
    assert out.rewritten == text and out.backend == "api"


def test_codec_consistency_uniqueness_case_and_overlapping_names():
    import re

    from clean_chat.modules.rewrite.nicknames import NicknameCodec

    codec = NicknameCodec(["달빛", "달빛고양이", "BlueWolf", "bluewolf"])
    original = "달빛고양이 BLUEWOLF 달빛 리신"
    encoded = codec.encode(original)
    codes = re.findall(r"플레이어_[0-9]{4}", encoded)
    assert len(codes) == len(set(codes)) == 3
    assert encoded.endswith("리신")
    assert codec.encode("bluewolf") == codec.encode("BLUEWOLF")
    assert codec.preserves(encoded, [encoded])
    assert codec.restore(encoded) == "달빛고양이 BlueWolf 달빛 리신"
    assert not codec.preserves(encoded + " 플레이어_12345", [encoded])
    assert not codec.preserves(encoded.replace(codes[0], ""), [encoded])


def named_request():
    from clean_chat.core.schemas import Player

    text = "달빛고양이 리신이랑 용 먼저 치자"
    req = request(text, [text])
    req.players = [Player(name="달빛고양이", champion="리신"), Player(name="밤하늘별", champion="애쉬")]
    return req


@pytest.mark.parametrize("source", ["self_input", "ocr"])
def test_roster_is_forwarded_and_nicknames_roundtrip_in_both_actual_pipelines(monkeypatch, source):
    import re

    from clean_chat.core.pipeline import Pipelines
    from clean_chat.core.schemas import Analysis, ChatMessage, ParseResult, RawLine

    monkeypatch.setattr(
        backend, "options", lambda: {"LLM_BACKEND": "api", "LLM_MODEL": "gemini/test", "LLM_API_KEY": "test"}
    )
    req = named_request()
    seen = []
    received = []

    def parse(item):
        data = req.message.model_dump()
        data.update(
            id=item.line.id,
            text=item.line.text,
            text_norm=item.line.text,
            raw=item.line.text,
            source=item.line.source,
            is_me=item.line.source == "self_input",
        )
        return ParseResult(line_id=item.line.id, message=ChatMessage.model_validate(data))

    def analyze(item):
        return Analysis(msg_id=item.message.id, level=2, feedback_spans=[item.message.text], model_version="test")

    def rewrite(item):
        received.append(item)
        return impl.run(item)

    def completion(**kwargs):
        prompt = kwargs["messages"][1]["content"]
        payload = json.loads(prompt)
        seen.append(payload)
        code = re.search(r"플레이어_[0-9]{4}", payload["feedback_spans"][0]).group()
        assert code in payload["original"] and code in payload["cleaned"]
        assert "달빛고양이" not in prompt and "밤하늘별" not in prompt
        assert "리신" in prompt
        return response(f"{code} 리신이랑 용 먼저 공격해 주세요")

    monkeypatch.setattr(backend, "_completion", completion)
    pipeline = Pipelines(modules.ModuleSet({"parse": parse, "analyze": analyze, "rewrite": rewrite}))
    pipeline.set_players(req.players)
    if source == "self_input":
        incident = pipeline.outgoing.submit(req.message.text, msg_id="named-self")
    else:
        incident = pipeline.incoming.process_line(RawLine(id="named-ocr", ts=1, text=req.message.text, source="ocr"))
    assert received[0].players == req.players
    assert received[0].message.source == source
    assert incident.rewrite.rewritten == "달빛고양이 리신이랑 용 먼저 공격해 주세요"
    assert incident.rewrite.backend == "api"
    assert "플레이어_" not in incident.rewrite.rewritten
    assert len(seen) == 1


@pytest.mark.parametrize("failure", ["missing", "altered", "extra", "raw_nickname", "champion_missing"])
def test_bad_codes_or_missing_champion_use_safe_local_rule(monkeypatch, failure, caplog):
    import re

    api(monkeypatch, None)

    def generate(prompt, *_):
        code = re.search(r"플레이어_[0-9]{4}", json.loads(prompt)["feedback_spans"][0]).group()
        text = f"{code} 리신이랑 용 먼저 공격해 주세요"
        if failure == "missing":
            return text.replace(code, "")
        if failure == "altered":
            return text.replace(code, code + "0")
        if failure == "raw_nickname":
            return text.replace(code, "달빛고양이")
        if failure == "champion_missing":
            return text.replace("리신이랑", "")
        other = f"플레이어_{(int(code[-4:]) + 1) % 10000:04d}"
        return text + " " + other

    monkeypatch.setattr(backend, "_request", generate)
    with caplog.at_level("INFO", logger="clean_chat.modules.rewrite"):
        out = impl.run(named_request())
    assert out.backend == "rule"
    assert out.rewritten == "달빛고양이 리신이랑 용 먼저 공격해 주세요"
    assert "[API 결과 거절]" in caplog.text and "[예비 규칙 초안]" in caplog.text
    assert "달빛고양이" not in caplog.text


def test_context_only_nickname_cannot_be_added_to_selected_feedback(monkeypatch):
    import re

    api(monkeypatch, None)
    req = named_request()
    req.analysis.feedback_spans = ["용 먼저 치자"]

    def generate(prompt, *_):
        code = re.search(r"플레이어_[0-9]{4}", json.loads(prompt)["original"]).group()
        return f"{code} 용 먼저 공격해 주세요"

    monkeypatch.setattr(backend, "_request", generate)
    out = impl.run(req)
    assert out.backend == "rule" and out.rewritten == "용 먼저 공격해 주세요"


def test_nickname_cache_reencodes_with_new_request_map(monkeypatch):
    import re

    api(monkeypatch, None)
    calls = []

    def generate(prompt, *_):
        calls.append(prompt)
        code = re.search(r"플레이어_[0-9]{4}", json.loads(prompt)["feedback_spans"][0]).group()
        return f"{code} 리신이랑 용 먼저 공격해 주세요"

    monkeypatch.setattr(backend, "_request", generate)
    req = named_request()
    assert impl.run(req).backend == "api"
    req.message.id = req.analysis.msg_id = "next-named"
    out = impl.run(req)
    assert out.msg_id == "next-named" and out.rewritten == "달빛고양이 리신이랑 용 먼저 공격해 주세요"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "nickname,text", [("BlueWolf", "bluewolf ㅂㅅ아 용 먼저 치라고"), ("BlueFox", "bluefox야 용 먼저 치라고")]
)
def test_case_variant_nicknames_never_reach_mock_sdk_or_logs(monkeypatch, caplog, nickname, text):
    monkeypatch.setattr(
        backend, "options", lambda: {"LLM_BACKEND": "api", "LLM_MODEL": "gemini/test", "LLM_API_KEY": "test"}
    )
    req = request(text, ["용 먼저 치라고"])
    req.analysis.target = nickname
    seen = []

    def completion(**kwargs):
        seen.append(json.loads(kwargs["messages"][1]["content"]))
        return response("용 먼저 치자")

    monkeypatch.setattr(backend, "_completion", completion)
    with caplog.at_level("INFO", logger="clean_chat.modules.rewrite"):
        assert impl.run(req).rewritten == "용 먼저 치자"
    assert nickname.casefold() not in seen[0]["original"].casefold()
    assert nickname.casefold() not in seen[0]["cleaned"].casefold()
    assert nickname.casefold() not in caplog.text.casefold()


@pytest.mark.parametrize(
    "output, expected",
    [
        ("3초 뒤에 합류해 주세요", "3초 뒤에 합류해 주세요"),
        ("뒤에 합류해 주세요", None),
        ("5초 뒤에 합류해 주세요", None),
    ],
)
def test_quantities_cannot_be_dropped_or_changed(monkeypatch, output, expected):
    api(monkeypatch, output)
    assert impl.run(request("3초 뒤에 합류해", ["3초 뒤에 합류해"])).rewritten == expected


def test_token_digits_are_not_treated_as_game_quantities(monkeypatch):
    import re

    api(monkeypatch, None)
    req = named_request()
    req.message.text = req.message.text_norm = "달빛고양이 3초 뒤에 합류해"
    req.analysis.feedback_spans = [req.message.text]

    def generate(prompt, *_):
        code = re.search(r"플레이어_[0-9]{4}", json.loads(prompt)["feedback_spans"][0]).group()
        return f"{code} 3초 뒤에 합류해 주세요"

    monkeypatch.setattr(backend, "_request", generate)
    assert impl.run(req).rewritten == "달빛고양이 3초 뒤에 합류해 주세요"


def test_old_requests_still_default_to_empty_roster():
    data = request().model_dump()
    data.pop("players", None)
    assert RewriteRequest.model_validate(data).players == []
