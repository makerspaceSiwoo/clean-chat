"""숨김·폭주·재보정과 오버레이 영역 캡처 회귀 검사."""

import os
import threading
import time

import pytest

pytest.importorskip("PIL")
pytest.importorskip("numpy")
pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QImage

from clean_chat.core.engine import Engine
from clean_chat.core.grabber import ScreenGrabber, TextChangeGate
from clean_chat.core.pipeline import LineDedup, Pipelines
from clean_chat.core.schemas import OcrResult, RawLine, Region
from clean_chat.modules.parse.notices import system_notice
from clean_chat.ui.app import App
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
    assert gate.interval_ms(0) == 1000  # 채팅 영역은 1초마다 확인한다 (예전 0.1~0.2초)
    assert not gate.observe(snapshot(background=(93, 63, 85)), 0.5)  # 글자 없이 배경만 바뀜 → OCR 안 함
    assert gate.observe(snapshot(110), 2)  # 새 글자
    assert not gate.observe(snapshot(110, (55, 74, 61)), 2.5)
    assert gate.observe(snapshot(92), 4)  # 채팅이 밀려 올라감
    assert not gate.observe(snapshot(92), 4.5)  # 방금 읽은 화면 그대로
    assert gate.observe(snapshot(92), 5.01)  # 글자가 보이는 동안은 변화를 못 잡아도 1초마다 다시 읽는다
    assert not gate.observe(snapshot(), 6)  # 빈 화면은 3초마다만
    assert gate.observe(snapshot(92), 7)


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


def test_capture_buffer_bounded_order_cleanup_and_stop():
    src = ScreenGrabber()
    roi = Region(x=0, y=0, w=400, h=150)
    src.begin()
    for n in range(8):
        src.offer(snapshot(background=(n, n, n)), roi)
    assert src.dropped == 6  # 최근 2장만 둔다 (한 장에 보이는 채팅이 모두 들어 있다)
    frames = src.frames()
    first = next(frames)
    assert first.image.getpixel((0, 0)) == (6, 6, 6)
    assert first.image_path == "" and "image" not in first.model_dump()  # 디스크에 쓰지 않고 메모리로만 넘긴다
    src.invalidate()
    assert not src.current(first)
    src.finish()
    assert list(frames) == []
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


def fake_region_capture(monkeypatch, color=Qt.red):
    """실제 화면 대신 단색 이미지를 돌려주는 영역 캡처 (모든 OS에서 macOS 의 비동기 경로로 검사한다)."""
    from types import SimpleNamespace

    from clean_chat.ui import region_preview

    calls = []

    def capture(rect, scale):
        calls.append(rect)
        image = QImage(round(rect.width() * scale), round(rect.height() * scale), QImage.Format_RGB32)
        image.fill(color)
        return image

    monkeypatch.setattr(region_preview, "mac_snapshot", capture)
    monkeypatch.setattr(region_preview, "sys", SimpleNamespace(platform="darwin"))
    return calls


def test_ui_start_lock_pause_stop_and_failure_preserves_cover(tmp_path, monkeypatch):
    """게임 창을 찾지 않는다. 위치 잠금 = 게임 시작, 오버레이 종료 = 게임 끝."""
    src = ScreenGrabber()
    prefs = QSettings(str(tmp_path / "overlay.ini"), QSettings.IniFormat)
    monkeypatch.setattr("clean_chat.ui.app.QSettings", lambda *args: prefs)
    monkeypatch.setattr("clean_chat.ui.capture.capture_allowed", lambda: True)
    fake_region_capture(monkeypatch)
    app = App(Pipelines(fixture_modules()), src, src)
    app.client.preview_only.setChecked(False)
    app.show()
    assert not app.overlay.isVisible()
    app.client.btn_start.click()
    assert app.overlay.isVisible() and app.overlay.editing
    assert not src.running  # 위치를 맞추는 동안은 시작하지 않는다
    app.client.btn_lock.click()
    assert app.overlay.windowFlags() & Qt.WindowTransparentForInput
    assert app.sampler.timer.isActive() and app.sampler.sampling
    assert src.running  # 잠근 순간 게임 시작
    app.client.btn_lock.click()
    assert not app.sampler.timer.isActive() and not app.sampler.sampling
    assert src.running  # 영역을 다시 맞추는 동안에도 게임 기록은 이어진다
    app.capture_failed("캡처 실패")
    assert app.overlay.isVisible()
    app.client.btn_start.click()
    assert not app.overlay.isVisible()
    assert not src.running  # 오버레이 종료 = 게임 끝
    app.shutdown()
    app.client.close()


def test_unknown_and_player_chat_never_become_system_notices():
    assert system_notice("아군 팀이 내셔 남작을 처치했습니다!") == "아군 팀 · 내셔 남작 처치"
    assert system_notice("[팀] 나 (룰루): 위험 신호를 보냈습니다") is None
    assert system_notice("판독 실패") is None


def test_sampler_sends_only_the_overlay_region_to_ocr(monkeypatch):
    """감시 모드는 오버레이가 가린 사각형만 가져와 OCR 대기열에 넣는다 (게임 창 전체를 받지 않는다)."""
    from PySide6.QtWidgets import QApplication, QWidget

    from clean_chat.ui.capture import WindowSampler

    qt = QApplication.instance() or QApplication([])
    overlay = QWidget()
    overlay.setGeometry(120, 230, 200, 120)
    overlay.show()
    monkeypatch.setattr("clean_chat.ui.capture.capture_allowed", lambda: True)
    calls = fake_region_capture(monkeypatch)
    # 글자 변화 판단은 다른 테스트가 본다. 여기서는 가져온 영역을 모두 OCR 로 보낸다.
    monkeypatch.setattr(TextChangeGate, "observe", lambda self, image, now: True)
    src = ScreenGrabber()
    sampler = WindowSampler(src, overlay)
    previews, statuses = [], []
    sampler.preview.connect(previews.append)
    sampler.status.connect(statuses.append)
    sampler.start()
    assert src.running and sampler.sampling
    sampler.region_preview.pending.result(timeout=2)
    sampler.region_preview._tick()  # 가져온 이미지를 처리한다
    assert len(src._pending) == 1  # 대기열에 없으면 아래 next() 가 끝없이 기다린다
    frame = next(src.frames())
    scale = overlay.screen().devicePixelRatio()
    assert frame.image.size == (round(200 * scale), round(120 * scale)) and frame.image_path == ""
    assert frame.image.getpixel((0, 0)) == (255, 0, 0)
    assert calls[0] == overlay.geometry()  # 요청한 영역은 오버레이 사각형뿐
    assert any(not image.isNull() for image in previews)  # 읽는 영역을 클라이언트에 그대로 보여 준다
    assert statuses[-1] == "채팅 감시 중"
    sampler.stop()
    assert not src.running and not sampler.timer.isActive()
    overlay.close()
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
    assert any(4000 <= tick <= 6000 for tick in with_call)  # 콜이 뜨고 2초 안에 읽는다


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
