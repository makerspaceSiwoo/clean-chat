"""정답 JSONL로 OCR 엔진 비교. 원문과 결과는 Git 제외 로컬 폴더에만 저장한다."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import statistics
import time
import unicodedata
from pathlib import Path


def normalize(text: str) -> str:
    """NFC·연속 공백만 정규화한다. 자모/문장부호/대소문자는 보존한다."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def compare(reference: str, prediction: str) -> dict:
    """CER와 편집 정렬상 위치가 일치하는 자모 표현의 완전 일치 재현율."""
    reference, prediction = normalize(reference), normalize(prediction)
    table = [list(range(len(prediction) + 1))]
    for i, char in enumerate(reference, 1):
        row = [i]
        for j, other in enumerate(prediction, 1):
            row.append(min(table[-1][j] + 1, row[-1] + 1, table[-1][j - 1] + (char != other)))
        table.append(row)
    matched = {}
    i, j = len(reference), len(prediction)
    while i or j:
        if i and j and table[i][j] == table[i - 1][j - 1] + (reference[i - 1] != prediction[j - 1]):
            if reference[i - 1] == prediction[j - 1]:
                matched[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif i and table[i][j] == table[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    counts = {"jamo_total": 0, "jamo_correct": 0, "abuse_total": 0, "abuse_correct": 0}
    for run in re.finditer(r"[ㄱ-ㅣ]+", reference):
        indices = [matched.get(k, -1) for k in range(run.start(), run.end())]
        start = indices[0]
        end = start + len(indices)
        exact = (
            start >= 0
            and indices == list(range(start, end))
            and (start == 0 or not re.fullmatch(r"[ㄱ-ㅣ]", prediction[start - 1]))
            and (end == len(prediction) or not re.fullmatch(r"[ㄱ-ㅣ]", prediction[end]))
        )
        counts["jamo_total"] += 1
        counts["jamo_correct"] += int(exact)
        if re.fullmatch(r"(?:[ㅅㅆ]ㅂ|ㅂㅅ|ㅈㄴ|ㅗ+)", run.group()):
            counts["abuse_total"] += 1
            counts["abuse_correct"] += int(exact)
    return {"edits": table[-1][-1], "characters": len(reference), **counts}


def load_samples(dataset: Path) -> list[dict]:
    """각 스트립에서 8칸(1200px) 간격 6장씩. 인접 캡처 중복을 피한다."""
    records = [json.loads(line) for line in (dataset / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
    wanted = {f"images/{strip}_{index:03d}.png" for strip in "ABC" for index in range(0, 41, 8)}
    samples = sorted((row for row in records if row["image"] in wanted), key=lambda row: row["image"])
    if len(samples) != 18:
        raise ValueError("synth_v1 정답에서 지정된 18장을 모두 찾을 수 없습니다.")
    return samples


def evaluate(dataset: Path, output: Path, names: list[str], repeats: int) -> dict:
    """로딩·최초 추론은 별도 기록, 프레임 시간은 리사이즈와 OCR 호출을 포함한다."""
    from PIL import Image

    from .impl import _load_image

    samples = load_samples(dataset)
    report = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "dataset": "synth_v1 (synthetic; not real game screenshots)",
        "labels_sha256": hashlib.sha256((dataset / "labels.jsonl").read_bytes()).hexdigest(),
        "repeats": repeats,
        "packages": {p: importlib.metadata.version(p) for p in ("rapidocr", "onnxruntime", "pillow", "numpy")},
        "engines": {},
    }
    for name in names:
        started = time.perf_counter()
        if name == "rapidocr":
            from .rapid import RapidOcr

            engine = RapidOcr()
        else:
            if platform.system() != "Windows":
                report["engines"][name] = {"unavailable": "Windows only"}
                continue
            from .windows import WindowsOcr

            engine = WindowsOcr()
        init_seconds = time.perf_counter() - started
        frames = []
        try:
            with _load_image(str(dataset / samples[0]["image"])) as warmup:
                started = time.perf_counter()
                with (
                    warmup.resize((warmup.width * 2, warmup.height * 2))
                    if name == "windows_2x"
                    else warmup.copy() as img
                ):
                    engine.read(img)
                first_seconds = time.perf_counter() - started
            for sample in samples:
                full = [line for line in sample["lines"] if line["visible"] == "full"]
                reference = "\n".join(line["text"] for line in full)
                with (
                    _load_image(str(dataset / sample["image"])) as image,
                    image.crop(
                        (0, min(line["top"] for line in full), image.width, max(line["bottom"] for line in full))
                    ) as crop,
                ):
                    durations, predictions = [], []
                    for _ in range(repeats):
                        started = time.perf_counter()
                        with (
                            crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)
                            if name == "windows_2x"
                            else crop.copy() as img
                        ):
                            lines = engine.read(img)
                        durations.append(time.perf_counter() - started)
                        predictions.append("\n".join(text for text, _ in lines))
                frames.append(
                    {
                        "image": sample["image"],
                        "sha256": hashlib.sha256((dataset / sample["image"]).read_bytes()).hexdigest(),
                        "reference": reference,
                        "prediction": predictions[0],
                        "stable": len(set(predictions)) == 1,
                        "seconds": durations,
                        **compare(reference, predictions[0]),
                    }
                )
                print(f"{name}: {sample['image']} {statistics.median(durations):.3f}s", flush=True)
        finally:
            if hasattr(engine, "close"):
                engine.close()
        totals = {
            key: sum(frame[key] for frame in frames)
            for key in ("edits", "characters", "jamo_total", "jamo_correct", "abuse_total", "abuse_correct")
        }
        times = sorted(duration for frame in frames for duration in frame["seconds"])
        report["engines"][name] = {
            "init_seconds": init_seconds,
            "first_inference_seconds": first_seconds,
            "cer": totals["edits"] / totals["characters"],
            "jamo_recall": totals["jamo_correct"] / totals["jamo_total"] if totals["jamo_total"] else None,
            "jamo_abuse_recall": totals["abuse_correct"] / totals["abuse_total"] if totals["abuse_total"] else None,
            "mean_seconds": statistics.mean(times),
            "median_seconds": statistics.median(times),
            "p95_seconds": times[min(len(times) - 1, int(len(times) * 0.95))],
            "totals": totals,
            "frames": frames,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".clean-chat/ocr-benchmark/results.json"))
    parser.add_argument(
        "--engines",
        nargs="+",
        choices=["windows_1x", "windows_2x", "rapidocr"],
        default=["windows_1x", "windows_2x", "rapidocr"],
    )
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats 는 1 이상이어야 합니다")
    evaluate(args.dataset, args.output, args.engines, args.repeats)


if __name__ == "__main__":
    main()
