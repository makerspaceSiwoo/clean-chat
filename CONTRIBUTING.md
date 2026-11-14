# 협업 규칙 (브랜치 · 커밋 · PR · 병합)

> 이름·포맷 규칙은 **CI가 검사**하고, `main` 보호는 **GitHub 규칙**이 막습니다(ADR-0009).
> 규칙의 원본은 `scripts/repo_rules.py`이며, 수정은 리드만 합니다.

## 1. 브랜치 구조

```
main       ← 발표용. 항상 데모가 돌아가는 상태. develop → main PR만 (다른 팀원 승인 1명)
 └ develop ← 통합 브랜치. 작업 PR은 여기로 (직접 push도 가능)
    ├ mod/capture            ← 모듈별 장기 브랜치 (담당자)
    ├ mod/classify-finetune  ← 모듈 안의 세부 주제 브랜치
    ├ fix/ocr-dedupe
    ├ docs/spec-update
    └ data/label-batch1      ← 라벨 데이터 추가
```

### 브랜치 이름 규칙
| 형식 | 용도 | 예 |
|---|---|---|
| `mod/<모듈>` | 모듈 작업 (장기) | `mod/capture` |
| `mod/<모듈>-<주제>` | 모듈 안 세부 작업 | `mod/ui-overlay-calibrate` |
| `fix/<주제>` | 버그 수정 | `fix/parse-colon` |
| `docs/<주제>` | 문서 | `docs/labeling-guide` |
| `data/<주제>` | 데이터 추가 | `data/label-batch2` |
| `chore/<주제>` | 설정 등 잡일 | `chore/ci-cache` |

- 모듈 이름: `capture text classify rewrite policy report session ui simulator core` (`text` = parse·compose·normalize, `simulator` = 웹 시뮬레이터, `simulator/` 폴더만)
- 영어 소문자, 숫자, `-`만 사용합니다.

## 2. 커밋과 PR 제목
- 형식: `<종류>(<모듈>): <설명>`
  - 예: `feat(capture): 채팅 줄 중복 제거`, `fix(text): 콜론 오인식 처리`, `data(classify): 라벨 100건 추가`
- `<모듈>`에는 위 모듈 이름 외에 `repo`(레포 전체 설정·문서), `develop`(develop → main 반영)도 쓸 수 있습니다.
- 종류: `feat`(기능) `fix`(버그) `docs`(문서) `chore`(설정) `refactor`(구조 개선) `test`(테스트) `data`(데이터)
- **squash 병합**을 쓰므로 PR 제목이 곧 최종 커밋 메시지가 됩니다. 중간 커밋 메시지는 자유입니다.

## 3. PR과 병합 규칙
| 대상 | 조건 |
|---|---|
| `→ develop` | PR 권장. CI(린트, 포맷, 테스트, 브랜치 이름, PR 제목, 모듈 경계)가 초록인지 보고 **squash 병합**. 승인은 필수 아님 |
| `→ main` | `develop`에서만(`pr-rules`가 검사). 리드가 주말 통합 후 진행. **PR 필수 + 작성자가 아닌 팀원 승인 1명**(GitHub 규칙 `protect-main`) |
| 직접 푸시 | `main` **금지**(GitHub가 막음, 레포 주인만 긴급 우회 가능). `develop`은 가능하지만 CI가 깨지지 않게 확인 명령을 먼저 실행 |

- PR은 작게 자주 올리세요. **평일에도 `develop`으로 병합해도 됩니다**(ADR-0010). 주말에 몰아서 합치면 충돌이 커집니다.
- CI 실패는 병합을 자동으로 막지 않습니다(필수 검사로 걸지 않음). 빨간 PR은 고친 뒤 병합합니다.
- 다른 모듈 폴더를 꼭 고쳐야 하면, 리드에게 `cross-module` 라벨을 받으세요(모듈 경계 검사 생략).

## 4. 하루 작업 흐름 (바이브 코더용)
```bash
git switch mod/<내모듈>            # 내 브랜치로 이동
git pull origin develop           # 최신 develop 받기 (충돌 예방)
# ... AI와 작업 ...
uv run ruff check . --fix && uv run ruff format .
uv run pytest -q
git add -A && git commit -m "wip: 작업 내용"
git push
# GitHub에서 PR 만들기 (base: develop), 제목 형식 지키기
```

## 5. 주말 통합 체크리스트 (리드)
1. 모든 모듈 PR이 `develop`에 병합되었는지 확인
2. `uv run pytest -q` + `uv run clean-chat run --real <구현된 Stage들>` 실행 (Stage 이름, 쉼표 구분. 예: `parse,normalize`)
3. Windows PC에서 실제 게임(또는 녹화) 실행 확인
4. `develop → main` PR 생성, 결과 영상을 PR에 첨부
5. 다음 주 할 일을 각 모듈 이슈로 정리
