"""간단 입력(텍스트·이미지) → 모듈 입력 모델 JSON. 비개발자가 JSON 을 몰라도 모듈을 돌려 볼 수 있게.

모듈마다 화면에 그릴 칸(FORMS)과 변환 함수(build)를 둔다. 변환 결과는 화면의 콘솔·반환값 칸에 그대로 보여 준다.
"""

from __future__ import annotations

import re
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
    Player,
    RawLine,
    Region,
    RewriteRequest,
    Source,
)
from clean_chat.modules.analyze.judge import JudgeRequest

# 모듈 → 화면 설명과 간단 입력 칸. type: textarea | text | checkbox | image
DESCRIPTIONS = {
    "ocr": "채팅창 이미지 → 읽은 줄 전부",
    "parse": "줄 → 채팅만 (시스템 메시지·핑 제외) + 우회어 정규화",
    "analyze": "단발 채팅 분류 (게임 중, 메시지 1개) — 누가 누구에게(대상) · 욕설 등급 L0~L3 · 비속어·피드백 조각",
    "judge": "전체 대화 판단 (게임 후) — 화자별 신고 권고 · 고소 후보 · 판례 요건 점검. 한 줄씩 단발 분류한 뒤 흐름(반복·동조·몰이)을 본다",
    "rewrite": "피드백 조각 → 공손한 문장 1개",
    "report": "게임 기록 → 신고 문구 / 고소장 초안 (PDF)",
}
JUDGE_DEFAULT = """[팀] 밤하늘별 (가렌): 다들 화이팅
[팀] 불꽃남자 (징크스): 서폿 개못하네 와드 좀 박아
[팀] 달빛고양이 (제드): ㅇㅈ
[팀] 불꽃남자 (징크스): 서폿 개새끼
[팀] 불꽃남자 (징크스): 다들 서폿 신고해
[전체] 얼음땡 (다리우스): 서폿 니애미"""
CHAT_LINE = re.compile(r"^(?:\[(팀|전체)\]\s*)?(.+?)\s*\((.+?)\)\s*[:：]\s*(.+)$")
FORMS: dict[str, list[dict[str, Any]]] = {
    "ocr": [{"key": "image", "type": "image", "label": "채팅창 이미지 (PNG·JPG)"}],
    "parse": [
        {
            "key": "text",
            "type": "textarea",
            "label": "채팅창에 보이는 한 줄",
            "default": "[팀] 불꽃남자 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고",
        },
        {"key": "self_input", "type": "checkbox", "label": "내가 오버레이에 입력한 문장 (채널·화자 없이 본문만)"},
    ],
    "analyze": [
        {"key": "speaker", "type": "text", "label": "말한 사람", "default": "불꽃남자"},
        {"key": "text", "type": "textarea", "label": "채팅 문장", "default": "야 정글 ㅂㅅ아 용 먼저 치라고"},
    ],
    "judge": [
        {
            "key": "text",
            "type": "textarea",
            "label": "대화 (한 줄에 채팅 하나, 5초 간격으로 봄) — [팀] 닉네임 (챔피언): 내용",
            "default": JUDGE_DEFAULT,
        },
        {"key": "me", "type": "text", "label": "내 닉네임 (챔피언)", "default": "나 (쓰레쉬)"},
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


def _conversation(text: str, me: str) -> dict[str, Any]:
    """여러 줄 대화 → JudgeRequest. 줄마다 `[팀] 닉네임 (챔피언): 내용`, 채널을 안 쓰면 팀 채팅으로 본다.

    parse 를 거치지 않으므로 text_norm 은 원문 그대로다(우회어는 풀리지 않는다). 명단은 대화에 나온 사람 + 나.
    """
    named = CHAT_LINE.match(f"{me}: -") if "(" in me else None
    my_name, my_champion = (named.group(2), named.group(3)) if named else (me, None)
    players = {my_name: Player(name=my_name, champion=my_champion, is_me=True)}
    messages = []
    for i, line in enumerate(x.strip() for x in text.splitlines() if x.strip()):
        m = CHAT_LINE.match(line)
        if not m:
            raise SimpleInputError(f"{i + 1}번째 줄을 읽을 수 없습니다 (형식: [팀] 닉네임 (챔피언): 내용): {line}")
        channel, speaker, champion, body = m.groups()
        players.setdefault(speaker, Player(name=speaker, champion=champion))
        messages.append(
            ChatMessage(
                id=f"sim-{i + 1}",
                ts=1_762_920_000.0 + 5 * i,
                source=Source.DEMO,
                channel=Channel.ALL if channel == "전체" else Channel.TEAM,
                speaker=speaker,
                champion=champion,
                text=body,
                text_norm=body,
                is_me=speaker == my_name,
                raw=line,
            )
        )
    request = JudgeRequest(messages=messages, players=list(players.values()), my_name=my_name)
    return request.model_dump(mode="json")


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
    if module == "judge":
        return _conversation(_text(simple), str(simple.get("me") or "").strip() or settings.my_name)
    if module == "rewrite":
        msg = _message(_text(simple), "상대")
        spans = [s.strip() for s in str(simple.get("feedback") or "").split(",") if s.strip()]
        analysis = Analysis(msg_id=msg.id, level=Level.L2_ABUSIVE, feedback_spans=spans, model_version="sim")
        return RewriteRequest(message=msg, analysis=analysis).model_dump(mode="json")
    raise SimpleInputError(f"'{module}' 모듈은 간단 입력이 없습니다. 예시를 고르고 JSON 으로 실행하세요")
