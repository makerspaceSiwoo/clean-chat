# 협업 규칙 (브랜치 · PR · 병합)

> 규칙은 두 가지뿐입니다(ADR-0018).
> 1. **`main` 보호**: GitHub 규칙 `protect-main` (PR 필수, 다른 팀원 승인 1명, force push·삭제 금지)
> 2. **모듈 범위 검사**: 모듈 작업 브랜치는 `<모듈>/<작업 내용>`, PR 에서 모듈 범위 밖 파일을 바꾸면 CI(`module-scope`) 실패
>
> 규칙의 원본은 `scripts/repo_rules.py`이며, 수정은 리드만 합니다.

## 1. 브랜치
```
main      ← 발표용. 항상 데모가 돌아가는 상태 (보호됨)
develop   ← 통합 브랜치. 작업 PR 은 보통 여기로 (직접 push 도 가능)
  ├ parse/colon-fix        ← 모듈 작업: <모듈>/<작업 내용>
  ├ analyze/kcelectra
  └ (그 밖의 이름은 자유)   ← 리드·문서·설정 작업 등, 검사하지 않음
```

### 모듈 작업 브랜치: `<모듈>/<작업 내용>`
| 모듈 | 예 | 바꿔도 되는 파일 (모듈 범위) |
|---|---|---|
| `ocr` | `ocr/two-line-merge` | `src/clean_chat/modules/ocr/`, `tests/test_ocr.py`, `fixtures/ocr/` |
| `parse` | `parse/colon-fix` | `src/clean_chat/modules/parse/`, `tests/test_parse.py`, `fixtures/parse/` |
| `analyze` | `analyze/target-guess` | `src/clean_chat/modules/analyze/`, `tests/test_analyze.py`, `fixtures/analyze/` |
| `rewrite` | `rewrite/prompt-v2` | `src/clean_chat/modules/rewrite/`, `tests/test_rewrite.py`, `fixtures/rewrite/` |
| `report` | `report/complaint-pdf` | `src/clean_chat/modules/report/`, `tests/test_report.py`, `fixtures/report/` |

- 브랜치 이름의 앞부분(`/` 앞)이 모듈 이름이면 PR 에서 **모듈 범위 검사**를 합니다. 범위 밖 파일(예: `core/schemas.py`, 다른 모듈 폴더, `uv.lock`)을 바꾸면 CI 가 빨간색이 됩니다.
- 빨간색이어도 병합 버튼은 막히지 않습니다. 리드가 리뷰할 때 **모듈 범위를 넘는 변경**으로 보고 거절하거나 참고합니다. 꼭 필요한 변경이면 PR 설명에 이유를 적으세요.
- 계약(`core/schemas.py`)이나 패키지 추가가 필요하면 먼저 "계약 변경 요청" 이슈를 올립니다.

## 2. PR 과 병합
| 대상 | 조건 |
|---|---|
| `→ develop` | PR 권장. CI(린트, 포맷, 테스트, 모듈 범위)를 보고 리드가 **squash 병합** |
| `→ main` | **PR 필수 + 작성자가 아닌 팀원 승인 1명** (GitHub 규칙 `protect-main`). 보통 리드가 develop 을 통합해 올림 |
| 직접 push | `main` **금지**(GitHub 가 막음, 레포 주인만 긴급 우회). `develop` 은 가능하지만 확인 명령을 먼저 실행 |

- PR 제목·커밋 메시지 형식은 자유입니다. 무엇을 했는지 한 줄로 알 수 있게 쓰세요(squash 병합이라 PR 제목이 커밋 메시지가 됨).
- PR 은 작게 자주 올리세요. 평일에도 `develop` 으로 병합해도 됩니다(ADR-0010).
- CI 실패는 병합을 자동으로 막지 않습니다(필수 검사로 걸지 않음). 빨간 PR 은 고친 뒤 병합합니다.

## 3. 하루 작업 흐름 (모듈 담당자)
```bash
git switch develop && git pull                 # 최신 develop
git switch -c parse/colon-fix                  # <내 모듈>/<작업 내용>
# ... AI와 작업 (src/clean_chat/modules/parse/ 안에서만) ...
uv run ruff check . --fix && uv run ruff format .
uv run pytest -q
uv run clean-chat module parse --check
git add -A && git commit -m "콜론 오인식 처리"
git push -u origin parse/colon-fix
# GitHub 에서 PR 만들기 (base: develop) → CI 의 module-scope 가 초록인지 확인
```

## 4. 주말 통합 체크리스트 (리드)
1. 모듈 PR 이 `develop` 에 병합되었는지, `module-scope` 실패 PR 은 범위를 넘는 이유가 타당했는지 확인
2. `uv run pytest -q` + 구현된 모듈마다 `uv run clean-chat module <모듈> --check` (5개가 다 구현되면 `uv run clean-chat run --source demo`)
3. Windows PC 에서 실제 게임(또는 녹화) 실행 확인
4. `develop → main` PR 생성, 결과 영상을 PR 에 첨부
5. 다음 주 할 일을 각 모듈 이슈로 정리
