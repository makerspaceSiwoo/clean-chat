# GitHub 레포 설정 (리드가 한 번만)

> 레포: `makerspaceSiwoo/clean-chat` (공개). 공개 레포라서 무료 요금제로 브랜치 규칙(Rulesets)을 쓸 수 있습니다.
> 원칙: **규칙은 단순하게.** `develop`은 자유롭게 push, `main`만 보호합니다.

## 1. 브랜치 (적용됨)
| 브랜치 | 용도 | 규칙 |
|---|---|---|
| `main` | 발표용, 항상 데모가 도는 상태 | 규칙 `protect-main` (아래) |
| `develop` | 통합 브랜치 | 규칙 없음. 직접 push와 PR 모두 가능 |
| `<모듈>/<작업 내용>` | 모듈 작업 브랜치 (예: `parse/colon-fix`) | 규칙 없음. PR 에서 `module-scope` CI 가 모듈 범위 밖 수정을 표시 |
| 그 밖 | 리드·문서·설정 작업 | 규칙 없음, 이름 자유 |

처음 올릴 때 쓴 명령(기록용):
```bash
git init -b main
git add -A && git commit -m "chore(repo): 스타터 초기화"
gh repo create makerspaceSiwoo/clean-chat --public --source . --remote origin --push
git switch -c develop && git push -u origin develop
```

## 2. 규칙 `protect-main` (적용됨)
Settings → Rules → Rulesets → `protect-main`
- Target: `main` 하나
- ✅ Restrict deletions, ✅ Block force pushes
- ✅ Require a pull request before merging → Required approvals **1** (PR 작성자 본인 승인은 인정되지 않음)
- Status check 필수 아님: CI가 빨간색이어도 병합 버튼은 막히지 않습니다. 병합 전에 눈으로 확인합니다.
- Bypass list: **Repository admin**(레포 주인) — 긴급 시 승인 없이 병합 가능

## 3. 쓰지 않기로 한 것
초기 스타터 문서에 있던 아래 규칙은 **쓰지 않습니다**(팀 규모에 비해 복잡함).
- `develop` 보호 규칙(PR 필수, CODEOWNERS 승인)
- 작업 브랜치 force push 차단 규칙
- 필수 status check
- 브랜치 이름·PR 제목 형식 검사, "main 에는 develop 에서만" 검사 (ADR-0018 에서 없앰)

`.github/CODEOWNERS`는 리뷰 요청을 자동으로 보내는 용도로만 씁니다(승인 필수 아님).
`@LEAD`, `@M1_OCR` ~ `@M5_REPORT` 자리표시자를 `docs/MODULES.md`의 배정대로 실제 GitHub 아이디로 바꿉니다.

## 4. 선택 설정 (아직 안 함)
필요하면 Settings에서 직접 바꿉니다.
- Settings → General → Default branch: `develop` (새 PR이 자동으로 develop을 향함)
- Pull Requests: squash merging만 허용, "Default to pull request title"
- Issues → Labels: `contract`, `task`
- Settings → Collaborators → 팀원 초대(Write 권한)

## 5. 확인
- `main`에 직접 push → 거부되면 정상
- `parse/test` 브랜치에서 `src/clean_chat/modules/parse/` 만 수정한 PR → `module-scope` 초록이면 정상
- `parse/test` 브랜치에서 `core/schemas.py` 수정 PR → `module-scope` 실패 표시가 뜨면 정상
- `chore/test` 처럼 모듈 이름이 아닌 브랜치 → 검사 생략(초록)
