"""analyze 분류 모델 파인튜닝 스크립트 (그래픽 카드가 있는 PC·Apple MPS·Colab 에서 실행). 앱·테스트는 이 파일을 쓰지 않는다.

    uv sync --extra analyze
    uv run python -m clean_chat.modules.analyze.train \\
        --data fixtures/analyze/labeled_parsed.csv fixtures/analyze/train_aug.csv \\
        --base beomi/KcELECTRA-base --version kcelectra-base-ft-0.1

- 입력 CSV(여러 개 가능): `text_norm`(없으면 `text`), `harm_types`(`|` 연결) 열. `split` 열이 있으면 `train` 행만 학습하고
  `test` 행은 절대 학습에 넣지 않는다. 학습 뒤 평가는 evaluate.py 로 한다(같은 명령으로 브랜치끼리 비교).
- 검증: train 행의 일부(`--val-ratio`, 기본 15%)를 떼어 epoch 마다 유형별 F1 평균을 재고, 가장 좋았던 epoch 의
  가중치를 저장한다. `--patience` epoch 동안 나아지지 않으면 멈춘다. 행이 너무 적으면 검증 없이 끝까지 돈다.
- 드문 유형(정치질·성희롱 등)은 양성 가중치(pos_weight = 음성 수 / 양성 수, 최대 10)로 보정한다.
- 출력: 유형 5개 다중 라벨 분류 모델 + meta.json → `models/analyze-classifier/` (git 제외). model.py 가 이 폴더를 읽는다.
- 등급·대상·조각은 모델이 아니라 impl.py 의 규칙이 정한다. 모델은 유형별 점수만 낸다.
- 새 패키지 없이 torch + transformers 만 쓴다.
- 2단계 학습: 공개 데이터(public_data.py 로 같은 열 형식의 CSV 를 만든다)로 먼저 돌리고, 그 출력 폴더를 `--base` 로
  주어 우리 데이터로 다시 돌린다. 공개 데이터에 일부 유형의 라벨만 있으면 `--only-labels profanity` 처럼 주어
  나머지 유형은 손실에서 뺀다(라벨이 없는 유형을 "아님"으로 배우지 않게).
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


Example = tuple[str, list[float]]


def load_examples(paths: Path | list[Path], split: str = "train") -> list[Example]:
    """CSV(들) → (문장, 유형별 0/1 목록). split 열이 있으면 해당 split 행만. 같은 문장은 한 번만."""
    examples: list[Example] = []
    seen: set[str] = set()
    for path in [paths] if isinstance(paths, Path) else paths:
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                text = (row.get("text_norm") or row.get("text") or "").strip()
                if not text or text in seen or (row.get("split") or split).strip() != split:
                    continue
                seen.add(text)
                types = {t.strip() for t in (row.get("harm_types") or "").split("|")}
                examples.append((text, [1.0 if label in types else 0.0 for label in LABELS]))
    return examples


def split_validation(examples: list[Example], ratio: float, seed: int) -> tuple[list[Example], list[Example]]:
    """train 행에서 검증용을 뗀다. 유형 조합별로 같은 비율을 떼고(드문 유형이 한쪽에 몰리지 않게), 5행 미만이면 떼지 않는다."""
    groups: dict[tuple[float, ...], list[Example]] = {}
    for ex in examples:
        groups.setdefault(tuple(ex[1]), []).append(ex)
    rng = random.Random(seed)
    train_part: list[Example] = []
    val_part: list[Example] = []
    for key in sorted(groups):
        items = groups[key]
        rng.shuffle(items)
        cut = round(len(items) * ratio)
        val_part += items[:cut]
        train_part += items[cut:]
    return (train_part, val_part) if len(val_part) >= 5 else (examples, [])


def macro_f1(golds: list[list[float]], probs: list[list[float]], threshold: float = 0.5) -> tuple[float, dict]:
    """유형별 F1 과 그 평균(정답이 한 건도 없는 유형은 평균에서 뺀다)."""
    per: dict[str, float] = {}
    for j, label in enumerate(LABELS):
        tp = sum(1 for g, p in zip(golds, probs, strict=True) if g[j] and p[j] >= threshold)
        fp = sum(1 for g, p in zip(golds, probs, strict=True) if not g[j] and p[j] >= threshold)
        fn = sum(1 for g, p in zip(golds, probs, strict=True) if g[j] and p[j] < threshold)
        if tp + fn:
            per[label] = 2 * tp / (2 * tp + fp + fn)
    return (sum(per.values()) / len(per) if per else 0.0), per


def train(
    data: Path | list[Path],
    base: str,
    out: Path,
    version: str,
    epochs: int = 10,
    batch_size: int = 16,
    lr: float = 3e-5,
    max_length: int = 64,
    seed: int = 42,
    val_ratio: float = 0.15,
    patience: int = 3,
    only_labels: list[str] | None = None,
) -> Path:
    """파인튜닝 후 out 폴더에 모델·토크나이저·meta.json 을 저장한다."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    random.seed(seed)
    torch.manual_seed(seed)
    examples, val = split_validation(load_examples(data), val_ratio, seed)
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

    def encode(texts: list[str]):
        return tokenizer(texts, padding=True, truncation=True, max_length=max_length, return_tensors="pt").to(device)

    def predict(texts: list[str]) -> list[list[float]]:
        net.eval()
        probs: list[list[float]] = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                probs += torch.sigmoid(net(**encode(texts[i : i + 64])).logits).cpu().tolist()
        net.train()
        return probs

    # 불균형 보정: 유형별 양성 가중치. 손실에서 뺄 유형은 mask 0.
    positives = [sum(y[j] for _, y in examples) for j in range(len(LABELS))]
    pos_weight = torch.tensor([min(10.0, max(1.0, (len(examples) - p) / p)) if p else 1.0 for p in positives])
    mask = torch.tensor([1.0 if not only_labels or label in only_labels else 0.0 for label in LABELS])
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight.to(device), reduction="none")
    mask = mask.to(device)
    optimizer = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=0.01)
    steps = epochs * ((len(examples) + batch_size - 1) // batch_size)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(steps * 0.1), steps)
    print(f"학습 {len(examples)}문장 · 검증 {len(val)}문장 · {device} · 최대 {epochs} epoch · lr {lr} · base={base}")
    best: dict = {"score": -1.0, "epoch": 0, "state": None, "per": {}}
    net.train()
    for epoch in range(epochs):
        random.shuffle(examples)
        total = 0.0
        for i in range(0, len(examples), batch_size):
            chunk = examples[i : i + batch_size]
            labels = torch.tensor([y for _, y in chunk], device=device)
            loss = (loss_fn(net(**encode([t for t, _ in chunk])).logits, labels) * mask).sum() / (
                mask.sum() * len(chunk)
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total += loss.item() * len(chunk)
        line = f"  epoch {epoch + 1}/{epochs}  loss {total / len(examples):.4f}"
        if val:
            score, per = macro_f1([y for _, y in val], predict([t for t, _ in val]))
            line += f"  검증 F1 평균 {score:.3f}"
            if score > best["score"]:
                state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
                best = {"score": score, "epoch": epoch + 1, "state": state, "per": per}
            elif epoch + 1 - best["epoch"] >= patience:
                print(line + "  → 조기 종료")
                break
        print(line)
    if best["state"] is not None:
        net.load_state_dict(best["state"])
        print(f"  가장 좋은 epoch {best['epoch']} (검증 F1 평균 {best['score']:.3f}) 의 가중치를 저장")
    out.mkdir(parents=True, exist_ok=True)
    net.to("cpu").save_pretrained(out)
    tokenizer.save_pretrained(out)
    meta = {
        "version": version,
        "labels": LABELS,
        "max_length": max_length,
        "base": base,
        "train_rows": len(examples),
        "val_rows": len(val),
        "best_epoch": best["epoch"] or epochs,
        "val_macro_f1": round(best["score"], 4) if val else None,
        "val_f1": {k: round(v, 4) for k, v in best["per"].items()},
        "lr": lr,
        "seed": seed,
        "only_labels": only_labels,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out}  (평가: uv run python -m clean_chat.modules.analyze.evaluate <CSV> --split test)")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="analyze 분류 모델 파인튜닝")
    ap.add_argument("--data", type=Path, nargs="+", required=True, help="라벨 CSV (text_norm, harm_types, split 열)")
    ap.add_argument("--base", default="beomi/KcELECTRA-base", help="Hugging Face 모델 이름 또는 로컬 폴더")
    ap.add_argument("--out", type=Path, default=Path(DEFAULT_DIR), help="저장 폴더 (git 제외)")
    ap.add_argument("--version", required=True, help="Analysis.model_version 에 남길 이름")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--max-length", type=int, default=64)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--val-ratio", type=float, default=0.15, help="train 행에서 검증용으로 뗄 비율 (0 이면 검증 없음)")
    ap.add_argument("--patience", type=int, default=3, help="검증 점수가 이만큼의 epoch 동안 안 오르면 멈춤")
    ap.add_argument("--only-labels", nargs="+", choices=LABELS, help="이 유형만 손실에 넣는다 (공개 데이터 1단계용)")
    args = ap.parse_args(argv)
    train(
        args.data,
        args.base,
        args.out,
        args.version,
        args.epochs,
        args.batch_size,
        args.lr,
        args.max_length,
        args.seed,
        args.val_ratio,
        args.patience,
        args.only_labels,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
