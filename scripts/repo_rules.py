"""레포 규칙의 단일 기준 (브랜치 이름, PR 제목, 모듈별 수정 가능 경로).

CONTRIBUTING.md 와 CI가 모두 이 파일을 기준으로 합니다. 수정은 리드만.
"""

from __future__ import annotations

import re
import sys

# 검사 스크립트는 모두 이 파일을 import 한다. Windows 콘솔(cp949)에서도 한글·이모지 출력이 깨지지 않게 UTF-8로 맞춘다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

MODULES = ("capture", "parse", "normalize", "classify", "rewrite", "policy", "report", "ui", "core")

# 브랜치 이름 규칙
BRANCH_RE = re.compile(
    rf"^(develop|mod/({'|'.join(MODULES)})(-[a-z0-9]+(-[a-z0-9]+)*)?|(fix|docs|chore|data)/[a-z0-9]+(-[a-z0-9]+)*)$"
)

# PR 제목 규칙 (squash 병합 시 이 제목이 커밋 메시지가 됨)
PR_TITLE_RE = re.compile(rf"^(feat|fix|docs|chore|refactor|test|data)\(({'|'.join(MODULES)}|repo|develop)\): .{{3,}}$")

# 모듈 브랜치가 수정해도 되는 경로 (앞부분 일치)
SHARED_OK = ("data/labeled/", "data/lexicon/", "data/demo/", "docs/modules/", "uv.lock")
# 모듈 → 담당 fixtures 폴더 (Stage 이름 기준)
STAGES_OF = {
    "capture": ("ocr",),
    "parse": ("parse", "compose"),
    "policy": ("incoming_policy", "outgoing_policy"),
    "report": ("report", "complaint"),
}
MODULE_PATHS: dict[str, tuple[str, ...]] = {
    m: (f"src/clean_chat/{m}/", f"tests/{m}/", f"tests/test_{m}.py")
    + tuple(f"fixtures/{st}/" for st in STAGES_OF.get(m, (m,)))
    for m in MODULES
}
MODULE_PATHS["classify"] += ("training/",)
MODULE_PATHS["core"] += (
    "src/clean_chat/__main__.py",
    "fixtures/",
    "scripts/",
    "tests/",
    "docs/",
    ".github/",
    "pyproject.toml",
)
