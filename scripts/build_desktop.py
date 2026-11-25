"""현재 OS용 독립 실행 앱을 dist에 만든다. uv run --extra ui --with pyinstaller python scripts/build_desktop.py"""

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
            "--add-data",
            f"{ROOT / 'fixtures' / 'scenario'}:fixtures/scenario",
            "--add-data",
            f"{ROOT / 'data' / 'lexicon'}:data/lexicon",
            str(ROOT / "src" / "clean_chat" / "__main__.py"),
        ]
    )


if __name__ == "__main__":
    build()
