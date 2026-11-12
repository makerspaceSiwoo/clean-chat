"""PR 제목 검사.  사용: python scripts/check_pr_title.py "<title>" """

import sys

from repo_rules import PR_TITLE_RE

title = sys.argv[1] if len(sys.argv) > 1 else ""
if not PR_TITLE_RE.match(title):
    print(f"❌ PR 제목 규칙 위반: {title!r}")
    print("   형식: <종류>(<모듈>): <설명>   예) feat(capture): 채팅 줄 중복 제거 추가")
    print("   종류: feat fix docs chore refactor test data")
    sys.exit(1)
print("✅ PR 제목 OK")
