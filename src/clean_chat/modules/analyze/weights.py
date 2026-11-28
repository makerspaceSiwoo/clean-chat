"""모델 가중치를 Hugging Face Hub 에서 받거나 올린다 (가중치는 git 에 넣지 않는다).

    uv run python -m clean_chat.modules.analyze.weights download          # 두 모델을 models/ 아래에 받는다 (학습용 가중치까지)
    uv run python -m clean_chat.modules.analyze.weights upload            # (모델을 학습한 사람) 로컬 모델을 올린다

  분류 모델은 학습(train.py) → ONNX 내보내기(export_onnx.py) → 올리기 순서. 앱은 model.onnx 만 받는다.

  실시간 필터(impl)  models/analyze-classifier/  ←  <owner>/clean-chat-analyze-classifier
  대화 판단(judge)   models/analyze-judge/       ←  <owner>/clean-chat-analyze-judge

저장소는 공개라 받을 때는 로그인이 필요 없다. 올릴 때만 쓰기 권한 계정으로 로그인한다: `uv run hf auth login`
가중치가 없어도 analyze 는 규칙만으로 돈다(정확도는 낮다).
huggingface_hub 는 transformers 와 함께 설치되며 함수 안에서만 import 한다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from clean_chat.core.config import resolve_repo_path
from clean_chat.modules.analyze import judge_model, model

OWNER_ENV = "CLEAN_CHAT_HF_OWNER"
DEFAULT_OWNER = "seeyouspace0"  # 가중치를 올린 Hugging Face 계정
MODELS = {
    "classifier": ("models/analyze-classifier", "clean-chat-analyze-classifier"),
    "judge": ("models/analyze-judge", "clean-chat-analyze-judge"),
}
BASE_FILES = ["config.json", "meta.json", "tokenizer.json", "tokenizer_config.json"]
# 실행에 필요한 파일. 분류 모델은 ONNX 로 돈다(앱에 torch 가 없다). judge 는 시뮬레이터 전용이라 torch 가중치.
RUN_FILES = {
    "classifier": [*BASE_FILES, "model.onnx"],
    "judge": [*BASE_FILES, "model.safetensors"],
}
ALL_FILES = [*BASE_FILES, "model.safetensors", "model.onnx"]  # 학습·내보내기까지 하는 개발 환경
FILES = RUN_FILES["classifier"]  # 앱(core/setup.py)이 받는 파일. 앱은 분류 모델만 쓴다.


def repo_id(name: str, owner: str | None = None) -> str:
    owner = owner or os.environ.get(OWNER_ENV) or DEFAULT_OWNER
    if not owner:
        raise ValueError(f"Hugging Face 계정 이름이 없습니다. --owner 나 환경 변수 {OWNER_ENV} 로 알려 주세요")
    return f"{owner}/{MODELS[name][1]}"


def folder(name: str) -> Path:
    """모델을 불러오는 폴더 (model.py · judge_model.py 와 같은 곳, 환경 변수로 바꾼 경로 포함)."""
    return {"classifier": model.model_dir, "judge": judge_model.model_dir}[name]()


def missing(names: list[str] | None = None) -> list[str]:
    """아직 받지 않은 모델 이름. 파일이 하나라도 없으면 받지 않은 것으로 본다."""
    return [name for name in names or list(MODELS) if not all((folder(name) / f).is_file() for f in RUN_FILES[name])]


def download(
    names: list[str], owner: str | None = None, revision: str | None = None, everything: bool = False
) -> list[Path]:
    """Hub → 모델 폴더. 기본은 실행에 필요한 파일만, everything 이면 학습용 가중치까지. 이미 같은 파일은 다시 받지 않는다."""
    from huggingface_hub import snapshot_download

    out = []
    for name in names:
        target = folder(name)
        patterns = ALL_FILES if everything else RUN_FILES[name]
        snapshot_download(repo_id(name, owner), local_dir=target, allow_patterns=patterns, revision=revision)
        out.append(target)
    return out


def upload(names: list[str], owner: str | None = None, private: bool = True) -> list[str]:
    """models/<폴더> → Hub (저장소가 없으면 비공개로 만든다 — 공개 전환은 직접). 커밋 메시지는 meta.json 의 version."""
    from huggingface_hub import HfApi

    api = HfApi()
    owner = owner or os.environ.get(OWNER_ENV) or DEFAULT_OWNER or api.whoami()["name"]
    urls = []
    for name in names:
        folder = resolve_repo_path(MODELS[name][0])
        missing = [f for f in RUN_FILES[name] if not (folder / f).exists()]
        if missing:
            raise FileNotFoundError(f"{folder} 에 파일이 없습니다: {missing}")
        version = json.loads((folder / "meta.json").read_text(encoding="utf-8")).get("version", "unknown")
        rid = repo_id(name, owner)
        api.create_repo(rid, private=private, exist_ok=True)
        api.upload_folder(folder_path=folder, repo_id=rid, allow_patterns=ALL_FILES, commit_message=str(version))
        urls.append(f"https://huggingface.co/{rid}")
    return urls


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="analyze 모델 가중치를 Hugging Face Hub 에서 받거나 올린다")
    ap.add_argument("action", choices=["download", "upload"])
    ap.add_argument("names", nargs="*", choices=[*MODELS, []], help="classifier · judge (비우면 둘 다)")
    ap.add_argument("--owner", help="Hugging Face 계정 이름")
    ap.add_argument("--revision", help="download: 받을 커밋·태그 (기본은 최신)")
    args = ap.parse_args(argv)
    names = args.names or list(MODELS)
    if args.action == "download":
        for folder in download(names, args.owner, args.revision, everything=True):
            version = json.loads((folder / "meta.json").read_text(encoding="utf-8")).get("version")
            print(f"받음: {folder.name} ({version})")
    else:
        for url in upload(names, args.owner):
            print("올림:", url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
