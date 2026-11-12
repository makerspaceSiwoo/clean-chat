"""브랜치 이름 검사.  사용: python scripts/check_branch_name.py <branch>"""

import sys

from repo_rules import BRANCH_RE

name = sys.argv[1] if len(sys.argv) > 1 else ""
if not BRANCH_RE.match(name):
    print(f"❌ 브랜치 이름 규칙 위반: {name!r}")
    print("   허용 예: mod/capture, mod/classify-finetune, fix/ocr-dedupe, docs/spec-update, data/label-batch1")
    sys.exit(1)
print(f"✅ 브랜치 이름 OK: {name}")
