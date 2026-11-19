"""실행 명령은 두 개뿐입니다 (옵션 없음).

uv run sim              모듈 시뮬레이터 (브라우저가 열림). 모듈 하나 골라 입력 → 디버깅 콘솔 → 반환값
uv run sim parse        그 모듈 화면으로 바로 열기 (ocr · parse · analyze · rewrite · report)
uv run app              앱 전체 (Windows = 실제 게임 화면, 그 밖 = 데모 재생)

Mock 은 없습니다 (ADR-0017). app 은 모듈 5개가 모두 구현돼야 끝까지 돌고, 구현 없는 모듈을 만나면 이름을 알리고 멈춥니다.
"""

from __future__ import annotations

import sys

from clean_chat.core.config import FIXTURES
from clean_chat.core.modules import MODULE_NAMES
from clean_chat.core.platform import IS_WINDOWS, use_utf8_console
from clean_chat.core.schemas import Region

SCENARIO = FIXTURES / "scenario"
DEFAULT_REGION = Region(x=0, y=600, w=500, h=250)  # TODO: 오버레이 보정값에서 읽기


def sim() -> None:
    """`uv run sim [모듈]`"""
    use_utf8_console()
    args = sys.argv[1:]
    module = args[0] if args else None
    if len(args) > 1 or (module is not None and module not in MODULE_NAMES):
        print(f"사용법: uv run sim [{' | '.join(MODULE_NAMES)}]")
        raise SystemExit(2)
    from clean_chat.sim.server import serve

    serve(module)


def app() -> None:
    """`uv run app` — OS 에 맞게 자동으로: Windows 는 실제 화면 캡처 + LCU, 그 밖은 시나리오 데모 재생."""
    use_utf8_console()
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print("화면 패키지(PySide6)가 없습니다. 한 번만 실행하세요:  uv sync --extra ui")
        raise SystemExit(1) from None
    from clean_chat.core.pipeline import Pipelines
    from clean_chat.ui.app import run_app

    if IS_WINDOWS:
        from clean_chat.core.config import settings
        from clean_chat.core.grabber import ScreenGrabber
        from clean_chat.session.windows import LcuPhaseDetector

        source, detector = ScreenGrabber(DEFAULT_REGION), LcuPhaseDetector(settings.phase_poll_sec)
    else:
        from clean_chat.core.sources import DemoLineSource
        from clean_chat.session.fake import FakePhaseDetector

        print("Windows 가 아니라서 데모 재생으로 실행합니다 (fixtures/scenario).")
        source = DemoLineSource(SCENARIO / "lines.jsonl", delay_sec=1.0)
        detector = FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl", delay_sec=1.0)
    raise SystemExit(run_app(Pipelines(), source, detector))


main = app  # python -m clean_chat

if __name__ == "__main__":
    main()
