"""모듈 단독 실행기: `uv run clean-chat module <이름>`. fixtures 입력을 실제 함수로 실행하고 기대값과 비교한다.

uv run clean-chat module parse                     # fixtures/parse/input.jsonl 실행 → 출력 JSONL
uv run clean-chat module parse --check             # expected.jsonl 과 비교 (다르면 종료 코드 1)
uv run clean-chat module parse --in my.jsonl --out out.jsonl
구현이 없으면(NotImplementedError) "구현 안 됨" 으로 종료 코드 2. Mock 은 없다 (ADR-0017).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from clean_chat.core import modules
from clean_chat.core.config import FIXTURES
from clean_chat.core.jsonl import read_jsonl, write_jsonl
from clean_chat.core.platform import PlatformNotSupported


def run_module(name: str, inp: Path | None = None, out: Path | None = None, check: bool = False) -> int:
    spec = modules.MODULES[name]
    items = read_jsonl(inp or FIXTURES / name / "input.jsonl", spec.input_model)
    fn = modules.load(name)
    t0 = time.perf_counter()
    try:
        outs = [modules.invoke(name, fn, x) for x in items]
    except modules.ModuleNotImplemented as e:
        print(f"⏳ {e}", file=sys.stderr)
        return 2
    except PlatformNotSupported as e:
        print(f"🪟 [{name}] {e}", file=sys.stderr)
        return 3
    dt = (time.perf_counter() - t0) / max(len(items), 1)
    for o in outs:
        print(o.model_dump_json())
    print(f"✅ [{name}] {len(outs)}건 처리, 평균 {dt * 1000:.1f}ms, 출력 형식 OK", file=sys.stderr)
    if out:
        write_jsonl(out, outs)
    if not check:
        return 0
    exp = read_jsonl(FIXTURES / name / "expected.jsonl", spec.output_model)
    same = sum(o == e for o, e in zip(outs, exp, strict=False))
    print(f"🔎 expected 일치: {same}/{len(exp)}", file=sys.stderr)
    return 0 if same == len(exp) == len(outs) else 1
