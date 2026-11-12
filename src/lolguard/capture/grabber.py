"""[구현 · capture 담당 · Windows 전용] 화면 영역 캡처 → Frame 스트림 (FrameSource)

해야 할 일:
  - region(오버레이 보정값) 영역을 settings.capture_interval_sec 간격으로 캡처
  - 오버레이 창이 캡처에 찍히지 않아야 함 (ADR-0003, ui/win32.py 와 함께 실측)
  - 이미지를 임시 폴더에 PNG로 저장(또는 메모리) 후 Frame 생성
  - Windows 전용 라이브러리 import 는 frames() 함수 안에서 (Mac에서 import 에러 방지)
"""

from collections.abc import Iterator

from lolguard.core.platform import require_windows
from lolguard.core.schemas import Frame, Region


class ScreenGrabber:
    def __init__(self, region: Region) -> None:
        self.region = region

    def frames(self) -> Iterator[Frame]:
        require_windows("화면 캡처")
        raise NotImplementedError("capture 담당: 화면 캡처 구현")
