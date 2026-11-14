# Clean Chat 모듈 시뮬레이터 (사내 개발용 웹앱)

모듈 5개(① ocr · ② parse · ③ analyze · ④ rewrite · ⑤ report) 중 하나를 골라 **입력을 넣고 실행하면, 실제 파이썬 모듈 함수가 돌려준 output 을 그대로 보여 주는** 도구입니다(ADR-0017).
**Mock 은 없습니다.** 모듈이 아직 구현되지 않았으면 결과 대신 `501 구현 안 됨` 오류가 나옵니다. 기대값 비교, E2E 체크리스트도 없습니다.

```bash
# 터미널 1 (레포 루트): 실제 모듈 함수를 부르는 로컬 서버
uv run clean-chat serve          # http://localhost:8765

# 터미널 2
cd simulator
npm ci
npm run dev                      # http://localhost:3100
npm test                         # 단위·통합 테스트 (Jest + React Testing Library)
npm run verify                   # 타입 검사 + 테스트 + 프로덕션 빌드 (CI 와 같음)
```

## 화면
| 화면 | 주소 | 내용 |
|---|---|---|
| 홈 | `/` | 모듈 5개 카드 (번호, 이름, 입력 → 출력 모델, 예시 입력 수) |
| 모듈 실행 | `/modules/<모듈>` | 왼쪽: 예시 입력 고르기(`fixtures/<모듈>/input.jsonl`)·입력 JSON 편집·(OCR) 이미지 첨부 / 오른쪽: 실행 → **output JSON** 또는 **오류(상태 코드 + 메시지)** |

| 결과 | 뜻 |
|---|---|
| `HTTP 200` + output | 실제 함수가 돌려준 출력 |
| `501 구현 안 됨` | 함수가 `NotImplementedError` (담당자가 아직 구현 전) |
| `422 입력 형식 오류` | 입력 JSON 이 계약(`schemas.py`)과 다름 |
| `500 모듈 오류` | 함수 안에서 예외 (메시지에 예외 이름과 내용) |
| `서버 연결 안 됨` | `uv run clean-chat serve` 가 꺼져 있음 |

**이미지 첨부 (OCR)**: 입력에 이미지 경로가 있는 모듈(`registry.ts` 의 `imageField`, 지금은 ocr 의 `image_path`)은 이미지 첨부(파일 선택·끌어다 놓기, PNG·JPG·WEBP·BMP 10MB 이하)가 생깁니다. 실행하면 이미지를 base64 로 로컬 서버에 보내고, 서버가 `.clean-chat/uploads/` 에 저장한 뒤 `image_path` 를 그 경로로 바꿔 실제 ocr 함수를 부릅니다(git 제외 폴더).

PC 전용입니다. 화면 폭은 1280px 고정이고, 반응형 처리를 하지 않습니다.

## 배포 (Vercel) — 화면만
데스크톱 앱은 배포하지 않습니다. 같은 레포에서 이 폴더만 Vercel 프로젝트로 연결했습니다(ADR-0015).
**배포 주소에서는 모듈을 실행할 수 없습니다**(실행 서버가 각자 PC 의 `localhost:8765` 라서, 대부분 `서버 연결 안 됨`). 화면 확인용이고, 실제 실행은 로컬에서 합니다.

| 브랜치 | Vercel 환경 | 주소 | `NEXT_PUBLIC_APP_ENV` |
|---|---|---|---|
| `main` | Production | https://cleanchat-simul.vercel.app | `main` |
| `develop` | Preview (브랜치 고정 주소) | https://develop-cleanchat-simul.vercel.app | `develop` |
| PR·그 밖의 브랜치 | Preview (커밋마다 임시 주소) | PR 댓글·`vercel ls` 에 표시 | `local` |

- **Vercel 프로젝트**: `clean-chat-simulator` (팀 `siwoojung's team`). GitHub `makerspaceSiwoo/clean-chat` 연결, Production Branch `main`.
- **볼 수 있는 사람**: **모든 주소(main·develop·PR 미리보기)가 공개**입니다. 팀원이 Vercel 팀 계정(유료) 없이 볼 수 있도록 Deployment Protection 을 껐습니다. secret 이 없고 검색 엔진 수집은 막아 두었습니다(`robots: noindex`). 실제 채팅·닉네임·secret 은 이 앱에 넣지 않습니다.
- **자동 배포**: GitHub push 마다. 단, `simulator/`·`fixtures/`·`contracts/` 가 바뀐 커밋만 빌드합니다(`vercel.json` 의 `ignoreCommand`).
- **프로젝트 설정**: Root Directory `simulator`, Framework Next.js, Node 22(`package.json` engines), "Root Directory 밖 파일 포함" 켜짐(공통 `../fixtures`, `../contracts` 를 읽음).
- **환경 변수 위치**: Vercel 프로젝트 → Settings → Environment Variables. `NEXT_PUBLIC_APP_ENV` 만 씁니다(예전 `NEXT_PUBLIC_API_MODE` 는 더 이상 읽지 않음). **secret 은 없습니다.**

## 환경 변수
`.env.example` 을 복사해 `.env.local` 로 씁니다. 없어도 기본값으로 동작합니다.

| 변수 | 값 | 설명 |
|---|---|---|
| `NEXT_PUBLIC_APP_ENV` | `local` · `develop` · `main` | 화면 오른쪽 위 배지 |
| `NEXT_PUBLIC_API_BASE_URL` | 기본 `http://localhost:8765` | 로컬 모듈 서버 주소 (`clean-chat serve --port` 와 맞춤) |
| `NEXT_PUBLIC_API_TIMEOUT_MS` | 기본 30000 | 넘으면 시간 초과 (모델 로딩이 길면 늘림) |

- `NEXT_PUBLIC_*` 는 **빌드할 때** 코드에 들어갑니다. 비밀값은 넣지 않습니다(브라우저에 그대로 보임).
- 값이 잘못돼도 앱은 멈추지 않습니다. 기본값으로 대신하고 화면 위에 "설정 경고"를 띄웁니다(`src/config/env.ts`).

## 서버 계약 (로컬 모듈 서버, `src/clean_chat/core/server.py`)
```
POST {BASE_URL}/modules/{모듈}/run
요청  { "input": <모듈 입력 모델 JSON>, "image"?: { "name": "a.png", "base64": "..." } }
응답  { "output": <모듈 출력 모델 JSON | null>, "error"?: "사람이 읽는 문장" }
      200 성공 · 501 구현 없음 · 422 입력 형식 오류 · 500 모듈 예외 · 404 모르는 모듈
GET   {BASE_URL}/modules   → [{ name, title, path }]
```
- 서버는 `127.0.0.1` 에만 열리고, CORS 는 `localhost`·`127.0.0.1` 출처만 허용합니다. 표준 라이브러리만 씁니다(새 패키지 없음).
- 타입: `src/types/api.ts`.

## 설계 결정
| 결정 | 이유 |
|---|---|
| **실제 함수만 호출, Mock·기대값 비교 없음** (ADR-0017) | 구현이 없는데 동작하는 것처럼 보이는 착각을 없앤다. 실행 결과가 곧 구현 상태 |
| 실행은 **로컬 파이썬 서버**(`clean-chat serve`) | OCR·분류 모델은 Vercel 함수 용량(250MB)을 넘는다. 각자 PC 에서 자기 모듈을 바로 돌려 본다 |
| 입력 예시 = 레포 `fixtures/<모듈>/input.jsonl`, 타입 = 레포 `contracts/modules.schema.json` (`scripts/sync-shared.mjs` 가 dev·build·test 전에 변환, 결과는 git 제외) | 데이터·계약을 손으로 베끼지 않는다 (ADR-0015) |
| API 는 **포트(`ModuleApiClient`) + HTTP 어댑터**, React Context 로 주입(`ApiProvider`) | 테스트는 가짜 클라이언트를 주입 |
| 클라이언트는 **예외 대신 `RunModuleResponse`** 로 실패를 돌려줌 (연결 실패·타임아웃은 status 0) | 화면이 실패 종류별로 try/catch 하지 않게. 취소만 `AbortError` |
| 늦게 도착한 옛 응답 무시, 화면 이탈 시 요청 취소, 결과에 Error Boundary, 라우트 `error.tsx` | 실행 버튼 연타·느린 모듈에서도 화면이 깨지지 않게 |

## 폴더 구조
```
simulator/
├─ scripts/sync-shared.mjs       ../fixtures → src/examples/generated/, ../contracts → src/shared/generated/ (자동, git 제외)
├─ src/
│  ├─ app/                       라우트: layout, page(홈), modules/[moduleId], error, not-found
│  ├─ api/                       ApiProvider(주입), httpClient(로컬 모듈 서버)
│  ├─ config/env.ts              환경 변수 → 설정 (검증·기본값)
│  ├─ shared/contracts.ts        공통 계약 읽기 (모듈 목록, 제목, 구현 위치, 입출력 모델 이름)
│  ├─ modules/registry.ts        모듈 5개 화면용 설명·이미지 필드
│  ├─ examples/examples.ts       입력 예시 (fixtures 입력만)
│  ├─ types/                     api.ts(서버 요청·응답), contracts.ts(자동 생성 타입 다시 내보내기)
│  ├─ hooks/useModuleRun.ts      실행 상태 (idle/loading/success/error, 취소·경쟁 처리)
│  ├─ components/                ModuleCard·ModuleGrid(홈), simulator/(입력·이미지 첨부·실행·결과), ErrorBoundary
│  └─ lib/                       json·image 도우미 (순수 함수)
└─ vercel.json, .env.example
```

## 모듈 계약이 바뀌면
1. 파이썬 쪽에서 `schemas.py`·`core/modules.py` 를 바꾸고 `uv run python scripts/export_contracts.py` 로 계약을 다시 만듭니다.
2. 모듈이 늘거나 줄면 `registry.test.ts` 가 "registry 와 계약이 다름"으로 실패합니다 → `src/modules/registry.ts` 에 설명을 맞춥니다.
