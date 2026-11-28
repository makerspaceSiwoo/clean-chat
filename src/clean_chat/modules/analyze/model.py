"""파인튜닝한 분류 모델 연결 (실시간 필터용). 모델이 없으면 규칙만으로 돈다.

모델 폴더(기본 `models/analyze-classifier/`, git 제외)에 아래가 있으면 자동으로 쓴다. train.py 가 이 형식으로 저장한다.
  config.json · 가중치 · 토크나이저 파일   ← transformers `save_pretrained` 결과 (다중 라벨 분류)
  meta.json   {"version": "kcelectra-base-ft-0.1", "labels": ["profanity", ...], "max_length": 64}
폴더를 바꾸려면 환경 변수 CLEAN_CHAT_ANALYZE_MODEL 에 경로를 준다.

torch · transformers 는 analyze extra 라서(`uv sync --extra analyze`) 함수 안에서만 import 한다.
불러오다 실패하면 한 번만 경고하고 규칙으로 계속 간다 (앱을 멈추지 않는다).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from functools import cache
from pathlib import Path
from typing import Any

from clean_chat.core.config import resolve_repo_path

logger = logging.getLogger(__name__)

DEFAULT_DIR = "models/analyze-classifier"
ENV_VAR = "CLEAN_CHAT_ANALYZE_MODEL"
_LOAD_LOCK = threading.Lock()  # 앱 시작 때 미리 불러오는 스레드와 캡처 스레드가 동시에 두 번 불러오지 않게


def model_dir() -> Path:
    return resolve_repo_path(os.environ.get(ENV_VAR) or DEFAULT_DIR)


def _load(path: Path) -> dict[str, Any] | None:
    """모델을 한 번만 불러온다. 폴더가 없거나 실패하면 None (→ 규칙만 사용)."""
    with _LOAD_LOCK:
        return _load_once(path)


@cache
def _load_once(path: Path) -> dict[str, Any] | None:
    if not (path / "config.json").exists() or not (path / "meta.json").exists():
        return None
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        tokenizer = AutoTokenizer.from_pretrained(path)
        net = AutoModelForSequenceClassification.from_pretrained(path)
        net.eval()
        return {"torch": torch, "tokenizer": tokenizer, "net": net, "meta": meta}
    except Exception:
        logger.exception("analyze 모델을 불러오지 못했습니다 (%s) → 규칙만 사용", path)
        return None


def version() -> str | None:
    """불러온 모델의 버전 문자열. 모델이 없으면 None."""
    loaded = _load(model_dir())
    return str(loaded["meta"].get("version", "unknown")) if loaded else None


def predict(text_norm: str) -> dict[str, float]:
    """유형별 점수 0~1. 모델이 없거나 실패하면 빈 dict. 예) {"profanity": 0.97, "blame": 0.81, ...}"""
    loaded = _load(model_dir())
    if loaded is None:
        return {}
    try:
        torch, meta = loaded["torch"], loaded["meta"]
        batch = loaded["tokenizer"](
            text_norm, truncation=True, max_length=int(meta.get("max_length", 64)), return_tensors="pt"
        )
        with torch.no_grad():
            probs = torch.sigmoid(loaded["net"](**batch).logits[0]).tolist()
        return {label: float(p) for label, p in zip(meta["labels"], probs, strict=True)}
    except Exception:
        logger.exception("analyze 모델 실행 실패 → 이 문장은 규칙만 사용")
        return {}
