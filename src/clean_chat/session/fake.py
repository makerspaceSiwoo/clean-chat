"""[동작함 · 모든 OS] 가짜 단계 감지기: 시나리오 JSONL 의 단계 이벤트와 플레이어 명단을 재생한다.

Mac 개발, 테스트, 발표 백업(데모 재생 모드)에서 LCU 대신 쓴다.
  fixtures/scenario/phases.jsonl   한 줄 = PhaseEvent  예) {"ts": 1762919900.0, "phase": "in_game", "raw": "InProgress"}
  fixtures/scenario/players.jsonl  한 줄 = Player
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

from clean_chat.core.schemas import PhaseEvent, Player
from clean_chat.core.stage import read_jsonl


class FakePhaseDetector:
    def __init__(self, phases: Path, players: Path | None = None, delay_sec: float = 0.0) -> None:
        self.phases_path, self.players_path, self.delay = Path(phases), players, delay_sec
        self._stop = threading.Event()

    def events(self) -> Iterator[PhaseEvent]:
        for ev in read_jsonl(self.phases_path, PhaseEvent):
            if self._stop.wait(self.delay):  # delay 만큼 기다리다가 stop() 이 불리면 바로 멈춤
                return
            yield ev

    def players(self) -> list[Player]:
        if self.players_path is None or not Path(self.players_path).exists():
            return []
        return read_jsonl(Path(self.players_path), Player)

    def stop(self) -> None:
        self._stop.set()
