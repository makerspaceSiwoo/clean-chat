# 모듈 명세 & 작업 패키지

> 각 모듈이 **무엇을 받아서, 무엇을 돌려주고, 무엇을 책임지는지** 정의합니다. 구현 방법은 담당자가 자유롭게 정합니다.
> 입·출력의 정확한 예시는 `fixtures/<stage>/`에 있습니다. 예시와 이 문서가 다르면 **예시(expected.jsonl)가 기준**입니다.

## 작업 패키지 (WP) — 이 단위로 사람을 배정합니다

| WP | 범위 | Stage / 파일 | OS 필요 | 난이도 | 추천 대상 |
|---|---|---|---|---|---|
| **WP1** 코어·정책 | 계약, 파이프라인, 엔진, CI, 통합 + **policy** | core/, policy/ | Mac | ★★★ | 리드 |
| **WP2** 캡처·OCR | 화면 캡처, OCR, 줄 중복 제거 | capture/ (`ocr`) | **Windows**(캡처) / Mac(OCR) | ★★★ | 개발자 또는 Windows 바이브 코더 |
| **WP3** 텍스트 정리 | 채팅 줄 분해, 우회어 복원 | parse/, normalize/ | 모두 | ★★ | 바이브 코더 |
| **WP4** 분류 모델 | 분류 모델, 학습·평가, 라벨 관리 | classify/, training/ | 모두 + Colab | ★★★ | 개발자 |
| **WP5** 피드백 다듬기 | 피드백 추출, 문장 다듬기 (LLM) | rewrite/ | 모두 | ★★ | 바이브 코더 |
| **WP6** 신고·고소장 | 신고 문구, 고소장 양식, 한글 PDF | report/ (`report`, `complaint`) | 모두 | ★★ | 바이브 코더 |
| **WP7** 화면 | 클라이언트, 오버레이, 캡처 제외 | ui/ | 모두(화면) / **Windows**(캡처 제외) | ★★ | Windows 바이브 코더 |
| 공통 | 라벨링 1인 100문장 | data/labeled/ | – | ★ | 전원 |

**5명 배정 예시 (선택용)**

| 사람 | 안 A (모델 집중) | 안 B (균형) |
|---|---|---|
| 리드 (Mac) | WP1 | WP1 + WP3 |
| 개발자 B (Mac) | WP4 + WP3 | WP4 |
| 바이브 C (Win) | WP2 | WP2 |
| 바이브 D (Win) | WP7 | WP7 |
| 바이브 E | WP5 + WP6 | WP5 + WP6 |

> 배정이 끝나면 `.github/CODEOWNERS`의 `@WP*` 자리표시자를 실제 GitHub 아이디로 바꿉니다.

---

## Stage 명세

공통 규칙
- 실제 구현은 `<모듈>/impl.py`의 클래스 하나입니다. 무거운 준비는 `setup()`에서 1번, 처리는 `run()`, 정리는 `close()`에서 합니다.
- 실패해도 **예외로 앱을 멈추지 않습니다.** 안전한 기본값을 돌려주고 로그를 남깁니다(예외: 미구현 상태의 `NotImplementedError`).
- 단독 실행: `uv run python -m clean_chat.<모듈> [--impl mock|real] [--check] [--in 파일] [--out 파일]`

### `ocr` — capture/ (WP2) · AI 지점 A1
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `Frame`(채팅창 이미지 경로 + 영역) → `OcrResult`(**새로 나타난** 줄 `RawLine[]`) |
| 책임 | 이미지 전처리(확대, 흑백, 채팅 색 분리) → OCR → 줄 분리 → **이전 프레임과 중복 제거**(상태 유지) |
| 책임 아님 | 채널·화자 분리(parse), 맞춤법 보정(normalize) |
| 별도 클래스 | `grabber.py: ScreenGrabber` (🪟 Windows 전용, Frame 스트림 생성, 오버레이 캡처 제외 확인) |
| 성능 | 프레임당 0.5초 이내 |
| Mac 테스트 | `fixtures/ocr/images/*.png` + `clean-chat run --source screenshots` |
| 결정 필요 | OPEN-02(캡처 제외), OPEN-03(OCR 엔진), OPEN-06(채팅 색 설정) |

### `parse` — parse/ (WP3)
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `RawLine` → `ParseResult`(`ChatMessage` 또는 잡음이면 `None`) |
| 책임 | `"[팀] 닉네임 (챔피언): 본문"` 분해, 채널 판별(team/all/ping/system), `is_me` 표시, `self_input` 처리 |
| 책임 아님 | 욕설 판단, 우회어 복원 |
| 검사 | **STRICT**: `expected.jsonl`과 정확히 같아야 함 |

### `normalize` — normalize/ (WP3)
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `ChatMessage` → `NormalizedMessage`(+`text_norm`, `hints`) |
| 책임 | 우회 비속어 복원(`시1발`, `ㅅ ㅂ`, `tlqkf`), 반복 축약, OCR 오인식 보정, 사전(`data/lexicon/`) 관리 |
| 주의 | 원문 `text`, `raw`는 그대로 두고 **`text_norm`만** 바꿉니다(증거 보존). 학습 데이터에도 같은 함수를 적용합니다 |

### `classify` — classify/ (WP4) · AI 지점 A2
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `NormalizedMessage` → `Classification`(`level`, `harm_types`, `has_feedback`, `scores`, `model_version`) |
| 책임 | **분류만.** 유해 유형(다중), 등급 L0~L3, 피드백 포함 여부. 내 채팅과 타 유저 채팅에 같은 기준 적용 |
| 책임 아님 | 숨김, 신고 여부(policy) |
| 성능 | CPU 1문장 0.2초 이내. 모델 파일이 없어도 동작해야 함(사전 규칙 등 대체 수단) |
| 평가 | `data/eval/test.csv` 기준 리포트 (training/) |

### `rewrite` — rewrite/ (WP5) · AI 지점 A3
| 항목 | 내용 |
|---|---|
| 호출 조건 | `level >= 2` 이면서 `has_feedback == True` 일 때만 (Pipeline이 판단) |
| 입력 → 출력 | `RewriteRequest`(메시지 + 분류) → `Rewrite`(`feedback_spans`, `rewritten`, `backend`) |
| 책임 | ① 원문에서 게임 피드백 부분만 추출 ② 롤 용어로 자연스럽고 공손한 한 문장으로 다듬기 |
| 안전장치 | 3초 제한. 실패, 지연, **결과에 욕설이 남은 경우** → `rewritten=None` (policy가 숨김 처리) |
| 결정 필요 | OPEN-04 (LLM 실행 위치) |

### `policy` — policy/ (WP1)
| 항목 | 내용 |
|---|---|
| 입력 → 출력 | `PolicyRequest`(메시지 + 분류 + 리라이트 + 플레이어 명단) → `Decision` |
| 책임 | `docs/SPEC.md` 5장 정책표 그대로 적용(타 유저 / 내 채팅), 공격 대상 추정, 신고·고소 후보 표시, 같은 화자 누적 |
| 검사 | **STRICT** |

### `report` / `complaint` — report/ (WP6) · AI 지점 A4
| 항목 | 내용 |
|---|---|
| report | `ReportRequest`(**이번 게임 세션** + 대상) → `ReportDraft`(복사용 신고 문구). 자동 신고 금지 (ADR-0007) |
| complaint | `ComplaintRequest`(세션 + 대상 + 고소인) → `ComplaintDraft` + **한글 PDF 파일**. 고정 양식에 사실을 채우고 '사건 경위'만 LLM 사용 (ADR-0008) |
| 실행 시점 | **게임 종료(POST_GAME)에서만.** 이번 게임 세션 전체를 한 번에 처리합니다(배치) |
| 필수 | "법률 자문이 아님" 고지, 원문(`raw`)과 시각 그대로 인용 |

### UI — ui/ (WP7) · Stage 아님
| 파일 | 책임 |
|---|---|
| `app.py` | QApplication, Engine, 창 2개 조립 |
| `bridge.py` | Engine 콜백 → Qt Signal (스레드 안전) |
| `client.py` | 시작/중지, 사용법, 처리 내역 표, 신고 복사, 고소장 저장 |
| `overlay.py` | 투명·항상 위, 위치 보정 → `Region`, 필터된 채팅 표시, 내 채팅 입력 → 클립보드 (ADR-0006) |
| `win32.py` | 🪟 오버레이를 캡처에서 제외 (ADR-0003) |
| 규칙 | `Decision.display_text`만 보여 주고 **판단하지 않습니다** |

---

## 주말 통합 기준 (모듈 공통)
| 주말 | 기준 |
|---|---|
| #2 | 내 Stage가 `--impl real`로 fixtures를 통과(형식 OK, STRICT면 일치) + `clean-chat run --real <내 stage>`가 끝까지 돌아감 |
| #3 | 전체 real로 Windows에서 `clean-chat app --source screen` 시연. 새 기능 금지, 버그 수정과 발표만 |
