"""기존 parse 결과가 message=None인 경우에도 식별 가능한 시스템 알림."""

import re

_PING = re.compile(
    r"(?:[^:\[\]：()\n]{1,32} \((?P<champion>[가-힣A-Za-z .']{1,22})\))님이 "
    r"(?P<signal>점멸 쿨타임|위험|도움 요청|적 사라짐|이동 중|공격|후퇴) 신호를 보냈습니다[.!]?"
)
_OBJECTIVE = re.compile(r"(아군|적) 팀이 (내셔 남작|드래곤|협곡의 전령|장로 드래곤)[을를] 처치했습니다[.!]?")


def system_notice(text: str) -> str | None:
    text = text.strip()
    if match := _PING.fullmatch(text):
        return f"{match['champion']} · {match['signal']} 신호"
    if match := _OBJECTIVE.fullmatch(text):
        return f"{match[1]} 팀 · {match[2]} 처치"
    return None
