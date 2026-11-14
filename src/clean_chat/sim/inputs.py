"""간단 입력(텍스트·이미지) → 모듈 입력 모델 JSON. 비개발자가 JSON 을 몰라도 모듈을 돌려 볼 수 있게.

모듈마다 화면에 그릴 칸(FORMS)과 변환 함수(build)를 둔다. 변환 결과는 화면의 콘솔·반환값 칸에 그대로 보여 준다.
"""

from __future__ import annotations

import time
from typing import Any

from clean_chat.core.config import settings
from clean_chat.core.schemas import (
    Analysis,
    AnalyzeRequest,
    Channel,
    ChatMessage,
    Frame,
    Level,
    ParseRequest,
    RawLine,
    Region,
    RewriteRequest,
    Source,
)

# 모듈 → 화면 설명과 간단 입력 칸. type: textarea | text | checkbox | image
DESCRIPTIONS = {
    "ocr": "채팅창 이미지 → 읽은 줄 전부",
    "parse": "줄 → 채팅만 (시스템 메시지·핑 제외) + 우회어 정규화",
    "analyze": "누가 누구에게(대상) · 욕설 등급 L0~L3 · 비속어·피드백 조각",
    "rewrite": "피드백 조각 → 공손한 문장 1개",
    "report": "게임 기록 → 신고 문구 / 고소장 초안 (PDF)",
}
FORMS: dict[str, list[dict[str, Any]]] = {
    "ocr": [{"key": "image", "type": "image", "label": "채팅창 이미지 (PNG·JPG)"}],
    "parse": [
        {
            "key": "text",
            "type": "textarea",
            "label": "채팅창에 보이는 한 줄",
            "default": "[팀] 원딜러 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고",
        },
        {"key": "self_input", "type": "checkbox", "label": "내가 오버레이에 입력한 문장 (채널·화자 없이 본문만)"},
    ],
    "analyze": [
        {"key": "speaker", "type": "text", "label": "말한 사람", "default": "원딜러"},
        {"key": "text", "type": "textarea", "label": "채팅 문장", "default": "야 정글 ㅂㅅ아 용 먼저 치라고"},
    ],
    "rewrite": [
        {"key": "text", "type": "textarea", "label": "원래 문장", "default": "야 정글 ㅂㅅ아 용 먼저 치라고"},
        {"key": "feedback", "type": "text", "label": "피드백 조각 (쉼표로 구분)", "default": "용 먼저 치라고"},
    ],
    "report": [],  # 게임 기록(세션)이 필요해서 간단 입력 없음 → 예시 JSON 사용
}


class SimpleInputError(ValueError):
    """간단 입력이 비었거나 이 모듈은 간단 입력을 지원하지 않음."""


def _text(simple: dict[str, Any], key: str = "text") -> str:
    value = str(simple.get(key) or "").strip()
    if not value:
        raise SimpleInputError(f"'{key}' 칸이 비어 있습니다")
    return value


def _message(text: str, speaker: str) -> ChatMessage:
    return ChatMessage(
        id="sim-1",
        ts=time.time(),
        source=Source.DEMO,
        channel=Channel.TEAM,
        speaker=speaker,
        text=text,
        text_norm=text,  # 간단 입력은 parse 를 거치지 않으므로 원문 그대로
        is_me=speaker == settings.my_name,
        raw=text,
    )


def build(module: str, simple: dict[str, Any], image_path: str | None = None) -> dict[str, Any]:
    """간단 입력 → 입력 모델 JSON (dict). 지원하지 않거나 칸이 비면 SimpleInputError."""
    now = time.time()
    if module == "ocr":
        if not image_path:
            raise SimpleInputError("이미지를 첨부하세요")
        frame = Frame(id="sim-frame", ts=now, image_path=image_path, region=Region(x=0, y=0, w=0, h=0))
        return frame.model_dump(mode="json")
    if module == "parse":
        source = Source.SELF_INPUT if simple.get("self_input") else Source.OCR
        line = RawLine(id="sim-1", ts=now, text=_text(simple), source=source)
        return ParseRequest(line=line, my_name=settings.my_name).model_dump(mode="json")
    if module == "analyze":
        speaker = str(simple.get("speaker") or "").strip() or "상대"
        return AnalyzeRequest(message=_message(_text(simple), speaker)).model_dump(mode="json")
    if module == "rewrite":
        msg = _message(_text(simple), "상대")
        spans = [s.strip() for s in str(simple.get("feedback") or "").split(",") if s.strip()]
        analysis = Analysis(msg_id=msg.id, level=Level.L2_ABUSIVE, feedback_spans=spans, model_version="sim")
        return RewriteRequest(message=msg, analysis=analysis).model_dump(mode="json")
    raise SimpleInputError(f"'{module}' 모듈은 간단 입력이 없습니다. 예시를 고르고 JSON 으로 실행하세요")
