"""OCR 이 읽은 줄의 흔한 오독을 글자 수준에서 바로잡는다 (실제 게임 화면 기록에서 확인한 것만).

1. 웃음 자모: `ㅋㅋㅋㅋㅋㅋㅋ` 를 `키키키ㅋ키키`, `카ㅋㅋ카카크키`, `ㅋㅋ브ㅋㅋㅋㅋ` 로 읽는다 → 다시 `ㅋ` 로.
2. 채팅 머리: `[전체]닉네임(챔피언)내용` 처럼 `:` 과 띄어쓰기를 빠뜨리고 괄호를 섞어 읽는다(`[전체)`, `(가렌]`)
   → `[전체] 닉네임 (챔피언): 내용`. `:` 이 없으면 parse 가 채팅으로 보지 않아 그 줄이 통째로 사라진다.
   팀 채팅은 채널 표시 없이 시간으로 시작한다: `[13:18]돌여울(가렌)정글 …` → `[13:18] 돌여울 (가렌): 정글 …`.
낱말을 추측해서 바꾸지는 않는다. 채널 표시(`[전체]`·`[팀]`)나 시간(`[03:35]`)으로 시작하는 줄만 채팅 머리로 본다.
`(챔피언)님이 …` 로 이어지는 시스템 알림은 채팅 머리로 바꾸지 않는다.
"""

from __future__ import annotations

import re

_LAUGHS = (("ㅋ", frozenset("ㅋ크키카코쿠케캬")), ("ㅎ", frozenset("ㅎ흐히하호후")))
_MIN_RUN = 4  # 이보다 짧은 낱말은 건드리지 않는다 ("키카" 같은 말)
_SHARE = 0.7  # 낱말의 한글 중 이 비율 이상이 웃음 글자여야 한다

# [시간] [채널] 닉네임 (챔피언) : 내용 — 괄호 짝이 틀리거나 띄어쓰기·콜론이 빠져도 찾는다.
_HEAD = re.compile(
    r"^\s*(?P<time>\[\d{1,2}:\d{2}\])?\s*"
    r"(?:\[(?P<channel>전체|팀)[\]\)]\s*)?"
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
    """채널 표시나 시간으로 시작하는 줄의 머리를 `[시간] [채널] 닉네임 (챔피언): 내용` 으로 맞춘다.

    내용이 없거나, 채널·시간이 둘 다 없거나, `(챔피언)님이 …` 시스템 알림이면 그대로 둔다.
    """
    match = _HEAD.match(text)
    if not match or not (match["time"] or match["channel"]) or not match["name"].strip():
        return text
    body = match["body"].strip()
    if not body or body.startswith("님"):
        return text
    time = f"{match['time']} " if match["time"] else ""
    channel = f"[{match['channel']}] " if match["channel"] else ""
    champion = match["champion"].strip(" |")  # OCR 이 괄호 앞에 세로줄을 붙여 읽는다 ("(쓰레쉬|)")
    return f"{time}{channel}{match['name'].strip()} ({champion}): {body}"


def tidy(text: str) -> str:
    return fix_laughs(fix_chat_head(text))
