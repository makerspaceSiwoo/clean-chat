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
- 내부 파일: `lexicon.py`(사전), `champions.py`(챔피언 → 주 라인), `model.py`(파인튜닝 모델 연결), `train.py`(학습), `public_data.py`(공개 데이터 → 학습 CSV), `evaluate.py`(평가).

### 파인튜닝 모델 넣기
`models/analyze-classifier/`(git 제외)에 모델이 있으면 `run()` 이 자동으로 씁니다. 없으면 규칙만으로 돕니다.
```bash
uv sync --extra analyze
uv run python -m clean_chat.modules.analyze.train \
    --data fixtures/analyze/labeled_parsed.csv fixtures/analyze/train_aug.csv \
    --base beomi/KcELECTRA-base --version kcelectra-base-ft-0.1 --epochs 20 --patience 6 --lr 5e-5 --seed 1
uv run python -m clean_chat.modules.analyze.evaluate fixtures/analyze/labeled_parsed.csv --split test   # 브랜치·모델끼리 같은 명령으로 비교
CLEAN_CHAT_ANALYZE_MODEL=<다른 모델 폴더> uv run python -m clean_chat.modules.analyze.evaluate fixtures/analyze/labeled_parsed.csv --split test
```
- 모델은 유형 점수만 냅니다. 규칙 점수와 유형별로 큰 값을 쓰고(기준 0.5), 등급·대상·조각은 규칙이 정합니다.
- **욕설(profanity)은 모델 점수를 쓰지 않고 규칙만 씁니다**(`impl.py` `_RULE_ONLY`). 사전이 이미 정확하고, 모델만 걸린 욕설은 가릴 조각이 없으며, 정상 문장 오탐이 여기서 나왔기 때문입니다(아래 비교 참고).
- 라벨 CSV 열: `text`, `text_norm`, `hints`, `level`, `harm_types`, `profanity_spans`, `split`(`train`/`test`). `test` 행은 학습에 쓰지 않습니다.
- `train.py` 는 train 행의 15%를 검증용으로 떼어 가장 좋은 epoch 의 가중치를 저장하고(조기 종료), 드문 유형은 양성 가중치로 보정합니다. 결과는 `meta.json` 에 남습니다.
- `Analysis.model_version` 은 `rule-0.2+<모델 버전>` 으로 남습니다.

### 모델 비교와 추천 (2026-11-21, Apple M5 · MPS 학습 / CPU 추론)
**추천: `beomi/KcELECTRA-base` 를 우리 데이터로 바로 파인튜닝** (학습률 5e-5, 최대 20 epoch, 버전 `kcelectra-base-ft-0.1`).

시험 60문장(`labeled_parsed.csv` 의 `split=test`, 고정) · 규칙 + 모델 · 욕설은 규칙만 쓰는 현재 코드 기준. 범위는 시드(42·1·2)별 최솟값~최댓값입니다.

| 구성 | 학습 횟수 | 등급 일치율 | 악성(L2↑) 재현율 | 정상 오탐률 | blame F1 | family F1 | 조각 일치율 | CPU 중앙값 / p95 | 크기 |
|---|---|---|---|---|---|---|---|---|---|
| 규칙만 | - | 80.0% | 63.3% | 0.0% | 57.1 | 80.0 | 95.0% | 0.05 / 0.08ms | - |
| **KcELECTRA-base, 바로 학습** (lr 5e-5) | 3 | **95.0%** | **90.0%** | **0.0%** | 88.9~91.9 | 80.0~92.3 | 95.0% | 12.4 / 13.0ms | 419MB |
| KcELECTRA-base, K-MHaS 1단계 → 우리 데이터 (lr 5e-5) | 3 | 95.0% | 90.0% | 0.0% | 89.5~91.9 | 92.3~100 | 95.0% | 12.6 / 13.5ms | 419MB |
| KcELECTRA-small-v2022, 바로 학습 (lr 3e-4) | 4 | 78.3~95.0% | 86.7~90.0% | 0.0~42.9% | 65.1~89.5 | 80.0~92.3 | 95.0% | 2.8 / 3.2ms | 65MB |
| KcELECTRA-small-v2022, K-MHaS 1단계 → (lr 3e-5~5e-4) | 5 | 71.7~76.7% | 86.7~93.3% | 42.9% | 53.1~64.3 | 66.7~80.0 | 95.0% | 2.8 / 3.2ms | 65MB |
| KoELECTRA-small-v3, 바로 학습 (lr 1e-4·3e-4) | 2 | 76.7~78.3% | 90.0% | 42.9% | 59.1~61.9 | 75.0~85.7 | 95.0% | 2.8 / 3.1ms | 55MB |
| KoELECTRA-small-v3, K-MHaS 1단계 → (lr 3e-5~5e-4) | 5 | 46.7~78.3% | 86.7~90.0% | 42.9~100% | 53.1~61.9 | 23.8~85.7 | 95.0% | 2.8 / 3.2ms | 55MB |

- profanity F1 은 모든 구성에서 100(규칙). instigation(시험 정답 1건)·sexual_harassment(2건)은 건수가 적어 F1 을 표에 넣지 않았습니다(base: instigation 40~100, sexual 57~80).
- 모델 첫 로딩은 따로입니다: 프로세스 시작 후 import + 로딩 + 첫 추론이 세 후보 모두 약 3.1초(대부분 torch import). 그 뒤 1문장 12ms 안팎으로 0.2초 기준을 지킵니다.
- `uv run sim analyze` 는 실행마다 새 프로세스라 매번 로딩이 들어가 **1회 약 3.4초**가 걸립니다(모델 없이는 수십 ms). 앱은 프로세스가 하나라 첫 문장만 느립니다 — 게임 시작 전에 한 번 미리 불러 두는 것이 좋습니다(구성 쪽 작업).

추천 이유
1. **안정성.** base 는 학습률·시드·1단계 여부를 바꾼 8회 모두 95.0% / 90.0% / 오탐 0% 였습니다. KcELECTRA-small 은 잘 될 때는 base 와 같지만(4회 중 2회) 시드에 따라 포지션 낱말만 보고 비난으로 찍어 정상 오탐 42.9%까지 떨어졌습니다. 510문장으로는 소형 모델 학습이 흔들립니다.
2. **속도는 충분.** 12ms 는 기준 200ms 의 1/16 입니다. small 의 3ms 는 여기서 이득이 없습니다.
3. **크기 419MB 는 부담**이지만 데모에서는 Hugging Face 비공개 저장소로 받으면 됩니다. 라벨 데이터가 수천 문장으로 늘면 KcELECTRA-small(65MB)을 다시 비교할 만합니다.
4. **K-MHaS 1단계는 base 에 뚜렷한 이득이 없고 소형 모델에는 해로웠습니다.** 그래서 라이선스(CC-BY-SA) 고민이 없는 "바로 학습"을 골랐습니다. 지금 `models/analyze-classifier/` 에 둔 것은 바로 학습·시드 1(검증 F1 평균 0.958)입니다.

남은 오답 3건(악성 재현율이 90%에서 멈춘 이유)은 모두 "제드 ㅁㅊ놈인가"처럼 **챔피언 이름으로 부른 문장**입니다. 평가 CSV 에 명단(players)이 없어 대상을 못 찾아 L1 이 된 것으로, 모델이 아니라 평가 입력의 한계입니다.

#### 데이터
| 데이터 | 용도 | 출처·라이선스 | 위치 |
|---|---|---|---|
| `labeled_parsed.csv` train 140 / test 60 | 학습 / 시험(고정) | AI 작성 가상 문장, 팀 검수 전 | `fixtures/analyze/` |
| `train_aug.csv` 370문장 (전부 train) | 학습 보강 | **AI(Claude) 작성 가상 문장, 검수 전** (`writer=AI(claude)`). 욕설 없는 비난 162 · 정치질 32 · 패드립 20 · 성희롱 16 · 비난처럼 보이는 정상 문장 144. `feedback` 열(다듬은 문장)은 비어 있음 | `fixtures/analyze/` |
| K-MHaS 뉴스 댓글 10.9만 건 중 2만 건 | 1단계 학습(대조군) | [adlnlp/K-MHaS](https://github.com/adlnlp/K-MHaS), **CC-BY-SA 4.0**. 욕설 라벨만 profanity 로 사용. 받는 법은 `public_data.py` 맨 위 | `data/raw/kmhas/` (git 제외) |
| Korean UnSmile | **쓰지 않음** | 원문 README 기준 데이터셋 **CC-BY-NC-ND 4.0**(비상업·변경 금지) | - |

후보 모델 라이선스: `beomi/KcELECTRA-base`·`KcELECTRA-small-v2022` 는 MIT, `monologg/koelectra-small-v3-discriminator` 는 모델 카드에 표기가 없고 원 저장소(monologg/KoELECTRA)는 Apache-2.0 입니다.

#### 직접 돌려 보기 (노트북)
`notebooks/model_demo.ipynb` — 학습률·배치·epoch 로그, 인코더 벡터가 유형 점수가 되는 과정, 유형별 대표 문장과의 코사인 유사도 비교를 실행 결과와 함께 담았습니다. 주피터는 프로젝트 의존성이 아니므로 일회용으로 띄웁니다: `uv run --with jupyterlab jupyter lab src/clean_chat/modules/analyze/notebooks/model_demo.ipynb`

#### 다시 해 보기
```bash
D="fixtures/analyze/labeled_parsed.csv fixtures/analyze/train_aug.csv"    # bash 기준 (zsh 는 $D 를 나누지 않으니 경로를 직접 적기)
# 바로 학습 (추천 구성)
uv run python -m clean_chat.modules.analyze.train --data $D --base beomi/KcELECTRA-base \
    --version kcelectra-base-ft-0.1 --out models/analyze-classifier --epochs 20 --patience 6 --lr 5e-5 --seed 1
# 소형 모델: --base beomi/KcELECTRA-small-v2022 (또는 monologg/koelectra-small-v3-discriminator) --epochs 40 --lr 3e-4
# K-MHaS 2단계 (대조군): public_data.py 맨 위의 명령으로 1단계 모델을 만든 뒤 --base models/ft/stage1-<이름>
uv run python -m clean_chat.modules.analyze.evaluate fixtures/analyze/labeled_parsed.csv --split test
```

#### 확인하지 못한 것 · 주의
- **시험 문장이 60개뿐이고, 학습·보강·시험 문장을 모두 AI 가 썼습니다.** 말투가 비슷해 수치가 실제보다 좋게 나왔을 가능성이 큽니다. 팀이 직접 쓴 문장으로 시험셋을 다시 만들어 재야 합니다. 시드 간 차이도 60문장에서는 1문장 = 1.7%p 입니다.
- 보강 문장을 쓰기 전에 규칙만 돌린 평가의 오답 목록(시험 문장 9개)을 봤습니다. 그 문장과 표현은 피해서 썼고 같은 문장이 없는지는 테스트(`test_augmented_train_rows_do_not_leak_into_test`)가 확인하지만, 완전히 모르는 상태에서 쓴 것은 아닙니다.
- "욕설은 규칙만" 결정은 검증 문장(train 에서 뗀 15%)의 오탐 양상과 설계 이유로 정했지만, 그 전에 시험 오답 목록도 봤습니다. 이 수정 전 base 의 시험 수치는 등급 일치율 91.7~95.0%, 정상 오탐률 0~9.5% 였습니다("나이스 갱", "아 렉 걸렸네" 가 욕설로 찍힘).
- 유형별 기준값은 0.5 그대로입니다. 검증 문장에서 0.5~0.9 로 바꿔 봐도 정상 오탐이 줄지 않아(점수가 0.9 이상으로 확신하며 틀림) 조정하지 않았습니다.
- 지연은 Apple M5 CPU(torch 2.15, 4 스레드)에서만 쟀습니다. **실제 대상인 Windows PC 에서는 재지 않았습니다.**
- `text_norm` 은 parse 가 이상적으로 동작한다고 가정한 값입니다(`--with-parse` 로는 평가하지 않음).
- K-MHaS 로 학습한 가중치를 배포할 때 CC-BY-SA 의 동일조건변경허락이 어디까지 미치는지는 확인하지 않았습니다(추천 모델은 K-MHaS 를 쓰지 않습니다).
- 협박("집 주소 안다 찾아간다")은 유형 코드가 없어 라벨이 비어 있습니다. 모델이 패드립·성희롱으로 찍어 L3 이 되기도 합니다 — 유형 추가는 팀 논의가 필요합니다.
- 예문 유사도 방식(SetFit 류)은 새 패키지가 필요해 비교하지 않았습니다.
- 지금 받는 `beomi/KcELECTRA-base` 의 토크나이저(어휘 30,000, 바이트 단위 BPE)는 `[CLS]`·`[SEP]` 를 붙이지 않습니다. 그래서 분류 층이 읽는 맨 앞 벡터는 문장의 첫 조각 자리입니다. `[CLS]`·`[SEP]` 를 붙여 같은 조건으로 3회 학습해 봤지만 등급 일치율 93.3~95.0% 로 나아지지 않아 그대로 둡니다.
- `docs/DATA.md` 의 외부 데이터셋 표(모듈 범위 밖)에 위 라이선스를 옮겨 적는 일이 남았습니다.

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
uv run sim analyze                         # 단발 채팅 분류 — 브라우저: 입력 | 디버깅 콘솔(print·logging·오류) | 반환값
uv run sim judge                           # 전체 대화 판단 — 여러 줄 대화를 넣으면 화자별 신고 권고·고소 후보
uv run pytest tests/test_analyze.py        # 자동 테스트 (구현 전이면 skip)
uv run python scripts/pack_context.py analyze   # 웹 AI 채팅에 첨부할 맥락 묶음
```
모듈 코드를 고친 뒤 시뮬레이터에서 [실행]만 다시 누르면 됩니다(서버를 다시 켤 필요 없음).
