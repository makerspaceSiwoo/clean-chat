"""현재 OS용 독립 실행 앱을 dist에 만든다.

uv run --extra ui --extra ocr --extra analyze-app --extra rewrite --extra report --with "pyinstaller>=6.16,<7" python scripts/build_desktop.py
analyze 분류 모델은 ONNX(onnxruntime · tokenizers, analyze-app extra)로 돌린다. torch·transformers(analyze extra)는
학습용이라 깔려 있어도 넣지 않는다. analyze-app extra 를 빼고 빌드하면 분류 모델 없이 규칙만 쓰는 앱이 된다.
Gemini 는 표준 라이브러리로 직접 부르므로(core/gemini.py) 따로 묶을 LLM 패키지가 없다.
설치 파일에는 게임 오버레이로 모듈을 실행하는 메인 앱(clean_chat.desktop)만 넣고, 시뮬레이터는 뺀다.
analyze 모델 가중치(약 440MB)는 넣지 않는다. 앱이 첫 실행 준비 화면에서 사용자 데이터 폴더에 내려받는다.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
# 학습·평가·ONNX 내보내기에만 쓰는 패키지 (analyze extra). 앱은 ONNX 로 추론만 하므로 넣지 않는다.
# 개발 PC 에서 analyze extra 가 깔린 채로 빌드해도 1GB 가까운 torch 가 들어가지 않게 한다.
TRAINING_ONLY = ("torch", "transformers", "sklearn", "scipy", "onnx")
BUNDLE_ID = "com.cleanchat.desktop"  # macOS 가 화면 기록 권한을 이 ID 에 묶는다. 바꾸면 권한을 다시 받아야 한다.


def build(distpath: Path = ROOT / "dist") -> None:
    if sys.platform not in {"win32", "darwin"}:
        raise SystemExit("macOS 또는 Windows에서 실행하세요.")
    os.chdir(ROOT)
    assets = ROOT / "src" / "clean_chat" / "ui" / "assets"
    # 실행 파일 아이콘(Windows .ico · macOS .icns)과, 실행 중 창·작업 표시줄 아이콘으로 쓸 PNG.
    icon = assets / ("icon.icns" if sys.platform == "darwin" else "icon.ico")
    options = ["--icon", str(icon), "--add-data", f"{assets / 'icon.png'}:clean_chat/ui/assets"]
    name = "Clean Chat"
    identity = os.environ.get("CLEAN_CHAT_CODESIGN_IDENTITY")
    if sys.platform == "darwin":
        from clean_chat.ui.region_preview import build_snapshot_library

        lib = ROOT / "build" / "native" / "region_snapshot.dylib"
        build_snapshot_library(lib)
        options.extend(["--add-binary", f"{lib}:clean_chat/ui", "--osx-bundle-identifier", BUNDLE_ID])
        if identity and identity != "-":
            options.extend(["--codesign-identity", identity])
    ocr_script = ROOT / "src" / "clean_chat" / "modules" / "ocr" / "windows.ps1"
    if ocr_script.exists():  # Windows OCR은 모듈 옆의 PowerShell 스크립트를 읽는다 (ocr 모듈이 합쳐진 뒤).
        options.extend(["--add-data", f"{ocr_script}:clean_chat/modules/ocr"])
    if importlib.util.find_spec("rapidocr"):
        # RapidOCR은 설정 yaml 등 패키지 데이터를 읽는다. OCR 모델은 첫 실행 때 사용자 폴더에 내려받는다.
        options.extend(["--collect-all", "rapidocr"])
    PyInstaller.__main__.run(
        [
            "--name",
            name,
            "--noconfirm",  # 이전 빌드 결과(dist)가 있어도 묻지 않고 덮어쓴다
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
            *[arg for module in TRAINING_ONLY for arg in ("--exclude-module", module)],
            "--add-data",
            f"{ROOT / 'fixtures' / 'scenario'}:fixtures/scenario",
            "--add-data",
            f"{ROOT / 'data' / 'lexicon'}:data/lexicon",
            str(ROOT / "src" / "clean_chat" / "desktop.py"),
        ]
    )
    if sys.platform == "darwin" and not (identity and identity != "-"):
        sign_with_stable_identity(distpath / f"{name}.app")


def sign_with_stable_identity(app: Path) -> None:
    """인증서 없이 만든 빌드도 버전이 바뀔 때 화면 기록 권한이 유지되게 서명한다.

    macOS 는 권한을 앱의 "지정 요구 사항"에 묶는다. 인증서 없는(ad-hoc) 서명은 이 값이 실행 파일의 해시라서,
    빌드할 때마다 다른 앱으로 보고 권한을 다시 받아야 했다(목록에는 예전 항목이 켜진 채 남아 헷갈린다).
    요구 사항을 번들 ID 로 지정하면 같은 ID 의 다음 빌드에도 같은 권한이 적용된다.
    """
    subprocess.run(
        ["codesign", "--force", "--sign", "-", "--identifier", BUNDLE_ID]
        + ["--requirements", f'=designated => identifier "{BUNDLE_ID}"', str(app)],
        check=True,
    )


if __name__ == "__main__":
    build()
