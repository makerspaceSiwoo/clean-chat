"""[구현 · WP8 · 🪟 Windows 전용] LCU·Live Client Data API 로 게임 단계와 플레이어 명단을 읽는 감지기.

읽기 전용으로만 쓴다. 채팅은 읽지 않는다(ADR-0002, ADR-0014). Windows 전용 라이브러리는 함수 안에서 import.
관련: HANDOFF 5-2, OPEN-12(단계 이름·전환 시점 실측)
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from clean_chat.core.schemas import GamePhase, PhaseEvent, Player


class LcuPhaseDetector:
    """[구현 · WP8] PhaseDetector 어댑터 (명세: docs/MODULES.md#session)"""

    def __init__(self, poll_sec: float = 1.5) -> None:
        """poll_sec: gameflow-phase 확인 주기 (settings.phase_poll_sec, 1~2초)."""
        self.poll_sec = poll_sec

    def events(self) -> Iterator[PhaseEvent]:
        """poll_sec 마다 LCU 단계를 읽고, 바뀌었을 때만 PhaseEvent 를 내보낸다. stop() 까지 계속.

        입력: 없음 (LCU 로컬 API) → 출력: PhaseEvent 스트림
        예) LCU "Lobby" → "InProgress" 로 바뀜 → PhaseEvent(ts=..., phase=in_game, raw="InProgress")
        순서: require_windows → _read_lockfile → (반복) _get_gameflow_phase → _to_game_phase → 바뀌었으면 yield
        주의: 클라이언트가 꺼져 있으면(lockfile 없음) 예외 대신 IDLE 로 보고 기다린다. 같은 단계는 다시 보내지 않는다.
        관련: OPEN-12
        """
        raise NotImplementedError("session 담당: events")

    def players(self) -> list[Player]:
        """게임 중 참가자 명단. Live Client Data API(https://127.0.0.1:2999/liveclientdata/playerlist).

        입력: 없음 → 출력: Player 목록 (내 소환사는 is_me=True, activeplayername 과 비교)
        예) [{"summonerName": "원딜러", "championName": "Jinx", "team": "ORDER", "position": "BOTTOM"}, ...]
            → Player(name="원딜러", champion="징크스", team="ORDER", position="BOTTOM")
        순서: _get_live_client_json("playerlist") → _to_players
        주의: 게임 로딩 중에는 응답이 없다(연결 거부) → 빈 목록. 자체 서명 인증서라 검증을 끈다(로컬 주소 한정).
        관련: OPEN-11(플레이어 명단), policy 의 공격 대상 추정
        """
        raise NotImplementedError("session 담당: players")

    def stop(self) -> None:
        """events() 반복을 멈춘다 (앱 종료 시)."""
        raise NotImplementedError("session 담당: stop")

    def _read_lockfile(self) -> tuple[int, str] | None:
        """롤 클라이언트 설치 폴더의 lockfile → (포트, 비밀번호). 클라이언트가 꺼져 있으면 None.

        예) "LeagueClient:1234:54321:abcd:https" → (54321, "abcd")
        주의: 비밀번호는 로그·파일에 남기지 않는다. 설치 경로는 기본값 + 설정으로 바꿀 수 있게.
        """
        raise NotImplementedError

    def _get_gameflow_phase(self, port: int, password: str) -> str | None:
        """GET https://127.0.0.1:<port>/lol-gameflow/v1/gameflow-phase (Basic 인증 riot:<password>) → 단계 문자열.

        예) "InProgress". 실패하면 None. 읽기 전용 GET 만 쓴다.
        """
        raise NotImplementedError

    def _to_game_phase(self, raw: str | None) -> GamePhase:
        """LCU 단계 문자열 → GamePhase.

        예) "InProgress" → IN_GAME, "EndOfGame" → POST_GAME, "Lobby"/"None"/None → IDLE
        주의: "Reconnect", "WaitingForStats", "PreEndOfGame" 등 경계 단계는 실측해서 표를 채운다(OPEN-12).
        """
        raise NotImplementedError

    def _get_live_client_json(self, path: str) -> object | None:
        """GET https://127.0.0.1:2999/liveclientdata/<path> → JSON. 게임 중이 아니면 None."""
        raise NotImplementedError

    def _to_players(self, playerlist: object) -> list[Player]:
        """Live Client Data playerlist JSON → Player 목록. 챔피언 영문 이름 → 한글 표기 변환 포함."""
        raise NotImplementedError

    @staticmethod
    def _lockfile_path() -> Path:
        """기본 lockfile 경로 (예: C:/Riot Games/League of Legends/lockfile). 실측 후 확정."""
        raise NotImplementedError
