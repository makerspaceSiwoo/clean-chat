"""파인튜닝한 분류 모델 연결 (실시간 필터용). 모델이 없으면 규칙만으로 돈다.

모델 폴더(기본 `models/analyze-classifier/`, git 제외)에 아래가 있으면 자동으로 쓴다. train.py 가 이 형식으로 저장한다.
  config.json · 가중치 · 토크나이저 파일   ← transformers `save_pretrained` 결과 (다중 라벨 분류)
  meta.json   {"version": "kcelectra-base-ft-0.1", "labels": ["profanity", ...], "max_length": 64}
폴더를 바꾸려면 환경 변수 CLEAN_CHAT_ANALYZE_MODEL 에 경로를 준다.

실행 방식은 두 가지이고 점수는 같다 (dev_eval·labeled_parsed 판정 차이 0, export_onnx.py 참고).
  ONNX   model.onnx + tokenizer.json → onnxruntime · tokenizers. 앱은 이것만 쓴다 (torch 없이, 더 빠르다).
  torch  model.safetensors → torch · transformers (analyze extra). model.onnx 가 없을 때 (학습 직후 등).
패키지는 함수 안에서만 import 한다. 불러오다 실패하면 한 번만 경고하고 규칙으로 계속 간다 (앱을 멈추지 않는다).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
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


ONNX_FILE = "model.onnx"


@cache
def _load_once(path: Path) -> dict[str, Any] | None:
    if not (path / "config.json").exists() or not (path / "meta.json").exists():
        return None
    try:
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        if (path / ONNX_FILE).exists():
            try:
                return {"run": _onnx_runner(path, meta), "meta": meta, "backend": "onnx"}
            except ImportError:  # onnxruntime·tokenizers 가 없는 학습 환경(analyze extra 만)
                if not (path / "model.safetensors").exists():
                    raise
                logger.info("onnxruntime 이 없어 torch 로 analyze 모델을 실행합니다")
        return {"run": _torch_runner(path, meta), "meta": meta, "backend": "torch"}
    except Exception:
        logger.exception("analyze 모델을 불러오지 못했습니다 (%s) → 규칙만 사용", path)
        return None


def _onnx_runner(path: Path, meta: dict[str, Any]) -> Callable[[str], list[float]]:
    import numpy as np
    import onnxruntime
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
    tokenizer.enable_truncation(int(meta.get("max_length", 64)))
    tokenizer.no_padding()
    session = onnxruntime.InferenceSession(str(path / ONNX_FILE), providers=["CPUExecutionProvider"])
    names = {i.name for i in session.get_inputs()}

    def run(text: str) -> list[float]:
        enc = tokenizer.encode(text)
        feed = {"input_ids": np.array([enc.ids], dtype=np.int64)}
        if "attention_mask" in names:
            feed["attention_mask"] = np.array([enc.attention_mask], dtype=np.int64)
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.array([enc.type_ids], dtype=np.int64)
        logits = session.run(None, feed)[0][0].astype(np.float64)
        return (1.0 / (1.0 + np.exp(-logits))).tolist()

    return run


def _torch_runner(path: Path, meta: dict[str, Any]) -> Callable[[str], list[float]]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(path)
    net = AutoModelForSequenceClassification.from_pretrained(path)
    net.eval()
    max_length = int(meta.get("max_length", 64))

    def run(text: str) -> list[float]:
        batch = tokenizer(text, truncation=True, max_length=max_length, return_tensors="pt")
        with torch.no_grad():
            return torch.sigmoid(net(**batch).logits[0]).tolist()

    return run


def backend() -> str | None:
    """불러온 모델의 실행 방식 ("onnx" · "torch"). 모델이 없으면 None."""
    loaded = _load(model_dir())
    return loaded["backend"] if loaded else None


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
        probs = loaded["run"](text_norm)
        return {label: float(p) for label, p in zip(loaded["meta"]["labels"], probs, strict=True)}
    except Exception:
        logger.exception("analyze 모델 실행 실패 → 이 문장은 규칙만 사용")
        return {}
