"""대화 판단(judge) 평가 도구 — 게임 단위 대화 데이터로 "유저별 신고 권고 · 고소 후보"가 맞는지 잰다.

    uv run python -m clean_chat.modules.analyze.judge_evaluate fixtures/analyze/judge_games.jsonl --split test

실시간 필터(impl)와 과제가 다르다.
  impl   문장 1개 → 가릴 조각 · 피드백 유무 (0.5초 미만, 평가는 evaluate.py)
  judge  게임 1판의 전체 채팅 → 유저별 신고 권고 · 고소 후보 (1~5초, 5초 이상이면 로딩 창)

데이터 형식 (JSONL, 한 줄에 게임 하나. 모두 가상 문장):
  {"id", "split": "train"|"test", "my_name", "players": [10명: name, champion, team, position, is_me],
   "messages": [{"t": 초, "channel": "team"|"all", "speaker", "text", "text_norm"}],
   "labels": {닉네임: {"report", "complaint", "toward_me", "targets", "types", "reason"}}}   ← 문제 있는 유저만 적는다
한 판에 최대 10명(나 포함, 팀마다 5명). 상대 팀의 말은 전체 채팅(all)으로만 보인다.
표준 라이브러리만 쓴다 (추가 패키지 없음).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from clean_chat.core.schemas import ChatMessage, Player
from clean_chat.modules.analyze.judge import JudgeRequest, Judgment, judge

Game = dict[str, Any]
FAST_SEC, SLOW_SEC = 1.0, 5.0  # 1초 미만이면 바로, 5초 이상이면 로딩 창을 띄워야 한다


def load_games(path: Path, split: str | None = None) -> list[Game]:
    """JSONL → 게임 목록. split 을 주면 그 split 만."""
    with path.open(encoding="utf-8") as f:
        games = [json.loads(line) for line in f if line.strip()]
    return [g for g in games if split is None or g.get("split") == split]


def to_request(game: Game) -> JudgeRequest:
    """게임 1판 → JudgeRequest. 메시지 id 는 `<게임 id>-<순번>`."""
    players = [Player(**p) for p in game["players"]]
    champions = {p.name: p.champion for p in players}
    me = game["my_name"]
    messages = [
        ChatMessage(
            id=f"{game['id']}-{i}",
            ts=float(m["t"]),
            source="demo",
            channel=m.get("channel", "team"),
            speaker=m["speaker"],
            champion=champions.get(m["speaker"]),
            text=m["text"],
            text_norm=m.get("text_norm") or m["text"],
            is_me=m["speaker"] == me,
            raw=m["text"],
        )
        for i, m in enumerate(game["messages"])
    ]
    return JudgeRequest(messages=messages, players=players, my_name=me)


def transcripts(game: Game) -> dict[str, list[str]]:
    """유저별로 모은 채팅 (나 제외, 말한 순서). 한 판에 최대 9명."""
    out: dict[str, list[str]] = {p["name"]: [] for p in game["players"] if not p.get("is_me")}
    for m in game["messages"]:
        if m["speaker"] in out:
            out[m["speaker"]].append(m["text"])
    return out


def evaluate(games: Iterable[Game], predict: Callable[[JudgeRequest], Judgment] = judge) -> dict[str, Any]:
    """게임마다 judge 를 돌려 유저 단위로 채점한다. 정답에 없는 유저는 "문제없음"이다."""
    counts = {"report": Counter(), "complaint": Counter()}  # tp / fp / fn / tn
    latency: list[float] = []
    errors: list[dict[str, Any]] = []
    users = 0
    version = ""
    for game in games:
        req = to_request(game)
        start = time.perf_counter()
        result = predict(req)
        latency.append(time.perf_counter() - start)
        version = result.version
        pred = {s.speaker: s for s in result.speakers}
        for player in game["players"]:
            name = player["name"]
            if player.get("is_me"):
                continue
            users += 1
            gold = game.get("labels", {}).get(name, {})
            got = pred.get(name)
            for key, value in (
                ("report", bool(got and got.report)),
                ("complaint", bool(got and got.complaint_candidate)),
            ):
                want = bool(gold.get(key))
                counts[key][("t" if value == want else "f") + ("p" if value else "n")] += 1
                if value != want:
                    errors.append(
                        {"game": game["id"], "user": name, "what": key, "gold": want, "pred": value}
                        | {"reason": gold.get("reason", ""), "score": got.score if got else 0.0}
                    )
    if not latency:
        raise ValueError("평가할 게임이 없습니다")
    return {
        "version": version,
        "games": len(latency),
        "users": users,
        "report": _prf(counts["report"]),
        "complaint": _prf(counts["complaint"]),
        "latency_sec": {
            "mean": statistics.fmean(latency),
            "median": statistics.median(latency),
            "p95": sorted(latency)[min(len(latency) - 1, round(0.95 * (len(latency) - 1)))],
            "max": max(latency),
            "over_fast": sum(t >= FAST_SEC for t in latency),
            "over_slow": sum(t >= SLOW_SEC for t in latency),
        },
        "errors": errors,
    }


def format_report(result: dict[str, Any], max_errors: int = 30) -> str:
    def pct(v: float | None) -> str:
        return "  -  " if v is None else f"{v * 100:5.1f}%"

    lines = [f"{result['version']} · 게임 {result['games']}판 · 유저 {result['users']}명 (나 제외)"]
    lines.append("판단       정답률  정밀도  재현율   F1    정답 수  오탐  놓침")
    for key, label in (("report", "신고 권고"), ("complaint", "고소 후보")):
        m = result[key]
        lines.append(
            f"{label}  {pct(m['accuracy'])} {pct(m['precision'])} {pct(m['recall'])} {pct(m['f1'])}"
            f" {m['support']:>6} {m['fp']:>5} {m['fn']:>5}"
        )
    lat = result["latency_sec"]
    lines.append(
        f"속도(1판)  평균 {lat['mean']:.2f}초 · 중앙값 {lat['median']:.2f}초 · p95 {lat['p95']:.2f}초 · 최대 {lat['max']:.2f}초"
        f" · {FAST_SEC:.0f}초 이상 {lat['over_fast']}판 · {SLOW_SEC:.0f}초 이상(로딩 창) {lat['over_slow']}판"
    )
    if result["errors"]:
        lines.append(f"틀린 예 ({min(max_errors, len(result['errors']))}/{len(result['errors'])})")
        for e in result["errors"][:max_errors]:
            kind = "놓침" if e["gold"] else "오탐"
            lines.append(f"  {e['game']} {e['user']} [{e['what']} {kind}] 점수 {e['score']}  {e['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="judge 평가: 게임 단위 대화 데이터 → 유저별 신고·고소 판단의 정확도와 속도"
    )
    ap.add_argument("jsonl", type=Path, help="게임 데이터 (fixtures/analyze/judge_games.jsonl)")
    ap.add_argument("--split", help="split 이 이 값인 게임만 (예: test)")
    ap.add_argument("--out", type=Path, help="결과를 JSON 으로 저장할 경로")
    ap.add_argument(
        "--mode", choices=["hybrid", "rules", "model"], default="hybrid", help="규칙 + 모델 / 규칙만 / 모델만"
    )
    args = ap.parse_args(argv)
    games = load_games(args.jsonl, args.split)
    if games:
        judge(to_request(games[0]), mode=args.mode)  # 첫 실행의 모델 로딩 시간을 속도 측정에서 뺀다
    result = evaluate(games, lambda req: judge(req, mode=args.mode))
    print(format_report(result))
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _prf(c: Counter) -> dict[str, Any]:
    tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {
        "accuracy": (tp + tn) / total if total else None,  # 유저 단위 정답률 (오답률 = 1 - 정답률)
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "support": tp + fn,
        "fp": fp,
        "fn": fn,
    }


if __name__ == "__main__":
    sys.exit(main())
