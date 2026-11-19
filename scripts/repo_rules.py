"""모듈 범위 규칙의 단일 기준 (ADR-0018). CONTRIBUTING.md 와 CI(module-scope)가 이 파일을 기준으로 합니다. 수정은 리드만.

브랜치 이름이 `<모듈>/<작업 내용>` 이면(예: parse/colon-fix) 그 PR 은 아래 모듈 범위 안의 파일만 바꿔야 합니다.
범위 밖 파일을 바꾸면 CI 가 실패하고, 리드는 리뷰할 때 "모듈 범위를 넘는 변경"으로 보고 판단합니다.
그 밖의 브랜치 이름은 자유이고 검사하지 않습니다. main 보호는 GitHub 규칙(protect-main)이 맡습니다.
"""

from __future__ import annotations

import sys

# 검사 스크립트는 이 파일을 import 한다. Windows 콘솔(cp949)에서도 한글·이모지 출력이 깨지지 않게 UTF-8로 맞춘다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# 모듈 5개 = 5명 (ADR-0017). 브랜치 이름의 첫 부분이 이 중 하나면 모듈 브랜치
MODULES = ("ocr", "parse", "analyze", "rewrite", "report")


def module_scope(module: str) -> tuple[str, ...]:
    """모듈 담당자가 바꿔도 되는 경로 (앞부분 일치): 모듈 폴더 + 내 테스트 + 내 예시."""
    return (f"src/clean_chat/modules/{module}/", f"tests/test_{module}.py", f"fixtures/{module}/")


def module_of(branch: str) -> str | None:
    """브랜치 이름 → 모듈 이름. `parse/colon-fix` → "parse", 모듈 브랜치가 아니면 None."""
    head, sep, rest = branch.partition("/")
    return head if sep and rest and head in MODULES else None


def out_of_scope(module: str, files: list[str]) -> list[str]:
    """모듈 범위 밖에서 바뀐 파일 목록."""
    allowed = module_scope(module)
    return [f for f in files if not f.startswith(allowed)]
