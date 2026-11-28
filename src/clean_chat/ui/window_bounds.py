"""운영체제 창 목록에서 게임 창의 위치만 조회한다. 좌표는 OS 데스크톱 기준."""

from __future__ import annotations

import ctypes
import plistlib
import sys
from ctypes import wintypes
from functools import cache
from pathlib import Path

from PySide6.QtCore import QRect, QSettings


@cache
def _mac_window_list():
    ptr = ctypes.c_void_p
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    for fn, args, result in (
        (cg.CGWindowListCopyWindowInfo, [ctypes.c_uint32, ctypes.c_uint32], ptr),
        (cf.CFPropertyListCreateData, [ptr, ptr, ctypes.c_long, ctypes.c_ulong, ptr], ptr),
        (cf.CFDataGetLength, [ptr], ctypes.c_long),
        (cf.CFDataGetBytePtr, [ptr], ptr),
        (cf.CFRelease, [ptr], None),
        (cg.CGPreflightScreenCaptureAccess, [], ctypes.c_bool),
        (cg.CGRequestScreenCaptureAccess, [], ctypes.c_bool),
    ):
        fn.argtypes, fn.restype = args, result
    return cg, cf


def capture_allowed(request: bool = True) -> bool:
    if sys.platform != "darwin":
        return True
    cg, _ = _mac_window_list()
    if cg.CGPreflightScreenCaptureAccess():
        return True
    if not request:
        return False

    # 승인 시 macOS가 즉시 종료할 수 있으므로 요청 전에 기록한다. 승인 여부는 항상 OS가 결정한다.
    prefs = QSettings("CleanChat", "ScreenCapture")
    key = f"requested/{Path(sys.executable).resolve().as_posix().lstrip('/')}"
    if prefs.value(key, False, type=bool):
        return False
    prefs.setValue(key, True)
    prefs.sync()
    return bool(cg.CGRequestScreenCaptureAccess())


def capture_permission_message() -> str:
    name = Path(sys.executable).stem if getattr(sys, "frozen", False) else "앱"
    return f"화면 기록 권한 대기 중 · 화면 기록 설정에서 {name}을 허용하세요. 이미 허용했다면 현재 실행 파일을 다시 추가하세요."


def _mac_windows(window_id: int):
    cg, cf = _mac_window_list()
    # 처음에는 보이는 창만, 연결 후에는 대상 창 한 개만 조회한다.
    windows = cg.CGWindowListCopyWindowInfo(8 if window_id else 1, window_id)
    if not windows:
        return []
    try:
        data = cf.CFPropertyListCreateData(None, windows, 200, 0, None)
        if not data:
            return []
        try:
            return plistlib.loads(ctypes.string_at(cf.CFDataGetBytePtr(data), cf.CFDataGetLength(data)))
        finally:
            cf.CFRelease(data)
    finally:
        cf.CFRelease(windows)


@cache
def _win_user():
    user = ctypes.WinDLL("user32", use_last_error=True)
    for fn, args, result in (
        (user.FindWindowW, [wintypes.LPCWSTR, wintypes.LPCWSTR], wintypes.HWND),
        (user.GetWindowRect, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        (user.GetWindowTextW, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        (user.IsIconic, [wintypes.HWND], wintypes.BOOL),
        (user.IsWindowVisible, [wintypes.HWND], wintypes.BOOL),
    ):
        fn.argtypes, fn.restype = args, result
    return user


def native_rect(hwnd: int) -> QRect:
    rect = wintypes.RECT()
    if not _win_user().GetWindowRect(hwnd, ctypes.byref(rect)):
        return QRect()
    return QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def game_window(window_id: int = 0) -> tuple[int, str, QRect] | None:
    if sys.platform == "win32":
        user = _win_user()
        hwnd = user.FindWindowW("RiotWindowClass", None)
        if not hwnd or (window_id and window_id != hwnd):
            return None
        if user.IsIconic(hwnd) or not user.IsWindowVisible(hwnd):
            return hwnd, "", QRect()
        title = ctypes.create_unicode_buffer(512)
        user.GetWindowTextW(hwnd, title, len(title))
        return hwnd, title.value, native_rect(hwnd)
    if sys.platform == "darwin":
        for win in _mac_windows(window_id):
            owner = win.get("kCGWindowOwnerName", "")
            if owner.casefold() not in {"leagueoflegends", "league of legends", "league of legends (tm) client"}:
                continue
            if win.get("kCGWindowLayer") != 0:
                continue
            if not win.get("kCGWindowIsOnscreen"):
                return win["kCGWindowNumber"], "", QRect()
            b = win["kCGWindowBounds"]
            rect = QRect(*(round(b[k]) for k in ("X", "Y", "Width", "Height")))
            if rect.width() >= 320 and rect.height() >= 240:
                return win["kCGWindowNumber"], win.get("kCGWindowName") or owner, rect
    return None


def join_fullscreen_spaces(view_id: int) -> None:
    """Qt의 NSView가 속한 도구 창을 다른 Space와 전체 화면 앱 위에도 표시한다."""
    if sys.platform != "darwin":
        return
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    send = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
    set_flags = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)(("objc_msgSend", objc))
    window = send(view_id, objc.sel_registerName(b"window"))
    if window:
        flags = send(window, objc.sel_registerName(b"collectionBehavior")) or 0
        # CanJoinAllSpaces, FullScreenAuxiliary. 상호 배타적인 이동/주 창 플래그는 해제한다.
        flags = (flags & ~(2 | (1 << 7) | (1 << 9))) | 1 | (1 << 8)
        set_flags(window, objc.sel_registerName(b"setCollectionBehavior:"), flags)
