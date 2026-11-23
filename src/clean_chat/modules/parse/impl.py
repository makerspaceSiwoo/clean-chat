"""② parse — 줄 → 채팅 메시지 (시스템 메시지·핑 제외) + 정규화  (명세: docs/MODULES.md#parse, 예시: fixtures/parse/)

규칙(코드)만으로 처리한다. 결과가 정해진 규칙 모듈이라 fixtures 와 정확히 같아야 한다.
"""

from __future__ import annotations

import re

from clean_chat.core.schemas import Channel, ChatMessage, ParseRequest, ParseResult, Source
from clean_chat.modules.parse.normalization import normalize

_CHANNEL = re.compile(r"^[\[(（［][ \t]*(팀|전체)[ \t]*[\])）］][ \t]*")
_HEADER_TEXT = r"[^:;：；()（）\[\]［］\r\n]+?"
_SPEAKER = re.compile(rf"({_HEADER_TEXT})(?:[ \t]*[(（]({_HEADER_TEXT})[)）])?[ \t]*[:;：；][ \t]?([^\r\n]*)")
_SYSTEM = re.compile(
    rf"{_HEADER_TEXT}(?:[ \t]*[(（]{_HEADER_TEXT}[)）])?[ \t]*님이 "
    r"(?:[^\r\n]*(?:신호를 보냈습니다|처치했습니다)|게임을 (?:종료했습니다|떠났습니다))[.!]?"
)
_UI_CLOCK = re.compile(r"(?:게임 시간|남은 시간)[ \t]*[:;：；][ \t]*[0-9]{1,3}[:：][0-9]{2}")
_NOTICE_LABEL = re.compile(r"^(?:알림|시스템)[ \t]*[:;：；][ \t]*")
_GAME_CLOCK = r"[0-9]{1,3}:[0-5][0-9]"
_GAME_TIME = re.compile(rf"^(?P<clock>{_GAME_CLOCK}|\[{_GAME_CLOCK}\])[ \t]+")
_TIME_LIKE = re.compile(r"^\[?[0-9]+[ \t]*[:;：；][0-9]")


def run(req: ParseRequest) -> ParseResult:
    """줄 1개 → 채팅이면 ChatMessage(채널·화자·챔피언·본문 + text_norm), 채팅이 아니면 None.

    입력: ParseRequest(line, my_name) → 출력: ParseResult(line_id, message)
    message 안에 raw_norm(복원 줄), game_time_sec(게임 경과 초)를 함께 반환한다.
    예) "[팀] 불꽃남자 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고"
        → channel=team, speaker="불꽃남자", champion="징크스", text="야 정글 ㅂㅅ아 용 먼저 치라고",
          text_norm="야 정글 병신아 용 먼저 치라고", hints=["lexicon:ㅂㅅ"], is_me=False
    예) "[팀] 나 (쓰레쉬): 정글 합류 부탁해요" (my_name="나") → is_me=True
    예) "17:02 [팀] 밤하늘별 (코그모): 합류 부탁해요" → 시간 접두부를 떼고 채널·화자·본문 분리.
        → game_time_sec=1022. raw_norm에는 표준 헤더와 본문 원문을 재구성한다.
        ts는 입력의 유닉스 캡처 시각 그대로 유지하고 raw도 바꾸지 않는다.
    예) "초코우유 (리신)님이 점멸 쿨타임 신호를 보냈습니다" → 핑·시스템 메시지라 message=None
    예) "@@ ㅡ ##" → 잡음이라 message=None
    예) source=self_input, text="아 정글 ㅂㅅ 왜 안 와" (내 입력, 흐름 B)
        → channel=team, speaker=my_name, champion=None, is_me=True, raw=입력 그대로
    순서: (self_input 이면 _split_channel_command) /
          (아니면 _is_noise → _split_game_time → _split_channel → _is_system → _split_speaker)
          → normalize(본문) → ChatMessage(raw=원본 줄 그대로)
    주의: text 와 raw 는 증거라서 절대 고치지 않는다(정규화는 text_norm 에만). OCR 오인식([ ↔ (, : ↔ ;)에 강하게.
    관련: ADR-0002, ADR-0006, OPEN-09
    """
    line = req.line
    game_time_sec = None
    if line.source == Source.SELF_INPUT:
        channel, body = _split_channel_command(line.text)
        speaker, champion, is_me = req.my_name, None, True
    else:
        if _is_noise(line.text):
            return ParseResult(line_id=line.id, message=None)
        timed_line = _split_game_time(line.text)
        if timed_line is None:
            return ParseResult(line_id=line.id, message=None)
        game_time_sec, rest = timed_line
        channel, rest = _split_channel(rest)
        if channel is None and _is_system(rest):
            return ParseResult(line_id=line.id, message=None)
        speaker, champion, body = _split_speaker(rest)
        if speaker is None:
            return ParseResult(line_id=line.id, message=None)
        is_me = bool(req.my_name) and speaker == req.my_name
        channel = channel or Channel.UNKNOWN
    if not body.strip():
        return ParseResult(line_id=line.id, message=None)
    text_norm, hints = normalize(body)
    message = ChatMessage(
        id=line.id,
        ts=line.ts,
        source=line.source,
        channel=channel,
        speaker=speaker,
        champion=champion,
        text=body,
        text_norm=text_norm,
        hints=hints,
        is_me=is_me,
        raw=line.text,
        game_time_sec=game_time_sec,
    )
    message.raw_norm = _format_raw_norm(message)
    return ParseResult(line_id=line.id, message=message)


# ── 줄 분해 ──
def _split_game_time(text: str) -> tuple[int | None, str] | None:
    """게임 경과 초와 나머지를 분리한다. 시간 없음과 잘못된 시간 표기를 구별한다."""
    stripped = text.lstrip(" \t")
    match = _GAME_TIME.match(stripped)
    if match is not None:
        minutes, seconds = match["clock"].strip("[]").split(":")
        return int(minutes) * 60 + int(seconds), stripped[match.end() :]
    return None if _TIME_LIKE.match(stripped) else (None, stripped)


def _format_raw_norm(message: ChatMessage) -> str:
    """확인한 헤더 정보만 표준 형식으로 재구성한다. 본문은 text_norm 대신 원문 text를 쓴다."""
    parts: list[str] = []
    if message.game_time_sec is not None:
        minutes, seconds = divmod(message.game_time_sec, 60)
        parts.append(f"{minutes:02d}:{seconds:02d}")
    tag = {Channel.TEAM: "[팀]", Channel.ALL: "[전체]"}.get(message.channel)
    if tag is not None:
        parts.append(tag)
    champion = f" ({message.champion})" if message.champion else ""
    parts.append(f"{message.speaker}{champion}: {message.text}")
    return " ".join(parts)


def _split_channel(text: str) -> tuple[Channel | None, str]:
    """팀·전체 표기의 괄호 오인식만 허용해 분리한다. 본문에는 치환을 적용하지 않는다."""
    match = _CHANNEL.match(text.lstrip())
    if match is None:
        return None, text.lstrip()
    return (Channel.TEAM if match[1] == "팀" else Channel.ALL), text.lstrip()[match.end() :]


def _split_speaker(rest: str) -> tuple[str | None, str | None, str]:
    """공백 있는 닉네임과 선택적 챔피언을 분리한다. 콜론·세미콜론과 전각 구분자를 허용한다."""
    match = _SPEAKER.fullmatch(rest)
    if match is None or not match[1].strip() or (match[2] is not None and not match[2].strip()):
        return None, None, ""
    return match[1].strip(), match[2].strip() if match[2] else None, match[3]


def _is_system(text: str) -> bool:
    """알려진 알림 전체 형식과 시계 UI만 제외한다. 실제 문구 목록 확정은 OPEN-09."""
    stripped = text.strip()
    # 본문 키워드만 찾지 않는다. 명시적 채널이 없는 경우에도 일반 화자의 인용 채팅은 남긴다.
    notice = _NOTICE_LABEL.sub("", stripped, count=1)
    return _SYSTEM.fullmatch(notice) is not None or _UI_CLOCK.fullmatch(stripped) is not None


def _is_noise(text: str) -> bool:
    """채팅이 아닌 줄(빈 줄, 깨진 글자, UI 텍스트)인지."""
    return not text.strip() or not any(char.isalnum() for char in text)


def _split_channel_command(text: str) -> tuple[Channel, str]:
    """내 입력 앞의 채널 명령 해석. 예) "/all 굿굿" → (all, "굿굿"). 명령이 없으면 (team, 그대로)."""
    match = re.match(r"^[ \t]*/all(?:[ \t]+|$)", text, re.IGNORECASE)
    return (Channel.ALL, text[match.end() :]) if match else (Channel.TEAM, text)
