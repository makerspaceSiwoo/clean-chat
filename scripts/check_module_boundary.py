"""모듈 브랜치가 자기 폴더 밖을 수정했는지 검사 (바이브 코딩 사고 방지).

사용: python scripts/check_module_boundary.py <branch> <변경파일1> <변경파일2> ...
- mod/<모듈>[-주제] 브랜치만 검사. 그 외 브랜치(fix/, docs/ 등)는 통과.
- PR에 'cross-module' 라벨이 있으면 CI에서 이 검사를 건너뜀 (리드 승인 필요).
"""

import sys

from repo_rules import MODULE_PATHS, SHARED_OK

branch, files = sys.argv[1], sys.argv[2:]
if not branch.startswith("mod/"):
    print(f"✅ 모듈 브랜치 아님 ({branch}) → 검사 생략")
    sys.exit(0)
module = branch.removeprefix("mod/").split("-")[0]
allowed = MODULE_PATHS[module] + SHARED_OK
bad = [f for f in files if not f.startswith(allowed)]
if bad:
    print(f"❌ [{module}] 모듈 브랜치에서 담당 폴더 밖 파일을 수정했습니다:")
    for f in bad:
        print(f"   - {f}")
    print("   → 되돌리거나, 꼭 필요하면 리드에게 'cross-module' 라벨을 요청하세요.")
    print("   → core/schemas.py 변경이 필요하면 이슈를 먼저 올려 주세요.")
    sys.exit(1)
print(f"✅ [{module}] 모듈 경계 OK ({len(files)}개 파일)")
