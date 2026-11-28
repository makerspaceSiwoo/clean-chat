"""공개 악플 데이터를 train.py 가 읽는 CSV 로 바꾼다 (1단계 학습용). 원본과 결과는 `data/raw/`(git 제외)에만 둔다.

    mkdir -p data/raw/kmhas
    curl -L -o data/raw/kmhas/kmhas_train.txt https://raw.githubusercontent.com/adlnlp/K-MHaS/main/data/kmhas_train.txt
    uv run python -m clean_chat.modules.analyze.public_data kmhas data/raw/kmhas/kmhas_train.txt data/raw/kmhas/stage1.csv
    uv run python -m clean_chat.modules.analyze.train --data data/raw/kmhas/stage1.csv --only-labels profanity \\
        --base beomi/KcELECTRA-base --version stage1 --out models/stage1-kcelectra-base --epochs 1 --batch-size 32

- K-MHaS (Lee et al., COLING 2022, https://github.com/adlnlp/K-MHaS): 뉴스 댓글 10.9만 건, **CC-BY-SA 4.0**.
  라벨 9개(출신·외모·정치·욕설·연령·성별·인종·종교·혐오 아님) 중 우리 유형과 겹치는 것은 **욕설(3) → profanity** 뿐이다.
  나머지 혐오 라벨은 우리 유형에 대응하지 않아 쓰지 않는다. 그래서 1단계는 `--only-labels profanity` 로 돌린다.
- 뉴스 댓글이라 게임 말투가 아니다. 롤 말투·비난·정치질은 2단계(우리 라벨 CSV)에서 배운다.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

KMHAS_PROFANITY = "3"


def convert_kmhas(src: Path, out: Path, limit: int = 20000, seed: int = 42) -> int:
    """K-MHaS 원본(탭 구분: document, label "2,4") → CSV(text, harm_types, split). 욕설 문장과 그 밖의 문장을 반반 뽑는다."""
    with src.open(encoding="utf-8", newline="") as f:
        rows = [
            (r["document"].strip(), KMHAS_PROFANITY in r["label"].split(",")) for r in csv.DictReader(f, delimiter="\t")
        ]
    rng = random.Random(seed)
    positive = [t for t, hit in rows if hit and t]
    negative = [t for t, hit in rows if not hit and t]
    rng.shuffle(positive)
    rng.shuffle(negative)
    half = min(limit // 2, len(positive), len(negative))
    picked = [(t, "profanity") for t in positive[:half]] + [(t, "") for t in negative[:half]]
    rng.shuffle(picked)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "harm_types", "split"])
        writer.writerows((t, label, "train") for t, label in picked)
    return len(picked)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="공개 데이터 → train.py 용 CSV")
    ap.add_argument("dataset", choices=["kmhas"])
    ap.add_argument("src", type=Path, help="내려받은 원본 파일")
    ap.add_argument("out", type=Path, help="저장할 CSV (data/raw/ 아래)")
    ap.add_argument("--limit", type=int, default=20000, help="뽑을 문장 수 (욕설 절반 + 그 밖 절반)")
    args = ap.parse_args(argv)
    print(f"{convert_kmhas(args.src, args.out, args.limit)}문장 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
