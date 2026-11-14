# 모듈 명세 & 배정

> 모듈은 **5개, 함수 5개**입니다(ADR-0017). 한 사람이 한 폴더(`src/clean_chat/modules/<모듈>/`)만 개발합니다.
> 각 모듈이 **무엇을 받아서, 무엇을 돌려주는지**만 정합니다. 구현 방법은 담당자가 자유롭게 정합니다.
> 입·출력의 정확한 예시는 `fixtures/<모듈>/`에 있습니다. 예시와 이 문서가 다르면 **예시(expected.jsonl)가 기준**입니다.
> 흐름 A(다른 유저 채팅)와 흐름 B(내 입력), 게임 단계는 `docs/ARCHITECTURE.md` 2장 그림을 먼저 보세요.

## 모듈 5개 = 5명

| # | 모듈 | 하는 일 | 입력 → 출력 | 방식 | OS | 난이도 |
|---|---|---|---|---|---|---|
| ① | **ocr** | 채팅창 이미지 → 텍스트 줄 | `Frame` → `OcrResult` | OCR 엔진 (OPEN-03) | Mac 개발 / Windows 실측 | ★★★ |
| ② | **parse** | 줄 → **채팅만** (시스템 메시지·핑 제외, 규칙 코드) + 우회어 정규화 | `ParseRequest` → `ParseResult` | 규칙 (정규식·사전) | 모두 | ★★ |
| ③ | **analyze** | **누가 누구에게** 욕하는지(대상), 욕설 등급 L0~L3, 유형, 비속어·**피드백 조각** | `AnalyzeRequest` → `Analysis` | 소형 분류 모델 + 규칙 | 모두 + Colab | ★★★ |
| ④ | **rewrite** | 피드백 조각 → **순화한 문장** 1개 | `RewriteRequest` → `Rewrite` | LLM 또는 규칙 | 모두 | ★★ |
| ⑤ | **report** | 게임 기록 → **신고 문구 / 고소장 초안 PDF** | `ReportRequest` → `ReportDraft` | 템플릿 + LLM(사건 경위) | 모두 | ★★ |
| – | 공통 | 라벨링 1인 100문장 | `data/labeled/` | – | – | ★ |

**구성 (리드, 모듈 아님)**: 흐름 연결(`core/pipeline.py`), 정책표(`core/policy.py`, SPEC 5장), 화면 캡처(`core/grabber.py` 🪟), 게임 단계·세션(`core/game.py`, `session/`), UI(`ui/`), 로컬 모듈 시뮬레이터(`sim/`).

> 배정이 끝나면 `.github/CODEOWNERS`의 `@M1_OCR` ~ `@M5_REPORT`, `@LEAD` 자리표시자를 실제 GitHub 아이디로 바꿉니다.

---

## 공통 규칙
- 할 일은 `impl.py` 의 **`run()` 함수 하나**입니다. 시그니처와 docstring(예시·순서·주의)이 할 일 목록입니다. 아래 `_도우미()` 함수는 제안이라 바꿔도 됩니다.
- 같은 폴더에 내부 파일(사전, 프롬프트, 템플릿 등)을 자유롭게 추가합니다. **다른 모듈 폴더는 import 하지 않습니다.**
- 모델 로딩처럼 무거운 준비는 `functools.cache` 로 한 번만 합니다. 무거운 import(torch 등)는 함수 안에서 합니다.
- 실패해도 앱을 멈추지 않게 안전한 값을 돌려줍니다(예: ocr → 빈 lines, rewrite → `rewritten=None`). 구현 전에는 `NotImplementedError`.
- 실행: `uv run sim <모듈>` → 브라우저에서 입력 | 디버깅 콘솔(print·logging·오류) | 반환값. 모듈 코드를 고치면 서버를 다시 켜지 않아도 다음 실행에 반영됩니다.
- 테스트: `tests/test_<모듈>.py` (구현하면 자동으로 fixtures 검사 시작)

### ① `ocr` — modules/ocr/ · AI 지점 A1
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `Frame`(이미지 경로, 영역) → `OcrResult`(보이는 **줄 전부**, 위에서 아래) |
| 책임 | 이미지 전처리(확대·흑백·대비), OCR, 두 줄로 꺾인 채팅 합치기 |
| 하지 않는 것 | 화면 캡처(`core/grabber.py`), 앞 프레임과 겹치는 줄 제거(`core/pipeline.py`의 `LineDedup`) |
| 기준 | 프레임당 0.5초 이내, 실패하면 빈 lines |
| 관련 | ADR-0002, ADR-0003, OPEN-02, OPEN-03, OPEN-06 |

### ② `parse` — modules/parse/ (규칙, STRICT)
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `ParseRequest`(줄, 내 소환사명) → `ParseResult`(채팅이면 `ChatMessage`, 아니면 `None`) |
| 책임 | 채널·화자·챔피언·본문 분해, **시스템 메시지·핑·잡음 제외**, `is_me`, 내 입력(`source=self_input`) 처리(채널 명령 `/all`), **정규화**(`text_norm`, `hints`: 우회어 복원·OCR 오타·반복 축약) |
| 기준 | 규칙이라 fixtures 와 **정확히 같아야** 합니다. `text`·`raw`는 절대 고치지 않습니다 |
| 관련 | ADR-0002, ADR-0006, OPEN-09, `data/lexicon/` |

### ③ `analyze` — modules/analyze/ · AI 지점 A2
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `AnalyzeRequest`(메시지, 최근 대화, 명단) → `Analysis` |
| 책임 | **대상(target)** 추정(포지션·닉네임·챔피언·직전 대화), **등급 L0~L3**·유형, 가릴 **비속어 조각**, **피드백 조각**(L2 이상) |
| 하지 않는 것 | 숨김·신고·차단 결정 (정책표 `core/policy.py`가 Analysis 를 보고 정함) |
| 기준 | CPU 1문장 0.2초 이내. 조각은 `message.text` 에 그대로 있는 문자열. 정확도는 `training/` 평가 |
| 관련 | SPEC 4장, ADR-0005, `docs/LABELING_GUIDE.md`, `docs/DATA.md` |

### ④ `rewrite` — modules/rewrite/ · AI 지점 A3
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `RewriteRequest`(메시지, Analysis) → `Rewrite`(순화 문장 또는 `None`) |
| 언제 | 구성이 **L2 이상 & `feedback_spans` 가 있을 때만** 부릅니다 |
| 책임 | 피드백 조각을 롤 용어를 살린 공손한 문장 1개로. 원문에 없는 내용 금지, 욕설이 남으면 `None` |
| 기준 | 3초 이내 (SPEC 8장). LLM 백엔드 `settings.llm_backend` (OPEN-04), API 키는 `.env` |

### ⑤ `report` — modules/report/ · AI 지점 A4
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `ReportRequest`(kind, 세션, 대상, 고소인?, 저장 폴더?) → `ReportDraft` |
| 언제 | 게임이 끝난 뒤(POST_GAME) 구성이 대상 화자마다 부릅니다. `report` = 정책표가 `report=True` 표시한 화자, `complaint` = `complaint_candidate=True` 화자 |
| 책임 | `report`: 복사용 신고 문구 (자동 신고 금지, ADR-0007) / `complaint`: 사건 경위 + 고정 양식 고소장 + 한글 PDF (ADR-0008, "법률 자문 아님" 고지) |
| 기준 | 원문·시각은 그대로 인용(한국 시간). PDF 는 git 에 올리지 않음 |

---

## 구성 (리드)
| 위치 | 책임 |
|---|---|
| `core/schemas.py`, `core/modules.py` | 계약과 모듈 연결표 |
| `core/pipeline.py` | 흐름 A: ocr → 줄 중복 제거 → parse → analyze → (조건부) rewrite → 정책표 / 흐름 B: 내 입력 → parse(self_input) → … → 복사·차단 |
| `core/policy.py` | 정책표 SPEC 5-1(다른 유저)·5-2(내 채팅): `Analysis` → `Decision` |
| `core/game.py`, `core/engine.py` | 게임 단계 상태 기계, 세션 기록, 게임 종료 배치(report 를 kind 별로) |
| `sim/` | `uv run sim`: 로컬 모듈 시뮬레이터 (서버 + HTML 화면, 실행마다 새 프로세스) |
| `core/grabber.py` | 🪟 화면 캡처 → Frame |
| `session/` | 단계 감지기(LCU 읽기 전용, 가짜), 세션 저장소 |
| `ui/` | 클라이언트(대기/게임 중/게임 결과), 오버레이(필터된 채팅, 내 입력 → 클립보드), 캡처 제외 |

---

## 통합 기준
| 시점 | 기준 |
|---|---|
| 1주차 끝 | 내 모듈이 `uv run sim <모듈>` 에서 예시 입력으로 성공 + `uv run pytest tests/test_<모듈>.py` 통과 (parse 는 기대값 전부 일치) |
| 2주차 | 5개가 모두 구현되면 `uv run app` 이 끝까지 돎 (Mac 데모) → Windows 에서 `uv run app` 실제 시연 |
