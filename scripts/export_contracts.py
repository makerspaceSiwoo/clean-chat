"""공통 계약 내보내기: core/schemas.py(pydantic) → contracts/modules.schema.json (JSON Schema).

데스크톱 앱(Python)과 웹앱(simulator/, TypeScript)이 같은 계약을 쓰기 위한 단일 출처입니다.
웹앱은 이 파일에서 TS 타입과 모듈 목록을 자동으로 만듭니다(simulator/scripts/sync-shared.mjs).

  uv run python scripts/export_contracts.py           # 다시 만들기 (schemas.py 를 바꾼 뒤 꼭 실행)
  uv run python scripts/export_contracts.py --check   # 최신인지 확인만 (CI·pytest 가 사용)
"""

from __future__ import annotations

import argparse
import json
import sys

from pydantic.json_schema import models_json_schema

from clean_chat.core.config import ROOT
from clean_chat.core.modules import MODULES
from clean_chat.core.schemas import SCHEMA_VERSION

OUT = ROOT / "contracts" / "modules.schema.json"


def build() -> str:
    """모듈별 입력·출력 모델을 하나의 JSON Schema 문서로 (모델 정의는 $defs 에 한 번씩만)."""
    models = []
    for spec in MODULES.values():
        models += [(spec.input_model, "validation"), (spec.output_model, "validation")]
    refs, schema = models_json_schema(models, ref_template="#/$defs/{model}")
    ref_of = {model: ref["$ref"] for (model, _mode), ref in refs.items()}
    doc = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Clean Chat module contracts",
        "description": "자동 생성 파일 — 직접 고치지 말고 scripts/export_contracts.py 로 다시 만드세요.",
        "schema_version": SCHEMA_VERSION,
        "modules": {
            name: {
                "title": spec.title,
                "path": spec.path,
                "input": {"$ref": ref_of[spec.input_model]},
                "output": {"$ref": ref_of[spec.output_model]},
            }
            for name, spec in MODULES.items()
        },
        "$defs": schema["$defs"],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows 콘솔에서 한글 출력
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="파일이 최신인지 확인만 (다르면 종료 코드 1)")
    a = ap.parse_args(argv)
    text = build()
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else None
    if a.check:
        if current != text:
            print(f"❌ {OUT.relative_to(ROOT)} 가 schemas.py 와 다릅니다 → uv run python scripts/export_contracts.py")
            return 1
        print(f"✅ {OUT.relative_to(ROOT)} 최신 (schema {SCHEMA_VERSION})")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"✅ {OUT.relative_to(ROOT)} 생성 (모듈 {len(MODULES)}개, schema {SCHEMA_VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
