"""② parse — 줄 → 채팅 메시지 (시스템 메시지·핑 제외) + 정규화  (명세: docs/MODULES.md#parse, 예시: fixtures/parse/)

규칙(코드)만으로 처리한다. 결과가 정해진 규칙 모듈이라 fixtures 와 정확히 같아야 한다.
"""

from __future__ import annotations

import csv
import re
from functools import cache

from clean_chat.core.config import DATA
from clean_chat.core.schemas import Channel, ChatMessage, ParseRequest, ParseResult, Source

_CHANNEL = re.compile(r"^\[(팀|전체)\][ \t]*")
_SPEAKER = re.compile(r"([^:()\r\n]+?)(?:[ \t]*\(([^()\r\n]+)\))?[ \t]*:[ \t]?([^\r\n]*)")
_SYSTEM = re.compile(r".+(?:님이 .*(?:신호를 보냈습니다|처치했습니다)|님이 게임을 (?:종료|떠났)습니다)[.!]?")


def run(req: ParseRequest) -> ParseResult:
    """줄 1개 → 채팅이면 ChatMessage(채널·화자·챔피언·본문 + text_norm), 채팅이 아니면 None.

    입력: ParseRequest(line, my_name) → 출력: ParseResult(line_id, message)
    예) "[팀] 불꽃남자 (징크스): 야 정글 ㅂㅅ아 용 먼저 치라고"
        → channel=team, speaker="불꽃남자", champion="징크스", text="야 정글 ㅂㅅ아 용 먼저 치라고",
          text_norm="야 정글 병신아 용 먼저 치라고", hints=["lexicon:ㅂㅅ"], is_me=False
    예) "[팀] 나 (쓰레쉬): 정글 합류 부탁해요" (my_name="나") → is_me=True
    예) "초코우유 (리신)님이 점멸 쿨타임 신호를 보냈습니다" → 핑·시스템 메시지라 message=None
    예) "@@ ㅡ ##" → 잡음이라 message=None
    예) source=self_input, text="아 정글 ㅂㅅ 왜 안 와" (내 입력, 흐름 B)
        → channel=team, speaker=my_name, champion=None, is_me=True, raw=입력 그대로
    순서: (self_input 이면 _split_channel_command) / (아니면 _is_noise → _split_channel → _split_speaker → _is_system)
          → normalize(본문) → ChatMessage(raw=원본 줄 그대로)
    주의: text 와 raw 는 증거라서 절대 고치지 않는다(정규화는 text_norm 에만). OCR 오인식([ ↔ (, : ↔ ;)에 강하게.
    관련: ADR-0002, ADR-0006, OPEN-09
    """
    line = req.line
    if line.source == Source.SELF_INPUT:
        channel, body = _split_channel_command(line.text)
        speaker, champion, is_me = req.my_name, None, True
    else:
        if _is_noise(line.text):
            return ParseResult(line_id=line.id, message=None)
        channel, rest = _split_channel(line.text)
        speaker, champion, body = _split_speaker(rest)
        if speaker is None or _is_system(rest):
            return ParseResult(line_id=line.id, message=None)
        is_me = bool(req.my_name) and speaker == req.my_name
        channel = channel or Channel.UNKNOWN
    if not body.strip():
        return ParseResult(line_id=line.id, message=None)
    text_norm, hints = normalize(body)
    return ParseResult(
        line_id=line.id,
        message=ChatMessage(
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
        ),
    )


# ── 줄 분해 ──
def _split_channel(text: str) -> tuple[Channel | None, str]:
    """앞의 채널 표기와 나머지를 분리. 예) "[팀] 원딜러 (징크스): ..." → (team, "원딜러 (징크스): ...")"""
    match = _CHANNEL.match(text.lstrip())
    if match is None:
        return None, text.lstrip()
    return (Channel.TEAM if match[1] == "팀" else Channel.ALL), text.lstrip()[match.end() :]


def _split_speaker(rest: str) -> tuple[str | None, str | None, str]:
    """닉네임·챔피언·본문 분리. 예) "원딜러 (징크스): 용 먼저" → ("원딜러", "징크스", "용 먼저"). 닉네임에 공백 가능."""
    match = _SPEAKER.fullmatch(rest)
    if match is None or not match[1].strip():
        return None, None, ""
    return match[1].strip(), match[2].strip() if match[2] else None, match[3]


def _is_system(text: str) -> bool:
    """시스템 메시지·핑·스펠 체크 문구인지 (예: "~님이 처치했습니다", "~신호를 보냈습니다"). 문구 목록은 OPEN-09."""
    # 화자 구분자가 있는 실제 채팅은 본문에 알림 문구를 인용해도 보존한다.
    return _SPEAKER.fullmatch(text) is None and _SYSTEM.fullmatch(text.strip()) is not None


def _is_noise(text: str) -> bool:
    """채팅이 아닌 줄(빈 줄, 깨진 글자, UI 텍스트)인지."""
    return not text.strip() or not any(char.isalnum() for char in text)


def _split_channel_command(text: str) -> tuple[Channel, str]:
    """내 입력 앞의 채널 명령 해석. 예) "/all 굿굿" → (all, "굿굿"). 명령이 없으면 (team, 그대로)."""
    match = re.match(r"^[ \t]*/all(?:[ \t]+|$)", text, re.IGNORECASE)
    return (Channel.ALL, text[match.end() :]) if match else (Channel.TEAM, text)


# ── 정규화 (text → text_norm, hints) ──
def normalize(text: str) -> tuple[str, list[str]]:
    """본문을 분석하기 좋게 정리. 학습 데이터(training/)에도 같은 함수를 쓸 수 있다.

    예) "미드 시1발 개못하네" → ("미드 시발 개못하네", ["noise_removed"])
    예) "탑 니애미 tlqkf" → ("탑 니애미 시발", ["lexicon:tlqkf"])
    예) "다들 화이팅" → ("다들 화이팅", [])  ← 정상 문장은 그대로 (과잉 보정 금지)
    순서: _remove_noise_between_hangul → _join_spaced_jamo → _squeeze_repeats → _fix_ocr_errors → _apply_lexicon
    사전: data/lexicon/bypass.csv (variant, canonical, harm_type, note)
    """
    hints: list[str] = []
    text, changes = _remove_noise_between_hangul(text)
    hints.extend(changes)
    text, changes = _apply_lexicon(text)
    hints.extend(changes)
    return text, list(dict.fromkeys(hints))


def _remove_noise_between_hangul(text: str) -> tuple[str, list[str]]:
    """한글 사이 숫자·특수문자 제거. 예) "시1발" → "시발". (바뀐 문장, 붙일 hints)"""
    result = re.sub(r"시[0-9]+발", "시발", text)
    return result, ["noise_removed"] if result != text else []


def _join_spaced_jamo(text: str) -> tuple[str, list[str]]:
    """자모 사이 공백 제거. 예) "ㅅ ㅂ" → "ㅅㅂ"."""
    return text, []


def _squeeze_repeats(text: str) -> tuple[str, list[str]]:
    """같은 글자 반복 축약. 예) "ㅋㅋㅋㅋㅋ" → "ㅋㅋ"."""
    return text, []


def _fix_ocr_errors(text: str) -> tuple[str, list[str]]:
    """OCR 오인식 보정표 적용. 예) "l" ↔ "1", "0" ↔ "o" (한글 맥락에서만)."""
    return text, []


def _apply_lexicon(text: str) -> tuple[str, list[str]]:
    """우회어 사전 치환. 예) "tlqkf" → "시발" (hints: "lexicon:tlqkf"). 영타 변환 포함."""
    lexicon = _load_lexicon()
    # 한 번의 치환으로 끝내서 치환 결과를 다시 해석하지 않는다.
    pattern = "|".join(re.escape(variant) for variant in sorted(lexicon, key=lambda item: (-len(item), item)))
    hints: list[str] = []

    def replace(match: re.Match[str]) -> str:
        variant = match[0]
        hints.append(f"lexicon:{variant}")
        return lexicon[variant]

    return re.sub(pattern, replace, text), hints


@cache
def _load_lexicon() -> dict[str, str]:
    """공유 사전은 읽기만 하며 실행 위치와 관계없이 저장소 기준으로 찾는다."""
    with (DATA / "lexicon" / "bypass.csv").open(encoding="utf-8-sig", newline="") as stream:
        return {row["variant"]: row["canonical"] for row in csv.DictReader(stream) if row["variant"]}
