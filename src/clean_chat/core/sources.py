"""입력 포트와 어댑터 (패턴: 포트와 어댑터 / Hexagonal). OS별로 어댑터만 바꿔 끼운다.

채팅 소스 (흐름 A 입력, IN_GAME 동안만 읽음)
| 어댑터            | 내보내는 것 | OS       | 용도                              |
|------------------|-----------|----------|----------------------------------|
| DemoLineSource   | RawLine   | 모두      | 시나리오 재생 (Mac 개발, 발표 백업) |
| ScreenshotSource | Frame     | 모두      | 저장된 스크린샷으로 OCR 테스트       |
| ScreenGrabber    | Frame     | Windows  | 실제 게임 화면 캡처 (capture 모듈)  |

게임 단계 감지기 (PhaseDetector)
| 어댑터                         | OS      | 용도                                        |
|-------------------------------|---------|--------------------------------------------|
| session.fake.FakePhaseDetector | 모두     | 시나리오 JSONL 의 {"phase": ...} 이벤트 재생   |
| session.windows.LcuPhaseDetector | Windows | LCU gameflow-phase 읽기 (읽기 전용, 실측 필요) |

finite = True 인 소스는 끝이 있는 재생용이다. 게임 종료 신호가 와도 남은 줄을 끝까지 처리한다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from clean_chat.core.schemas import Frame, PhaseEvent, Player, RawLine, Region
from clean_chat.core.stage import read_jsonl


class LineSource(Protocol):
    def lines(self) -> Iterator[RawLine]: ...


class FrameSource(Protocol):
    def frames(self) -> Iterator[Frame]: ...


class PhaseDetector(Protocol):
    """게임 단계 감지기 (포트). 단계가 바뀔 때마다 PhaseEvent 를 내보낸다."""

    def events(self) -> Iterator[PhaseEvent]:
        """단계 이벤트 스트림. 실제 감지기는 끝나지 않고, stop() 이 불리면 멈춘다."""
        ...

    def players(self) -> list[Player]:
        """지금 게임의 참가자 명단 (게임 중에 호출). 모르면 빈 목록."""
        ...

    def stop(self) -> None: ...


class DemoLineSource:
    finite = True

    def __init__(self, path: Path, delay_sec: float = 1.0) -> None:
        self.path, self.delay = Path(path), delay_sec

    def lines(self) -> Iterator[RawLine]:
        for line in read_jsonl(self.path, RawLine):
            if self.delay > 0:
                time.sleep(self.delay)
            yield line


class ScreenshotSource:
    """폴더 안의 PNG를 순서대로 Frame으로 내보냄 (Mac에서 OCR 테스트용)."""

    finite = True

    def __init__(self, folder: Path, region: Region, delay_sec: float = 0.5) -> None:
        self.folder, self.region, self.delay = Path(folder), region, delay_sec

    def frames(self) -> Iterator[Frame]:
        for i, p in enumerate(sorted(self.folder.glob("*.png"))):
            if self.delay > 0:
                time.sleep(self.delay)
            yield Frame(id=f"shot-{i}", ts=time.time(), image_path=str(p), region=self.region)
