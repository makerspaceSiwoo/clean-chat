"""설치용 데스크톱 앱 진입점 (`uv run app`, PyInstaller 빌드).

게임 오버레이로 모듈을 실행하는 메인 앱만 담는다. 모듈 시뮬레이터(`clean_chat.sim`, `uv run sim`)는
개발용이라 이 파일에서 import 하지 않고, scripts/build_desktop.py 도 빌드에서 제외한다.
"""

from __future__ import annotations

import sys

from clean_chat.core.config import FIXTURES
from clean_chat.core.platform import use_utf8_console

SCENARIO = FIXTURES / "scenario"


def app() -> None:
    """`uv run app` — 클라이언트 창에서 실시간 감시를 시작한다. --demo 는 시나리오 재생."""
    use_utf8_console()
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print("화면 패키지(PySide6)가 없습니다. 한 번만 실행하세요:  uv sync --extra ui")
        raise SystemExit(1) from None
    from clean_chat.core.pipeline import Pipelines
    from clean_chat.ui.app import run_app

    if "--demo" in sys.argv[1:]:
        from clean_chat.core.sources import DemoLineSource
        from clean_chat.session.fake import FakePhaseDetector

        source = DemoLineSource(SCENARIO / "lines.jsonl", delay_sec=1.0)
        detector = FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl", delay_sec=1.0)
    elif sys.platform in {"win32", "darwin"}:
        from clean_chat.core.grabber import ScreenGrabber

        source = detector = ScreenGrabber()
    else:
        raise SystemExit("실시간 캡처는 macOS와 Windows에서 지원합니다. 데모는 app --demo 로 실행하세요.")
    raise SystemExit(run_app(Pipelines(), source, detector))


if __name__ == "__main__":
    app()
