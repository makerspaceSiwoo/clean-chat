# ③ analyze — 분석 — 대상·등급·피드백

명세: `docs/MODULES.md`의 `analyze` 절 · 계약: `docs/CONTRACTS.md` · 예시: `fixtures/analyze/`

**할 일은 `impl.py` 의 `run(AnalyzeRequest) -> Analysis` 함수 하나입니다.** docstring 의 예시·순서·주의를 따라 본문을 채우세요.

| 파일 | 내용 | 수정 |
|---|---|---|
| `impl.py` | `run()` + 제안용 도우미 함수 (`_`로 시작, 바꿔도 됨) | ✅ |
| 그 밖의 파일 | 이 폴더 안에 자유롭게 추가 (사전, 프롬프트, 내부 모듈) | ✅ |
| `fixtures/analyze/input.jsonl` | 입력 예시 추가 | ✅ |
| `fixtures/analyze/expected.jsonl` | 기대값 (명세) | 리드 승인 |
| `tests/test_analyze.py` | 내 테스트 추가 | ✅ |

- **구현 방식: 로컬 소형 분류 모델 + 규칙** (LLM·외부 API 아님). 모든 채팅에 실행되므로 CPU 1문장 0.2초 이내가 목표입니다. 가중치는 `models/`(git 제외), 무거운 로딩은 `functools.cache` 로 한 번만.
- AI 모듈: 출력 형식만 자동 검사하고, 정확도는 `training/` 평가와 `data/eval/` 로 봅니다.
- **대상(target)은 닉네임입니다 (ADR-0020).** 채팅은 `닉네임 (챔피언)` 뿐이라 "정글"이 누구인지는 챔피언의 주 라인과 앞 대화로 추정합니다. 한 명으로 못 좁히면 포지션 단어를 그대로 둡니다.
- 숨김·신고 같은 처리는 하지 않습니다. 정책표(`core/policy.py`)가 이 결과를 보고 정합니다. 라벨 기준: `docs/LABELING_GUIDE.md`.
- 브랜치는 `analyze/<작업 내용>` 으로 만듭니다(예: `analyze/first-try`). PR 에서 위 표의 범위 밖 파일을 바꾸면 CI `module-scope` 가 실패합니다(CONTRIBUTING.md).
- 다른 모듈 폴더는 import 하지 않습니다. 함수 이름 `run` 과 입출력 타입은 바꾸지 않습니다(바꿔야 하면 "계약 변경 요청" 이슈).

## 폴더 구성 — 용도 2개

| 용도 | 언제 | 파일 | 하는 일 |
|---|---|---|---|
| **실시간 필터** | 게임 중, 메시지마다 (CPU 0.2초) | `impl.py` `run()` | 가릴 욕설 조각, 등급, 대상(닉네임), 피드백 조각 → 정책표·rewrite 로 |
| **대화 판단** | 게임 종료 후, 전체 대화에 1번 | `judge.py` `judge()` · `judge_session()` | 화자별로 누가 누구에게(특히 나에게) 무엇을 했는지, 신고 권고, 고소 후보 |
| └ 판례 대조 | 대화 판단의 마지막 단계 | `precedents.py` `review()` | 고소 후보에 죄목별 요건 점검표(충족/불명/미충족) + 비슷한 판례 |

- 신고·고소처럼 무거운 결정은 한 문장이 아니라 **대화 흐름**(반복, "ㅇㅈ" 같은 동조, 여러 명의 몰이)으로 판단합니다.
- 내부 파일: `lexicon.py`(사전), `champions.py`(챔피언 → 주 라인), `model.py`(파인튜닝 모델 연결), `train.py`(학습), `evaluate.py`(평가).

### 파인튜닝 모델 넣기
`models/analyze-classifier/`(git 제외)에 모델이 있으면 `run()` 이 자동으로 씁니다. 없으면 규칙만으로 돕니다.
```bash
uv sync --extra analyze
uv run python -m clean_chat.modules.analyze.train --data <라벨 CSV> --base beomi/KcELECTRA-base --version kcelectra-base-ft-0.1
uv run python -m clean_chat.modules.analyze.evaluate <라벨 CSV> --split test     # 브랜치·모델끼리 같은 명령으로 비교
```
- 모델은 유형 5개의 점수만 냅니다. 규칙 점수와 유형별로 큰 값을 쓰고, 등급·대상·조각은 규칙이 정합니다.
- 라벨 CSV 열: `text`, `text_norm`, `hints`, `level`, `harm_types`, `profanity_spans`, `split`(`train`/`test`). `test` 행은 학습에 쓰지 않습니다.
- `Analysis.model_version` 은 `rule-0.2+<모델 버전>` 으로 남습니다.

### 판례 준비 (오프라인, 한 번)
```bash
LAW_OC=<open.law.go.kr 에서 받은 값> uv run python -m clean_chat.modules.analyze.precedents fetch --query 모욕 --limit 50
```
- `data/raw/precedents.jsonl`(git 제외)에 저장됩니다. 파일이 없으면 요건 점검표만 나옵니다. 레포에 판례 본문을 넣지 않습니다.
- 수집 명령은 실제 OC 값으로 실행해 확인하지 못했습니다. 응답 필드 이름을 API 안내와 맞춰 보세요.
- **법률 자문이 아닙니다.** 요건 점검은 자동 추정이고, 점검 항목(`precedents.py` 의 `_insult`, `_obscenity`)은 전문가 검토가 필요합니다.

### 다음 단계 (계약 변경 필요 → 리드, ADR)
- 대화 판단은 아직 앱 흐름에 연결되지 않았습니다. 지금은 정책표가 실시간으로 신고·고소 후보를 표시합니다. 연결하려면 모듈 추가(`core/modules.py`·`core/schemas.py`), 게임 종료 배치가 `judge` 를 부르고 그 결과를 report 로 넘기는 변경이 필요합니다.
- 화면 표시 방침(정책표): 피드백이 없는 욕설은 문장 전체 숨김, 피드백이 있으면 욕설 조각을 가린 문장을 rewrite 에 넘겨 자연스럽게 다듬기.
- 지금 세션 기록(`GameSession.incidents`)에는 다른 유저 채팅만 들어가고 내 채팅(흐름 B)은 없습니다. 내 말에 대한 반응까지 보려면 대화 판단에 넘길 "전체 대화"를 저장하는 방법도 함께 정해야 합니다.

```bash
uv run sim analyze                         # 브라우저: 입력 | 디버깅 콘솔(print·logging·오류) | 반환값
uv run pytest tests/test_analyze.py        # 자동 테스트 (구현 전이면 skip)
uv run python scripts/pack_context.py analyze   # 웹 AI 채팅에 첨부할 맥락 묶음
```
모듈 코드를 고친 뒤 시뮬레이터에서 [실행]만 다시 누르면 됩니다(서버를 다시 켤 필요 없음).
