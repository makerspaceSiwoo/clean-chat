"""core/gemini.py — litellm 대신 Gemini 를 직접 부르는 클라이언트. 네트워크·실제 키를 쓰지 않는다."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from clean_chat.core import gemini

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
MESSAGES = [{"role": "system", "content": "지시"}, {"role": "user", "content": "입력"}]


def test_request_body_matches_litellm_rewrite_call():
    """litellm 1.110.2 가 rewrite 호출(JSON 스키마·minimal 생각·출력 256)로 보내던 본문과 같다."""
    body = gemini.request_body(
        MESSAGES,
        max_tokens=256,
        reasoning_effort="minimal",
        response_format={"type": "json_schema", "json_schema": {"name": "x", "strict": True, "schema": SCHEMA}},
    )
    assert body == {
        "contents": [{"role": "user", "parts": [{"text": "입력"}]}],
        "system_instruction": {"parts": [{"text": "지시"}]},
        "generationConfig": {
            "max_output_tokens": 256,
            "response_mime_type": "application/json",
            "response_json_schema": SCHEMA,
            "thinkingConfig": {"thinkingLevel": "minimal", "includeThoughts": True},
        },
    }


def test_request_body_matches_litellm_report_call():
    """옵션 없는 호출(report)은 generationConfig 를 보내지 않는다."""
    assert gemini.request_body(MESSAGES) == {
        "contents": [{"role": "user", "parts": [{"text": "입력"}]}],
        "system_instruction": {"parts": [{"text": "지시"}]},
    }


def test_parse_response_skips_thoughts_and_maps_finish():
    data = {
        "candidates": [
            {
                "content": {"parts": [{"text": "생각 중", "thought": True}, {"text": "답"}, {"text": "변"}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 2,
            "thoughtsTokenCount": 3,
            "totalTokenCount": 10,
        },
    }
    out = gemini.parse_response(data)
    assert out["choices"][0] == {"finish_reason": "stop", "message": {"content": "답변", "refusal": None}}
    assert out["usage"] == {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}


@pytest.mark.parametrize(
    ("data", "finish", "content"),
    [
        ({"candidates": [{"content": {"parts": [{"text": "잘"}]}, "finishReason": "MAX_TOKENS"}]}, "length", "잘"),
        ({"candidates": [{"finishReason": "SAFETY"}]}, "content_filter", None),
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "content_filter", None),
        ({"candidates": [{"content": {"parts": [{"text": "x"}]}, "finishReason": "NEW_REASON"}]}, "new_reason", "x"),
    ],
)
def test_parse_response_non_stop_is_not_stop(data, finish, content):
    out = gemini.parse_response(data)["choices"][0]
    assert out["finish_reason"] == finish and out["message"]["content"] == content


def test_completion_sends_key_only_in_header(monkeypatch):
    sent = []

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def urlopen(req, timeout, context):
        sent.append((req, timeout))
        return Reply(
            json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]}).encode()
        )

    monkeypatch.setattr(gemini.urllib.request, "urlopen", urlopen)
    out = gemini.completion(
        model="gemini/gemini-3.1-flash-lite", api_key="secret", messages=MESSAGES, timeout=3, num_retries=0
    )
    assert out["choices"][0]["message"]["content"] == "ok"
    ((req, timeout),) = sent
    assert (
        req.full_url == "https://generativelanguage.googleapis.com/v1alpha/models/gemini-3.1-flash-lite:generateContent"
    )
    assert "secret" not in req.full_url and req.get_header("X-goog-api-key") == "secret"
    assert timeout == 3


def test_http_error_has_status_code_without_body(monkeypatch):
    def urlopen(req, timeout, context):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"secret body"))

    monkeypatch.setattr(gemini.urllib.request, "urlopen", urlopen)
    with pytest.raises(gemini.GeminiError) as caught:
        gemini.completion(model="gemini/m", api_key="k", messages=MESSAGES)
    assert caught.value.status_code == 429
    assert "secret body" not in str(caught.value)


@pytest.mark.parametrize("model", ["gemini/", "gemini/a/b"])
def test_bad_model_name_is_rejected_before_network(monkeypatch, model):
    monkeypatch.setattr(gemini.urllib.request, "urlopen", lambda *a, **k: pytest.fail("네트워크 호출 금지"))
    with pytest.raises(ValueError):
        gemini.completion(model=model, api_key="k", messages=MESSAGES)
