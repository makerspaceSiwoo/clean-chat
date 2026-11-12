# 아키텍처 (Python + PySide6)

> "어떻게 생겼나"를 설명하는 문서입니다. 모듈별 역할은 `docs/MODULES.md`, 데이터 형식은 `docs/CONTRACTS.md`를 보세요.

## 1. 한 장 요약

```
┌──────────────────────────── UI 계층 (PySide6) ─────────────────────────────┐
│  ClientWindow (처리 내역·신고·고소장)        OverlayWindow (가림막·필터 채팅·입력) │
│              ▲ Qt Signal                          │ 내 채팅 텍스트              │
│        EngineBridge ◀──────────────────────────────┘                        │
└──────────────▲──────────────────────────────────────────────────────────────┘
               │ Incident (콜백)
┌──────────────┴─────────── 실행 계층 (core) ──────────────────────────────────┐
│ Engine (백그라운드 스레드)  ──  Source ──▶ Pipeline ──▶ 구독자들             │
│   Source: DemoLineSource | ScreenshotSource | ScreenGrabber(🪟)             │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │ Stage.run(입력 모델) → 출력 모델
┌──────────────────────────── 처리 계층 (Stage 8개) ──────────────────────────┐
│ ocr → parse → normalize → classify → [rewrite] → policy      report/complaint │
│  각 Stage = stage.py(인터페이스) + impl.py(실제) + MockStage(fixtures 응답)    │
└──────────────────────────────────────────────────────────────────────────────┘
               ▲ 모든 데이터는 core/schemas.py 의 pydantic 모델 (JSONL 직렬화)
```

## 2. 핵심 패턴: Stage

| 구성 | 파일 | 소유 | 설명 |
|---|---|---|---|
| 인터페이스 | `<모듈>/stage.py` | 리드 | `name`, `input_model`, `output_model`, `mock_default()` |
| 실제 구현 | `<모듈>/impl.py` (+ 내부 파일 자유) | 모듈 담당 | `setup()`, `run(입력) -> 출력`, `close()` |
| 가짜 구현 | `core/stage.py: MockStage` | 자동 | `fixtures/<name>/input.jsonl` → `expected.jsonl` 그대로 응답 |
| 단독 실행 | `<모듈>/__main__.py` | 자동 | `python -m lolguard.<모듈>` |
| 등록 | `core/registry.py` | 리드 | 이름 → 인터페이스·구현 연결 |

**웹 비유**: Stage = 요청·응답 스키마가 고정된 API 엔드포인트, MockStage = MSW 같은 목 서버, fixtures = API 문서의 요청·응답 예시입니다.

### 왜 이 구조인가 (ADR-0011)
- **모듈마다 real과 mock을 골라 끼울 수 있습니다.** `lolguard run --real parse` → parse만 실제, 나머지는 mock. 다른 사람의 작업이 끝나지 않아도 내 모듈을 전체 흐름 안에서 시험할 수 있습니다.
- **구현하는 순간 테스트가 켜집니다.** `tests/test_real_impls.py`는 `NotImplementedError`이면 skip하고, 구현되면 자동으로 형식과 기대값을 검사합니다.
- fixtures의 `expected.jsonl`이 곧 **명세**입니다. "이 입력에는 이 출력"을 예시로 못 박아 둡니다.

## 3. 실행 모드와 OS (ADR-0012)

| 명령 | 소스 | Mac | Windows | 용도 |
|---|---|---|---|---|
| `python -m lolguard.<모듈>` | fixtures | ✅ | ✅ | 모듈 단독 개발·테스트 |
| `lolguard run --source demo` | 시나리오 JSONL | ✅ | ✅ | 콘솔로 전체 흐름 확인 |
| `lolguard run --source screenshots` | PNG 폴더 | ✅ | ✅ | OCR 포함 흐름 확인 |
| `lolguard app --source demo` | 시나리오 | ✅ | ✅ | UI 개발 (게임 없이) |
| `lolguard app --source screen` | 실제 화면 캡처 | ❌ | ✅ | **실제 데모** |

- Windows 전용 코드는 딱 2곳입니다: `capture/grabber.py`(화면 캡처), `ui/win32.py`(오버레이 캡처 제외). 둘 다 `core/platform.py`의 `require_windows()` / `IS_WINDOWS`로 막습니다.
- Windows 전용 라이브러리는 **함수 안에서 import**하고, `pyproject.toml`에 `; sys_platform == 'win32'` 마커를 붙입니다. 그래야 Mac에서 `uv sync`가 깨지지 않습니다.
- CI는 **macOS와 Windows 두 곳**에서 설치, 린트, 테스트를 모두 돌립니다.

## 4. 스레드 구조 (데스크톱 앱 초보자용)
```
메인 스레드 (Qt 이벤트 루프)  ── 화면 그리기, 버튼 클릭     ← 여기서 오래 걸리는 일 금지 (앱이 멈춤)
백그라운드 스레드 (Engine)   ── 캡처 → OCR → 분류 → 정책   ← 무거운 일은 전부 여기
          └─ 결과(Incident) → EngineBridge.incident Signal → 메인 스레드에서 화면 갱신
```
- 내 채팅 입력은 1문장이라 메인 스레드에서 `pipeline.process_line()`을 바로 호출합니다. LLM 때문에 느려지면 rewrite 담당과 협의해 백그라운드로 옮깁니다.

## 5. 폴더 구조
```
src/lolguard/
├─ __main__.py         CLI (run / app / modules)
├─ core/               [WP1] 계약·실행 기반
│  ├─ schemas.py         통신 포맷 (모든 모델)
│  ├─ stage.py           Stage 틀, MockStage, JSONL 입출력
│  ├─ registry.py        Stage 등록표
│  ├─ pipeline.py        Stage 연결 순서 (판단 로직 없음)
│  ├─ engine.py          백그라운드 실행 + 구독
│  ├─ sources.py         입력 소스 (demo / screenshots)
│  ├─ runner.py          모듈 단독 실행기
│  ├─ platform.py        OS 구분
│  └─ config.py          설정 (모듈별 real/mock 포함)
├─ capture/  stage.py impl.py(OCR) grabber.py(🪟)      [WP2]
├─ parse/    stage.py impl.py                          [WP3]
├─ normalize/stage.py impl.py                          [WP3]
├─ classify/ stage.py impl.py                          [WP4]
├─ rewrite/  stage.py impl.py                          [WP5]
├─ policy/   stage.py impl.py                          [WP1]
├─ report/   stage.py impl.py (report + complaint)     [WP6]
└─ ui/       app.py bridge.py client.py overlay.py win32.py(🪟)  [WP7]
fixtures/<stage>/input.jsonl, expected.jsonl    모듈별 통신 예시 = 명세
fixtures/scenario/                              전체 흐름 예시
```

## 6. 모듈 안에서 자유롭게 해도 되는 것
- `impl.py`에서 내부 파일 추가 (예: `classify/model.py`, `rewrite/backends/api.py`, `report/templates/`)
- 내부 클래스, 설정, 캐시
- `fixtures/<내 stage>/`에 입력 사례 추가 (`expected`는 리드 리뷰)

## 7. 하면 안 되는 것
- `stage.py`의 입력·출력 모델 변경 (→ 계약 변경 이슈)
- 다른 모듈의 `impl.py`를 직접 import (→ 반드시 Pipeline이나 Stage를 거침)
- UI에서 분류나 정책 판단
