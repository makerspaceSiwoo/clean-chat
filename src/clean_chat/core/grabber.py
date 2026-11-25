"""게임 창에서 얻은 채팅 영역의 변화 검사와 OCR 작업자용 유한 버퍼."""

from __future__ import annotations

import tempfile
import threading
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from queue import Queue
from uuid import uuid4

from clean_chat.core.schemas import Frame, GamePhase, PhaseEvent, Player, Region


class TextChangeGate:
    """가로로 모인 밝은 획을 작은 칸으로 집계해 이전 OCR 후보와 비교한다."""

    def __init__(self) -> None:
        self.previous = None
        self.last_ink = None
        self.active_until = 0.0
        self.last_check: float | None = None

    def interval_ms(self, now: float) -> int:
        return 100 if now < self.active_until else 200

    def observe(self, image, now: float) -> bool:
        import numpy as np

        # 축소해도 한글 획과 짧은 콜을 구별할 수 있도록 두 픽셀마다 본다.
        rgb = np.asarray(image)[::2, ::2]
        light = rgb.max(axis=2).astype(np.int16)
        if min(light.shape) < 5:
            return False
        center = light[1:-1, 1:-1]
        dark = np.minimum(np.minimum(light[:-2, 1:-1], light[2:, 1:-1]), np.minimum(light[1:-1, :-2], light[1:-1, 2:]))
        strokes = (center >= 148) & (center - dark >= 48)
        h, w = strokes.shape

        def glyph_tiles(mask):
            tiles = np.pad(mask, ((0, -h % 3), (0, -w % 4))).reshape((h + 2) // 3, 3, (w + 3) // 4, 4)
            ink = tiles.sum(axis=(1, 3)) >= 2
            return ink & (np.pad(ink[:, :-1], ((0, 0), (1, 0))) | np.pad(ink[:, 1:], ((0, 0), (0, 1))))

        ink = glyph_tiles(strokes)
        busy = np.count_nonzero(ink.mean(axis=1) > 0.20) > len(ink) * 0.65
        if busy:
            # 전체가 반짝일 때만 글자 팔레트(흰색·황색·청색·적색)를 좁게 본다.
            r, g, b = rgb[1:-1, 1:-1].astype(np.int16).transpose(2, 0, 1)
            palette = (
                (center - np.minimum(np.minimum(r, g), b) < 32)
                | ((r > 210) & (g > 145) & (b < 100))
                | ((b > 205) & (g > 150) & (r < 110))
                | ((r > 210) & (g < 100) & (b < 100))
            )
            ink = glyph_tiles(strokes & palette)
        candidate = ink
        if busy:
            if self.last_ink is None or self.last_ink.shape != ink.shape:
                candidate = np.zeros_like(ink)
            else:
                candidate = ink & self.last_ink
                # 두 장에서 같은 위치에 모인 획이 있어야 채팅 줄로 인정한다.
                sums = np.pad(candidate, ((0, 0), (8, 0))).cumsum(axis=1)
                groups = sums[:, 8:] - sums[:, :-8]
                dense = groups >= 5
                support = dense.copy()
                for offset in range(1, min(8, dense.shape[1])):
                    support[:, :-offset] |= dense[:, offset:]
                candidate &= support
        self.last_ink = ink
        present = bool(candidate.any())
        if self.previous is None or self.previous.shape != candidate.shape:
            changed = present
        else:
            threshold = np.maximum(4, self.previous.sum(axis=1) * 0.15) if busy else 2
            changed_rows = np.count_nonzero(candidate != self.previous, axis=1) >= threshold
            changed = present and bool(changed_rows.any()) and (not busy or changed_rows.mean() < 0.6)
        if changed:
            self.active_until = now + 1.0
        # 놓친 작은 글자·색상과 숨김 판정 오류도 복구한다. 빈 화면에서는 드물게만 확인.
        if self.last_check is None:
            self.last_check = now
        due = now - self.last_check >= (1.0 if present or busy else 3.0)
        if not present:
            self.previous = None
        if changed or due:
            self.previous = candidate if present else None
            self.last_check = now
            return True
        return False


class ScreenGrabber:
    """UI는 crop만 넣고 엔진은 OCR에 필요한 이미지 한 장만 임시 PNG로 만든다."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._pending = deque(maxlen=6)
        self._events: Queue[PhaseEvent | None] = Queue()
        self._running = False
        self._epoch = 0
        self._closed = False
        self.dropped = 0
        self.next_roster_check = 0.0

    @property
    def generation(self) -> int:
        with self._condition:
            return self._epoch

    @property
    def running(self) -> bool:
        with self._condition:
            return self._running

    def begin(self) -> None:
        with self._condition:
            if self._running or self._closed:
                return
            self._running = True
            self.dropped = 0
            self.next_roster_check = 0.0
            self._events.put(PhaseEvent(ts=time.time(), phase=GamePhase.IN_GAME))

    def invalidate(self) -> None:
        with self._condition:
            self._pending.clear()
            self._epoch += 1
            self._condition.notify_all()

    def offer(self, image, region: Region) -> None:
        with self._condition:
            if self._running:
                if len(self._pending) == self._pending.maxlen:
                    self.dropped += 1
                self._pending.append((self._epoch, time.time(), image, region))
                self._condition.notify()

    def current(self, frame: Frame) -> bool:
        with self._condition:
            return self._running and frame.id.partition("-")[0] == str(self._epoch)

    def finish(self) -> None:
        with self._condition:
            if self._running:
                self._running = False
                self.invalidate()
                self._events.put(PhaseEvent(ts=time.time(), phase=GamePhase.POST_GAME))

    def frames(self) -> Iterator[Frame]:
        with tempfile.TemporaryDirectory(prefix="clean-chat-") as folder:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._pending or not self._running)
                    if not self._running:
                        return
                    epoch, ts, image, region = self._pending.popleft()
                frame_id = f"{epoch}-{uuid4().hex}"
                path = Path(folder) / "chat.png"
                image.save(path, compress_level=1)
                yield Frame(id=frame_id, ts=ts, image_path=str(path), region=region)

    def events(self) -> Iterator[PhaseEvent]:
        while (event := self._events.get()) is not None:
            yield event

    def players(self) -> list[Player]:
        from clean_chat.session.roster import live_players

        now = time.monotonic()
        if now < self.next_roster_check:
            return []
        self.next_roster_check = now + 5.0
        return live_players()

    def stop(self) -> None:
        with self._condition:
            self._closed = True
            self.finish()
            self._events.put(None)
