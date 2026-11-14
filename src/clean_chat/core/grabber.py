"""[구성 · 리드 · 🪟 Windows 전용] 화면 영역 캡처 → Frame 스트림 (FrameSource 어댑터)

Windows 전용 라이브러리 import 는 함수 안에서 한다 (Mac 에서 import 에러 방지).
관련: ADR-0002, ADR-0003, ADR-0012, OPEN-02
"""

from __future__ import annotations

from collections.abc import Iterator

from clean_chat.core.platform import require_windows
from clean_chat.core.schemas import Frame, Region


class ScreenGrabber:
    """[구성] FrameSource: 게임 채팅창 영역을 주기적으로 캡처한다. 게임 중(IN_GAME)에만 Engine 이 읽는다."""

    def __init__(self, region: Region) -> None:
        """region: 오버레이 보정값과 같은 화면 영역(채팅창 위치)."""
        self.region = region

    def frames(self) -> Iterator[Frame]:
        """settings.capture_interval_sec(0.4초)마다 region 을 캡처해 Frame 을 내보낸다. 끝나지 않는 스트림.

        입력: 없음 → 출력: Frame(id, ts, image_path, region) 스트림
        예) Frame(id="cap-000123", ts=..., image_path=".clean-chat/frames/cap-000123.png", region=Region(...))
        순서: require_windows → _open_capture → (반복) _grab → _save_png → Frame
        주의: 오버레이 창이 캡처에 찍히면 안 된다(ui/win32.py 의 캡처 제외와 함께 실측, OPEN-02).
              캡처 이미지는 디버그용으로만 남기고 git 에 올리지 않는다. 멈춤은 Engine 이 반복을 끊어서 한다.
        """
        require_windows("화면 캡처")
        raise NotImplementedError("capture 담당: frames")

    def _open_capture(self) -> object:
        """캡처 라이브러리 준비 (dxcam / mss 등, win32 마커로 설치)."""
        raise NotImplementedError

    def _grab(self, capture: object) -> object:
        """region 영역 이미지 1장."""
        raise NotImplementedError

    def _save_png(self, image: object, frame_id: str) -> str:
        """이미지를 PNG 로 저장하고 경로를 돌려준다 (또는 메모리 전달로 바꿀 수 있음)."""
        raise NotImplementedError
