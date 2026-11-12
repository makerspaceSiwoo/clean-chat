"""실행 환경(OS) 구분. Windows 전용 기능은 반드시 여기를 거쳐서 막는다.

- 실제 앱(화면 캡처, 오버레이 캡처 제외)은 Windows에서만 동작
- Mac/Linux에서는 설치, 모듈 단독 실행, mock 파이프라인, UI 화면 개발까지 가능
"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


class PlatformNotSupported(RuntimeError):
    pass


def require_windows(feature: str) -> None:
    if not IS_WINDOWS:
        raise PlatformNotSupported(
            f"'{feature}'은(는) Windows 전용입니다. Mac에서는 --source demo / --source screenshots 로 테스트하세요."
        )


def use_utf8_console() -> None:
    """콘솔 출력을 UTF-8로 맞춘다. 프로그램 시작 지점(CLI, 모듈 단독 실행)에서 1번 호출.

    Windows 콘솔 기본 인코딩(cp949, cp1252)은 한글·이모지를 못 찍어 UnicodeEncodeError로 멈춘다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
