"""analyze 분류 모델 파인튜닝 스크립트 (그래픽 카드가 있는 PC 나 Colab 에서 실행). 앱·테스트는 이 파일을 쓰지 않는다.

    uv sync --extra analyze
    uv run python -m clean_chat.modules.analyze.train \\
        --data fixtures/analyze/labeled_parsed.csv --base beomi/KcELECTRA-base --version kcelectra-base-ft-0.1

- 입력 CSV: `text_norm`(없으면 `text`), `harm_types`(`|` 연결) 열. `split` 열이 있으면 `train` 행만 학습하고
  `test` 행은 절대 학습에 넣지 않는다. 학습 뒤 평가는 evaluate.py 로 한다(같은 명령으로 브랜치끼리 비교).
- 출력: 유형 5개 다중 라벨 분류 모델 + meta.json → `models/analyze-classifier/` (git 제외). model.py 가 이 폴더를 읽는다.
- 등급·대상·조각은 모델이 아니라 impl.py 의 규칙이 정한다. 모델은 유형별 점수만 낸다.
- 새 패키지 없이 torch + transformers 만 쓴다. 공개 데이터로 먼저 학습하려면 같은 열 형식의 CSV 로 만들어
  이 스크립트를 한 번 돌리고, 그 출력 폴더를 `--base` 로 주어 우리 데이터로 다시 돌린다(2단계 학습).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

from clean_chat.core.schemas import HarmType
from clean_chat.modules.analyze.model import DEFAULT_DIR

LABELS = [t.value for t in HarmType]


def load_examples(path: Path, split: str = "train") -> list[tuple[str, list[float]]]:
    """CSV → (문장, 유형별 0/1 목록). split 열이 있으면 해당 split 행만."""
    examples = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            text = (row.get("text_norm") or row.get("text") or "").strip()
            if not text or (row.get("split") or split).strip() != split:
                continue
            types = {t.strip() for t in (row.get("harm_types") or "").split("|")}
            examples.append((text, [1.0 if label in types else 0.0 for label in LABELS]))
    return examples


def train(
    data: Path,
    base: str,
    out: Path,
    version: str,
    epochs: int = 10,
    batch_size: int = 16,
    lr: float = 3e-5,
    max_length: int = 64,
    seed: int = 42,
) -> Path:
    """파인튜닝 후 out 폴더에 모델·토크나이저·meta.json 을 저장한다."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    random.seed(seed)
    torch.manual_seed(seed)
    examples = load_examples(data)
    if not examples:
        raise ValueError(f"학습할 행이 없습니다: {data}")
    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(base)
    net = AutoModelForSequenceClassification.from_pretrained(
        base,
        num_labels=len(LABELS),
        problem_type="multi_label_classification",
        id2label=dict(enumerate(LABELS)),
        label2id={label: i for i, label in enumerate(LABELS)},
        ignore_mismatched_sizes=True,  # 2단계 학습: 이전 단계의 분류 층 크기가 달라도 이어서 학습
    ).to(device)
    optimizer = torch.optim.AdamW(net.parameters(), lr=lr)
    print(f"학습 {len(examples)}문장 · {device} · {epochs} epoch · base={base}")
    net.train()
    for epoch in range(epochs):
        random.shuffle(examples)
        total = 0.0
        for i in range(0, len(examples), batch_size):
            chunk = examples[i : i + batch_size]
            batch = tokenizer(
                [t for t, _ in chunk], padding=True, truncation=True, max_length=max_length, return_tensors="pt"
            ).to(device)
            labels = torch.tensor([y for _, y in chunk], device=device)
            loss = net(**batch, labels=labels).loss
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            total += loss.item() * len(chunk)
        print(f"  epoch {epoch + 1}/{epochs}  loss {total / len(examples):.4f}")
    out.mkdir(parents=True, exist_ok=True)
    net.to("cpu").save_pretrained(out)
    tokenizer.save_pretrained(out)
    meta = {"version": version, "labels": LABELS, "max_length": max_length, "base": base, "train_rows": len(examples)}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out}  (평가: uv run python -m clean_chat.modules.analyze.evaluate <CSV> --split test)")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="analyze 분류 모델 파인튜닝")
    ap.add_argument("--data", type=Path, required=True, help="라벨 CSV (text_norm, harm_types, split 열)")
    ap.add_argument("--base", default="beomi/KcELECTRA-base", help="Hugging Face 모델 이름 또는 로컬 폴더")
    ap.add_argument("--out", type=Path, default=Path(DEFAULT_DIR), help="저장 폴더 (git 제외)")
    ap.add_argument("--version", required=True, help="Analysis.model_version 에 남길 이름")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-5)
    args = ap.parse_args(argv)
    train(args.data, args.base, args.out, args.version, args.epochs, args.batch_size, args.lr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
