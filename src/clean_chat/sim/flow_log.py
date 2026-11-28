"""전체 흐름 오류 로그 (구성 · 리드): 단계마다 실패를 분류해 로컬 JSONL 에 쌓고, 화면에서 단계별로 모아 본다.

저장: .clean-chat/flow-logs/<YYYYMMDD>.jsonl (git 제외, 이 PC 에만 남는다). 한 줄 = 기록 1건
  {"type": "failure", "ts", "runId", "stage", "kind", "severity", "message", "traceback", "itemId", "sample"}
  {"type": "run", "ts", "runId", "status", "stoppedAt", "durationMs", "stages": {이름: {calls, real, fallback, errors, warnings}}}

stage = 모듈 이름(ocr · parse · analyze · rewrite · report) 또는 구성 단계(game · pipeline · post_game).
kind / severity:
  not_implemented  warning  구현 전 (NotImplementedError)
  platform         warning  이 OS 에서는 못 돎 (PlatformNotSupported, 예: Windows 내장 OCR)
  empty_result     warning  오류는 아니지만 결과가 비었음 (ocr 0줄, rewrite None → 정책이 숨김)
  missing_package  error    모듈 패키지 없음 (ModuleNotFoundError → uv run --extra <모듈>)
  import_error     error    모듈 파일을 불러오지 못함 (문법 오류, import 실패)
  bad_output       error    출력이 계약(core/schemas.py)과 다름
  exception        error    모듈 안에서 난 예외
  stage_exception  error    모듈 밖 구성 단계에서 난 예외 → 흐름이 멈춤
  mismatch         mismatch 기대값(정답)과 결과가 다름 (sim/flow_check.py). stage 에 policy(정책표)도 쓴다
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from clean_chat.core.config import settings
from clean_chat.core.modules import ModuleNotImplemented

SEVERITY = {
    "not_implemented": "warning",
    "platform": "warning",
    "empty_result": "warning",
    "missing_package": "error",
    "import_error": "error",
    "bad_output": "error",
    "exception": "error",
    "stage_exception": "error",
    "mismatch": "mismatch",
}
STAGES = ("ocr", "parse", "analyze", "rewrite", "policy", "report", "game", "pipeline", "post_game")
COUNT_FOR = {"error": "errors", "warning": "warnings", "mismatch": "mismatches"}
MAX_TRACEBACK = 8000  # 기록 1건 크기 제한 (긴 traceback 은 뒤쪽만 남긴다)


LOG_DIR_ENV = "CLEAN_CHAT_FLOW_LOG_DIR"  # 테스트 등에서 기록 위치를 바꿀 때


def log_dir() -> Path:
    return Path(os.environ.get(LOG_DIR_ENV) or settings.store_dir / "flow-logs")


def classify(e: BaseException, *, loading: bool = False) -> str:
    """예외 → kind. loading=True 면 모듈 파일을 불러오다 난 예외."""
    if isinstance(e, ModuleNotImplemented | NotImplementedError):
        return "not_implemented"
    if type(e).__name__ == "PlatformNotSupported":
        return "platform"
    if isinstance(e, ModuleNotFoundError):
        return "missing_package"
    if loading:
        return "import_error"
    if isinstance(e, ValidationError) or (isinstance(e, TypeError) and "돌려줬습니다" in str(e)):
        return "bad_output"  # core/modules.invoke 의 출력 형식 검사
    return "exception"


class FlowLog:
    """실행 1번의 기록기. 실패는 생길 때마다 바로 파일에 덧붙인다 (중간에 프로세스가 죽어도 남게)."""

    def __init__(self, run_id: str, sample: str | None = None, directory: Path | None = None) -> None:
        self.run_id, self.sample = run_id, sample
        self.dir = directory or log_dir()
        self.started = time.perf_counter()
        self.stages: dict[str, dict[str, int]] = {}

    @property
    def path(self) -> Path:
        return self.dir / f"{datetime.now():%Y%m%d}.jsonl"

    def _write(self, record: dict[str, Any]) -> None:
        """로그를 못 써도 흐름은 멈추지 않는다 (디스크 문제는 콘솔에만 알림)."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"⚠ 오류 로그를 쓰지 못했습니다 ({self.path}): {e}", file=sys.stderr, flush=True)

    def count(self, stage: str, key: str) -> None:
        s = self.stages.setdefault(stage, _counts())
        s[key] = s.get(key, 0) + 1

    def failure(
        self, stage: str, kind: str, message: str, traceback: str = "", item_id: str | None = None
    ) -> dict[str, Any]:
        severity = SEVERITY.get(kind, "error")
        self.count(stage, COUNT_FOR.get(severity, "errors"))
        record = {
            "type": "failure",
            "ts": time.time(),
            "runId": self.run_id,
            "sample": self.sample,
            "stage": stage,
            "kind": kind,
            "severity": severity,
            "message": message[:1000],
            "traceback": traceback[-MAX_TRACEBACK:],
            "itemId": item_id,
        }
        self._write(record)
        return record

    def finish(self, status: str, stopped_at: str | None = None) -> dict[str, Any]:
        record = {
            "type": "run",
            "ts": time.time(),
            "runId": self.run_id,
            "sample": self.sample,
            "status": status,
            "stoppedAt": stopped_at,
            "durationMs": round((time.perf_counter() - self.started) * 1000),
            "stages": self.stages,
        }
        self._write(record)
        return record


def read_records(directory: Path | None = None, days: int = 7) -> list[dict[str, Any]]:
    """최근 days 일치 파일을 시간순으로. 깨진 줄은 건너뛴다."""
    d = directory or log_dir()
    files = sorted(d.glob("*.jsonl"))[-days:] if d.exists() else []
    out = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _counts() -> dict[str, int]:
    """단계 1개의 합계. checked·mismatches 는 정답 비교 (기대값이 있는 예시에서만)."""
    return {"calls": 0, "real": 0, "fallback": 0, "errors": 0, "warnings": 0, "checked": 0, "mismatches": 0}


def _empty() -> dict[str, Any]:
    return {**_counts(), "failedRuns": 0, "mismatchRuns": 0}


def summary(directory: Path | None = None, runs: int = 50, failures: int = 100) -> dict[str, Any]:
    """화면용 모음: 최근 runs 번 실행의 단계별 합계 + 최근 실패 목록 (최신이 앞)."""
    records = read_records(directory)
    run_recs = [r for r in records if r.get("type") == "run"][-runs:]
    run_ids = {r["runId"] for r in run_recs}
    fails = [r for r in records if r.get("type") == "failure" and r.get("runId") in run_ids]
    stages: dict[str, dict[str, Any]] = {name: _empty() for name in STAGES}
    for r in run_recs:
        for name, counts in (r.get("stages") or {}).items():
            s = stages.setdefault(name, _empty())
            for k, v in counts.items():
                s[k] = s.get(k, 0) + v
            if counts.get("errors"):
                s["failedRuns"] += 1
            if counts.get("mismatches"):
                s["mismatchRuns"] += 1
    for f in fails:
        stages.setdefault(f["stage"], _empty())["last"] = {k: f.get(k) for k in ("ts", "kind", "severity", "message")}
    return {
        "path": str(directory or log_dir()),
        "runs": list(reversed(run_recs)),
        "stages": stages,
        "failures": list(reversed(fails))[:failures],
    }
