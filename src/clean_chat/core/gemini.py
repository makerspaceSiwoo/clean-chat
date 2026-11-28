"""Gemini REST(generateContent)를 표준 라이브러리로 직접 부른다 (litellm 대신, 용량·첫 호출 지연을 줄이려고).

요청 본문은 litellm 1.110.2 가 `gemini/<모델>` 로 보내던 것과 같게 만든다 (같은 주소·같은 본문 → 같은 응답 분포).
응답은 litellm 과 같은 모양의 dict 로 돌려준다:
    {"choices": [{"finish_reason": "stop", "message": {"content": "...", "refusal": None}}],
     "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}
키는 헤더로만 보내고 주소·로그·예외 메시지에 넣지 않는다. 재시도는 하지 않는다.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any

URL = "https://generativelanguage.googleapis.com/v1alpha/models/{model}:generateContent"
MAX_RESPONSE_BYTES = 1 << 20
# Gemini finishReason → litellm(OpenAI) finish_reason. 모르는 값은 "stop" 이 아닌 값으로 남겨 호출 쪽이 거절하게 한다.
_FINISH = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "BLOCKLIST": "content_filter",
    "PROHIBITED_CONTENT": "content_filter",
    "SPII": "content_filter",
    "IMAGE_SAFETY": "content_filter",
}


class GeminiError(Exception):
    """HTTP 오류. report 가 로그에 쓰는 status_code 를 litellm 예외처럼 갖는다. 응답 본문(입력 원문 포함 가능)은 넣지 않는다."""

    def __init__(self, status_code: int | None, reason: str = "") -> None:
        super().__init__(f"Gemini HTTP {status_code} {reason}".strip())
        self.status_code = status_code


def request_body(
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """OpenAI 형식 messages·옵션 → generateContent 본문. system 은 system_instruction 으로 옮긴다."""
    body: dict[str, Any] = {
        "contents": [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
            if m["role"] != "system"
        ]
    }
    system = [{"text": m["content"]} for m in messages if m["role"] == "system"]
    if system:
        body["system_instruction"] = {"parts": system}
    config: dict[str, Any] = {}
    if max_tokens is not None:
        config["max_output_tokens"] = max_tokens
    if response_format and response_format.get("type") == "json_schema":
        config["response_mime_type"] = "application/json"
        config["response_json_schema"] = response_format["json_schema"]["schema"]
    if reasoning_effort:
        config["thinkingConfig"] = {"thinkingLevel": reasoning_effort, "includeThoughts": True}
    if config:
        body["generationConfig"] = config
    return body


def parse_response(data: dict[str, Any]) -> dict[str, Any]:
    """generateContent 응답 → litellm 모양 dict. 생각(thought) 조각은 빼고 글자만 합친다."""
    candidates = data.get("candidates") or []
    if not candidates:  # 입력이 막힌 경우 (promptFeedback.blockReason)
        finish, text = "content_filter", None
    else:
        first = candidates[0]
        parts = (first.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")) or None
        reason = first.get("finishReason")
        finish = _FINISH.get(reason, str(reason).lower() if reason else ("stop" if text else None))
    usage = data.get("usageMetadata") or {}
    completion_tokens = (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)
    return {
        "choices": [{"finish_reason": finish, "message": {"content": text, "refusal": None}}],
        "usage": {
            "prompt_tokens": usage.get("promptTokenCount"),
            "completion_tokens": completion_tokens if usage else None,
            "total_tokens": usage.get("totalTokenCount"),
        },
    }


def _ssl_context() -> ssl.SSLContext:
    # 설치한 앱(PyInstaller)은 파이썬 빌드 때의 인증서 경로가 없을 수 있다. certifi 가 있으면 그 인증서 묶음을 쓴다.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def completion(
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    timeout: float = 10,
    num_retries: int = 0,  # litellm 과 같은 인자로 부를 수 있게 받기만 한다 (재시도는 하지 않는다)
    **options: Any,
) -> dict[str, Any]:
    """`gemini/<모델>` 을 한 번 호출한다. 네트워크 오류는 그대로, HTTP 오류는 GeminiError 로 올린다."""
    del num_retries
    name = model.removeprefix("gemini/")
    if not name or "/" in name:
        raise ValueError("Gemini 모델 이름이 필요합니다 (예: gemini/gemini-3.1-flash-lite)")
    request = urllib.request.Request(
        URL.format(model=name),
        data=json.dumps(request_body(messages, **options), ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise GeminiError(error.code, str(error.reason or "")) from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Gemini 응답이 너무 큽니다")
    return parse_response(json.loads(raw))
