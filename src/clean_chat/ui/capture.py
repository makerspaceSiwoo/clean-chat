"""오버레이가 가린 영역만 캡처한다. 게임 창은 찾지 않는다. 잠근 동안은 항상 OCR 로 읽는다.

위치를 잠근 순간이 게임 시작이고, 오버레이를 종료한 순간이 게임 끝이다.
오버레이 아래에 있는 것은 무엇이든 읽으므로, 게임이 끝나면 오버레이를 종료해야 한다.
"""

from __future__ import annotations

import time

from PIL import Image
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage

from clean_chat.core.grabber import ScreenGrabber, TextChangeGate
from clean_chat.core.schemas import Region
from clean_chat.ui.region_preview import RegionPreview
from clean_chat.ui.window_bounds import capture_allowed, capture_permission_message


def _ocr_image(crop: QImage) -> Image.Image:
    rgb = crop.convertToFormat(QImage.Format.Format_RGB888)
    return Image.frombytes("RGB", (rgb.width(), rgb.height()), rgb.constBits(), "raw", "RGB", rgb.bytesPerLine(), 1)


class WindowSampler(QObject):
    preview = Signal(QImage)  # 방금 캡처한 영역 (클라이언트의 캡처 미리보기)
    status = Signal(str)
    permission_needed = Signal(bool)
    failed = Signal(str)

    def __init__(self, source: ScreenGrabber, overlay):
        super().__init__()
        self.source, self.overlay = source, overlay
        self.gate = TextChangeGate()
        self.sampling = False  # 캡처한 영역을 OCR 로 보내는 중인가 (위치를 잠근 동안 True)
        self.region_preview = RegionPreview(overlay)
        self.timer = self.region_preview.timer  # 영역을 가져오는 주기 타이머
        self.permission_timer = QTimer(self)
        self.permission_timer.setInterval(1000)
        self.permission_timer.timeout.connect(self._check_permission)
        self.region_preview.image.connect(self._captured)
        self.region_preview.status.connect(self._status)

    def start(self) -> None:
        if capture_allowed():
            self._start_capture()
            return
        self.status.emit(capture_permission_message())
        self.permission_needed.emit(True)
        self.permission_timer.start()

    def _check_permission(self) -> None:
        if self.permission_timer.isActive() and capture_allowed(request=False):
            self._start_capture()

    def _start_capture(self) -> None:
        self.permission_timer.stop()
        self.permission_needed.emit(False)
        self.sampling = True  # 잠그면 항상 OCR 로 읽는다. 미리보기는 화면에 보여 줄지 말지만 정한다.
        self.source.begin()  # 위치를 잠근 순간이 게임 시작이다 (게임 창을 찾지 않는다)
        self.region_preview.start()

    def pause(self) -> None:
        """캡처만 멈춘다 (영역 다시 맞추기). 게임 기록은 이어진다."""
        self.permission_timer.stop()
        self.permission_needed.emit(False)
        self.sampling = False
        self.region_preview.stop()
        self.reset_region()

    def stop(self) -> None:
        """오버레이 종료 = 게임 끝. 이번 게임 기록으로 신고 문구·고소장 초안을 만든다."""
        self.pause()
        self.source.finish()

    def reset_region(self) -> None:
        self.gate = TextChangeGate()
        self.source.invalidate()

    def _captured(self, image: QImage) -> None:
        self.preview.emit(image)
        if not self.sampling:
            return
        if image.isNull():  # 오버레이를 옮겼거나 캡처에 실패함 → 앞 영역의 판독은 버린다
            self.reset_region()
            return
        try:
            frame = _ocr_image(image)
            if self.gate.observe(frame, time.monotonic()):
                rect = self.overlay.geometry()
                self.source.offer(frame, Region(x=rect.x(), y=rect.y(), w=frame.width, h=frame.height))
        except Exception as exc:
            self.stop()
            self.failed.emit(f"채팅 영역 캡처 실패 · {exc}")

    def _status(self, text: str) -> None:
        if self.sampling:
            if text == RegionPreview.OK:
                dropped = self.source.dropped
                text = "채팅 감시 중" if not dropped else f"채팅 감시 중 · 대기열 초과 {dropped}프레임"
            else:
                text = text.replace("미리보기", "캡처")
        self.status.emit(text)
