"""시뮬레이터와 데스크톱 앱 진입점.

uv run sim              모듈 시뮬레이터 (브라우저가 열림). 모듈 하나 골라 입력 → 디버깅 콘솔 → 반환값
uv run sim parse        그 모듈 화면으로 바로 열기 (ocr · parse · analyze · rewrite · report)
uv run app              앱 전체 (macOS/Windows 게임 창 · --demo 시나리오 재생)

Mock 은 없습니다 (ADR-0017). app 은 모듈 5개가 모두 구현돼야 끝까지 돌고, 구현 없는 모듈을 만나면 이름을 알리고 멈춥니다.
"""

from __future__ import annotations

import sys

from clean_chat.core.config import FIXTURES
from clean_chat.core.modules import MODULE_NAMES
from clean_chat.core.platform import use_utf8_console

SCENARIO = FIXTURES / "scenario"


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


main = app  # python -m clean_chat

if __name__ == "__main__":
    main()
