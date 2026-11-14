"""웹 채팅(ChatGPT/Gemini/Claude 사이트)용 컨텍스트 묶음 파일 만들기.

  uv run python scripts/pack_context.py parse   →  context_parse.md 생성
그 파일을 AI 채팅에 첨부하고 "이 맥락을 기준으로 작업해 줘"라고 시작하세요.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # Windows 콘솔에서 한글·이모지 출력 깨짐 방지
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
COMMON = [
    "AGENTS.md",
    "docs/SPEC.md",
    "docs/ARCHITECTURE.md",
    "docs/MODULES.md",
    "docs/CONTRACTS.md",
    "src/clean_chat/core/schemas.py",
    "src/clean_chat/core/modules.py",
]
MODULES = ("ocr", "parse", "analyze", "rewrite", "report")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in MODULES:
        sys.exit(f"사용법: pack_context.py <{' | '.join(MODULES)}>")
    mod = sys.argv[1]
    mod_dir = ROOT / "src" / "clean_chat" / "modules" / mod
    files = [ROOT / p for p in COMMON] + sorted(p for p in mod_dir.rglob("*") if p.suffix in {".py", ".md"})
    files += sorted((ROOT / "fixtures" / mod).glob("*.jsonl"))
    parts = [
        f"# 컨텍스트 묶음: {mod} 모듈\n\n나는 `{mod}` 모듈 담당이다. "
        f"`src/clean_chat/modules/{mod}/` 밖은 수정하지 않는다. 할 일은 impl.py 의 run() 함수 하나다.\n"
    ]
    for f in files:
        lang = {".py": "python", ".md": "markdown", ".jsonl": "json"}.get(f.suffix, "")
        parts.append(f"\n## {f.relative_to(ROOT)}\n```{lang}\n{f.read_text(encoding='utf-8')}\n```\n")
    out = ROOT / f"context_{mod}.md"
    out.write_text("".join(parts), encoding="utf-8")
    print(f"✅ {out.name} 생성 ({len(files)}개 파일). AI 채팅에 첨부하세요. (git에는 올리지 않음)")


if __name__ == "__main__":
    main()
