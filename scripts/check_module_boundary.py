"""모듈 범위 검사 (CI: module-scope).  사용: python scripts/check_module_boundary.py <브랜치> <바뀐파일1> <바뀐파일2> ...

- `<모듈>/<작업 내용>` 브랜치(예: parse/colon-fix)만 검사합니다. 그 밖의 브랜치는 통과.
- 모듈 범위(src/clean_chat/modules/<모듈>/, tests/test_<모듈>.py, fixtures/<모듈>/) 밖 파일을 바꾸면 실패합니다.
  실패해도 병합이 막히지는 않습니다. 리드가 리뷰할 때 "모듈 범위를 넘는 변경"으로 보고 판단합니다.
"""

import sys

from repo_rules import MODULES, module_of, module_scope, out_of_scope

branch, files = sys.argv[1], sys.argv[2:]
module = module_of(branch)
if module is None:
    print(f"✅ 모듈 브랜치가 아님 ({branch}) → 검사 생략. 모듈 작업은 <모듈>/<작업 내용> 으로: {', '.join(MODULES)}")
    sys.exit(0)
bad = out_of_scope(module, files)
if bad:
    print(f"❌ [{module}] 모듈 범위 밖 파일을 수정했습니다 ({len(bad)}개):")
    for f in bad:
        print(f"   - {f}")
    print(f"   모듈 범위: {', '.join(module_scope(module))}")
    print("   → 되돌리거나, 꼭 필요한 변경이면 PR 설명에 이유를 적어 주세요 (리드가 리뷰에서 판단).")
    sys.exit(1)
print(f"✅ [{module}] 모듈 범위 OK ({len(files)}개 파일)")
