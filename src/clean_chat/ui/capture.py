"""Qt 단일 창 캡처. 오버레이와 게임 창의 교차 좌표로 채팅 영역만 복사한다."""

from __future__ import annotations

import sys
import time

from PIL import Image
from PySide6.QtCore import QObject, QRect, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaCaptureSession, QVideoFrame, QVideoFrameFormat, QVideoSink, QWindowCapture

from clean_chat.core.grabber import ScreenGrabber, TextChangeGate
from clean_chat.core.schemas import Region
from clean_chat.ui.region_preview import RegionPreview
from clean_chat.ui.window_bounds import capture_allowed, capture_permission_message, game_window, native_rect


def pixel_crop(bounds: QRect, overlay: QRect, width: int, height: int) -> QRect:
    if bounds.isEmpty() or overlay.isEmpty() or not bounds.contains(overlay):
        return QRect()
    sx, sy = width / bounds.width(), height / bounds.height()
    x = round((overlay.x() - bounds.x()) * sx)
    y = round((overlay.y() - bounds.y()) * sy)
    right = round((overlay.x() + overlay.width() - bounds.x()) * sx)
    bottom = round((overlay.y() + overlay.height() - bounds.y()) * sy)
    return QRect(x, y, right - x, bottom - y)


def crop_frame(frame: QVideoFrame, rect: QRect) -> QImage:
    fmt = QVideoFrameFormat.imageFormatFromPixelFormat(frame.pixelFormat())
    if fmt != QImage.Format.Format_Invalid and frame.map(QVideoFrame.MapMode.ReadOnly):
        try:
            mapped = QImage(frame.bits(0), frame.width(), frame.height(), frame.bytesPerLine(0), fmt)
            if frame.surfaceFormat().scanLineDirection() == QVideoFrameFormat.Direction.BottomToTop:
                source = QRect(rect.x(), frame.height() - rect.y() - rect.height(), rect.width(), rect.height())
                crop = mapped.copy(source).mirrored(False, True)
            else:
                crop = mapped.copy(rect)
        finally:
            frame.unmap()
    else:
        crop = frame.toImage().copy(rect)
    if crop.isNull():
        raise RuntimeError("게임 프레임을 읽지 못했습니다.")
    return crop


def _ocr_image(crop: QImage) -> Image.Image:
    rgb = crop.convertToFormat(QImage.Format.Format_RGB888)
    return Image.frombytes("RGB", (rgb.width(), rgb.height()), rgb.constBits(), "raw", "RGB", rgb.bytesPerLine(), 1)


class WindowSampler(QObject):
    preview = Signal(QImage)
    status = Signal(str)
    permission_needed = Signal(bool)
    ended = Signal()
    failed = Signal(str)

    def __init__(self, source: ScreenGrabber, overlay):
        super().__init__()
        self.source, self.overlay = source, overlay
        self.capture = QWindowCapture(self)
        self.session = QMediaCaptureSession(self)
        self.sink = QVideoSink(self)
        self.session.setWindowCapture(self.capture)
        self.session.setVideoSink(self.sink)
        self.capture.errorOccurred.connect(self._failed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.window_id = 0
        self.missing_since = None
        self.last_region = None
        self.gate = TextChangeGate()
        self.started_at = 0.0
        self.received = False
        self.sampling = False
        self.preview_only = False
        self.region_preview = RegionPreview(overlay)
        self.permission_timer = QTimer(self)
        self.permission_timer.setInterval(1000)
        self.permission_timer.timeout.connect(self._check_permission)
        self.region_preview.image.connect(self.preview)
        self.region_preview.status.connect(self.status)

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
        if self.preview_only:
            self.region_preview.start()
            return
        self.sampling = True
        self.timer.start(self.gate.interval_ms(0))
        self._tick()

    def pause(self) -> None:
        self.permission_timer.stop()
        self.permission_needed.emit(False)
        if self.preview_only:
            self.region_preview.stop()
        self.sampling = False
        self.timer.stop()
        self.capture.stop()
        self.sink.setVideoFrame(QVideoFrame())
        self.window_id = 0
        self.missing_since = None
        self.reset_region()

    def stop(self) -> None:
        self.pause()
        self.source.finish()

    def reset_region(self) -> None:
        self.last_region = None
        self.gate = TextChangeGate()
        self.source.invalidate()

    def _failed(self, _error, message: str) -> None:
        if self.sampling:
            self.stop()
            self.failed.emit(f"게임 창 캡처 실패 · {message}")

    def _tick(self) -> None:
        try:
            self._sample()
        except Exception as exc:
            self._failed(None, str(exc))

    def _sample(self) -> None:
        now = time.monotonic()
        target = game_window(self.window_id)
        if target is None:
            if self.window_id:
                if self.missing_since is None:
                    self.missing_since = now
                    self.reset_region()
                    self.status.emit("게임 창이 숨겨졌습니다. 복귀 대기 중")
                if now - self.missing_since >= 10:
                    self.stop()
                    self.ended.emit()
                    return
            else:
                self.status.emit("인게임 창을 기다리는 중")
            self.timer.setInterval(1000)
            return
        self.missing_since = None
        ident, title, bounds = target
        if bounds.isEmpty():
            if self.last_region is not None:
                self.reset_region()
            self.status.emit("게임 창 복귀 대기 중")
            self.timer.setInterval(1000)
            return
        if not self.window_id:
            windows = [w for w in self.capture.capturableWindows() if w.description() == title]
            if len(windows) != 1:
                self.status.emit("게임 창을 식별할 수 없습니다. 테두리 없는 창 모드를 확인하세요.")
                self.timer.setInterval(1000)
                return
            self.window_id = ident
            self.capture.setWindow(windows[0])
            if hasattr(self.capture, "setMaximumFrameRate"):
                self.capture.setMaximumFrameRate(2)  # 1초마다 확인하므로 초당 2장이면 충분하다
            self.started_at, self.received = now, False
            self.capture.start()
            if self.sampling:
                self.timer.setInterval(self.gate.interval_ms(now))
            return
        frame = self.sink.videoFrame()
        if not frame.isValid():
            if self.last_region is not None:
                self.reset_region()
            if now - self.started_at > 5 and not self.received:
                self._failed(None, "프레임이 없습니다. 화면 기록 권한과 게임 창 모드를 확인하세요.")
            return
        self.received = True
        overlay = native_rect(int(self.overlay.winId())) if sys.platform == "win32" else self.overlay.geometry()
        rect = pixel_crop(bounds, overlay, frame.width(), frame.height())
        if rect.isEmpty():
            if self.last_region is not None:
                self.reset_region()
            self.status.emit("오버레이 전체를 게임 채팅 위에 놓아 주세요.")
            self.timer.setInterval(self.gate.interval_ms(now))
            return
        if rect != self.last_region:
            self.reset_region()
            self.last_region = rect
        crop = crop_frame(frame, rect)
        image = _ocr_image(crop)
        self.source.begin()
        if self.gate.observe(image, now):
            self.source.offer(image, Region(x=rect.x(), y=rect.y(), w=rect.width(), h=rect.height()))
        self.timer.setInterval(self.gate.interval_ms(now))
        self.status.emit(
            "채팅 감시 중" if not self.source.dropped else f"채팅 감시 중 · 대기열 초과 {self.source.dropped}프레임"
        )
