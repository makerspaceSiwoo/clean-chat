"""모듈별 평가 데이터(data/eval/modules/)로 ocr · parse · rewrite · report 를 채점한다.

    uv run python scripts/score_eval.py parse
    uv run python scripts/score_eval.py all

통과·실패가 아니라 점수를 본다. 구현 전인 모듈은 "구현 안 됨"으로 표시한다. 데이터 설명: data/eval/modules/README.md
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from typing import Any

from clean_chat.core import modules
from clean_chat.core.config import resolve_repo_path
from clean_chat.core.schemas import Frame, GameSession, ParseRequest, ReportRequest, RewriteRequest

DATA = resolve_repo_path("data/eval/modules")


def _load(name: str) -> list[dict[str, Any]]:
    with (DATA / name).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _pct(n: int, d: int) -> str:
    return "  -  " if not d else f"{100 * n / d:5.1f}% ({n}/{d})"


def _timed(name: str, fn: Any, req: Any, times: list[float]) -> Any:
    start = time.perf_counter()
    out = modules.invoke(name, fn, req)
    times.append((time.perf_counter() - start) * 1000)
    return out


def _speed(times: list[float]) -> str:
    return f"평균 {statistics.fmean(times):.1f}ms · 최대 {max(times):.1f}ms" if times else "-"


def score_parse() -> None:
    fn, cases, times = modules.load("parse"), _load("parse_cases.jsonl"), []
    kind = fields = norm = norm_changed = chat = changed = 0
    for case in cases:
        out = _timed("parse", fn, ParseRequest.model_validate(case["input"]), times).message
        exp = case["expect"]
        kind += (out is not None) == exp["is_chat"]
        if not exp["is_chat"] or out is None:
            continue
        chat += 1
        got = (out.channel.value, out.speaker, out.champion, out.text, out.is_me, out.raw)
        fields += got == (exp["channel"], exp["speaker"], exp["champion"], exp["text"], exp["is_me"], exp["raw"])
        norm += out.text_norm == exp["text_norm"]
        if exp["norm_changed"]:
            changed += 1
            norm_changed += out.text_norm == exp["text_norm"]
    print(f"parse · {len(cases)}줄")
    print(f"  채팅 여부(시스템 메시지·핑·잡음 구분)   {_pct(kind, len(cases))}")
    print(f"  채널·화자·챔피언·본문·is_me·raw 일치   {_pct(fields, chat)}")
    print(
        f"  text_norm 일치 (참고)                  {_pct(norm, chat)} · 우회 표기가 있는 줄만 {_pct(norm_changed, changed)}"
    )
    print(f"  속도 {_speed(times)}")


def score_rewrite() -> None:
    fn, cases, times = modules.load("rewrite"), _load("rewrite_cases.jsonl"), []
    produced = clean = short = 0
    for case in cases:
        out = _timed("rewrite", fn, RewriteRequest.model_validate(case["input"]), times)
        exp = case["expect"]
        if not out.rewritten:
            continue
        produced += 1
        clean += not any(word in out.rewritten for word in exp["must_not_contain"])
        short += len(out.rewritten) <= exp["max_chars"]
    print(f"rewrite · {len(cases)}건")
    print(f"  순화문이 나옴          {_pct(produced, len(cases))}")
    print(f"  욕설 조각이 남지 않음   {_pct(clean, produced)}")
    print(f"  60자 이내              {_pct(short, produced)}")
    print(f"  속도 {_speed(times)}  (자연스러움·뜻 보존은 사람이 확인)")


def score_report() -> None:
    fn, cases, times = modules.load("report"), _load("report_cases.jsonl"), []
    sessions = {s["id"]: GameSession.model_validate(s) for s in _load("report_sessions.jsonl")}
    ids = quoted = contains = 0
    for case in cases:
        inp = dict(case["input"])
        req = ReportRequest(session=sessions[inp.pop("session_id")], **inp)
        out = _timed("report", fn, req, times)
        exp = case["expect"]
        ids += sorted(out.incident_ids) == sorted(exp["incident_ids"])
        quoted += all(text in out.text for text in exp["must_quote"]) if exp["kind"] == "report" else True
        contains += all(word in out.text for word in exp["must_contain"])
    print(f"report · {len(cases)}건 (세션 {len(sessions)}판)")
    print(f"  incident_ids 가 그 유저의 기록과 같음   {_pct(ids, len(cases))}")
    print(f"  신고 문구가 원문을 그대로 인용          {_pct(quoted, len(cases))}")
    print(f"  꼭 들어가야 할 말(대상 닉네임·고지)      {_pct(contains, len(cases))}")
    print(f"  속도 {_speed(times)}  (문구 품질은 사람이 확인)")


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score_ocr() -> None:
    fn, cases, times = modules.load("ocr"), _load("ocr_cases.jsonl"), []
    exact = total = errors = chars = 0
    for case in cases:
        out = _timed("ocr", fn, Frame.model_validate(case["input"]), times)
        got = [line.text.strip() for line in out.lines]
        want = case["expect"]["lines"]
        total += len(want)
        exact += sum(line in got for line in want)
        errors += _edit_distance("\n".join(got), "\n".join(want))
        chars += len("\n".join(want))
    print(f"ocr · 합성 이미지 {len(cases)}장 · {total}줄 (실제 게임 화면이 아님)")
    print(f"  줄 정확 일치   {_pct(exact, total)}")
    print(f"  글자 오류율    {100 * errors / max(1, chars):.1f}%")
    print(f"  속도 {_speed(times)} (기준: 프레임당 500ms)")


SCORERS = {"ocr": score_ocr, "parse": score_parse, "rewrite": score_rewrite, "report": score_report}


def main(argv: list[str]) -> int:
    names = list(SCORERS) if argv[1:] in ([], ["all"]) else argv[1:]
    for name in names:
        if name not in SCORERS:
            print(f"모르는 모듈: {name} (ocr · parse · rewrite · report · all)")
            return 2
        try:
            SCORERS[name]()
        except modules.ModuleNotImplemented:
            print(f"{name} · 구현 안 됨 (run() 이 NotImplementedError)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
