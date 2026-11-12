"""입력 소스: 파이프라인에 무엇을 흘려보낼지 (OS별 선택 지점).

| 소스              | 내보내는 것 | OS       | 용도                              |
|------------------|-----------|----------|----------------------------------|
| DemoLineSource   | RawLine   | 모두      | 시나리오 재생 (Mac 개발, 발표 백업) |
| ScreenshotSource | Frame     | 모두      | 저장된 스크린샷으로 OCR 테스트       |
| ScreenGrabber    | Frame     | Windows  | 실제 게임 화면 캡처 (capture 모듈)  |
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from clean_chat.core.schemas import Frame, RawLine, Region
from clean_chat.core.stage import read_jsonl


class LineSource(Protocol):
    def lines(self) -> Iterator[RawLine]: ...


class FrameSource(Protocol):
    def frames(self) -> Iterator[Frame]: ...


class DemoLineSource:
    def __init__(self, path: Path, delay_sec: float = 1.0) -> None:
        self.path, self.delay = Path(path), delay_sec

    def lines(self) -> Iterator[RawLine]:
        for line in read_jsonl(self.path, RawLine):
            if self.delay > 0:
                time.sleep(self.delay)
            yield line


class ScreenshotSource:
    """폴더 안의 PNG를 순서대로 Frame으로 내보냄 (Mac에서 OCR 테스트용)."""

    def __init__(self, folder: Path, region: Region, delay_sec: float = 0.5) -> None:
        self.folder, self.region, self.delay = Path(folder), region, delay_sec

    def frames(self) -> Iterator[Frame]:
        for i, p in enumerate(sorted(self.folder.glob("*.png"))):
            if self.delay > 0:
                time.sleep(self.delay)
            yield Frame(id=f"shot-{i}", ts=time.time(), image_path=str(p), region=self.region)
