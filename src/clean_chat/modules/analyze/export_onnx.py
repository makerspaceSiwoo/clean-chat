"""학습한 분류 모델(model.safetensors)을 ONNX(model.onnx)로 바꾼다. 앱은 torch 없이 이 파일로 추론한다.

    uv run --extra analyze --extra ocr python -m clean_chat.modules.analyze.export_onnx            # models/analyze-classifier
    uv run --extra analyze --extra ocr python -m clean_chat.modules.analyze.export_onnx <모델 폴더>

내보낸 뒤 같은 폴더에서 torch 와 ONNX 점수를 문장마다 비교해, 차이가 크거나 0.5 기준 판정이 하나라도 다르면 실패한다.
비교 문장은 fixtures/analyze/*.csv 의 text_norm 이다. 통과하면 `weights upload classifier` 로 올린다.
torch·transformers·onnx 는 analyze extra, onnxruntime 은 ocr extra 에 있다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from clean_chat.core.config import FIXTURES
from clean_chat.modules.analyze import model

OPSET = 17
MAX_DIFF = 1e-3  # 점수 차이 허용 (실측 최대 2e-5)
THRESHOLD = 0.5  # impl.THRESHOLD 와 같은 판정 기준


def export(folder: Path) -> Path:
    """folder/model.safetensors → folder/model.onnx. 입력: input_ids · attention_mask (배치·길이 가변)."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(folder)
    net = AutoModelForSequenceClassification.from_pretrained(folder).eval()
    sample = tokenizer("야 정글 병신아 용 먼저 치라고", return_tensors="pt", truncation=True, max_length=64)
    names = [name for name in ("input_ids", "attention_mask", "token_type_ids") if name in sample]
    out = folder / model.ONNX_FILE
    torch.onnx.export(
        net,
        tuple(sample[name] for name in names),
        str(out),
        input_names=names,
        output_names=["logits"],
        dynamic_axes={**{name: {0: "batch", 1: "seq"} for name in names}, "logits": {0: "batch"}},
        opset_version=OPSET,
        dynamo=False,
    )
    return out


def sentences() -> list[str]:
    texts: list[str] = []
    for path in sorted((FIXTURES / "analyze").glob("*.csv")):
        with path.open(encoding="utf-8") as stream:
            texts += [(row.get("text_norm") or row.get("text") or "").strip() for row in csv.DictReader(stream)]
    return list(dict.fromkeys(t for t in texts if t))


def compare(folder: Path, texts: list[str]) -> dict[str, float | int]:
    """같은 폴더의 torch 와 ONNX 점수 비교: 최대 차이, 0.5 기준 판정이 다른 수."""
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    onnx_run, torch_run = model._onnx_runner(folder, meta), model._torch_runner(folder, meta)
    worst, flips = 0.0, 0
    for text in texts:
        for a, b in zip(torch_run(text), onnx_run(text), strict=True):
            worst = max(worst, abs(a - b))
            flips += (a >= THRESHOLD) != (b >= THRESHOLD)
    return {"sentences": len(texts), "max_diff": worst, "flips": flips}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="analyze 분류 모델 → ONNX (torch 와 점수 비교까지)")
    ap.add_argument("folder", type=Path, nargs="?", help="모델 폴더 (기본: model.py 가 읽는 폴더)")
    ap.add_argument("--limit", type=int, help="비교 문장 수 제한 (빠른 확인용)")
    args = ap.parse_args(argv)
    folder = args.folder or model.model_dir()
    out = export(folder)
    print(f"내보냄: {out} ({out.stat().st_size / 1e6:.0f}MB)")
    texts = sentences()[: args.limit] if args.limit else sentences()
    result = compare(folder, texts)
    print(f"비교: 문장 {result['sentences']}개, 점수 최대 차이 {result['max_diff']:.6f}, 판정 차이 {result['flips']}")
    if result["max_diff"] > MAX_DIFF or result["flips"]:
        out.unlink()
        print("실패: torch 와 결과가 달라 model.onnx 를 지웠습니다", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
