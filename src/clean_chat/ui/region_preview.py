"""오디오 장치 없이 오버레이 뒤 화면의 최신 이미지 한 장을 가져온다."""

from __future__ import annotations

import ctypes
import hashlib
import platform
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

INTERVAL_MS = 1000  # 미리보기를 새로 가져오는 주기


def build_snapshot_library(output: Path) -> None:
    source = Path(__file__).with_name("region_snapshot.m")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        lib = Path(temp) / output.name
        subprocess.run(
            [
                "xcrun",
                "clang",
                "-dynamiclib",
                "-O2",
                "-Wl,-install_name,@rpath/region_snapshot.dylib",
                "-fobjc-arc",
                "-fblocks",
                "-framework",
                "Foundation",
                "-framework",
                "CoreGraphics",
                "-framework",
                "CoreMedia",
                "-framework",
                "CoreVideo",
                "-framework",
                "ScreenCaptureKit",
                str(source),
                "-o",
                str(lib),
            ],
            check=True,
            capture_output=True,
        )
        lib.replace(output)


@cache
def _mac_grab():
    lib = Path(__file__).with_name("region_snapshot.dylib")
    if not getattr(sys, "frozen", False):
        digest = hashlib.sha256(lib.with_suffix(".m").read_bytes()).hexdigest()[:16]
        root = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        lib = Path(root) / f"region-{platform.machine()}-{digest}.dylib"
        if not lib.exists():
            build_snapshot_library(lib)
    fn = ctypes.CDLL(str(lib)).cc_snapshot
    fn.argtypes = [ctypes.c_double] * 4 + [ctypes.c_int] * 2 + [ctypes.c_void_p] * 2 + [ctypes.c_size_t]
    fn.restype = ctypes.c_int
    return fn


def mac_snapshot(rect, scale: float) -> QImage:
    width, height = max(1, round(rect.width() * scale)), max(1, round(rect.height() * scale))
    pixels = ctypes.create_string_buffer(width * height * 4)
    error = ctypes.create_string_buffer(512)
    if not _mac_grab()(*rect.getRect(), width, height, pixels, error, len(error)):
        raise RuntimeError(error.value.decode("utf-8", errors="replace"))
    return QImage(pixels.raw, width, height, width * 4, QImage.Format_RGB32).copy()


class RegionPreview(QObject):
    """오버레이 좌표의 사각형만 주기적으로 한 장 가져온다 (우리 앱 창은 캡처에서 뺀다)."""

    OK = "오버레이 아래 화면 · 이미지 미리보기"
    image = Signal(QImage)
    status = Signal(str)

    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="region-preview")
        self.pending = None
        self.pending_key = None
        self.epoch = 0
        self.excluded = set()
        self.last_key = None

    def start(self) -> None:
        if self.timer.isActive():
            return
        self.status.emit("오버레이 아래 첫 이미지를 가져오는 중")
        self.timer.start(INTERVAL_MS)
        self._tick()

    def stop(self) -> None:
        self.timer.stop()
        self.epoch += 1
        self.last_key = None
        self.image.emit(QImage())
        if sys.platform == "win32":
            from clean_chat.ui.win32 import capture_exclusion

            for hwnd in self.excluded:
                capture_exclusion(hwnd, False)
            self.excluded.clear()

    def _tick(self) -> None:
        try:
            rect = self.overlay.geometry()
            screen = self.overlay.screen()
            key = (self.epoch, rect.getRect(), screen.name(), screen.devicePixelRatio())
            if key != self.last_key:
                self.image.emit(QImage())
                self.last_key = key
            if not screen.geometry().contains(rect):
                raise RuntimeError("오버레이 전체를 한 모니터 안으로 옮겨 주세요.")
            if sys.platform == "darwin":
                if self.pending is not None:
                    if not self.pending.done():
                        return
                    task, self.pending = self.pending, None
                    if self.pending_key == key:
                        self._show(task.result())
                self.pending_key = key
                self.pending = self.worker.submit(mac_snapshot, rect, screen.devicePixelRatio())
            else:
                from clean_chat.ui.win32 import capture_exclusion

                windows = {int(w.winId()) for w in QApplication.topLevelWidgets() if w.isVisible() and w.isWindow()}
                for hwnd in windows - self.excluded:
                    if not capture_exclusion(hwnd, True):
                        raise RuntimeError(
                            "Windows가 앱 창을 캡처에서 제외할 수 없습니다. Windows 10 2004 이상이 필요합니다."
                        )
                    self.excluded.add(hwnd)
                local = rect.translated(-screen.geometry().topLeft())
                self._show(screen.grabWindow(0, *local.getRect()).toImage())
            self.timer.setInterval(INTERVAL_MS)
        except Exception as exc:
            self.image.emit(QImage())
            self.status.emit(f"미리보기 재시도 중 · {exc}")
            self.timer.setInterval(1000)

    def _show(self, image: QImage) -> None:
        if image.isNull():
            raise RuntimeError("화면 이미지가 비어 있습니다.")
        self.image.emit(image)
        self.status.emit(self.OK)
