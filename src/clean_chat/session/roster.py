"""로컬 인게임 API에서 분석에 사용할 참가자 정보만 조회한다."""

import json
import ssl
from http.client import HTTPException, HTTPSConnection

from clean_chat.core.schemas import Player


def live_players() -> list[Player]:
    # 자체 서명 인증서인 고정 loopback 주소에만 접속한다. 리디렉션을 따르지 않는다.
    connection = HTTPSConnection("127.0.0.1", 2999, timeout=0.35, context=ssl._create_unverified_context())
    try:
        connection.request("GET", "/liveclientdata/playerlist")
        response = connection.getresponse()
        if response.status != 200:
            return []
        players = json.loads(response.read(128 * 1024))
        return [
            Player(
                name=p["summonerName"],
                champion=p.get("championName"),
                team=p.get("team"),
                position=p.get("position") or None,
            )
            for p in players
            if isinstance(p, dict) and p.get("summonerName")
        ]
    except (OSError, HTTPException, ValueError, TypeError):
        return []
    finally:
        connection.close()
