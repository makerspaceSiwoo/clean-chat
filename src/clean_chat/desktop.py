"""설치용 데스크톱 앱 진입점 (`uv run app`, PyInstaller 빌드).

게임 오버레이로 모듈을 실행하는 메인 앱만 담는다. 모듈 시뮬레이터(`clean_chat.sim`, `uv run sim`)는
개발용이라 이 파일에서 import 하지 않고, scripts/build_desktop.py 도 빌드에서 제외한다.
"""

from __future__ import annotations

import multiprocessing
import os
import sys

from clean_chat.core.config import FIXTURES
from clean_chat.core.platform import use_utf8_console

SCENARIO = FIXTURES / "scenario"


CHECK_PACKAGES = ("PySide6", "PIL", "numpy", "rapidocr", "onnxruntime", "tokenizers", "huggingface_hub")


ARGS = ("--demo", "--check")
CONSOLE_LOG_LIMIT = 1_000_000  # logs/console.log 이 이보다 커지면 새로 시작한다


def ensure_std_streams() -> None:
    """콘솔 없는 창 앱이면 sys.stdout·sys.stderr 를 logs/console.log 로 돌린다.

    Windows 설치 파일(PyInstaller --windowed)은 둘 다 None 이다. 그러면 진행 막대(tqdm)를 그리는
    Hugging Face 모델 내려받기·RapidOCR 모델 내려받기가 "'NoneType' object has no attribute 'write'" 로 실패한다.
    파일을 열 수 없으면 버리는 곳(os.devnull)으로 보낸다. 이미 있는 스트림(터미널 실행)은 건드리지 않는다.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    from clean_chat.core.config import settings

    try:
        folder = settings.store_dir / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "console.log"
        if path.exists() and path.stat().st_size > CONSOLE_LOG_LIMIT:
            path.unlink()
        stream = open(path, "a", encoding="utf-8", errors="replace", buffering=1)  # noqa: SIM115 (앱이 끝날 때까지 연다)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def unexpected_args(args: list[str]) -> list[str]:
    """앱이 모르는 실행 인자. macOS 가 Finder 실행 때 붙이는 -psn_… 은 허용한다."""
    return [arg for arg in args if arg not in ARGS and not arg.startswith("-psn_")]


def check() -> int:
    """`--check` — 화면 없이 앱이 쓰는 패키지를 불러 보고, analyze 모델이 있으면 불러온다. 문제가 있으면 1.

    결과는 화면에 찍고 사용자 데이터 폴더의 logs/check.txt 에도 남긴다. Finder 나 `open` 으로 실행하면
    출력이 보이지 않고, 화면 기록 권한은 앱을 직접 실행했을 때의 값이 진짜이기 때문이다.
    """
    import importlib

    from clean_chat.core import setup
    from clean_chat.core.config import settings

    lines, failed = [], []
    for name in CHECK_PACKAGES:
        try:
            importlib.import_module(name)
            lines.append(f"ok   {name}")
        except Exception as exc:  # 설치 파일에서 빠진 패키지를 한 번에 모두 보여 준다
            failed.append(name)
            lines.append(f"FAIL {name}: {type(exc).__name__}: {exc}")
    lines.append(f"Gemini API 키: {'있음' if setup.key_ready() else '없음 (첫 실행 준비 화면에서 입력)'}")
    if sys.platform == "darwin" and "PySide6" not in failed:
        from clean_chat.ui.window_bounds import capture_allowed

        lines.append(f"화면 기록 권한: {'있음' if capture_allowed(request=False) else '없음 (위치를 잠글 때 요청)'}")
    if "onnxruntime" not in failed and "tokenizers" not in failed and setup.models_ready():
        lines.append(f"analyze 모델: {setup.warm_up() or '불러오지 못함'}")
    else:
        lines.append("analyze 모델: 없음 (첫 실행 준비 화면에서 내려받음)")
    print("\n".join(lines))
    try:
        folder = settings.store_dir / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "check.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass
    return 1 if failed else 0


def app() -> None:
    """`uv run app` — 클라이언트 창에서 실시간 감시를 시작한다. --demo 는 시나리오 재생, --check 는 설치 점검."""
    # 반드시 맨 먼저. 설치 파일에서는 tqdm·torch 가 만드는 multiprocessing 보조 프로세스가 이 실행 파일을
    # 다시 실행한다. 여기서 가로채지 않으면 그 프로세스가 앱 창을 또 띄우고, 그 창이 다시 모델을 불러와 끝없이 반복된다.
    multiprocessing.freeze_support()
    ensure_std_streams()
    if getattr(sys, "frozen", False) and (unknown := unexpected_args(sys.argv[1:])):
        # 설치 파일을 파이썬 인터프리터처럼 부른 경우(-c, -m 등)에는 창을 띄우지 않고 끝낸다.
        print(f"알 수 없는 실행 인자라 시작하지 않습니다: {unknown}", file=sys.stderr)
        raise SystemExit(2)
    use_utf8_console()
    if "--check" in sys.argv[1:]:
        raise SystemExit(check())
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
