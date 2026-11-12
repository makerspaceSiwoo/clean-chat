"""실행 진입점.

uv run clean-chat run   --source demo                 # 콘솔로 파이프라인 실행 (모든 OS)
uv run clean-chat run   --source demo --real parse    # parse 만 실제 구현, 나머지 mock
uv run clean-chat app   --source demo                 # UI 앱 (모든 OS, mock 데이터)
uv run clean-chat app   --source screen               # 🪟 실제 데모 (Windows)
uv run clean-chat modules                             # 모듈 목록과 단독 실행 명령

모듈 단독 실행:  uv run python -m clean_chat.<모듈> [--impl mock|real] [--check]
"""

from __future__ import annotations

import argparse

from clean_chat.core.config import FIXTURES, STAGE_NAMES
from clean_chat.core.pipeline import Pipeline
from clean_chat.core.platform import IS_WINDOWS, use_utf8_console
from clean_chat.core.schemas import Incident, Region
from clean_chat.core.sources import DemoLineSource, ScreenshotSource

SCENARIO = FIXTURES / "scenario" / "lines.jsonl"
DEFAULT_REGION = Region(x=0, y=600, w=500, h=250)  # TODO: 오버레이 보정값에서 읽기


def _source(kind: str, delay: float, shots: str | None):
    if kind == "demo":
        return DemoLineSource(SCENARIO, delay_sec=delay)
    if kind == "screenshots":
        return ScreenshotSource(shots or str(FIXTURES / "ocr" / "images"), DEFAULT_REGION, delay_sec=delay)
    from clean_chat.capture.grabber import ScreenGrabber  # Windows 전용

    return ScreenGrabber(DEFAULT_REGION)


def _print(inc: Incident) -> None:
    d = inc.decision
    print(
        f"{d.action:>15} | {inc.msg.speaker or '-':>8} | {d.display_text if d.display_text is not None else '(숨김)'}"
    )


def main() -> None:
    use_utf8_console()
    ap = argparse.ArgumentParser(prog="clean-chat")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("run", "app"):
        p = sub.add_parser(c)
        p.add_argument("--source", choices=["demo", "screenshots", "screen"], default="demo")
        p.add_argument("--real", default="", help="실제 구현으로 바꿀 모듈들, 쉼표 구분 (예: parse,normalize)")
        p.add_argument("--delay", type=float, default=0.0 if c == "run" else 1.0)
        p.add_argument("--shots", default=None, help="--source screenshots 일 때 PNG 폴더")
    sub.add_parser("modules")
    a = ap.parse_args()

    if a.cmd == "modules":
        for n in STAGE_NAMES:
            mod = {"ocr": "capture", "complaint": "report complaint"}.get(n, n)
            print(f"  {n:<10} uv run python -m clean_chat.{mod} --impl mock --check")
        return

    if a.source == "screen" and not IS_WINDOWS:
        ap.error("--source screen 은 Windows 전용입니다. Mac에서는 demo 또는 screenshots 를 쓰세요.")
    overrides = {n: "real" for n in a.real.split(",") if n}
    pipeline = Pipeline(overrides)
    src = _source(a.source, a.delay, a.shots)
    if a.cmd == "app":
        from clean_chat.ui.app import run_app  # PySide6 필요: uv sync --extra ui

        raise SystemExit(run_app(pipeline, src))

    from clean_chat.core.engine import Engine

    eng = Engine(pipeline, src)
    eng.subscribe(_print)
    eng.start(block=True)


if __name__ == "__main__":
    main()
