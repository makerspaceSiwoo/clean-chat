# Clean Chat 모듈 시뮬레이터 (사내 테스트용 웹앱)

데스크톱 앱의 각 Stage(모듈)를 웹에서 실행해 보고, 결과와 E2E 체크리스트를 눈으로 확인하는 도구입니다.
모듈이 `develop` 에 병합될 때마다 이 화면으로 동작을 QA 합니다. **웹앱 안에는 모듈의 실제 로직이 없습니다.**

```bash
cd simulator
npm ci
npm run dev        # http://localhost:3100 (공통 fixtures·계약을 변환한 뒤 실행)
npm test           # 단위·통합 테스트 (Jest + React Testing Library)
npm run verify     # 타입 검사 + 테스트 + 프로덕션 빌드 (CI 와 같음)
```

## 화면
| 화면 | 주소 | 내용 |
|---|---|---|
| 홈 | `/` | Stage 10개를 흐름별(흐름 A · 흐름 B · 공통 필터 · 게임 종료 후) 카드로 표시. 카드 → 시뮬레이션 화면 |
| 시뮬레이션 | `/modules/<stageId>` | 왼쪽: Mock 케이스 선택·입력 JSON 편집·응답 흉내 / 가운데: 실행 버튼·로딩·결과(요약 표, 실제 응답 vs 기대값) / 오른쪽: E2E 체크리스트(자동 판정 + 사람이 확인) |

PC 전용입니다. 화면 폭은 1280px 고정이고, 반응형 처리를 하지 않습니다(창이 좁으면 가로 스크롤).

## 배포 (Vercel)
데스크톱 앱은 배포하지 않습니다. 같은 레포에서 이 폴더만 Vercel 프로젝트로 연결했습니다(ADR-0015).

| 브랜치 | Vercel 환경 | 주소 | `NEXT_PUBLIC_APP_ENV` |
|---|---|---|---|
| `main` | Production | 첫 main 배포 후 기록 (`vercel project inspect clean-chat-simulator`) | `main` |
| `develop` | Preview (브랜치 고정 주소) | https://clean-chat-simulator-git-develop-seeyouspace0-5824s-projects.vercel.app | `develop` |
| PR·그 밖의 브랜치 | Preview (커밋마다 임시 주소) | PR 댓글·`vercel ls` 에 표시 | `local` |

- **Vercel 프로젝트**: `clean-chat-simulator` (팀 `siwoojung's team`). GitHub `makerspaceSiwoo/clean-chat` 연결, Production Branch `main`.
- **볼 수 있는 사람**: 기본 보호(Vercel Authentication, "커스텀 도메인을 뺀 모든 배포")라서 main·develop·PR 주소 모두 **Vercel 에 로그인한 팀 멤버만** 볼 수 있습니다. 팀원은 Vercel 팀에 초대해야 합니다. 커스텀 도메인을 붙이면 그 주소는 공개됩니다.
- **자동 배포**: GitHub push 마다. 단, `simulator/`·`fixtures/`·`contracts/` 가 바뀐 커밋만 빌드합니다(`vercel.json` 의 `ignoreCommand`). 파이썬만 고친 커밋은 건너뜁니다.
- **프로젝트 설정**: Root Directory `simulator`, Framework Next.js, Node 22(`package.json` engines), "Root Directory 밖 파일 포함" 켜짐(공통 `../fixtures`, `../contracts` 를 읽음).
- **환경 변수 위치**: Vercel 프로젝트 → Settings → Environment Variables. Production(`APP_ENV=main`), Preview·develop 브랜치(`develop`), Preview 그 밖(`local`), 셋 다 `API_MODE=mock`. **secret 은 없습니다.** 바꾸려면 `npx vercel@65.8.0 env ls` / `env add --force`.
- 실제 모듈을 웹에서 실행하는 API(HTTP 모드)는 이번 범위가 아닙니다. 분류 모델(torch)은 Vercel 함수 크기 제한을 넘을 가능성이 커서, 필요해지면 Render·Fly.io 같은 곳에 따로 둡니다.

## 환경 변수 (main / develop 서버 분리)
같은 코드를 서버마다 다른 환경 변수로 띄웁니다. `.env.example` 을 복사해 `.env.local` 로 씁니다.

| 변수 | 값 | 설명 |
|---|---|---|
| `NEXT_PUBLIC_APP_ENV` | `local` · `develop` · `main` | 화면 오른쪽 위 배지 (어느 서버인지) |
| `NEXT_PUBLIC_API_MODE` | `mock` · `http` | `mock`: fixtures 응답(백엔드 불필요) / `http`: 실제 Stage 실행 API 호출 |
| `NEXT_PUBLIC_API_BASE_URL` | 예: `https://sim-api-develop.internal` | `http` 모드 API 주소 |
| `NEXT_PUBLIC_API_TIMEOUT_MS` | 기본 10000 | 넘으면 타임아웃 오류 |
| `NEXT_PUBLIC_MOCK_LATENCY_MS` | 기본 500 | Mock 응답 지연 흉내 (로딩 화면 확인용) |

- `NEXT_PUBLIC_*` 는 **빌드할 때** 코드에 들어갑니다. 서버마다 따로 `npm run build` 하세요. 비밀값은 넣지 않습니다(브라우저에 그대로 보임).
- 값이 잘못돼도 앱은 멈추지 않습니다. 기본값으로 대신하고 화면 위에 "설정 경고"를 띄웁니다(`src/config/env.ts`).
- 예) develop 서버: `NEXT_PUBLIC_APP_ENV=develop NEXT_PUBLIC_API_MODE=http NEXT_PUBLIC_API_BASE_URL=... npm run build && npm start`

## 설계 결정과 가정
| 결정 | 이유 |
|---|---|
| **Next.js 15 (App Router) + TypeScript + Tailwind 3**, 레포 안 `simulator/` 폴더 | fixtures·스키마와 같은 레포에 있어야 모듈 병합 때 웹앱 Mock 이 함께 바뀐다. 파이썬 패키지와 섞이지 않게 폴더만 분리 |
| **Mock 데이터 = 레포 `fixtures/`, 타입 = 레포 `contracts/`** (`scripts/sync-shared.mjs` 가 dev·build·test 전에 변환, 결과는 git 제외) | 데이터·계약을 웹앱에 손으로 베끼면 파이썬 쪽과 어긋난다. 단일 출처 유지 (ADR-0015) |
| Mock 은 **입력이 fixtures 와 구조까지 같을 때만** 기대값 응답(200), 다르면 404 | 파이썬 `MockStage` 와 같은 규칙. 값을 지어내지 않는다(= 실제 로직 배제) |
| API 는 **포트(`StageApiClient`) + 어댑터(Mock / HTTP)**, React Context 로 주입(`ApiProvider`) | 실제 백엔드로 바꿀 때 화면 코드는 그대로. 테스트는 가짜 클라이언트를 주입 |
| 클라이언트는 **예외 대신 `RunStageResponse`** 로 실패를 돌려줌 (네트워크·타임아웃은 status 0) | 화면이 실패 종류별로 try/catch 하지 않게. 취소만 `AbortError` |
| 체크리스트 자동 판정은 **순수 함수**(`lib/checklist.ts`). 출력 필드는 **공통 계약**에서, 지연 목표·STRICT·QA 항목은 **registry** 에서 | 계약이 바뀌면 필드 검사가 자동으로 따라간다. 판정 규칙은 단위 테스트로 고정 |
| STRICT 모듈(parse, compose, 정책 2개)은 기대값과 다르면 **실패**, AI 모듈은 **경고** | `tests/test_real_impls.py` 의 STRICT 기준과 같음 |
| Mock 모드에서는 **응답 시간 검사 건너뜀** | Mock 지연은 흉내라 의미가 없다. http 모드에서만 SPEC 8장 목표로 검사 |
| 늦게 도착한 옛 응답 무시, 화면 이탈 시 요청 취소, 결과·체크리스트에 Error Boundary, 라우트 `error.tsx` | 실행 버튼 연타·느린 서버·예상 못 한 응답 모양에서도 화면이 깨지지 않게 |
| **응답 흉내**(500 · 타임아웃 · 빈 응답) 선택 | 오류 화면과 체크리스트 실패 표시를 백엔드 없이 QA |
| TS 타입은 `contracts/stages.schema.json` 에서 **자동 생성**(`json-schema-to-typescript`), `src/types/contracts.ts` 는 다시 내보내기만 | 손 사본 제거. `schemas.py` 변경 → `export_contracts.py` 실행 → 웹앱 타입 자동 갱신 |

가정: 시뮬레이터는 사내망 전용(로그인 없음), 사용자는 PC 크롬 계열, 실제 채팅 원문·닉네임은 다루지 않음(fixtures 는 팀이 쓴 가상 문장).

## Mock 으로 처리된 부분
| 부분 | 지금 (Mock) | 실제로 바꾸려면 |
|---|---|---|
| Stage 실행 결과 | `fixtures/<stage>/expected.jsonl` 그대로 | `NEXT_PUBLIC_API_MODE=http` + 아래 API 서버 |
| 응답 지연 | `NEXT_PUBLIC_MOCK_LATENCY_MS` 만큼 대기 | 실제 측정값(`durationMs`) |
| 서버 오류·타임아웃·빈 응답 | 화면의 "응답 흉내" 선택 | 실제 서버 응답 |
| impl 표시 | `mock-fixture` / `mock` | 서버가 보내는 `impl` (예: `real`) |

## HTTP API 계약 (`API_MODE=http`, 아직 서버 없음)
```
POST {BASE_URL}/stages/{stageId}/run
요청  { "input": <Stage 입력 모델 JSON> }
응답  { "output": <Stage 출력 모델 JSON | null>, "impl": "real" | "mock" ..., "error"?: "사람이 읽는 문장" }
상태  200 성공 / 4xx 입력 문제 / 5xx 실행 실패 (본문 형식은 같음)
```
타입: `src/types/api.ts`. 서버는 파이썬 `StageSet` 으로 Stage 1개를 실행해 감싸기만 하면 됩니다(브라우저에서 부르므로 CORS 허용 필요).

## 폴더 구조
```
simulator/
├─ vercel.json                  Vercel 빌드 설정 (빌드 건너뛰기 규칙)
├─ scripts/sync-shared.mjs       ../fixtures → src/mocks/generated/, ../contracts → src/shared/generated/ (자동, git 제외)
├─ src/
│  ├─ app/                       라우트: layout, page(홈), modules/[stageId], error, not-found
│  ├─ api/                       ApiProvider(주입), mockClient, httpClient
│  ├─ config/env.ts              환경 변수 → 설정 (검증·기본값·경고)
│  ├─ shared/contracts.ts        공통 계약 읽기 (Stage 목록, 입출력 모델 이름, 출력 필드)
│  ├─ modules/registry.ts        Stage 별 화면 메타·지연 목표·QA 항목 (새 모듈은 여기에 추가)
│  ├─ mocks/fixtures.ts          생성된 Mock 데이터 접근
│  ├─ lib/                       checklist(자동 판정), json(파싱·비교)
│  ├─ hooks/useStageRun.ts       실행 상태 (idle/loading/success/error, 취소·경쟁 처리)
│  ├─ components/                ModuleCard·ModuleGrid(홈), simulator/(입력·실행·결과·체크리스트), ErrorBoundary
│  └─ types/                     contracts(생성 타입 다시 내보내기), api(요청/응답·클라이언트 인터페이스)
└─ *.test.ts(x)                  각 파일 옆에 테스트
```

## 새 모듈(Stage)을 추가할 때
1. 파이썬 쪽에서 Stage 를 등록하고 `uv run python scripts/export_contracts.py` 로 계약을 다시 만들면 → `registry.test.ts` 가 "registry 와 계약이 다름"으로 실패합니다.
2. `src/modules/registry.ts` 에 화면 메타 1개를 추가합니다 (타입·필드는 계약에서 자동).
3. `npm run verify` 통과 → 홈 카드와 시뮬레이션 화면이 자동으로 생깁니다.
