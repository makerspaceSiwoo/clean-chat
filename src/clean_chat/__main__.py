"""실행 진입점.

uv run clean-chat modules                             # 모듈 5개와 실행 명령
uv run clean-chat module parse [--check]              # 모듈 1개를 fixtures 입력으로 실제 실행
uv run clean-chat serve                               # 웹 시뮬레이터용 로컬 모듈 실행 서버 (http://localhost:8765)
uv run clean-chat run   --source demo                 # 게임 단계 전환 + 흐름 A + 게임 결과를 콘솔로 (모든 OS)
uv run clean-chat say   "아 정글 ㅂㅅ 왜 안 와"          # 흐름 B(내 입력) 1문장 처리 결과
uv run clean-chat app   --source demo                 # UI 앱 (모든 OS)
uv run clean-chat app   --source screen               # 🪟 실제 데모 (Windows)

Mock 은 없습니다 (ADR-0017). run / say / app 은 필요한 모듈이 모두 구현돼야 끝까지 돕니다.
구현이 없는 모듈을 만나면 그 이름을 알려 주고 멈춥니다.
"""

from __future__ import annotations

import argparse

from clean_chat.core import modules
from clean_chat.core.config import FIXTURES
from clean_chat.core.jsonl import read_jsonl
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.platform import IS_WINDOWS, use_utf8_console
from clean_chat.core.schemas import GamePhase, GameSession, Incident, Player, PostGameResult, Region
from clean_chat.core.sources import DemoLineSource, ScreenshotSource

SCENARIO = FIXTURES / "scenario" / "lines.jsonl"
SCENARIO_PHASES = FIXTURES / "scenario" / "phases.jsonl"
SCENARIO_PLAYERS = FIXTURES / "scenario" / "players.jsonl"
DEFAULT_REGION = Region(x=0, y=600, w=500, h=250)  # TODO: 오버레이 보정값에서 읽기


def _source(kind: str, delay: float, shots: str | None):
    if kind == "demo":
        return DemoLineSource(SCENARIO, delay_sec=delay)
    if kind == "screenshots":
        return ScreenshotSource(shots or str(FIXTURES / "ocr" / "images"), DEFAULT_REGION, delay_sec=delay)
    from clean_chat.core.grabber import ScreenGrabber  # Windows 전용

    return ScreenGrabber(DEFAULT_REGION)


def _detector(kind: str, delay: float):
    if kind == "screen":
        from clean_chat.core.config import settings
        from clean_chat.session.windows import LcuPhaseDetector  # Windows 전용

        return LcuPhaseDetector(settings.phase_poll_sec)
    from clean_chat.session.fake import FakePhaseDetector

    return FakePhaseDetector(SCENARIO_PHASES, SCENARIO_PLAYERS, delay_sec=delay)


def _print_phase(phase: GamePhase, session: GameSession | None) -> None:
    sid = f" · 세션 {session.id}" if session else ""
    names = f" · 플레이어 {len(session.players)}명" if session and phase == GamePhase.IN_GAME else ""
    print(f"── 게임 단계: {phase.name}{sid}{names}", flush=True)


def _print_result(result: PostGameResult) -> None:
    print(
        f"── 이번 게임 결과 (세션 {result.session_id}): 신고 {len(result.reports)}건, 고소장 초안 {len(result.complaints)}건"
    )
    for r in result.reports:
        print(f"[신고 문구 · {r.speaker}]\n{r.text}")
    for c in result.complaints:
        print(f"[고소장 초안 · {c.speaker}] {c.text} (PDF: {c.pdf_path or '-'})")


def _print(inc: Incident) -> None:
    d = inc.decision
    print(f"{d.action:>15} | {inc.msg.speaker:>8} | {d.display_text if d.display_text is not None else '(숨김)'}")


def _say(pipelines: Pipelines, text: str) -> None:
    """데모 게임 중이라고 보고 처리 (플레이어 명단 = 시나리오 명단)"""
    pipelines.set_players(read_jsonl(SCENARIO_PLAYERS, Player))
    try:
        inc = pipelines.outgoing.submit(text)
    except modules.ModuleNotImplemented as e:
        raise SystemExit(f"⏳ {e}") from None
    if inc is None:
        print("(채팅이 아닌 입력이라 처리하지 않았습니다)")
        return
    d = inc.decision
    shown = d.display_text if d.display_text is not None else "(전송 차단) 이 문장은 보낼 수 없어요"
    print(f"{d.action:>15} | {shown}")
    print(f"{'':>15} | 등급 L{int(inc.analysis.level)} · {d.reason}")


def main() -> None:
    use_utf8_console()
    ap = argparse.ArgumentParser(prog="clean-chat")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("run", "app"):
        p = sub.add_parser(c)
        p.add_argument("--source", choices=["demo", "screenshots", "screen"], default="demo")
        p.add_argument("--delay", type=float, default=0.0 if c == "run" else 1.0)
        p.add_argument("--shots", default=None, help="--source screenshots 일 때 PNG 폴더")
    p = sub.add_parser("say", help="흐름 B: 내 문장 1개를 처리한 결과")
    p.add_argument("text")
    sub.add_parser("modules", help="모듈 5개와 실행 명령")
    p = sub.add_parser("module", help="모듈 1개를 fixtures 입력으로 실제 실행")
    p.add_argument("name", choices=modules.MODULE_NAMES)
    p.add_argument("--in", dest="inp", default=None, help="입력 JSONL (기본: fixtures/<이름>/input.jsonl)")
    p.add_argument("--out", default=None, help="출력 JSONL 저장 경로")
    p.add_argument("--check", action="store_true", help="expected.jsonl 과 비교")
    p = sub.add_parser("serve", help="웹 시뮬레이터용 로컬 모듈 실행 서버")
    p.add_argument("--port", type=int, default=None)
    a = ap.parse_args()

    if a.cmd == "modules":
        for m in modules.MODULES.values():
            print(f"  {m.number} {m.name:<8} {m.title:<28} {m.path}")
        print("\n  실행: uv run clean-chat module <이름> [--check]   ·   시뮬레이터 서버: uv run clean-chat serve")
        return
    if a.cmd == "module":
        from pathlib import Path

        from clean_chat.core.runner import run_module

        raise SystemExit(run_module(a.name, Path(a.inp) if a.inp else None, Path(a.out) if a.out else None, a.check))
    if a.cmd == "serve":
        from clean_chat.core.server import serve

        serve(a.port)
        return

    pipelines = Pipelines()
    if a.cmd == "say":
        _say(pipelines, a.text)
        return

    if a.source == "screen" and not IS_WINDOWS:
        ap.error("--source screen 은 Windows 전용입니다. Mac에서는 demo 또는 screenshots 를 쓰세요.")
    src = _source(a.source, a.delay, a.shots)
    if a.cmd == "app":
        from clean_chat.ui.app import run_app  # PySide6 필요: uv sync --extra ui

        raise SystemExit(run_app(pipelines, src, _detector(a.source, a.delay)))

    from clean_chat.core.engine import Engine

    eng = Engine(pipelines, src, _detector(a.source, a.delay))
    eng.on_phase(_print_phase)
    eng.subscribe(_print)
    eng.on_result(_print_result)
    _print_phase(eng.phase, None)  # 시작 단계(IDLE)
    eng.start(block=True)
    if eng.error is not None:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
