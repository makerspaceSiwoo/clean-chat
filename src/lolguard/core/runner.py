"""모듈 단독 실행기. 모든 모듈의 `python -m lolguard.<모듈>` 이 이 함수를 씁니다.

uv run python -m lolguard.parse                 # 실제 구현(real)을 fixtures 입력으로 실행
uv run python -m lolguard.parse --impl mock     # 형식 확인용 가짜 실행
uv run python -m lolguard.parse --check         # expected.jsonl 과 비교
uv run python -m lolguard.parse --in my.jsonl --out out.jsonl
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from lolguard.core import registry
from lolguard.core.config import FIXTURES
from lolguard.core.platform import PlatformNotSupported
from lolguard.core.stage import read_jsonl, write_jsonl


def run_module(name: str, argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=f"python -m lolguard.<{name}>")
    ap.add_argument("--impl", choices=["real", "mock"], default="real")
    ap.add_argument("--in", dest="inp", type=Path, default=FIXTURES / name / "input.jsonl")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--check", action="store_true", help="expected.jsonl 과 결과 비교")
    a = ap.parse_args(argv)

    iface = registry.interface(name)
    items = read_jsonl(a.inp, iface.input_model)
    stage = registry.create(name, a.impl)
    try:
        stage.setup()
        t0 = time.perf_counter()
        outs = [iface.output_model.model_validate(stage.run(x).model_dump()) for x in items]  # 출력 형식 검증
        dt = (time.perf_counter() - t0) / max(len(items), 1)
    except NotImplementedError as e:
        print(f"⏳ [{name}] 실제 구현이 아직 없습니다: {e}\n   → 형식 확인은 --impl mock 으로 실행하세요.")
        return 2
    except PlatformNotSupported as e:
        print(f"🪟 [{name}] {e}")
        return 3
    finally:
        stage.close()

    for o in outs:
        print(o.model_dump_json())
    print(f"✅ [{name}/{a.impl}] {len(outs)}건 처리, 평균 {dt * 1000:.1f}ms, 출력 형식 OK", file=sys.stderr)
    if a.out:
        write_jsonl(a.out, outs)
    if a.check:
        exp = read_jsonl(FIXTURES / name / "expected.jsonl", iface.output_model)
        same = sum(o == e for o, e in zip(outs, exp, strict=False))
        print(f"🔎 expected 일치: {same}/{len(exp)}", file=sys.stderr)
    return 0
