# HANDOFF — Claude Code 인수인계 문서

> 이 문서는 claude.ai에서 정리한 내용을 데스크톱의 Claude Code로 넘기기 위한 문서입니다.
> **Claude Code는 이 파일을 가장 먼저 읽고, 맨 아래 "작업 지시"를 따릅니다.**
> 작성: 2026-11-12 · 작성자: 리드 + Claude

---

## 0. 사용법 (사람용)
1. `lol-guard-starter.zip`의 압축을 풀고 폴더로 이동합니다.
2. 터미널에서 `claude`를 실행합니다.
3. 첫 메시지로 아래를 붙여넣습니다.
   ```
   HANDOFF.md를 처음부터 끝까지 읽고, 9장 "작업 지시"를 순서대로 진행해 줘.
   각 단계 시작 전에 계획을 보여 주고, 내가 확인하면 진행해.
   ```

---

## 1. 프로젝트 요약
- **무엇**: 리그 오브 레전드 게임 중 악성 채팅(욕설, 패드립, 성희롱, 비난, 정치질)을 감지해 숨기거나 피드백만 남겨 보여 주는 앱입니다. 내가 치는 채팅도 같은 필터를 거치고, 게임이 끝나면 신고 문구와 고소장 초안(PDF)을 만들어 줍니다.
- **형태**: 해커톤형 데모. 발표 전 주말 3번 중 마지막 주말은 데모 완성과 발표 자료 제작에 씁니다. 유저 테스트는 없습니다.
- **팀**: 팀명 "내 고통을 느껴라". 5명 = 개발자 2명(macOS, 리드 포함) + 바이브 코더 3명(이 중 2명 이상 Windows + 롤 설치). AI 도구는 Claude, GPT(Codex), Gemini를 섞어 씁니다.
- **실행 환경**: 실제 앱은 **Windows**에서 돌고, 개발은 **Mac**에서도 해야 합니다(clone, 설치, 모듈 단독 실행, 테스트).
- **레포 이름**: `tiltguard` 추천(미확정). 현재 코드의 패키지 이름은 `lolguard`이며, 이름에 lol은 넣지 않기로 했습니다.

## 2. 확정된 결정 (자세한 이유: docs/DECISIONS.md)
| ADR | 결정 |
|---|---|
| 0001 | 클라우드 서버 없이 로컬 단일 파이썬 프로그램 |
| 0002 | 채팅 수집은 **화면 캡처 + OCR**. Overwolf, LCU 채팅, 메모리 읽기와 드라이버는 사용하지 않음(Vanguard 위험, 기록 금지 조건 등) |
| 0003 | 오버레이는 화면 캡처에서 제외(`SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`). **실측 필요** |
| 0004 | UI는 PySide6 하나로 만듦(클라이언트 창 + 오버레이 창) |
| 0005 | AI는 빠른 분류기(KcBERT 계열)를 모든 채팅에 쓰고, LLM은 악성 채팅의 리라이트와 고소장 요약에만 씀 |
| 0006 | 내 채팅은 가상 키 입력 없이 **클립보드 복사** → 사용자가 직접 붙여넣기 |
| 0007 | 신고는 **문구 복사**만. 자동 신고 금지 |
| 0008 | 고소장은 고정 양식에 사실을 채우고 한글 PDF로 출력. "법률 자문 아님" 고지 |
| 0009 | 브랜치, PR 제목, 린트·포맷, 모듈 경계 규칙을 CI로 강제 |
| 0010 | 모듈 브랜치 `mod/<모듈>` → `dev`(주말 통합) → `main`(발표용) |
| 0011 | 모든 처리 모듈 = Stage(입력 1 → 출력 1) + mock(fixtures) + 단독 실행기 |
| 0012 | Windows 전용 코드는 `capture/grabber.py`, `ui/win32.py` 두 곳으로 격리. CI는 macOS와 Windows 모두에서 실행 |

## 3. 처리 규칙 요약 (자세히: docs/SPEC.md 4~5장)
- **등급**: L0 정상 / L1 경미(대상 없는 혼잣말 비속어) / L2 악성(특정인 비난, 욕설, 정치질) / L3 법적 대응 후보(패드립, 성희롱, 심한 모욕)
- **유해 유형**(여러 개 가능): `profanity`(욕설), `family_insult`(패드립), `sexual_harassment`(성희롱), `blame`(비난), `instigation`(정치질)
- `has_feedback`: L2 이상 채팅에 게임 플레이 지적이나 방향 제시가 섞여 있는지
- **타 유저 채팅**:
  - L0 → 그대로 표시
  - L1 → 비속어만 가려서 표시
  - L2 + 피드백 → 피드백만 다듬어 표시하고 원문은 신고 목록에
  - L2 → 숨기고 신고 목록에
  - L3 → 숨기고 신고 목록 + 고소장 후보에
- **내 채팅**:
  - L0 → 그대로 복사
  - L1 → 비속어만 가려서 복사
  - L2 + 피드백 → 피드백만 다듬어 복사
  - 그 외 → 전송 차단
- 분류(classify)는 **분류만** 하고, 처리 결정은 policy가 합니다.

## 4. 현재 스타터 상태 (이 zip)
- 구조: `src/lolguard/<모듈>/{stage.py, impl.py, __main__.py, README.md}`, `core/`(schemas, stage, registry, pipeline, engine, sources, runner, platform, config), `ui/`(PySide6 뼈대)
- 모든 `impl.py`는 `NotImplementedError`만 있고 로직은 없습니다.
- `fixtures/<stage>/input.jsonl → expected.jsonl`이 통신 포맷 예시이자 명세입니다. 목(mock)은 이 예시를 그대로 응답합니다.
- 명령:
  - `uv run lolguard run --source demo`: 전체 흐름
  - `uv run python -m lolguard.<모듈> --impl mock --check`: 모듈 단독 실행
  - `uv run lolguard app --source demo`: UI
- 상태: 테스트 27개 통과, 9개는 미구현이라 건너뜀. ruff 통과. PySide6 화면 없는 모드 실행 확인. **실제 Mac과 Windows 실행은 아직 확인하지 않음.**
- 문서: SPEC, ARCHITECTURE, MODULES(작업 패키지 WP1~7), CONTRACTS, DECISIONS, DATA, LABELING_GUIDE, OPEN_QUESTIONS, SETUP, GITHUB_SETTINGS, CONTRIBUTING, AGENTS.md

## 5. 아직 반영 안 된 변경 사항 ← Claude Code가 할 일

### 5-1. 기능을 두 흐름으로 분리
| | A. 다른 유저 채팅 (수신) | B. 내 입력 (송신) |
|---|---|---|
| 계기 | 캡처 주기(0.4초)마다 자동 | 오버레이 입력칸에서 Enter |
| 실행 | 백그라운드 스레드, 스트림 | 동기 요청-응답 |
| 입구 | Frame → `ocr` → `parse` | 텍스트 → `ChatMessage` 바로 생성 (`compose` 단계) |
| 공통 | `normalize` → `classify` → (조건부) `rewrite` | 같음 |
| 정책 | `incoming_policy` (타 유저 표) | `outgoing_policy` (내 채팅 표) |
| 출구 | 오버레이 표시 + **세션 기록** | 클립보드 복사 / 차단 안내 |
| 특이점 | **최근 내가 보낸 문장이 OCR로 다시 읽히면 건너뜀** | – |

- `policy` Stage를 `incoming_policy`와 `outgoing_policy`로 나눕니다. fixtures도 나눕니다.
- `Pipeline`을 `IncomingPipeline`(process_frame, process_line)과 `OutgoingPipeline`(submit(text) → Incident)으로 나눕니다.

### 5-2. 게임 단계 (상태 기계)
```
대기(IDLE) ──InProgress──▶ 게임 중(IN_GAME) ──EndOfGame──▶ 게임 종료(POST_GAME) ──사용자 닫음──▶ 대기
```
| 단계 | 화면 | 처리 |
|---|---|---|
| IDLE | 클라이언트 창만 | 지난 처리 내역, 설정 |
| IN_GAME | 오버레이 표시 | 흐름 A·B 실행, `GameSession`에 Incident 기록, 플레이어 명단 갱신 |
| POST_GAME | 오버레이 숨김, "이번 게임 결과" 화면 | 캡처 중지 → 세션 전체를 배치 처리해 신고 문구와 고소장 초안 생성 |

- **단계 감지기**(새 모듈 `session/`):
  - Windows: LCU `/lol-gameflow/v1/gameflow-phase`를 1~2초마다 읽음(읽기 전용). 보조 수단으로 Live Client Data API(`https://127.0.0.1:2999/liveclientdata/...`)가 응답하는지 확인하고, 플레이어 명단도 여기서 받음. 단계 이름은 **실측 필요**.
  - Mac: 가짜 감지기(시나리오 JSONL에 `{"phase": ...}` 이벤트).
- 새 스키마: `GamePhase`(IDLE, IN_GAME, POST_GAME), `PhaseEvent`(ts, phase, raw), `GameSession`(id, started_at, ended_at, players, incidents)
- `report`와 `complaint`의 입력을 `GameSession` 기반으로 바꾸고, **POST_GAME에서만** 실행합니다.
- 세션 저장소: `.lolguard/sessions/<id>.jsonl` (로컬 전용, git 제외)

### 5-3. 디자인 패턴 (ARCHITECTURE.md에 명시)
| 위치 | 패턴 |
|---|---|
| 앱 전체 | **상태 기계(State)** + **이벤트 기반 발행·구독(Observer)** |
| 흐름 A | **파이프-필터(Pipes and Filters)** |
| 흐름 B | 같은 필터를 동기 요청-응답으로 재사용 |
| 게임 종료 후 | **배치 처리 + 저장소(Repository)** |
| real/mock, LLM 백엔드, OCR 엔진 | **Strategy + Registry(Factory)** |
| 입력 소스 | **포트와 어댑터(Hexagonal)** |
| UI | MVP에 가까운 구조(보여 주기만, 판단 없음) |

### 5-4. 작업 패키지 갱신
- 기존 WP1~WP7은 유지합니다.
- **WP8 세션·단계 감지**(session/, Windows 실측 필요)를 추가합니다.
- WP1의 policy는 incoming과 outgoing 두 개가 됩니다.

### 5-5. 이름 변경 (리드가 확정하면)
> ✅ 적용됨 (2026-11-12): 레포·패키지·명령 `clean-chat`, import·폴더 `clean_chat` (`src/clean_chat/`), 저장 폴더 `.clean-chat/`. 같은 때 통합 브랜치를 `dev` → `develop`으로 바꿨습니다. 이 문서의 나머지 `lolguard` 표기는 작성 당시 이름입니다.
- `lolguard` → `tiltguard`(또는 확정된 이름): 패키지 폴더, `pyproject.toml`(name, scripts), import, 문서, CLI 명령, `.lolguard/` 저장 폴더, CODEOWNERS, `scripts/repo_rules.py`

## 6. 스텁(뼈대) 작성 규칙 — "로직 없이 주석으로 함수만"
- 각 `impl.py`(와 새 모듈)에는 **들어가야 할 함수와 메서드의 시그니처, 타입 힌트, docstring만** 둡니다. 본문은 `raise NotImplementedError("<모듈> 담당: <함수> 구현")` 한 줄입니다.
- docstring에는 다음을 적습니다: ① 무엇을 하는지 ② 입력과 출력 ③ 예시 1개(fixtures 기준) ④ 주의할 점 ⑤ 관련 ADR/OPEN 번호
- 공개 함수 `run()`과 그 아래 **내부 helper 함수 후보**(예: `_preprocess_image`, `_dedupe_lines`)까지 시그니처로 쪼개 둡니다. 담당자가 하나씩 채우면 되게 합니다.
- **조건문, 반복문, 정규식, 실제 라이브러리 호출을 쓰지 않습니다.** (core의 실행 기반인 stage/registry/pipeline/engine/runner/sources는 예외로, 지금처럼 동작해야 합니다)
- 예시:
```python
class Parser(ParseStage):
    """[구현 · WP3] RawLine → ParseResult  (명세: docs/MODULES.md#parse)"""

    def setup(self) -> None:
        """채널 표기·핑 문구 사전 로딩. 앱 시작 시 1번."""
        raise NotImplementedError("parse 담당: setup")

    def run(self, item: RawLine) -> ParseResult:
        """한 줄을 채널/화자/챔피언/본문으로 분해한다.
        예) "[팀] 원딜러 (징크스): 용 먼저 치라고" → team, 원딜러, 징크스, "용 먼저 치라고"
        잡음 줄이면 message=None. 순서: _split_channel → _split_speaker → _classify_channel
        """
        raise NotImplementedError("parse 담당: run")

    def _split_channel(self, text: str) -> tuple[str | None, str]:
        """ "[팀] ..." 에서 채널 표기와 나머지를 분리. OCR 오인식([ ↔ ( ) 고려."""
        raise NotImplementedError

    def _split_speaker(self, rest: str) -> tuple[str | None, str | None, str]:
        """ "닉네임 (챔피언): 본문" → (닉네임, 챔피언, 본문)"""
        raise NotImplementedError

    def _classify_channel(self, tag: str | None, body: str) -> Channel:
        """팀/전체/핑/시스템 판별. 핑·스펠체크 문구 목록은 OPEN-09."""
        raise NotImplementedError
```
- UI 파일(`client.py`, `overlay.py`)은 위젯 배치 뼈대는 유지하고, 동작 메서드는 같은 방식의 스텁으로 둡니다.

## 7. 완료 기준 (Claude Code가 마지막에 확인)
- [ ] `uv sync` → `uv run ruff check .` → `uv run ruff format --check .` → `uv run pytest -q` 모두 통과 (미구현은 skip)
- [ ] `uv run <패키지> run --source demo`로 단계 전환(IDLE → IN_GAME → POST_GAME)과 흐름 A, 신고 생성(mock)이 콘솔에 보임
- [ ] `uv run python -m <패키지>.<모듈> --impl mock --check`가 모든 Stage에서 통과
- [ ] 흐름 B를 단독으로 확인할 명령이 있음(예: `uv run <패키지> say "정글 ㅂㅅ 왜 안 와"` → mock 결과)
- [ ] docs/SPEC, ARCHITECTURE(패턴 표와 mermaid 그림 2개: 두 흐름, 상태 기계), MODULES(WP8 포함), CONTRACTS(새 스키마), DECISIONS(ADR-0013 두 흐름 분리, ADR-0014 게임 단계와 세션) 갱신
- [ ] AGENTS.md의 구조와 명령어 갱신
- [ ] Windows 전용 코드는 `capture/grabber.py`, `ui/win32.py`, `session/` 안의 Windows 감지기로만 한정

## 8. 미결정 항목 (docs/OPEN_QUESTIONS.md)
- OPEN-02: 오버레이 캡처 제외 실측
- OPEN-03: OCR 엔진 (Windows 내장 / PaddleOCR / EasyOCR)
- OPEN-04: LLM 실행 위치 (로컬 / API / 데모만 API). 추천은 "데모만 API"
- OPEN-07: L1 마스킹 여부
- OPEN-09: 핑 범위
- **신규**: LCU 게임 진행 단계 이름과 전환 시점 실측, 내가 보낸 채팅의 중복 판단 기준
- 레포 이름 확정, GitHub 요금제(비공개 레포에서 병합 규칙을 강제할지)

## 9. 작업 지시 (Claude Code용)
순서대로 진행하고, 단계마다 계획을 먼저 보여 준 뒤 확인을 받습니다.

1. **현황 파악**: AGENTS.md, docs/SPEC.md, docs/ARCHITECTURE.md, docs/MODULES.md, `src/*/core/schemas.py`를 읽고 이 문서와 다른 점을 보고합니다.
2. **이름 변경**(5-5): 리드에게 최종 이름을 물어보고 적용합니다.
3. **스키마 추가**: `GamePhase`, `PhaseEvent`, `GameSession`. 그리고 report와 complaint 요청을 세션 기반으로 바꿉니다.
4. **두 흐름 분리**(5-1): incoming_policy와 outgoing_policy Stage, `compose` 단계, IncomingPipeline과 OutgoingPipeline, fixtures를 분리하고 갱신합니다.
5. **session 모듈**(5-2): 단계 감지기 인터페이스, Windows 감지기 스텁, Mac 가짜 감지기, 상태 기계, 세션 저장소 스텁. Engine에 단계 이벤트를 연결합니다.
6. **모든 impl.py를 6장 규칙으로 다시 작성**(helper 시그니처까지).
7. **UI 뼈대 갱신**: 단계에 따른 오버레이 표시/숨김, "이번 게임 결과" 화면 자리.
8. **문서 갱신**(7장 목록) + mermaid 그림.
9. **검증**(7장 체크리스트) 후 변경 요약을 보고합니다.

## 10. 진행 상황 (Claude Code, 2026-11-12)
9장 1~8단계를 `develop`에 반영했습니다. 9단계(검증) 결과와 남은 일은 커밋 기록과 아래를 봅니다.
- 이름: `clean-chat`(레포·패키지·명령), `clean_chat`(import), `.clean-chat/`(저장). 통합 브랜치 `develop`, `main`만 보호(`docs/GITHUB_SETTINGS.md`)
- 두 흐름(ADR-0013), 게임 단계·세션(ADR-0014), 모든 `impl.py` 스텁(6장 규칙), UI 단계별 화면 뼈대
- 새 미결정: OPEN-12(LCU 단계 이름 실측), OPEN-13(내 채팅 중복 기준)
- 남은 일: CODEOWNERS 아이디, WP 배정, OPEN 항목 실측, 실제 Windows 실행 확인
- (2026-11-14) 웹 시뮬레이터 `simulator/` 추가(PR #2), 공통 계약 `contracts/` + Vercel 배포(PR #3, ADR-0015). Vercel 프로젝트 `clean-chat-simulator`, develop 주소는 `simulator/README.md`
