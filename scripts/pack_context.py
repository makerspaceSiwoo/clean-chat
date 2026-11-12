"""웹 채팅(ChatGPT/Gemini/Claude 사이트)용 컨텍스트 묶음 파일 만들기.

  uv run python scripts/pack_context.py capture   →  context_capture.md 생성
그 파일을 AI 채팅에 첨부하고 "이 맥락을 기준으로 작업해 줘"라고 시작하세요.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMON = [
    "AGENTS.md",
    "docs/SPEC.md",
    "docs/ARCHITECTURE.md",
    "docs/MODULES.md",
    "docs/CONTRACTS.md",
    "src/lolguard/core/schemas.py",
    "src/lolguard/core/stage.py",
]
STAGES_OF = {"capture": ["ocr"], "report": ["report", "complaint"]}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("사용법: pack_context.py <모듈명>")
    mod = sys.argv[1]
    mod_dir = ROOT / "src" / "lolguard" / mod
    files = [ROOT / p for p in COMMON] + sorted(p for p in mod_dir.rglob("*") if p.suffix in {".py", ".md"})
    for st in STAGES_OF.get(mod, [mod]):
        files += sorted((ROOT / "fixtures" / st).glob("*.jsonl"))
    parts = [
        f"# 컨텍스트 묶음: {mod} 모듈\n\n나는 `{mod}` 모듈 담당이다. `src/lolguard/{mod}/` 밖은 수정하지 않는다.\n"
    ]
    for f in files:
        lang = {".py": "python", ".md": "markdown", ".jsonl": "json"}.get(f.suffix, "")
        parts.append(f"\n## {f.relative_to(ROOT)}\n```{lang}\n{f.read_text(encoding='utf-8')}\n```\n")
    out = ROOT / f"context_{mod}.md"
    out.write_text("".join(parts), encoding="utf-8")
    print(f"✅ {out.name} 생성 ({len(files)}개 파일). AI 채팅에 첨부하세요. (git에는 올리지 않음)")


if __name__ == "__main__":
    main()
