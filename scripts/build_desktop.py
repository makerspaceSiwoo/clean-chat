"""현재 OS용 독립 실행 앱을 dist에 만든다.

uv run --extra ui --extra rewrite --extra report --with "pyinstaller>=6.16,<7" python scripts/build_desktop.py
rewrite·report extra 없이 빌드하면 LLM 없이 로컬 규칙만 쓰는 앱이 된다.
설치 파일에는 게임 오버레이로 모듈을 실행하는 메인 앱(clean_chat.desktop)만 넣고, 시뮬레이터는 뺀다.
"""

import importlib.util
import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]


def build(distpath: Path = ROOT / "dist") -> None:
    if sys.platform not in {"win32", "darwin"}:
        raise SystemExit("macOS 또는 Windows에서 실행하세요.")
    os.chdir(ROOT)
    options = []
    name = "Clean Chat"
    if sys.platform == "darwin":
        from clean_chat.ui.region_preview import build_snapshot_library

        lib = ROOT / "build" / "native" / "region_snapshot.dylib"
        build_snapshot_library(lib)
        options = ["--add-binary", f"{lib}:clean_chat/ui"]
        identity = os.environ.get("CLEAN_CHAT_CODESIGN_IDENTITY")
        if identity and identity != "-":
            options.extend(["--codesign-identity", identity, "--osx-bundle-identifier", "com.cleanchat.desktop"])
        else:
            name = "Clean Chat Preview"
            options.extend(["--osx-bundle-identifier", "com.cleanchat.desktop.preview"])
    ocr_script = ROOT / "src" / "clean_chat" / "modules" / "ocr" / "windows.ps1"
    if ocr_script.exists():  # Windows OCR은 모듈 옆의 PowerShell 스크립트를 읽는다 (ocr 모듈이 합쳐진 뒤).
        options.extend(["--add-data", f"{ocr_script}:clean_chat/modules/ocr"])
    if importlib.util.find_spec("litellm"):
        # litellm은 가격표·토크나이저 데이터 파일과 tiktoken 플러그인을 런타임에 읽는다.
        options.extend(
            ["--collect-all", "litellm", "--collect-all", "tiktoken", "--collect-submodules", "tiktoken_ext"]
        )
    PyInstaller.__main__.run(
        [
            "--name",
            name,
            "--windowed",
            "--onedir",
            "--specpath",
            str(ROOT / "build"),
            "--workpath",
            str(ROOT / "build" / "packaging"),
            "--distpath",
            str(distpath),
            *options,
            "--collect-submodules",
            "clean_chat.modules",
            "--exclude-module",  # 개발용 모듈 시뮬레이터(uv run sim)는 설치 파일에 넣지 않는다.
            "clean_chat.sim",
            "--add-data",
            f"{ROOT / 'fixtures' / 'scenario'}:fixtures/scenario",
            "--add-data",
            f"{ROOT / 'data' / 'lexicon'}:data/lexicon",
            str(ROOT / "src" / "clean_chat" / "desktop.py"),
        ]
    )


if __name__ == "__main__":
    build()
