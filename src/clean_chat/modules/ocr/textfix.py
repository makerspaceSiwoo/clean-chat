"""OCR 이 읽은 줄의 흔한 오독을 글자 수준에서 바로잡는다 (실제 게임 화면 기록에서 확인한 것만).

1. 웃음 자모: `ㅋㅋㅋㅋㅋㅋㅋ` 를 `키키키ㅋ키키`, `카ㅋㅋ카카크키`, `ㅋㅋ브ㅋㅋㅋㅋ` 로 읽는다 → 다시 `ㅋ` 로.
2. 채팅 머리: `[전체]닉네임(챔피언)내용` 처럼 `:` 과 띄어쓰기를 빠뜨리고 괄호를 섞어 읽는다(`[전체)`, `(가렌]`)
   → `[전체] 닉네임 (챔피언): 내용`. `:` 이 없으면 parse 가 채팅으로 보지 않아 그 줄이 통째로 사라진다.
낱말을 추측해서 바꾸지는 않는다. 채널 표시(`[전체]`·`[팀]`)로 시작하는 줄만 채팅 머리로 본다.
"""

from __future__ import annotations

import re

_LAUGHS = (("ㅋ", frozenset("ㅋ크키카코쿠케캬")), ("ㅎ", frozenset("ㅎ흐히하호후")))
_MIN_RUN = 4  # 이보다 짧은 낱말은 건드리지 않는다 ("키카" 같은 말)
_SHARE = 0.7  # 낱말의 한글 중 이 비율 이상이 웃음 글자여야 한다

# [시간] [채널] 닉네임 (챔피언) : 내용 — 괄호 짝이 틀리거나 띄어쓰기·콜론이 빠져도 찾는다.
_HEAD = re.compile(
    r"^\s*(?P<time>\[\d{1,2}:\d{2}\])?\s*"
    r"\[(?P<channel>전체|팀)[\]\)]\s*"
    r"(?P<name>[^\[\]\(\):]{1,24}?)\s*"
    r"[\(\[](?P<champion>[^\[\]\(\):]{1,12})[\)\]]\s*"
    r":?\s*(?P<body>.*)$"
)


def _is_hangul(char: str) -> bool:
    return "가" <= char <= "힣" or "ㄱ" <= char <= "ㅣ"


def fix_laughs(text: str) -> str:
    """웃음 자모가 대부분인 낱말의 한글을 그 자모로 되돌린다. 예) "키키키ㅋ키키=" → "ㅋㅋㅋㅋㅋㅋ=" """

    def fix(word: str) -> str:
        letters = [char for char in word if _is_hangul(char)]
        if len(letters) < _MIN_RUN:
            return word
        for jamo, family in _LAUGHS:
            if sum(char in family for char in letters) >= len(letters) * _SHARE:
                return "".join(jamo if _is_hangul(char) else char for char in word)
        return word

    return re.sub(r"\S+", lambda match: fix(match[0]), text)


def fix_chat_head(text: str) -> str:
    """채널 표시로 시작하는 줄의 머리를 `[채널] 닉네임 (챔피언): 내용` 으로 맞춘다. 내용이 없으면 그대로 둔다."""
    match = _HEAD.match(text)
    if not match or not match["body"].strip() or not match["name"].strip():
        return text
    time = f"{match['time']} " if match["time"] else ""
    return f"{time}[{match['channel']}] {match['name'].strip()} ({match['champion'].strip()}): {match['body'].strip()}"


def tidy(text: str) -> str:
    return fix_laughs(fix_chat_head(text))
