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

# 모듈 5개 = 5명 (ADR-0017). 각자 src/clean_chat/modules/<모듈>/ 만 고친다
WORK_MODULES = ("ocr", "parse", "analyze", "rewrite", "report")
# 구성 (리드): 흐름 연결·정책표·게임 단계·UI·시뮬레이터
LEAD_AREAS = ("ui", "session", "simulator", "core")
MODULES = WORK_MODULES + LEAD_AREAS

# 브랜치 이름 규칙
BRANCH_RE = re.compile(
    rf"^(develop|mod/({'|'.join(MODULES)})(-[a-z0-9]+(-[a-z0-9]+)*)?|(fix|docs|chore|data)/[a-z0-9]+(-[a-z0-9]+)*)$"
)

# PR 제목 규칙 (squash 병합 시 이 제목이 커밋 메시지가 됨)
PR_TITLE_RE = re.compile(rf"^(feat|fix|docs|chore|refactor|test|data)\(({'|'.join(MODULES)}|repo|develop)\): .{{3,}}$")

# 모듈 브랜치가 수정해도 되는 경로 (앞부분 일치)
SHARED_OK = ("data/labeled/", "data/lexicon/", "data/demo/", "docs/modules/", "uv.lock")
MODULE_PATHS: dict[str, tuple[str, ...]] = {
    m: (f"src/clean_chat/modules/{m}/", f"tests/test_{m}.py", f"fixtures/{m}/") for m in WORK_MODULES
}
MODULE_PATHS["analyze"] += ("training/",)
MODULE_PATHS["ui"] = ("src/clean_chat/ui/", "tests/test_ui_smoke.py")
MODULE_PATHS["session"] = ("src/clean_chat/session/", "tests/test_session.py")
# 웹 시뮬레이터는 자기 폴더만 (공통 계약·fixtures 는 core = 리드, ADR-0015)
MODULE_PATHS["simulator"] = ("simulator/",)
MODULE_PATHS["core"] = (
    "src/clean_chat/",
    "fixtures/",
    "contracts/",
    "scripts/",
    "tests/",
    "docs/",
    ".github/",
    "pyproject.toml",
)
