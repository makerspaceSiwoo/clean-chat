import pytest

from lolguard.capture.grabber import ScreenGrabber
from lolguard.core.platform import IS_WINDOWS, PlatformNotSupported
from lolguard.core.schemas import Region


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
