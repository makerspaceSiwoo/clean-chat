"""실행 진입점.

uv run clean-chat run   --source demo                 # 흐름 A를 콘솔로 실행 (모든 OS)
uv run clean-chat run   --source demo --real parse    # parse 만 실제 구현, 나머지 mock
uv run clean-chat say   "아 정글 ㅂㅅ 왜 안 와"          # 흐름 B(내 입력) 1문장 처리 결과
uv run clean-chat app   --source demo                 # UI 앱 (모든 OS, mock 데이터)
uv run clean-chat app   --source screen               # 🪟 실제 데모 (Windows)
uv run clean-chat modules                             # 모듈 목록과 단독 실행 명령

모듈 단독 실행:  uv run python -m clean_chat.<모듈> [--impl mock|real] [--check]
"""

from __future__ import annotations

import argparse

from clean_chat.core.config import FIXTURES, STAGE_COMMANDS, STAGE_NAMES
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.platform import IS_WINDOWS, use_utf8_console
from clean_chat.core.schemas import Incident, OutgoingText, Region
from clean_chat.core.sources import DemoLineSource, ScreenshotSource
from clean_chat.core.stage import read_jsonl

SCENARIO = FIXTURES / "scenario" / "lines.jsonl"
SCENARIO_OUTGOING = FIXTURES / "scenario" / "outgoing.jsonl"
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


def _scenario_item(text: str) -> OutgoingText | None:
    """시나리오에 있는 문장이면 그 id·ts 를 그대로 쓴다 → mock 이 fixtures 응답을 돌려줄 수 있게."""
    return next((o for o in read_jsonl(SCENARIO_OUTGOING, OutgoingText) if o.text == text.strip()), None)


def _say(pipelines: Pipelines, text: str) -> None:
    known = _scenario_item(text)
    pipelines.setup()
    try:
        inc = pipelines.outgoing.submit(text, msg_id=known.id if known else None, ts=known.ts if known else None)
    finally:
        pipelines.close()
    d = inc.decision
    shown = d.display_text if d.display_text is not None else "(전송 차단) 이 문장은 보낼 수 없어요"
    print(f"{d.action:>15} | {shown}")
    print(f"{'':>15} | 등급 L{int(inc.classification.level)} · {d.reason}")


def main() -> None:
    use_utf8_console()
    ap = argparse.ArgumentParser(prog="clean-chat")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("run", "app"):
        p = sub.add_parser(c)
        p.add_argument("--source", choices=["demo", "screenshots", "screen"], default="demo")
        p.add_argument("--real", default="", help="실제 구현으로 바꿀 Stage들, 쉼표 구분 (예: parse,normalize)")
        p.add_argument("--delay", type=float, default=0.0 if c == "run" else 1.0)
        p.add_argument("--shots", default=None, help="--source screenshots 일 때 PNG 폴더")
    p = sub.add_parser("say", help="흐름 B: 내 문장 1개를 필터에 통과시킨 결과")
    p.add_argument("text")
    p.add_argument("--real", default="", help="실제 구현으로 바꿀 Stage들, 쉼표 구분")
    sub.add_parser("modules")
    a = ap.parse_args()

    if a.cmd == "modules":
        for n in STAGE_NAMES:
            print(f"  {n:<16} uv run python -m clean_chat.{STAGE_COMMANDS[n]} --impl mock --check")
        return

    overrides = {n: "real" for n in a.real.split(",") if n}
    pipelines = Pipelines(overrides)
    if a.cmd == "say":
        _say(pipelines, a.text)
        return

    if a.source == "screen" and not IS_WINDOWS:
        ap.error("--source screen 은 Windows 전용입니다. Mac에서는 demo 또는 screenshots 를 쓰세요.")
    src = _source(a.source, a.delay, a.shots)
    if a.cmd == "app":
        from clean_chat.ui.app import run_app  # PySide6 필요: uv sync --extra ui

        raise SystemExit(run_app(pipelines, src))

    from clean_chat.core.engine import Engine

    eng = Engine(pipelines, src)
    eng.subscribe(_print)
    eng.start(block=True)


if __name__ == "__main__":
    main()
