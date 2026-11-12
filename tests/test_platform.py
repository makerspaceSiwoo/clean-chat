import io
import sys

import pytest

from clean_chat.capture.grabber import ScreenGrabber
from clean_chat.core.platform import IS_WINDOWS, PlatformNotSupported, use_utf8_console
from clean_chat.core.schemas import Region


@pytest.mark.skipif(IS_WINDOWS, reason="Mac/Linux 동작 확인용")
def test_screen_grabber_blocked_off_windows():
    with pytest.raises(PlatformNotSupported):
        next(ScreenGrabber(Region(x=0, y=0, w=10, h=10)).frames())


@pytest.mark.windows
@pytest.mark.skipif(not IS_WINDOWS, reason="Windows 전용")
def test_screen_grabber_on_windows():
    try:
        frame = next(ScreenGrabber(Region(x=0, y=0, w=100, h=100)).frames())
    except NotImplementedError:
        pytest.skip("capture: 아직 미구현")
    assert frame.image_path


def test_use_utf8_console_prints_korean_on_cp1252(monkeypatch):
    """Windows CI 콘솔(cp1252)처럼 한글을 못 찍는 출력에서도 멈추지 않아야 한다."""
    buf = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(buf, encoding="cp1252"))
    use_utf8_console()
    print("한글 ✅")
    sys.stdout.flush()
    assert buf.getvalue().decode("utf-8").strip() == "한글 ✅"
