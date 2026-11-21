"""analyze 평가 도구 — 라벨 CSV 로 run() 의 정확도와 속도를 잰다. 모델 비교(브랜치별)에 같은 명령을 쓴다.

    uv run python -m clean_chat.modules.analyze.evaluate data/eval/test.csv
    uv run python -m clean_chat.modules.analyze.evaluate data/eval/test.csv --with-parse --out report.json

CSV 열은 docs/LABELING_GUIDE.md 를 따른다: text, level, harm_types(`|` 연결), has_feedback, target(me/team/enemy/none/unknown).
선택 열: text_norm·hints(parse 를 거친 값, 없으면 text 그대로), profanity_spans(`|` 연결, 있으면 조각도 채점),
split(--split test 로 시험 문장만 평가). --with-parse 를 주면 실제 parse 모듈로 정규화한다
(실행 시와 같은 전처리. parse 가 구현되어 있어야 한다).
표준 라이브러리만 쓴다 (추가 패키지 없음).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from clean_chat.core.schemas import Analysis, AnalyzeRequest, ChatMessage, HarmType
from clean_chat.modules.analyze.impl import run

Row = dict[str, str]
LEVELS = (0, 1, 2, 3)


def load_rows(path: Path, split: str | None = None) -> list[Row]:
    """라벨 CSV → 행 목록. text 나 level 이 빈 행은 건너뛴다. split 을 주면 split 열이 같은 행만."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("text") or "").strip() and (r.get("level") or "").strip()]
    return [r for r in rows if split is None or (r.get("split") or "").strip() == split]


def to_request(row: Row, index: int, normalize: Callable[[str], ChatMessage | None] | None = None) -> AnalyzeRequest:
    """CSV 한 행 → AnalyzeRequest. normalize(parse)가 있으면 그 결과를, 없으면 text_norm 열 또는 text 를 쓴다."""
    text = row["text"].strip()
    msg = normalize(text) if normalize else None
    if msg is None:
        msg = ChatMessage(
            id=f"E{index}",
            ts=0.0,
            source="self_input",
            channel="team",
            speaker="화자",
            text=text,
            text_norm=(row.get("text_norm") or "").strip() or text,
            hints=[h for h in (row.get("hints") or "").split("|") if h.strip()],
            raw=text,
        )
    return AnalyzeRequest(message=msg.model_copy(update={"id": f"E{index}"}))


def parse_normalizer() -> Callable[[str], ChatMessage | None]:
    """실제 parse 모듈을 연결표(core/modules.py)로 불러 정규화한다. 모듈 폴더를 직접 import 하지 않는다."""
    from clean_chat.core import modules
    from clean_chat.core.schemas import ParseRequest, RawLine

    fn = modules.load("parse")

    def normalize(text: str) -> ChatMessage | None:
        line = RawLine(id="E", ts=0.0, text=text, source="self_input")
        return modules.invoke("parse", fn, ParseRequest(line=line, my_name="화자")).message

    return normalize


def evaluate(
    rows: Iterable[Row],
    predict: Callable[[AnalyzeRequest], Analysis] = run,
    normalize: Callable[[str], ChatMessage | None] | None = None,
) -> dict[str, Any]:
    """라벨 행들을 predict 에 넣어 지표를 계산한다. 반환값은 JSON 으로 저장할 수 있는 dict."""
    confusion = {gold: dict.fromkeys(LEVELS, 0) for gold in LEVELS}
    types = {t.value: Counter() for t in HarmType}  # tp / fp / fn
    feedback, target, bypass, spans = Counter(), Counter(), Counter(), Counter()
    latency: list[float] = []
    errors: list[dict[str, Any]] = []
    model_version = ""
    for i, row in enumerate(rows):
        req = to_request(row, i, normalize)
        start = time.perf_counter()
        out = predict(req)
        latency.append((time.perf_counter() - start) * 1000)
        model_version = out.model_version
        gold_level, pred_level = int(row["level"]), int(out.level)
        confusion[gold_level][pred_level] += 1
        if req.message.text_norm != req.message.text:  # 우회 표현이 든 문장만 따로
            bypass["n"] += 1
            bypass["ok"] += gold_level == pred_level
        gold_types = {t for t in (row.get("harm_types") or "").split("|") if t.strip()}
        pred_types = {t.value for t in out.harm_types}
        for name, c in types.items():
            c["tp"] += name in gold_types and name in pred_types
            c["fp"] += name not in gold_types and name in pred_types
            c["fn"] += name in gold_types and name not in pred_types
        if (row.get("has_feedback") or "").strip() in ("0", "1"):
            feedback["n"] += 1
            feedback["ok"] += (row["has_feedback"].strip() == "1") == bool(out.feedback_spans)
        if (row.get("target") or "").strip() in ("me", "team", "enemy", "none"):
            target["n"] += 1
            target["ok"] += (row["target"].strip() != "none") == (out.target is not None)
        if row.get("profanity_spans") is not None:  # 가릴 조각이 정답과 정확히 같은가 (순서 무시)
            spans["n"] += 1
            spans["ok"] += {s for s in row["profanity_spans"].split("|") if s} == set(out.profanity_spans)
        if gold_level != pred_level:
            errors.append(
                {"text": req.message.text, "gold": gold_level, "pred": pred_level, "pred_types": sorted(pred_types)}
            )
    n = len(latency)
    if n == 0:
        raise ValueError("평가할 행이 없습니다 (text, level 열을 확인하세요)")
    severe = [g for g in LEVELS if g >= 2]
    severe_n = sum(sum(confusion[g].values()) for g in severe)
    clean_n = sum(confusion[0].values())
    return {
        "model_version": model_version,
        "n": n,
        "level_accuracy": sum(confusion[g][g] for g in LEVELS) / n,
        # 악성(L2 이상)을 L2 이상으로 잡은 비율 — 놓치면 악성 채팅이 그대로 보인다
        "severe_recall": _ratio(sum(confusion[g][p] for g in severe for p in severe), severe_n),
        # 정상(L0)인데 L1 이상으로 본 비율 — 높으면 멀쩡한 채팅을 가린다
        "clean_false_positive_rate": _ratio(clean_n - confusion[0][0], clean_n),
        "bypass_level_accuracy": _ratio(bypass["ok"], bypass["n"]),
        "span_accuracy": _ratio(spans["ok"], spans["n"]),
        "feedback_accuracy": _ratio(feedback["ok"], feedback["n"]),
        "target_presence_accuracy": _ratio(target["ok"], target["n"]),
        "harm_types": {name: _prf(c) for name, c in types.items()},
        "confusion": {str(g): {str(p): v for p, v in row.items()} for g, row in confusion.items()},
        "latency_ms": {"median": statistics.median(latency), "p95": _percentile(latency, 0.95), "max": max(latency)},
        "errors": errors,
    }


def format_report(result: dict[str, Any], max_errors: int = 20) -> str:
    """사람이 읽는 요약."""

    def pct(v: float | None) -> str:
        return "  -  " if v is None else f"{v * 100:5.1f}%"

    lines = [
        f"모델 {result['model_version']} · {result['n']}문장",
        f"등급 일치율          {pct(result['level_accuracy'])}",
        f"악성(L2↑) 재현율     {pct(result['severe_recall'])}",
        f"정상(L0) 오탐률      {pct(result['clean_false_positive_rate'])}",
        f"우회 표현 등급 일치율 {pct(result['bypass_level_accuracy'])}",
        f"가릴 조각 일치율      {pct(result['span_accuracy'])}",
        f"피드백 유무 일치율    {pct(result['feedback_accuracy'])}",
        f"대상 유무 일치율      {pct(result['target_presence_accuracy'])}",
        "유형별 (정밀도 / 재현율 / F1 / 정답 수)",
    ]
    for name, m in result["harm_types"].items():
        lines.append(f"  {name:<18} {pct(m['precision'])} {pct(m['recall'])} {pct(m['f1'])} {m['support']:>5}")
    lines.append("혼동 행렬 (행 = 정답, 열 = 예측 L0~L3)")
    for gold, row in result["confusion"].items():
        lines.append(f"  L{gold}  " + " ".join(f"{v:>5}" for v in row.values()))
    lat = result["latency_ms"]
    lines.append(f"속도  중앙값 {lat['median']:.2f}ms · p95 {lat['p95']:.2f}ms · 최대 {lat['max']:.2f}ms (기준 200ms)")
    if result["errors"]:
        lines.append(f"틀린 예 ({min(max_errors, len(result['errors']))}/{len(result['errors'])})")
        lines += [f"  정답 L{e['gold']} → 예측 L{e['pred']}  {e['text']}" for e in result["errors"][:max_errors]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="analyze 평가: 라벨 CSV → 정확도·속도")
    ap.add_argument("csv", type=Path, help="라벨 CSV (docs/LABELING_GUIDE.md 형식)")
    ap.add_argument("--with-parse", action="store_true", help="실제 parse 모듈로 정규화한 뒤 평가")
    ap.add_argument("--split", help="split 열이 이 값인 행만 평가 (예: test)")
    ap.add_argument("--out", type=Path, help="결과를 JSON 으로 저장할 경로")
    args = ap.parse_args(argv)
    normalize = parse_normalizer() if args.with_parse else None
    run(to_request({"text": "준비"}, -1))  # 첫 실행의 로딩 시간을 속도 측정에서 뺀다
    result = evaluate(load_rows(args.csv, args.split), normalize=normalize)
    print(format_report(result))
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def _prf(c: Counter) -> dict[str, Any]:
    precision = _ratio(c["tp"], c["tp"] + c["fp"])
    recall = _ratio(c["tp"], c["tp"] + c["fn"])
    f1 = None if precision is None or recall is None else _ratio(2 * precision * recall, precision + recall) or 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "support": c["tp"] + c["fn"]}


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


if __name__ == "__main__":
    sys.exit(main())
