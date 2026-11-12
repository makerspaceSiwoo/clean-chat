# GitHub 레포 설정 (리드가 한 번만)

> CI 파일은 레포에 들어 있지만, **"병합을 막는" 설정은 GitHub 웹에서 직접** 해야 합니다.
> 비공개 레포에서 Rulesets와 브랜치 보호를 쓰려면 **GitHub Team 이상** 요금제가 필요할 수 있습니다. 무료로 하려면 레포를 **공개(public)** 로 하거나, 규칙을 CI 실패 표시로만 운영합니다(아래 질문 참고).

## 1. 레포 만들기
1. GitHub → New repository → 이름 `lol-guard`
2. 이 스타터를 올립니다:
```bash
cd lol-guard
git init -b main
git add -A && git commit -m "chore(repo): 스타터 초기화"
git remote add origin https://github.com/<팀>/lol-guard.git
git push -u origin main
git switch -c dev && git push -u origin dev
```
3. Settings → General
   - Default branch: **dev** (PR이 자동으로 dev를 향하게)
   - Pull Requests: **Allow squash merging만 체크**, "Default to pull request title" 선택
   - **Automatically delete head branches**: 끄기 (모듈 브랜치는 오래 쓰기 때문)
4. Settings → Collaborators → 팀원 초대 (Write 권한)

## 2. 라벨 만들기
Issues → Labels → `cross-module`(빨강), `contract`(보라), `task`(파랑)

## 3. Rulesets (Settings → Rules → Rulesets → New branch ruleset)

### 규칙 A: `protect-dev`
- Target: `dev`
- ✅ Restrict deletions
- ✅ Require a pull request before merging → Required approvals **1**, ✅ Require review from Code Owners, ✅ Dismiss stale approvals
- ✅ Require status checks to pass → `check`(ci), `rules`(pr-rules) 추가, ✅ Require branches to be up to date
- ✅ Block force pushes
- Bypass list: 리드 (긴급 시)

### 규칙 B: `protect-main`
- Target: `main`
- 위 A와 같음 + Bypass list 비우기
- (dev에서만 병합 가능한지는 `pr-rules` CI가 검사)

### 규칙 C: `module-branches`
- Target: `mod/**`
- ✅ Block force pushes (실수로 남의 작업을 지우지 않게)

## 4. CODEOWNERS 아이디 바꾸기
`.github/CODEOWNERS`의 `@LEAD`, `@DEV_B`, `@VIBE_C`, `@VIBE_D`, `@VIBE_E`를 실제 GitHub 아이디로 바꿉니다.

## 5. 확인
- 아무 팀원이 `feature/test` 브랜치로 PR → `pr-rules` 실패하면 정상
- `mod/ui` 브랜치에서 `core/schemas.py` 수정 PR → `모듈 경계` 실패하면 정상
