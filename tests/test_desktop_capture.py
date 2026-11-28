"""숨김·폭주·재보정과 오버레이 아래 창의 좌표 변환 회귀 검사."""

import os
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PIL")
pytest.importorskip("numpy")
pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw
from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtMultimedia import QVideoFrame

from clean_chat.core.engine import Engine
from clean_chat.core.grabber import ScreenGrabber, TextChangeGate
from clean_chat.core.pipeline import LineDedup, Pipelines
from clean_chat.core.schemas import OcrResult, RawLine, Region
from clean_chat.modules.parse.notices import system_notice
from clean_chat.ui.app import App
from clean_chat.ui.capture import crop_frame, pixel_crop
from helpers import fixture_modules, fixture_pairs


def snapshot(y=None, background=(45, 74, 86)):
    image = Image.new("RGB", (400, 150), background)
    if y is not None:
        draw = ImageDraw.Draw(image)
        for x in range(14, 62, 8):
            draw.rectangle((x, y, x + 3, y + 11), fill="white")
    return image


def test_hidden_idle_first_call_scroll_and_watchdog():
    gate = TextChangeGate()
    gate.observe(snapshot(), 0)
    assert not gate.observe(snapshot(background=(93, 63, 85)), 0.2)
    assert gate.interval_ms(0.2) == 200
    assert gate.observe(snapshot(110), 0.4)
    assert gate.interval_ms(0.4) == 100
    assert not gate.observe(snapshot(110, (55, 74, 61)), 0.5)
    assert gate.observe(snapshot(92), 0.6)
    assert gate.interval_ms(1.61) == 200
    assert gate.observe(snapshot(92), 1.61)
    assert not gate.observe(snapshot(), 1.7)
    assert gate.observe(snapshot(92), 1.8)


def test_scroll_preserves_repeated_calls_and_hidden_history():
    dedup = LineDedup()

    def read(*words):
        return [
            line.text
            for line in dedup.new_lines([RawLine(id=str(i), ts=0, source="ocr", text=w) for i, w in enumerate(words)])
        ]

    assert read("A", "B", "C", "D", "E", "용") == ["A", "B", "C", "D", "E", "용"]
    assert read() == []
    assert read("B", "C", "D", "E", "용", "용") == ["용"]
    assert read("E", "용", "용", "후퇴", "핑", "바론") == ["후퇴", "핑", "바론"]


def test_retina_external_screen_and_native_crop():
    bounds = QRect(-1000, 100, 800, 600)
    rect = pixel_crop(bounds, QRect(-940, 300, 120, 100), 1600, 1200)
    assert rect == QRect(120, 400, 240, 200)
    assert pixel_crop(bounds, QRect(-1010, 100, 200, 100), 1600, 1200).isEmpty()
    image = QImage(1600, 1200, QImage.Format_RGB32)
    image.fill(QColor("black"))
    image.setPixelColor(120, 400, QColor("red"))
    crop = crop_frame(QVideoFrame(image), rect)
    assert (crop.width(), crop.height()) == (240, 200)
    assert crop.pixelColor(0, 0) == QColor("red")


def test_capture_buffer_bounded_order_cleanup_and_stop():
    src = ScreenGrabber()
    roi = Region(x=0, y=0, w=400, h=150)
    src.begin()
    for n in range(8):
        src.offer(snapshot(background=(n, n, n)), roi)
    assert src.dropped == 2
    frames = src.frames()
    first = next(frames)
    with Image.open(first.image_path) as img:
        assert img.getpixel((0, 0)) == (2, 2, 2)
    src.invalidate()
    assert not src.current(first)
    src.finish()
    assert list(frames) == []
    assert not Path(first.image_path).exists()
    src.stop()


def test_live_ocr_and_rewrite_do_not_block_capture_or_next_call(monkeypatch):
    src = ScreenGrabber()
    monkeypatch.setattr(src, "players", lambda: [])
    roi = Region(x=0, y=0, w=400, h=150)
    entered, release_ocr = threading.Event(), threading.Event()
    rewriting, release_rewrite = threading.Event(), threading.Event()
    fast_call = threading.Event()
    rows = []
    lines = {req.line.id: req.line for req, _ in fixture_pairs("parse")}
    batches = iter([["L3"], ["L3", "L1", "L0"]])

    def ocr(frame):
        entered.set()
        assert release_ocr.wait(3)
        return OcrResult(frame_id=frame.id, lines=[lines[k] for k in next(batches)])

    def rewrite(req):
        rewriting.set()
        assert release_rewrite.wait(3)
        return fixture_modules().run("rewrite", req)

    def row(_generation, index, text):
        rows.append((index, text))
        if "화이팅" in text:
            fast_call.set()

    engine = Engine(Pipelines(fixture_modules(ocr=ocr, rewrite=rewrite)), src, src)
    engine.on_row(row)
    engine.start()
    try:
        src.begin()
        src.offer(snapshot(100), roi)
        assert entered.wait(3)
        src.offer(snapshot(80), roi)
        release_ocr.set()
        assert rewriting.wait(3)
        assert fast_call.wait(3)
        assert rows[0] == (2, "리신 · 점멸 쿨타임 신호")
        release_rewrite.set()
        until = time.monotonic() + 3
        while len(rows) < 3 and time.monotonic() < until:
            time.sleep(0.01)
        assert [n for n, _ in rows] == [2, 3, 1]
    finally:
        release_ocr.set()
        release_rewrite.set()
        engine.stop()
        engine._thread.join(3)
    assert not engine._thread.is_alive()


def test_ui_start_lock_pause_stop_and_failure_preserves_cover(tmp_path, monkeypatch):
    src = ScreenGrabber()
    prefs = QSettings(str(tmp_path / "overlay.ini"), QSettings.IniFormat)
    monkeypatch.setattr("clean_chat.ui.app.QSettings", lambda *args: prefs)
    monkeypatch.setattr("clean_chat.ui.capture.capture_allowed", lambda: True)
    monkeypatch.setattr("clean_chat.ui.capture.game_window", lambda *args: None)
    app = App(Pipelines(fixture_modules()), src, src)
    app.client.preview_only.setChecked(False)
    app.show()
    assert not app.overlay.isVisible()
    app.client.btn_start.click()
    assert app.overlay.isVisible() and app.overlay.editing
    app.client.btn_lock.click()
    assert app.overlay.windowFlags() & Qt.WindowTransparentForInput
    assert app.sampler.timer.isActive()
    app.client.btn_lock.click()
    assert not app.sampler.timer.isActive()
    app.capture_failed("캡처 실패")
    assert app.overlay.isVisible()
    app.client.btn_start.click()
    assert not app.overlay.isVisible()
    app.shutdown()
    app.client.close()


def test_unknown_and_player_chat_never_become_system_notices():
    assert system_notice("아군 팀이 내셔 남작을 처치했습니다!") == "아군 팀 · 내셔 남작 처치"
    assert system_notice("[팀] 나 (룰루): 위험 신호를 보냈습니다") is None
    assert system_notice("판독 실패") is None


def test_sampler_reads_all_six_rows_from_game_frame(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QWidget

    from clean_chat.ui.capture import WindowSampler

    qt = QApplication.instance() or QApplication([])
    overlay = QWidget()
    overlay.setGeometry(120, 230, 200, 120)
    bounds = QRect(100, 200, 640, 480)
    game = QImage(640, 480, QImage.Format_RGB32)
    game.fill(Qt.black)
    for row in range(6):
        game.setPixelColor(20, 30 + 20 * row, QColor("red"))
    src = ScreenGrabber()
    sampler = WindowSampler(src, overlay)
    sampler.window_id = 7
    sampler.sampling = True
    sampler.sink.setVideoFrame(QVideoFrame(game))
    monkeypatch.setattr("clean_chat.ui.capture.game_window", lambda _id: (7, "game", bounds))
    # 이 테스트의 좌표는 Qt 논리 좌표와 네이티브 좌표가 같은 화면을 사용한다.
    monkeypatch.setattr("clean_chat.ui.capture.native_rect", lambda _id: overlay.geometry())
    sampler._sample()
    # 새 영역의 첫 검사는 초기 기준 화면으로 쓰일 수도 있다. 주기 재검사를 앞당긴다.
    sampler.gate.last_check = float("-inf")
    sampler._sample()
    frames = src.frames()
    frame = next(frames)
    with Image.open(frame.image_path) as img:
        assert img.size == (200, 120)
        assert all(img.getpixel((0, 20 * r)) == (255, 0, 0) for r in range(6))
    sampler.stop()
    frames.close()
    qt.processEvents()


def test_broad_fighting_effects_do_not_run_ocr_every_sample():
    import numpy as np

    def simulate(add_call):
        rng = np.random.default_rng(80)
        gate = TextChangeGate()
        events = []
        now = 0
        while now < 10_000:
            pixels = rng.integers(0, 256, (160, 460, 3), dtype=np.uint8)
            if add_call and now >= 4000:
                pixels[90:109, 10:190] = 55
                for x in range(14, 174, 8):
                    pixels[92:105, x : x + 3] = 255
            if gate.observe(Image.fromarray(pixels), now / 1000):
                events.append(now)
            now += gate.interval_ms(now / 1000)
        return events

    assert len(simulate(False)) < 20
    with_call = simulate(True)
    assert len(with_call) < 20
    assert any(4000 < tick <= 4400 for tick in with_call)


def test_preview_refreshes_same_and_changed_crops_without_ocr(tmp_path, monkeypatch):
    source = ScreenGrabber()
    prefs = QSettings(str(tmp_path / "preview.ini"), QSettings.IniFormat)
    monkeypatch.setattr("clean_chat.ui.app.QSettings", lambda *args: prefs)
    from clean_chat.ui import region_preview

    permission = [False]
    permission_queries = []

    def check_permission(request=True):
        permission_queries.append(request)
        return permission[0]

    color = [Qt.red]
    calls = []

    def capture(rect, scale):
        calls.append(rect)
        image = QImage(round(rect.width() * scale), round(rect.height() * scale), QImage.Format_RGB32)
        image.fill(color[0])
        return image

    monkeypatch.setattr("clean_chat.ui.capture.capture_allowed", check_permission)
    monkeypatch.setattr(region_preview, "mac_snapshot", capture)
    monkeypatch.setattr("clean_chat.ui.capture.game_window", lambda *args: pytest.fail("preview queried LoL"))
    monkeypatch.setattr(source, "begin", lambda: pytest.fail("preview started OCR"))
    app = App(Pipelines(), source, source)
    app.show()
    app.client.btn_start.click()
    preview = app.sampler.region_preview
    assert app.overlay.editing and not preview.timer.isActive()
    assert not permission_queries and not calls
    app.client.btn_lock.click()
    assert app.sampler.permission_timer.isActive() and not preview.timer.isActive() and not app.overlay.editing
    assert app.client.permission_settings.isVisible()
    app.sampler._check_permission()
    assert permission_queries == [True, False]
    assert "권한" in app.client.preview_image.text()
    assert not calls
    permission[0] = True
    # 이 검사는 macOS 비동기 이미지 경로와 권한 승인 후 자동 복구를 재현한다.
    from types import SimpleNamespace

    monkeypatch.setattr(region_preview, "sys", SimpleNamespace(platform="darwin"))

    app.sampler._check_permission()
    assert not app.sampler.permission_timer.isActive() and preview.timer.isActive()
    assert not app.client.permission_settings.isVisible()

    def tick():
        preview._tick()
        preview.pending.result(timeout=2)

    preview.pending.result(timeout=2)
    tick()
    assert app.client.preview_count == 1
    assert app.client.preview_image.pixmap().toImage().pixelColor(0, 0) == QColor(Qt.red)
    assert app.overlay.windowFlags() & Qt.WindowTransparentForInput
    app.client.btn_lock.click()
    assert not preview.timer.isActive() and app.client.preview_image.pixmap().isNull()
    color[0] = Qt.green
    app.overlay.resize(310, 130)
    app.client.btn_lock.click()
    # 다시 시작할 때 낸 캡처가 끝난 뒤 한 번만 갱신한다. 끝났는지에 따라 tick 결과가 달라지지 않게 먼저 기다린다.
    preview.pending.result(timeout=2)
    tick()
    assert app.client.preview_count == 1
    assert app.client.preview_image.pixmap().toImage().pixelColor(0, 0) == QColor(Qt.green)
    assert calls[-1] == app.overlay.geometry()
    app.client.btn_start.click()
    assert app.client.preview_image.pixmap().isNull() and not preview.timer.isActive()
    assert prefs.contains("overlay/geometry")
    queries_before_restart = len(permission_queries)
    app.client.btn_start.click()
    assert app.overlay.editing and not preview.timer.isActive()
    assert len(permission_queries) == queries_before_restart
    app.stop()
    app.shutdown()
    app.client.close()


def test_mac_permission_request_survives_restart_and_honors_os_state(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from clean_chat.ui import window_bounds

    allowed = False
    requests = []
    settings_file = str(tmp_path / "permission.ini")

    def settings(*_):
        return QSettings(settings_file, QSettings.IniFormat)

    def request():
        # 시스템이 승인 창에서 앱을 종료해도 다음 실행에서 요청을 반복하지 않는다.
        assert settings().allKeys()
        requests.append(True)
        return False

    cg = SimpleNamespace(CGPreflightScreenCaptureAccess=lambda: allowed, CGRequestScreenCaptureAccess=request)
    monkeypatch.setattr(
        window_bounds, "sys", SimpleNamespace(platform="darwin", executable="/Test.app/Contents/MacOS/Test")
    )
    monkeypatch.setattr(window_bounds, "_mac_window_list", lambda: (cg, None))
    monkeypatch.setattr(window_bounds, "QSettings", settings)
    assert not window_bounds.capture_allowed(request=False)
    assert not requests
    assert not window_bounds.capture_allowed()
    assert not window_bounds.capture_allowed()
    assert len(requests) == 1
    allowed = True
    assert window_bounds.capture_allowed()
    allowed = False
    assert not window_bounds.capture_allowed()
    assert len(requests) == 1
