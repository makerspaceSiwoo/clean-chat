"""첫 실행 준비: Gemini API 키와 analyze 모델 가중치가 준비됐는지 확인하고, 없는 모델을 받는다.

앱은 이 두 가지가 준비된 뒤에 시작한다 (화면은 ui/setup.py).
  - Gemini API 키: 순화(rewrite)·고소장 초안(report)에 쓴다. 없으면 순화 결과가 비어 피드백까지 숨겨진다.
  - analyze 모델: 실시간 필터의 분류 모델. 없으면 규칙만으로 돌아 정확도가 크게 떨어진다.
torch · transformers · huggingface_hub 는 analyze extra 라서 함수 안에서만 import 한다.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from clean_chat.core.config import current_llm_key, settings

SKIP_ENV = "CLEAN_CHAT_SKIP_SETUP"  # 값이 있으면 준비 화면을 건너뛴다 (CI 실행 확인, 자동 테스트용)
APP_MODELS = ("classifier",)  # 앱이 쓰는 모델. 대화 판단(judge) 모델은 시뮬레이터에서만 쓴다.
RUNTIME = ("torch", "transformers", "huggingface_hub")
INSTALL_HINT = "uv sync --extra ui --extra ocr --extra analyze --extra rewrite --extra report"


def key_ready() -> bool:
    return bool(current_llm_key(settings.llm_env))


def runtime_ready() -> bool:
    """모델을 돌릴 패키지(analyze extra)가 설치돼 있는가."""
    return all(importlib.util.find_spec(name) is not None for name in RUNTIME)


def missing_models() -> list[str]:
    from clean_chat.modules.analyze import weights

    return weights.missing(list(APP_MODELS))


def models_ready() -> bool:
    return runtime_ready() and not missing_models()


def needed() -> bool:
    """준비 화면을 띄워야 하는가. 패키지가 없어 모델을 못 돌리는 개발 환경에서는 키만 확인한다."""
    if os.environ.get(SKIP_ENV):
        return False
    return not key_ready() or (runtime_ready() and bool(missing_models()))


def _folders() -> list[Path]:
    from clean_chat.modules.analyze import weights

    return [weights.folder(name) for name in APP_MODELS]


def expected_bytes() -> int:
    """받을 파일의 전체 크기 (Hugging Face Hub 에 물어본다). 실패하면 0."""
    from huggingface_hub import HfApi

    from clean_chat.modules.analyze import weights

    total = 0
    for name in APP_MODELS:
        info = HfApi().model_info(weights.repo_id(name), files_metadata=True)
        total += sum(f.size or 0 for f in info.siblings if f.rfilename in weights.FILES)
    return total


def downloaded_bytes() -> int:
    """지금까지 받은 크기. 받는 중인 임시 파일(.incomplete)도 센다."""
    total = 0
    for folder in _folders():
        if folder.is_dir():
            total += sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    return total


def download_models() -> None:
    """없는 모델을 받는다 (끝날 때까지 기다린다). 받다가 끊겨도 다음에 이어 받는다."""
    from clean_chat.modules.analyze import weights

    weights.download(missing_models())


def warm_up() -> str | None:
    """모델을 미리 불러온다 (첫 채팅에서 몇 초 멈추지 않게). 불러온 모델 버전, 없으면 None."""
    from clean_chat.modules.analyze import model

    return model.version()
