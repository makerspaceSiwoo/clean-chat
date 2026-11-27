"""Windows 미리보기 동안 Clean Chat 창을 데스크톱 캡처에서 제외한다."""

import ctypes
from ctypes import wintypes
from functools import cache


@cache
def _set_affinity():
    fn = ctypes.WinDLL("user32", use_last_error=True).SetWindowDisplayAffinity
    fn.argtypes, fn.restype = [wintypes.HWND, wintypes.DWORD], wintypes.BOOL
    return fn


def capture_exclusion(hwnd: int, enabled: bool) -> bool:
    return bool(_set_affinity()(hwnd, 0x11 if enabled else 0))
