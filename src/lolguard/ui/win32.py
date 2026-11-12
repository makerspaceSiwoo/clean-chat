"""[뼈대 · ui/capture 공동 · Windows 전용] 창을 화면 캡처에서 제외 (ADR-0003, OPEN-02 실측 필요)"""

from PySide6.QtWidgets import QWidget

from lolguard.core.platform import IS_WINDOWS

WDA_EXCLUDEFROMCAPTURE = 0x11


def exclude_from_capture(widget: QWidget) -> bool:
    """성공하면 True. Windows가 아니면 아무것도 하지 않고 False."""
    if not IS_WINDOWS:
        return False
    # TODO(실측): ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE)
    raise NotImplementedError("Windows 담당: 캡처 제외 실측 후 구현")
