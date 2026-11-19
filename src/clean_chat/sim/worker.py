"""모듈 1번 실행 (시뮬레이터가 실행마다 새 프로세스로 띄움). 사람이 직접 쓸 일은 없다.

  python -u -m clean_chat.sim.worker <모듈> <입력.json> <결과.json>

- stdout·stderr 는 전부 화면의 디버깅 콘솔로 간다 (print, logging, 경고, traceback).
- 결과는 <결과.json> 파일에 {status, output, error, durationMs} 로 쓴다 → stdout 은 콘솔 전용.
- status: ok | not_implemented | invalid_input | error
- 테스트용: 환경 변수 CLEAN_CHAT_SIM_TARGET="패키지.모듈:함수" 면 실제 모듈 대신 그 함수를 부른다.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from importlib import import_module
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from clean_chat.core import modules
from clean_chat.core.platform import use_utf8_console


def _write(path: Path, status: str, started: float, output: Any = None, error: str | None = None) -> None:
    result = {
        "status": status,
        "output": output,
        "error": error,
        "durationMs": round((time.perf_counter() - started) * 1000),
    }
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _load(name: str):
    target = os.environ.get("CLEAN_CHAT_SIM_TARGET")
    if target:
        mod, fn = target.split(":")
        return getattr(import_module(mod), fn)
    return modules.load(name)


def _ms(t: float) -> str:
    return f"{(time.perf_counter() - t) * 1000:.0f}ms"


def main(argv: list[str]) -> int:
    use_utf8_console()
    name, inp, out = argv[0], Path(argv[1]), Path(argv[2])
    logging.basicConfig(
        level=logging.DEBUG, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True
    )
    spec = modules.MODULES[name]
    started = time.perf_counter()

    print(f"▶ [{name}] 입력 검증 ({spec.input_model.__name__})", flush=True)
    try:
        item = spec.input_model.model_validate(json.loads(inp.read_text(encoding="utf-8")))
    except ValidationError as e:
        print(f"✖ 입력이 계약과 다릅니다:\n{e}", file=sys.stderr, flush=True)
        _write(out, "invalid_input", started, error=f"입력이 계약({spec.input_model.__name__})과 다릅니다:\n{e}")
        return 0

    t = time.perf_counter()
    print(f"▶ 모듈 불러오기 ({spec.path})", flush=True)
    try:
        fn = _load(name)
    except Exception as e:  # 모듈 파일의 문법 오류, import 실패 등
        traceback.print_exc()
        _write(out, "error", started, error=f"모듈을 불러오지 못했습니다: {type(e).__name__}: {e}")
        return 0
    print(f"  불러옴 ({_ms(t)})", flush=True)

    t = time.perf_counter()
    print("▶ run() 실행", flush=True)
    try:
        result = modules.invoke(name, fn, item)
    except modules.ModuleNotImplemented as e:
        print(f"⏳ {e}", file=sys.stderr, flush=True)
        _write(out, "not_implemented", started, error=str(e))
        return 0
    except Exception as e:  # 모듈 안의 오류, 출력 형식 오류
        traceback.print_exc()
        _write(out, "error", started, error=f"{type(e).__name__}: {e}")
        return 0
    print(f"✔ run() 끝, 출력 형식 OK ({spec.output_model.__name__}, {_ms(t)})", flush=True)
    _write(out, "ok", started, output=result.model_dump(mode="json"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
