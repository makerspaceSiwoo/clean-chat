# 결정 기록 (Architecture Decision Records)

> "왜 이렇게 만들었나"를 남기는 곳입니다. 에이전트와 새 팀원이 같은 고민을 반복하지 않게 합니다.
> 새 결정은 아래 양식으로 **맨 아래에 추가**합니다. 기존 결정을 뒤집을 때는 지우지 말고 `상태: 대체됨 → ADR-00xx`로 표시합니다.

```
## ADR-00xx: 제목
- 날짜 / 상태(제안·확정·대체됨) / 결정자
- 배경: 무엇이 문제였나
- 결정: 무엇으로 정했나
- 이유: 왜
- 버린 대안: 무엇을, 왜 버렸나
- 영향: 이 결정 때문에 생기는 일, 위험
```

---

## ADR-0001: 서버 없이 로컬 단일 프로그램으로 만든다
- 2026-11-12 / 확정 / 팀
- **배경**: 2주짜리 데모이고 채팅은 개인 PC 화면에서만 얻을 수 있다.
- **결정**: 클라우드 서버 없이 **하나의 파이썬 프로그램**이 캡처부터 처리, 화면까지 모두 맡는다. 모듈은 파이썬 함수 호출로 연결한다(웹으로 치면 미들웨어 체인).
- **이유**: 배포, 인증, 네트워크 문제를 없애 데모 리스크를 줄인다. 채팅 원문이 외부로 나가지 않아 개인정보 부담도 적다.
- **버린 대안**: FastAPI 로컬 서버 + 별도 프론트 → 프로그램이 둘이 되어 연결과 실행 관리가 복잡해진다. (LLM을 외부 API로 쓸 경우는 ADR-0005 참고)
- **영향**: 모든 모듈은 `core/schemas.py`의 데이터 형식으로만 주고받는다.

## ADR-0002: 채팅 수집은 OCR로 한다 (Overwolf, LCU, 메모리 읽기 사용 안 함)
- 2026-11-12 / 확정 / 팀
- **배경**: 게임 중 채팅과 핑을 받아야 한다.
- **결정**: **화면 캡처 + OCR**로 채팅창의 글자를 읽는다.
- **이유**:
  - **LCU**(롤 클라이언트 로컬 API)는 챔피언 선택창과 게임 후 채팅용이며, 게임 중 채팅은 제공하지 않는다.
  - **메모리 읽기와 드라이버**는 Vanguard(커널 수준 핵 방지)에 걸려 계정 정지 위험이 크다.
  - **Overwolf**는 팀 조사 결과 게임 중 채팅과 핑을 우리 목적에 맞게 쓰기 어렵다고 판단했다. 개발자 계정과 라이엇 승인에 의존하고, JS 앱을 따로 만들어야 하는 부담도 있다.
    - 참고: Overwolf 개발 문서에는 LoL용 `chat` 이벤트(GEP 224.0 이후)가 소개되어 있다. 단, **실시간 용도로만 쓰고 기록하면 안 된다**는 조건이 있어 신고·고소 증거 보관 기능과 충돌한다. 핑 정보는 제공하지 않는다. → **OCR이 막힐 경우의 대안으로만** 남긴다(OPEN-01).
- **버린 대안**: 위 세 가지.
- **영향**: 게임을 **테두리 없는 창 모드**로 실행해야 한다. OCR 오인식(예: `ㅂ`↔`ㅃ`)을 전처리에서 보정해야 한다. 같은 줄이 여러 프레임에 반복 등장하므로 **중복 제거**가 필수다.
- **보충 (2026-11-12)**: 여기서 버린 것은 **LCU로 채팅을 읽는 것**이다. 게임 진행 단계(`gameflow-phase`)를 **읽기만** 하는 것은 ADR-0014에서 허용했다.

## ADR-0003: 오버레이는 화면 캡처에서 제외한다
- 2026-11-12 / 제안 (실측 필요, OPEN-02) / 리드
- **배경**: 오버레이가 게임 채팅창을 가리므로, 화면을 그대로 캡처하면 OCR은 **우리 오버레이**를 읽게 된다.
- **결정**: 오버레이 창에 Windows의 "캡처 제외" 속성(`SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`, Windows 10 2004 이상)을 건다. 이것이 안 되면 **게임 창만 캡처**하는 방식(Windows Graphics Capture)으로 바꾼다.
- **이유**: 사용자 화면에서는 가리고, 캡처에서는 투명하게 만드는 가장 단순한 방법이다.
- **버린 대안**: 오버레이를 잠깐 숨겼다가 캡처 → 화면이 깜빡여 사용 경험이 나쁘다.
- **영향**: 1주 차에 Windows 담당자가 반드시 실측해야 한다. **가장 큰 기술 리스크.**

## ADR-0004: UI는 PySide6 하나로 만든다 (클라이언트 + 오버레이)
- 2026-11-12 / 확정 / 리드
- **배경**: UI는 간단하면 되고, 중요한 것은 분류 로직과 처리다.
- **결정**: 클라이언트 창과 오버레이 창 모두 PySide6(Qt)로 만든다.
- **이유**: 파이썬 한 언어로 끝나고, 투명 창, 항상 위, 클릭 통과를 지원한다. 에이전트가 코드를 잘 작성하는 프레임워크이기도 하다.
- **버린 대안**: Electron(프로그램이 둘이 됨), pywebview(투명 오버레이가 까다로움), Overwolf 창(ADR-0002).
- **영향**: 게임은 **전체 화면이 아닌 테두리 없는 창 모드**여야 오버레이가 위에 보인다.

## ADR-0005: AI는 "빠른 분류기 + 필요할 때만 LLM" 2단 구조로 쓴다
- 2026-11-12 / 확정(LLM 실행 위치는 OPEN-04) / 팀
- **배경**: AI가 필요한 곳이 4군데(OCR, 분류, 피드백 추출과 다듬기, 신고·고소 문서)다. 모든 채팅에 큰 모델을 돌리면 느리다.
- **결정**:
  - **분류(A2)**: 모든 채팅에 실행한다. KcBERT/KcELECTRA 계열 소형 분류 모델을 파인튜닝하고, 우회어 사전과 규칙으로 보강한다.
  - **피드백 추출 + 다듬기(A3), 문서 작성(A4)**: L2 이상인 소수의 채팅에만 LLM을 실행한다.
  - LLM은 **교체 가능한 백엔드**로 감싼다: `rule`(규칙, 항상 동작하는 기본값) / `local`(Ollama 등 로컬 LLM) / `api`(외부 API).
- **이유**: 빠른 반응(1.5초 이내)과 문장 생성 품질을 함께 얻는다. LLM이 실패해도 `rule` 백엔드로 데모가 계속 돌아간다.
- **버린 대안**: LLM 하나로 전부 처리 → 느리고, 발표용 노트북에서 롤과 함께 돌리기 어렵다.
- **영향**: `rewrite`와 `report`는 백엔드 인터페이스를 지켜야 한다.

## ADR-0006: 내 채팅은 가상 키보드 입력이 아니라 "클립보드 복사"로 보낸다
- 2026-11-12 / 확정(실측 후 재검토 가능, OPEN-05) / 팀
- **배경**: 수정된 내 채팅을 게임에 넣으려면 게임 채팅창을 조작해야 한다.
- **결정**: 오버레이 입력칸 → 필터 → **결과를 클립보드에 복사** → 사용자가 직접 `Enter → Ctrl+V → Enter`로 보낸다.
- **이유**: Vanguard가 가상 키 입력(SendInput 등)을 엄격히 관리할 수 있어 계정 위험이 있다. 클립보드 복사는 게임을 전혀 건드리지 않는다.
- **영향**: 사용자 동작이 한 단계 늘어난다. 데모 대본에 이 동작을 넣는다.

## ADR-0007: 신고는 데모 단계에서 "신고 문구 복사"로 한다
- 2026-11-12 / 확정 / 팀
- **배경**: 자동 신고를 하려면 클라이언트 조작이나 비공식 API가 필요하다.
- **결정**: 신고 문구(닉네임, 시간, 원문, 유형)를 만들어 **복사 버튼**만 제공한다.
- **버린 대안**: 클라이언트 자동 클릭, LCU의 신고 관련 엔드포인트 사용 → 정책 위반과 자동화 위험이 있다. 정책 검토 후 이후 버전에서 다시 논의한다.

## ADR-0008: 고소장은 "고정 양식 + 사실 채우기" 방식으로 별도 모듈에서 PDF로 만든다
- 2026-11-12 / 확정 / 리드
- **배경**: 신고 문구는 짧은 텍스트지만, 고소장은 양식과 PDF 출력이 필요하다.
- **결정**: `report` 모듈 안에서 **신고(report)** 와 **고소장(complaint)** 을 하위 기능으로 나눈다. 고소장은 **정해진 양식(템플릿)** 에 사실(일시, 닉네임, 원문, 유형, 횟수)을 채우고, LLM은 "사건 경위" 문단 요약에만 쓴다. PDF는 한글 폰트를 포함해 생성한다.
- **이유**: 법률 문서를 LLM이 자유롭게 쓰면 형식 오류나 허위 내용 위험이 크다. 담당자 한 명이 끝까지 책임질 수 있는 크기로 유지한다.
- **영향**: "법률 자문이 아니며 실제 제출 전 전문가 검토 필요" 문구를 반드시 넣는다. 게임 닉네임만으로는 피해자 특정이 어려울 수 있다는 점을 발표 Q&A에 대비한다(OPEN-08).

## ADR-0009: 브랜치, 코드 스타일, 병합 규칙을 레포에서 강제한다
- 2026-11-12 / 확정 / 리드
- **배경**: 5명 중 3명이 바이브 코딩으로 작업한다. 에이전트가 다른 모듈을 고치거나 스타일이 제각각이 되는 사고를 막아야 한다.
- **결정**: `CONTRIBUTING.md`의 규칙(브랜치 이름, PR 제목, ruff 린트와 포맷, 모듈 경계 검사, 승인 1명 이상, squash 병합)을 **CI와 GitHub 규칙(Rulesets)** 으로 강제한다.
- **영향**: 규칙을 어긴 PR은 자동으로 병합이 막힌다. 규칙 변경은 리드만 한다.
- **변경 (2026-11-12)**: 규칙을 단순하게 줄였다. GitHub 규칙은 `main` 보호(`protect-main`: PR 필수, 다른 팀원 승인 1명, force push·삭제 차단, 레포 주인 우회 가능) 하나만 쓴다. `develop`은 직접 push를 허용하고, CI는 실패를 표시만 하며 병합을 막지 않는다. 자세한 설정: `docs/GITHUB_SETTINGS.md`.

## ADR-0010: 모듈 단위로 분담하고, 주말마다 `develop`에 통합한다
- 2026-11-12 / 확정 / 팀
- **결정**: 모듈별 브랜치에서 작업하고(ADR-0018 이후 이름 `<모듈>/<작업 내용>`), 주말 통합 때 `develop`으로 PR을 올린다. 평일에도 작은 PR은 허용한다(통합 충돌 감소).
- **이유**: 모듈마다 담당 폴더가 분명해서 충돌이 적다. 계약(스키마)과 `fixtures`로 각 모듈을 따로 실행하고 시험할 수 있다.
- **영향**: 스키마를 바꾸면 모든 모듈에 영향이 가므로, `core/`는 리드만 수정한다.

## ADR-0011: 모든 처리 모듈을 "Stage(입력 1 → 출력 1) + mock + 단독 실행기" 구조로 만든다
- 2026-11-12 / 확정 / 리드
- **배경**: 5명이 동시에 개발하면서, 다른 모듈이 끝나지 않아도 내 모듈을 개발하고 시험할 수 있어야 한다. 스타터에는 실제 구현을 넣지 않기로 했다.
- **결정**:
  - 모듈마다 `stage.py`(인터페이스, 리드 소유) / `impl.py`(실제 구현, 담당자) / `__main__.py`(단독 실행)를 둔다.
  - `MockStage`는 `fixtures/<stage>/input.jsonl → expected.jsonl`을 그대로 응답한다. 파이프라인은 모듈별로 real과 mock을 골라 끼운다.
  - 스타터의 `impl.py`는 모두 `NotImplementedError`이다. 테스트는 미구현이면 skip하고, 구현되면 자동으로 검사한다.
- **이유**: 통신 포맷을 예시 데이터로 고정하면 명세가 모호해지지 않는다. 담당자는 "이 입력을 이 출력으로"만 맞추면 된다.
- **버린 대안**: 모듈마다 직접 가짜 함수를 작성 → 사람마다 가짜가 달라 통합 때 어긋난다.
- **영향**: `expected.jsonl`은 명세이므로 수정 시 리드 리뷰가 필요하다(CODEOWNERS).

## ADR-0012: 개발은 Mac, 실행은 Windows — OS 의존 코드는 2곳으로 격리한다
- 2026-11-12 / 확정 / 리드
- **배경**: 개발자 2명은 Mac을 쓰지만 실제 데모(롤 + 화면 캡처 + 오버레이)는 Windows에서 돈다.
- **결정**:
  - Windows 전용 코드는 `capture/grabber.py`(화면 캡처)와 `ui/win32.py`(캡처 제외) 두 곳만 둔다. `core/platform.py`로 막는다.
  - Windows 전용 패키지는 `sys_platform == 'win32'` 마커와 함수 안 import로 처리해 Mac에서 `uv sync`가 항상 성공하게 한다.
  - Mac 대체 소스: `DemoLineSource`(시나리오), `ScreenshotSource`(PNG 폴더).
  - CI는 macOS와 Windows 두 곳에서 설치, 린트, 테스트를 모두 돌린다.
  - 발표 PC는 `scripts/run_windows.bat`로 실행한다(패키징 exe는 시간이 남으면).
- **영향**: OCR, UI 화면, 모델은 Mac에서도 개발할 수 있다. 실제 캡처와 오버레이 캡처 제외만 Windows 담당자가 실측한다.
- **변경 (2026-11-12)**: ADR-0014로 Windows 전용 코드가 한 곳 늘었다 → `session/windows.py`(LCU 단계 감지). 가짜 감지기 `session/fake.py`가 Mac 대체 수단이다.

## ADR-0013: 기능을 두 흐름(수신 A / 송신 B)으로 나눈다
- 2026-11-12 / 확정 / 리드
- **배경**: 처음 구조는 파이프라인 하나가 모든 줄을 처리했다. 내 입력도 `RawLine(source=self_input)`으로 만들어 `parse`를 거쳤고, `policy` 하나가 `is_me`로 두 정책표를 오갔다. 계기(자동 캡처 / Enter), 실행 방식(스트림 / 요청-응답), 출구(오버레이·세션 / 클립보드)가 모두 달라 한곳에 섞이면 조건문이 늘고 테스트가 어렵다.
- **결정**:
  - 흐름 A(다른 유저 채팅): `IncomingPipeline` — Frame → `ocr` → `parse` → 공통 필터 → `incoming_policy` → 오버레이 + 세션 기록. 백그라운드 스트림.
  - 흐름 B(내 입력): `OutgoingPipeline.submit(text)` — `compose`(OutgoingText → ChatMessage) → 공통 필터 → `outgoing_policy` → 클립보드/차단. 동기 요청-응답(실행은 작업 스레드).
  - 공통 필터(`normalize` → `classify` → 조건부 `rewrite`)는 `MessageFilters` 하나를 두 흐름이 같이 쓴다. Stage 인스턴스도 `StageSet` 하나로 공유한다(모델 중복 로딩 방지).
  - 흐름 B에서 보낸 문장은 `SentLog`에 잠시 기억하고, 흐름 A의 OCR이 다시 읽으면 건너뛴다(기준: OPEN-13).
  - `compose`는 parse 모듈(WP3), 정책 Stage 2개는 policy 모듈(WP1)에 둔다.
- **이유**: 정책표가 SPEC 5-1, 5-2로 이미 나뉘어 있고, 흐름별로 fixtures와 테스트를 따로 만들 수 있다. 분류(classify)는 두 흐름에 같은 기준을 쓴다는 원칙도 그대로 지킨다.
- **버린 대안**: (a) 파이프라인 하나 + `is_me` 분기 — 분기가 Stage마다 퍼진다. (b) `compose`를 별도 모듈로 — 담당자와 경계 규칙만 늘고 하는 일은 parse와 비슷하다.
- **영향**: Stage가 8개에서 10개가 됐다. fixtures `policy/`가 `incoming_policy/`, `outgoing_policy/`로 나뉘고 `compose/`가 생겼다. CLI에 `clean-chat say "<문장>"`이 생겼다.

## ADR-0014: 게임 단계(상태 기계)와 세션 단위로 처리한다
- 2026-11-12 / 확정 / 리드
- **배경**: 신고 문구와 고소장은 게임 1판의 기록을 묶어서 만들어야 한다. 게임 밖에서는 오버레이와 캡처가 필요 없다. 언제 게임이 시작되고 끝나는지 알아야 한다.
- **결정**:
  - 앱 상태를 `IDLE`(대기) → `IN_GAME`(게임 중) → `POST_GAME`(게임 종료) → 사용자가 닫으면 `IDLE`로 둔다(`core/game.py: GameStateMachine`). 표에 없는 전환은 무시한다.
  - 게임 중에만 캡처(흐름 A)하고, 결과를 `GameSession`(id, 시작·종료 시각, 플레이어 명단, Incident 목록)에 기록한다. 세션에는 흐름 A만 넣는다.
  - 게임 종료 시 캡처를 멈추고 세션을 저장한 뒤(`SessionRepository`, `.clean-chat/sessions/<id>.jsonl`), 세션 전체를 한 번에 `report`/`complaint`로 처리한다(`PostGameBatch`). report·complaint 입력은 `GameSession` 기반이다.
  - 단계 감지: Windows는 LCU `/lol-gameflow/v1/gameflow-phase`를 1~2초마다 **읽기 전용 GET**으로 확인하고, 플레이어 명단은 Live Client Data API(`127.0.0.1:2999`)에서 받는다. Mac은 시나리오 JSONL을 재생하는 가짜 감지기를 쓴다.
- **이유**: 롤 클라이언트가 이미 단계를 알려 주므로 화면 인식보다 정확하다. 읽기 전용 로컬 API는 메모리 읽기·드라이버와 달리 Vanguard 위험이 낮고, 많은 공개 도구가 같은 방식을 쓴다. 채팅은 여전히 LCU로 읽지 않는다(ADR-0002).
- **버린 대안**: (a) 화면 인식으로 게임 시작·종료 판단 — 부정확하고 OCR 부담이 커진다. (b) 단계 없이 항상 캡처 — 게임 밖 화면을 읽고, 신고 묶음 단위가 없다.
- **영향**: 새 모듈 `session/`(WP8)과 Windows 전용 코드 1곳(`session/windows.py`)이 생겼다. LCU 단계 이름과 전환 시점은 실측이 필요하다(OPEN-12). 세션 파일에는 실제 채팅 원문이 들어가므로 git에 올리지 않는다.

## ADR-0015: 웹 시뮬레이터는 같은 레포의 별도 앱으로 두고, 계약·데이터만 공유하며 Vercel 에 배포한다
- 2026-11-14 / 확정 / 리드
- **배경**: 모듈이 `develop`에 병합될 때마다 웹에서 동작을 확인할 시뮬레이터(`simulator/`)를 Vercel 에 배포해야 한다. 데스크톱 앱(Python)과는 명확히 분리하되, Stage 계약은 공통으로 써야 한다. 웹앱의 TS 타입과 필수 필드 목록이 `schemas.py` 손 사본이라 어긋날 위험이 있었다.
- **결정**:
  - 한 레포에 앱 2개를 나란히 둔다: 데스크톱(루트 `pyproject.toml`, `src/`) / 웹(`simulator/`). 각자 의존성·CI(`ci.yml` / `simulator.yml`, 경로로 분리)·배포를 따로 가진다.
  - 공유는 **데이터와 계약만**: `fixtures/`(예시) + `contracts/stages.schema.json`(`scripts/export_contracts.py` 가 pydantic 에서 생성, 커밋). 웹앱은 빌드 전에 여기서 Mock 데이터·TS 타입·출력 필드를 자동 생성한다(`simulator/scripts/sync-shared.mjs`).
  - 계약이 낡으면 pytest 가, 계약과 fixtures·화면 메타가 어긋나면 웹 테스트가 실패한다.
  - Vercel: Root Directory `simulator`, `main` → Production, `develop` → 브랜치 고정 Preview 주소, PR → 임시 Preview. `simulator/`·`fixtures/`·`contracts/` 가 바뀐 커밋만 빌드. 지금은 Mock 모드라 secret 없음.
  - `repo_rules.py`: `simulator` 모듈 추가(`mod/simulator` 는 `simulator/` 만), `contracts/` 는 리드(core).
- **이유**: Python 과 TypeScript 는 코드 패키지를 공유할 수 없어서 공유 대상은 계약·데이터뿐이다. 폴더 2개면 충분하고, 해커톤 중 경로를 옮기는 비용이 없다.
- **버린 대안**: (a) `apps/desktop`·`apps/simulator`·`packages/*` + pnpm/turborepo 모노레포 — JS 앱이 하나뿐이라 이점이 없고, Python 패키지를 옮기면 문서·CI·팀원 브랜치 경로가 모두 깨진다. (b) 웹앱을 별도 레포로 — fixtures·계약 동기화가 수동이 된다. (c) TS 타입 손 관리 — 어긋남을 못 막는다.
- **영향**: `schemas.py` 를 바꾸면 `export_contracts.py` 를 실행해 함께 커밋해야 한다. 실제 모듈을 웹에서 실행하는 API(HTTP 모드)는 범위 밖이며, 필요하면 Vercel 함수가 아닌 별도 서버(Render·Fly.io)에 둔다(분류 모델 크기).

## ADR-0016: parse · compose · normalize 를 문장 처리 모듈 `text/` 하나로 합친다
- 2026-11-14 / 확정 / 리드
- **배경**: 모듈 폴더가 Stage 단위로 잘게 쪼개져 있었다(`parse/`(parse, compose), `normalize/`). 셋 다 WP3 한 담당이 맡는 문장 처리이고, compose 는 몇 줄짜리라 폴더를 나눌 이유가 없다.
- **결정**: `src/clean_chat/text/` 한 모듈에 둔다. 인터페이스는 `stage.py` 하나(Stage 3개), 구현은 파일 하나에 클래스 하나(`parse.py: Parser`, `compose.py: Composer`, `normalize.py: Normalizer`). 단독 실행은 `python -m clean_chat.text <parse|compose|normalize>`.
- **바꾸지 않은 것**: Stage 이름·계약(`schemas.py`, `contracts/`), fixtures 폴더, 파이프라인, 웹 시뮬레이터 화면. 바뀐 것은 코드 위치와 `repo_rules.py`(모듈 `text`, 브랜치 `mod/text`), CODEOWNERS, 문서뿐이다.
- **버린 대안**: Stage 자체를 하나로 합치기 — 계약·fixtures·시뮬레이터를 모두 바꿔야 하고, 흐름 A/B 입구(parse/compose)와 공통 필터(normalize)의 경계가 사라진다.

## ADR-0017: 모듈을 함수 5개(ocr · parse · analyze · rewrite · report)로 줄이고, 나머지는 구성으로 둔다. Mock 은 없앤다
- 2026-11-14 / 확정 / 리드
- **배경**: Stage 10개, 모듈 폴더 8개(인터페이스 `stage.py` + 구현 클래스 + `setup/run/close` + MockStage)라 5명에게 나눠 주기에 복잡했다. 시뮬레이터와 `clean-chat run` 은 Mock(fixtures 응답)으로 돌아서 구현이 하나도 없는데도 동작하는 것처럼 보였다. E2E 시나리오도 아직 없어 기대값 비교가 의미가 없었다.
- **결정**:
  - 모듈 = **함수 1개**, 5개: ① `ocr` 이미지 → 줄 / ② `parse` 줄 → 채팅만(시스템 메시지·핑 제외, 규칙) + 정규화(옛 normalize) + 내 입력(옛 compose) / ③ `analyze` 누가 누구에게(대상, 옛 policy 의 대상 추정)·등급·유형·비속어·피드백 조각(옛 classify + rewrite 의 피드백 추출) / ④ `rewrite` 순화 문장 / ⑤ `report` 신고 문구·고소장(옛 report + complaint, `kind` 로 구분).
  - 위치: `src/clean_chat/modules/<모듈>/impl.py` 의 `run(입력 모델) -> 출력 모델`. 한 사람 = 한 폴더(모듈 브랜치는 그 폴더·`tests/test_<모듈>.py`·`fixtures/<모듈>/` 만, 브랜치 이름은 ADR-0018).
  - **구성(리드)**: 정책표(`core/policy.py`, SPEC 5장을 코드로 구현), 흐름 연결·프레임 사이 줄 중복 제거(`core/pipeline.py`), 화면 캡처(`core/grabber.py`), 게임 단계·세션, UI, 로컬 모듈 서버, 시뮬레이터.
  - **Mock 제거**: `MockStage`, `--impl mock`, `--real`, 시뮬레이터 Mock 클라이언트·장애 흉내·체크리스트·기대값 비교를 지운다. 구현 전 함수는 `NotImplementedError` → 어디서든 "구현 안 됨" 오류(`ModuleNotImplemented`, CLI 종료 코드 2, 서버 501, 엔진은 멈추고 모듈 이름을 알림).
  - **시뮬레이터 = 함수 호출기**: 입력 JSON(+ OCR 이미지)을 넣고 실행하면 로컬 서버(`uv run clean-chat serve`, 표준 라이브러리 HTTP, 127.0.0.1)가 실제 함수를 부르고 output 만 보여 준다. fixtures 는 입력 예시로만 쓴다.
  - 연결 구조(흐름·정책표·세션·배치) 검증은 테스트 안의 가짜 함수(`tests/helpers.py`)로만 한다.
  - 계약 1.0.0: `NormalizedMessage` → `ChatMessage` 에 합침, `Classification` → `Analysis`, `OutgoingText`·`PolicyRequest`·`ComplaintRequest`·`ComplaintDraft` 삭제. `contracts/stages.schema.json` → `modules.schema.json`.
- **이유**: 5명이 "함수 하나"만 보면 되고 경계가 폴더로 분명하다. 처리 결정(정책표)은 표를 옮기는 일이라 모듈로 둘 만큼 크지 않다. Mock 이 없으면 구현 여부가 실행 결과에 그대로 드러난다.
- **버린 대안**: (a) Stage 10개 유지하고 사람만 묶기 — 인터페이스·Mock·하위 Stage 명령이 그대로 복잡하다. (b) normalize 를 analyze 에 — 작업량이 가장 큰 analyze 에 몰려 parse(규칙)에 둔다. (c) 시뮬레이터를 Vercel 파이썬 함수로 — OCR·분류 모델이 용량 제한(250MB)을 넘는다. 배포 주소는 화면만 보이고, 실행은 로컬에서 한다.
- **영향**: ADR-0011(Stage 구조), ADR-0016(text 모듈)을 대체한다. 모듈 5개가 모두 구현되기 전에는 `clean-chat run/say/app` 이 끝까지 돌지 않는다. pyproject extra 이름도 `capture` → `ocr`, `ml` → `analyze`.

## ADR-0018: 브랜치 규칙은 `main` 보호 하나만 두고, 모듈 작업은 `<모듈>/<작업 내용>` 브랜치 + 모듈 범위 CI 검사로 본다
- 2026-11-14 / 확정 / 리드
- **배경**: 브랜치 이름 정규식(`mod/<모듈>-<주제>`, `fix/…` 등), PR 제목 형식, "main 에는 develop 에서만" 검사가 팀원에게 헷갈리기만 했다. 실제로 리드가 알고 싶은 것은 "이 PR 이 자기 모듈 범위를 넘었나" 하나다.
- **결정**:
  - GitHub 규칙은 `protect-main`(PR 필수, 다른 팀원 승인 1명, force push·삭제 금지) 하나만 둔다.
  - 브랜치 이름·PR 제목 형식 검사, develop → main 전용 검사, pre-commit 브랜치 이름 훅, `cross-module` 라벨을 없앤다.
  - 모듈 작업 브랜치는 `<모듈>/<작업 내용>`(예: `parse/colon-fix`). PR 이 열리면 CI `module-scope`(`.github/workflows/pr-rules.yml`, `scripts/check_module_boundary.py`)가 모듈 범위(`src/clean_chat/modules/<모듈>/`, `tests/test_<모듈>.py`, `fixtures/<모듈>/`) 밖 파일 변경을 찾아 실패시킨다. 그 밖의 브랜치 이름은 자유이고 검사하지 않는다.
  - 실패는 병합을 막지 않는다(필수 검사 아님). 리드가 리뷰에서 "모듈 범위를 넘는 변경"으로 보고 거절하거나 참고한다.
- **이유**: 규칙이 하나라서 설명이 쉽고, 리뷰에 필요한 신호(범위 초과)만 자동으로 준다.
- **영향**: ADR-0009 의 브랜치 이름·PR 제목 강제를 대체한다. 규칙 원본은 `scripts/repo_rules.py`(`MODULES`, `module_scope`).

## ADR-0019: 시뮬레이터는 로컬 전용으로, 파이썬이 화면까지 제공한다 (Vercel·Next.js 제거). 실행 명령은 `sim`, `app` 두 개
- 2026-11-14 / 확정 / 리드
- **배경**: 시뮬레이터의 목적은 비개발자가 바이브 코딩으로 만든 모듈 하나를 직관적으로 실행해 보는 것이다. OCR·경량 LLM 모듈은 Vercel 에서 돌릴 수 없고, 별도 파이썬 서버 운영은 부담이다. Next.js + 파이썬 서버를 따로 띄우는 구조와 많은 CLI 옵션이 헷갈렸다.
- **결정**:
  - `src/clean_chat/sim/`: 표준 라이브러리 HTTP 서버(127.0.0.1)가 HTML 화면(`static/`, 빌드 없음)과 API 를 함께 준다. 새 패키지·Node 없음.
  - 화면은 3칸: **입력**(간단 입력 = 텍스트·이미지 / JSON 직접 + fixtures 예시) · **디버깅 콘솔**(stdout·stderr 실시간) · **반환값**(상태 + return JSON).
  - 실행마다 새 파이썬 프로세스(`sim/worker.py`). 모듈 코드를 고치면 바로 반영되고, print·logging·traceback 이 모두 보이며, 멈추거나 죽어도 서버는 산다. 제한 시간 `settings.sim_timeout_sec`(120초), 중지 버튼·창 닫기 시 프로세스 종료.
  - 실행 명령은 `uv run sim [모듈]`, `uv run app`(Windows = 실제 화면, 그 밖 = 데모 재생) 두 개만. `clean-chat` 명령과 하위 명령·옵션은 없앤다.
  - Vercel 프로젝트 `clean-chat-simulator` 삭제, `simulator/`(Next.js), `simulator.yml`, `contracts/`·`export_contracts.py` 삭제(웹 TS 타입용이라 쓰는 곳이 없음; 화면은 `/api/modules` 의 JSON Schema 를 쓴다).
- **이유**: 설치·실행이 `uv sync` + `uv run sim` 으로 끝난다. 무거운 모듈도 각자 PC 에서 그대로 돈다.
- **버린 대안**: (a) Next.js 유지 + 명령 하나로 둘 다 실행 — 모두 Node 설치 필요. (b) 서버 프로세스 안에서 실행 — 코드 수정 시 재시작 필요, C 라이브러리 출력·크래시를 못 잡는다(대가: 실행마다 모델을 다시 불러와 느릴 수 있음).
- **영향**: ADR-0015 를 대체하고, ADR-0017 의 시뮬레이터 부분(로컬 서버 `clean-chat serve` + Next.js)을 갱신한다.
