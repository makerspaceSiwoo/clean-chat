# AGENTS.md — AI 코딩 에이전트 공통 규칙

> **새 세션이라면 `HANDOFF.md`를 먼저 읽으세요.**
> Claude Code(`CLAUDE.md` → 이 파일), Codex(직접 읽음), Gemini CLI(`.gemini/settings.json` → 이 파일)가 모두 이 파일을 먼저 읽습니다.
> 웹 채팅으로 작업할 때는 `uv run python scripts/pack_context.py <모듈>`로 묶음 파일을 만들어 첨부하세요.

## 1. 프로젝트 요약
Clean Chat은 **리그 오브 레전드 게임 중 악성 채팅을 감지하고 필터링하는 Windows 데스크톱 앱(2주 데모)** 입니다.
게임이 시작되면 자동으로 화면 OCR로 채팅창을 읽고 → 채팅만 뽑아 → 누가 누구에게 얼마나 나쁜 말을 했는지 분석하고 → 등급에 따라 숨김, 피드백만 표시를 합니다. 내가 쓰는 채팅도 같은 필터를 거칩니다.
게임이 끝나면 이번 게임 기록으로 신고 문구와 고소장 초안(PDF)을 만듭니다.
- 무엇을, 왜: `docs/SPEC.md`
- 왜 이렇게 만들었나: `docs/DECISIONS.md` (새 결정은 여기에 추가)
- 구조: `docs/ARCHITECTURE.md`
- 모듈 사이 데이터 형식: `docs/CONTRACTS.md`, 코드 기준은 `src/clean_chat/core/schemas.py`
- 모듈 5개 명세와 배정: `docs/MODULES.md`
- 아직 정해지지 않은 것: `docs/OPEN_QUESTIONS.md`

## 2. 구조 (자세히: docs/ARCHITECTURE.md)
```
게임 단계:  IDLE(대기) ─게임 시작─▶ IN_GAME(게임 중) ─게임 끝─▶ POST_GAME(결과 화면) ─사용자 닫음─▶ IDLE
흐름 A (다른 유저 채팅, 게임 중 자동):  [🪟 캡처] ─Frame→ ①ocr → (줄 중복 제거) → ②parse ─┐
흐름 B (내 입력, 오버레이 Enter):        내 문장(source=self_input) → ②parse ───────────┤
공통:  ③analyze → (L2 이상 & 피드백 조각) ④rewrite ─┬→ 정책표(다른 유저) → 오버레이 + 세션 기록   (A)
                                                 └→ 정책표(내 채팅) → 클립보드 / 차단           (B)
게임 종료:  GameSession → ⑤report(kind=report 신고 문구 / complaint 고소장 PDF)
```
- **모듈 = 함수 1개 × 5개** (ADR-0017): `src/clean_chat/modules/<모듈>/impl.py` 의 `run(입력) -> 출력`. 5명이 한 폴더씩 맡습니다. 목록: `uv run clean-chat modules`
  - ① `ocr` 이미지 → 줄 · ② `parse` 줄 → 채팅만(시스템 메시지 제외) + 정규화 · ③ `analyze` 대상·등급·피드백 · ④ `rewrite` 순화 · ⑤ `report` 신고·고소장
  - 그 밖(흐름 연결, 정책표, 캡처, 게임 단계, UI, 로컬 서버, 시뮬레이터)은 **구성**이고 리드가 `core/`, `ui/`, `session/`, `simulator/` 에서 합니다.
- `run()` 의 시그니처와 docstring이 할 일 목록입니다. docstring의 예시·순서·주의를 따라 본문을 채우세요.
- 통신 포맷 = `core/schemas.py`의 pydantic 모델, 연결표 = `core/modules.py`, 예시 = `fixtures/<모듈>/input.jsonl → expected.jsonl` (**이 예시가 명세**)
- **Mock 은 없습니다.** 구현 전 함수는 `NotImplementedError` 이고, 앱·시뮬레이터는 실행하면 "구현 안 됨" 오류를 냅니다.
- **analyze 는 "누가 누구에게, 얼마나 나쁜가"만 판단하고, 처리(숨김·신고 등)는 정책표(`core/policy.py`)가 결정합니다.** 섞지 마세요.
- 게임 단계 전환과 세션 기록은 `core/game.py`(상태 기계, 리드)가 합니다. 단계 감지기(`session/`)는 단계를 보고만 합니다.
- 실제 앱은 Windows, 개발은 Mac. Windows 전용 코드는 `core/grabber.py`, `ui/win32.py`, `session/windows.py`(구성)에만 둡니다. OCR 엔진은 모듈 안에서 Windows 전용 import 를 함수 안에 둡니다.
- 웹 시뮬레이터(`simulator/`, Next.js)는 **별도 앱**입니다. 파이썬 코드를 import 하지 않고 `contracts/`, `fixtures/`(입력 예시)를 읽고, 실행은 로컬 서버(`uv run clean-chat serve`)의 실제 함수를 HTTP 로 부릅니다. 작업 규칙은 `simulator/README.md`.

## 3. 반드시 지킬 규칙
1. **자기 모듈 폴더(`src/clean_chat/modules/<모듈>/`) 밖은 수정하지 않습니다.** CI가 검사합니다(`scripts/check_module_boundary.py`).
2. **`core/schemas.py`와 각 모듈의 `run()` 이름, 입력/출력 타입은 바꾸지 않습니다.** 필요하면 "계약 변경 요청" 이슈를 올립니다. (리드가 `schemas.py`를 바꾸면 `uv run python scripts/export_contracts.py`로 `contracts/`를 다시 만들어 함께 커밋합니다 — 웹 시뮬레이터가 이 파일을 씁니다.)
3. **새 패키지를 추가하기 전에 사용자에게 먼저 물어봅니다.** 추가할 때는 `pyproject.toml`의 해당 모듈 extra에 넣습니다(`uv add --optional <모듈> <패키지>`).
4. 판단 로직은 해당 모듈에만 둡니다. UI에 분류나 정책 로직을 넣지 않습니다.
5. 실제 유저 채팅 원문, 닉네임, 스크린샷, 모델 가중치, `.env`는 커밋하지 않습니다.
6. 작업이 끝나면 아래 "확인 명령"을 모두 실행하고 통과시킵니다.

## 4. 절대 금지 (계정 정지·법적 위험)
- 게임 프로세스 메모리 읽기·쓰기, 드라이버, DLL 주입, 패킷 가로채기, Vanguard 우회
- 게임에 가상 키보드·마우스 입력 보내기 (내 채팅은 **클립보드 복사**만, ADR-0006)
- 자동 신고 (신고는 **문구 복사**만, ADR-0007)
- LCU로 채팅 읽기나 게임 조작 요청 (LCU는 게임 단계 **읽기 전용 GET**만, ADR-0014)

## 5. 명령어
```bash
uv sync                                                  # 설치 (UI 작업: uv sync --extra ui)
uv run clean-chat modules                                # 모듈 5개와 구현 위치
uv run clean-chat module <모듈>                          # 내 함수를 fixtures 입력으로 실행 (구현 전이면 "구현 안 됨", 종료 코드 2)
uv run clean-chat module <모듈> --check                  # 기대값과 비교
uv run clean-chat serve                                  # 웹 시뮬레이터용 로컬 모듈 서버 (→ cd simulator && npm run dev)
uv run python -m clean_chat.session                      # 게임 단계 감지기 (가짜, --real 은 Windows)
uv run clean-chat run --source demo                      # 전체 흐름 (모듈 5개가 구현돼야 끝까지 돎)
uv run clean-chat say "아 정글 ㅂㅅ 왜 안 와"               # 흐름 B(내 입력) 1문장
uv run clean-chat app --source demo                      # UI 앱 (Mac 가능)
uv run clean-chat app --source screen                    # 실제 데모 (Windows)

# 확인 명령 (PR 전에 모두 통과해야 함)
uv run ruff check . --fix && uv run ruff format .
uv run pytest -q
```

## 6. 코드 스타일
- Python 3.11, 타입 힌트 필수, 데이터는 pydantic 모델(`core/schemas.py`)로 주고받습니다.
- ruff가 포맷과 린트를 담당합니다(줄 길이 120). 직접 스타일을 맞추려 하지 마세요.
- 주석과 문서는 한국어로 쓰고, 코드 식별자는 영어로 씁니다.
- 함수는 작게 만들고, 새 기능에는 `tests/test_<모듈>.py`에 테스트를 1개 이상 추가합니다.
- 구현은 내 모듈 폴더(`modules/<모듈>/`)의 `impl.py`와 내부 파일에만 합니다. 다른 모듈 폴더를 import하지 않습니다.
- 각 모듈은 `fixtures/<모듈>/`의 입력만으로 혼자 실행하고 테스트할 수 있어야 합니다.
- Windows 전용 라이브러리는 **함수 안에서 import**, `pyproject.toml`에는 `; sys_platform == 'win32'` 마커를 붙입니다. 테스트에는 `@pytest.mark.windows`를 붙입니다(Mac에서 설치와 테스트가 깨지지 않게).

## 7. 작업 방식
- 작업 시작 전에 내 모듈의 `README.md`(`src/clean_chat/modules/<모듈>/README.md`)를 읽습니다.
- 큰 작업은 먼저 계획을 사용자에게 보여 주고 확인을 받은 뒤 진행합니다.
- 결정한 것이 있으면 `docs/DECISIONS.md`에 ADR로 추가하자고 사용자에게 제안합니다.
- 브랜치와 PR 규칙은 `CONTRIBUTING.md`를 따릅니다.
