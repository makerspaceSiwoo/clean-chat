"""전체 흐름 정답 비교 (구성 · 리드): 예시 이미지마다 정해 둔 기대값(fixtures/flow/samples.jsonl 의 expect)과
단계별 실제 결과를 비교한다. 다르면 mismatch 로 화면에 빨간색, 오류 로그에 기록.

기대값 (expect.lines[i] 는 lines[i] 줄의 정답, 줄 텍스트로 찾는다 → OCR 가정 응답을 고쳐도 남은 줄은 비교된다)
  {"chat": false}                                  시스템 메시지 → parse 가 None 이어야 함
  {"chat": true, "speaker", "channel", "level",     parse 화자·채널, analyze 등급
   "level": 2 | [0, 1],                             analyze 등급 (목록이면 그중 하나면 정답)
   "target": 닉네임 | "*",                          analyze 대상 (L2 이상에서만, "*" 면 검사 안 함)
   "action": "hide" | ["hide", "show_rewritten"]}   정책 결과 (목록이면 그중 하나면 정답)
  expect.reports / expect.complaints                게임 종료 후 신고 문구·고소장 초안 대상 화자

비교 규칙
  - 가정 응답으로 대신한 모듈 결과는 비교하지 않는다 (모듈 정답률이 아니므로). 정책·report 대상은 항상 비교.
  - ocr 은 실제로 돌았을 때만, 정답 줄 목록과 읽은 줄 목록을 비교 (빠진 줄 · 더 읽은 줄).
결과 1건: {"stage", "field", "expected", "actual", "ok", "itemId", "note"}
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any

from pydantic import BaseModel

from clean_chat.core.config import FIXTURES

SAMPLES = FIXTURES / "flow" / "samples.jsonl"
ANY = "*"
MATCH = (
    0.8  # OCR 이 조금 틀리게 읽은 줄도 이 유사도 이상이면 같은 정답 줄로 보고 뒤 단계(parse·analyze·정책)를 비교한다
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def load_sample(sample_id: str | None) -> dict[str, Any] | None:
    if not sample_id or not SAMPLES.exists():
        return None
    for line in SAMPLES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            s = json.loads(line)
            if s.get("id") == sample_id:
                return s
    return None


class Checker:
    """실행 1번 동안 줄 id ↔ 줄 텍스트를 기억하며 단계별로 비교한다."""

    def __init__(self, sample: dict[str, Any]) -> None:
        expect = sample["expect"]
        self.status = expect.get("status", "draft")
        self.truth = [norm(t) for t in sample["lines"]]
        self.by_text = dict(zip(self.truth, expect["lines"], strict=True))
        self.reports = sorted(expect.get("reports", []))
        self.complaints = sorted(expect.get("complaints", []))
        self.text_of: dict[str, str] = {}  # 줄 id · 메시지 id → 정규화한 줄 텍스트

    @classmethod
    def for_sample(cls, sample_id: str | None) -> Checker | None:
        s = load_sample(sample_id)
        return cls(s) if s and s.get("expect") else None

    # ── 비교 1건 ──
    @staticmethod
    def _one(
        stage: str, field: str, expected: Any, actual: Any, item_id: str | None, note: str | None = None, any_of=False
    ) -> dict[str, Any]:
        """any_of=True 면 expected(목록) 중 하나면 정답. 아니면 그대로 같아야 정답 (목록끼리도)."""
        ok = actual in expected if any_of else actual == expected
        return {
            "stage": stage,
            "field": field,
            "expected": expected,
            "actual": actual,
            "ok": ok,
            "itemId": item_id,
            "note": note,
        }

    def _exp(self, item_id: str) -> dict[str, Any] | None:
        text = self.text_of.get(item_id)
        return self.by_text.get(text) if text is not None else None

    def _truth_for(self, text: str) -> str:
        """읽은 줄 → 정답 줄 텍스트. 똑같은 줄이 없으면 가장 비슷한 정답 줄(MATCH 이상), 없으면 그대로."""
        if text in self.by_text:
            return text
        best = max(self.truth, key=lambda t: difflib.SequenceMatcher(None, t, text).ratio(), default=None)
        if best is not None and difflib.SequenceMatcher(None, best, text).ratio() >= MATCH:
            return best
        return text

    # ── 모듈 호출 ──
    def after_call(self, name: str, item: BaseModel, out: BaseModel, mode: str) -> list[dict[str, Any]]:
        if name == "parse":  # 줄 id·메시지 id → 텍스트는 가정 응답이어도 기억 (뒤 단계 비교용)
            text = self._truth_for(norm(item.line.text))  # type: ignore[attr-defined]
            self.text_of[item.line.id] = text  # type: ignore[attr-defined]
            if out.message is not None:  # type: ignore[attr-defined]
                self.text_of[out.message.id] = text  # type: ignore[attr-defined]
        if mode != "real":
            return []
        check = getattr(self, f"_check_{name}", None)
        return check(item, out) if check else []

    def _check_ocr(self, item: BaseModel, out: BaseModel) -> list[dict[str, Any]]:
        read = [(ln.id, norm(ln.text)) for ln in out.lines]  # type: ignore[attr-defined]
        got = {t for _, t in read}
        # 정답 줄마다: 똑같이 읽었으면 정답, 비슷하게 읽었으면(MATCH 이상) 그 줄을 결과로 보여 주고 오답, 못 읽었으면 None
        results, used = [], set()
        for t in self.truth:
            if t in got:
                results.append(self._one("ocr", "line", t, t, None))
                used.add(t)
                continue
            near = [(difflib.SequenceMatcher(None, t, g).ratio(), i, g) for i, g in read if g not in used]
            score, line_id, g = max(near, default=(0.0, None, None))
            if score >= MATCH:
                used.add(g)
                r = self._one("ocr", "line", t, g, line_id)
                r["similarity"] = round(score, 3)
                results.append(r)
            else:
                results.append(self._one("ocr", "line", t, None, None))
        results += [self._one("ocr", "line", None, g, i) for i, g in read if g not in used and g not in self.by_text]
        return results

    def _check_parse(self, item: BaseModel, out: BaseModel) -> list[dict[str, Any]]:
        line_id = item.line.id  # type: ignore[attr-defined]
        exp = self._exp(line_id)
        if exp is None:
            return []
        msg = out.message  # type: ignore[attr-defined]
        results = [self._one("parse", "chat", exp["chat"], msg is not None, line_id, exp.get("note"))]
        if exp["chat"] and msg is not None:
            results.append(self._one("parse", "speaker", exp["speaker"], msg.speaker, line_id))
            results.append(self._one("parse", "channel", exp["channel"], str(msg.channel), line_id))
        return results

    def _check_analyze(self, item: BaseModel, out: BaseModel) -> list[dict[str, Any]]:
        msg_id = item.message.id  # type: ignore[attr-defined]
        exp = self._exp(msg_id)
        if not exp or not exp.get("chat"):
            return []
        level = int(out.level)  # type: ignore[attr-defined]
        expected = exp["level"]  # 목록이면 그중 하나면 정답 (판단이 갈리는 줄)
        results = [self._one("analyze", "level", expected, level, msg_id, exp.get("note"), isinstance(expected, list))]
        if exp.get("target", ANY) != ANY and min(expected if isinstance(expected, list) else [expected]) >= 2:
            results.append(self._one("analyze", "target", exp["target"], out.target, msg_id))  # type: ignore[attr-defined]
        return results

    # ── 정책 · 게임 종료 ──
    def after_incident(self, incident: BaseModel) -> list[dict[str, Any]]:
        msg_id = incident.msg.id  # type: ignore[attr-defined]
        exp = self._exp(msg_id)
        if not exp or not exp.get("chat") or "action" not in exp:
            return []
        action = str(incident.decision.action)  # type: ignore[attr-defined]
        expected = exp["action"]
        return [self._one("policy", "action", expected, action, msg_id, exp.get("note"), isinstance(expected, list))]

    def after_post_game(self, result: BaseModel | None) -> list[dict[str, Any]]:
        reports = sorted(d.speaker for d in result.reports) if result else []  # type: ignore[attr-defined]
        complaints = sorted(d.speaker for d in result.complaints) if result else []  # type: ignore[attr-defined]
        return [
            self._one("report", "reports", self.reports, reports, None),
            self._one("report", "complaints", self.complaints, complaints, None),
        ]


def describe(r: dict[str, Any]) -> str:
    """로그 한 줄 (채팅 원문은 남기지 않는다)."""
    where = f" ({r['itemId']})" if r.get("itemId") else ""
    return f"{r['field']}: 기대 {r['expected']!r} ≠ 결과 {r['actual']!r}{where}"
