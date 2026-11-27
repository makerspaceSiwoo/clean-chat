# Clean Chat 🛡️

리그 오브 레전드 게임 중 **악성 채팅을 감지해 숨기고, 피드백만 남기고, 신고·고소장 초안까지 만들어 주는** macOS·Windows 데스크톱 앱 (해커톤형 데모).

```
게임 시작 ─▶ 게임 중: [🪟 화면 캡처] → ①ocr → ②parse → ③analyze → ④rewrite → 정책표 → 오버레이
                    [오버레이 입력] → ②parse → ③analyze → ④rewrite → 정책표 → 클립보드 복사 / 차단
게임 종료 ─▶ 이번 게임 기록 → ⑤report → 신고 문구 / 고소장 초안 PDF
```

## 빠른 시작 (Mac / Windows 공통, Node 불필요)
```bash
uv sync                     # 설치 (처음 한 번, 앱 화면까지: uv sync --extra ui)
uv run sim                  # 모듈 시뮬레이터 (브라우저가 열림: 입력 | 디버깅 콘솔 | 반환값)
uv run sim parse            # 모듈 하나만 바로 열기 (ocr · parse · analyze · rewrite · report)
uv run app                  # 클라이언트 창 열기 (macOS·Windows)
uv run app --demo           # 기존 시나리오 재생
uv run pytest -q            # 테스트 (구현 전 모듈은 skip)
```
실행 명령은 `sim`, `app` 두 개뿐입니다. 발표 PC(Windows)는 `scripts\run_windows.bat` 더블클릭.

**캡처 확인** · 클라이언트의 **오버레이 아래 화면 미리보기 (OCR 끔)**가 기본으로 선택됩니다. **오버레이 실행**을 누르면 오버레이 위치를 조정할 수 있습니다. **위치 잠금**을 누르면 롤 실행 여부와 관계없이 오버레이 아래 이미지를 0.2초 간격으로 확인합니다. 채팅창 영역 카드의 **영역 다시 맞추기**를 누르면 캡처가 멈추고 미리보기가 비워집니다. 이전 위치가 저장되어 있어도 매번 잠가야 캡처를 시작합니다. macOS 14 이상에서 화면 기록 권한이 필요합니다. 오디오를 캡처하거나 저장하지 않습니다. 감지·필터 모듈을 연결해 사용할 때는 시작 전에 체크를 해제합니다.

macOS에서 처음 위치를 잠글 때 화면 기록을 허용한 뒤 시스템이 요청하면 앱을 재실행하고 다시 잠급니다. 계속 대기하면 클라이언트의 **화면 기록 설정**과 **Finder에서 앱 보기**를 열고, 현재 실행 중인 앱을 설정 목록에 추가합니다. 이미 이전 확인용 빌드가 켜져 있으면 해당 항목을 제거하고 현재 앱을 추가합니다.

**실시간 사용** · 롤을 테두리 없는 창 모드로 실행합니다. 클라이언트 설정에서 내 소환사명을 입력하고 홈의 **오버레이 실행**을 누릅니다. 오버레이를 드래그하고 가장자리로 크기를 맞춰 채팅 5~6줄을 전부 가린 뒤 클라이언트의 **위치 잠금**을 누릅니다. 잠그면 게임에 클릭이 전달되고 다음 실행에 위치가 복원됩니다. **영역 다시 맞추기**로 보정하거나 입력칸을 사용할 수 있습니다. **오버레이 종료**로 감시를 끝냅니다. macOS에서는 첫 캡처 때 화면 기록 권한이 필요합니다.

게임 창을 찾으면 200ms마다 전체 채팅 영역의 글자 후보를 비교합니다. 변화가 감지된 뒤 1초 동안은 100ms 간격으로 확인합니다. 같은 화면은 OCR을 건너뛰고 글자 후보가 있을 때 1초, 없을 때 3초마다 재확인합니다. OCR 대기열은 최근 6장의 후보를 보존하며 넘친 횟수를 클라이언트에 표시합니다. 순화 중에도 다음 콜을 표시합니다.

**독립 앱 빌드** · 각 OS에서 `uv run --extra ui --extra rewrite --extra report --with "pyinstaller>=6.16,<7" python scripts/build_desktop.py`를 실행합니다(rewrite·report extra를 빼면 LLM 없이 로컬 규칙만 씁니다). 빌드된 앱은 LLM 설정(`LLM_BACKEND`, `LLM_MODEL`, `GEMINI_API_KEY`)을 환경 변수나 사용자 데이터 폴더의 `.env`(Windows `%LOCALAPPDATA%\Clean Chat\.env`, macOS `~/Library/Application Support/Clean Chat/.env`)에서 읽습니다. macOS 확인용 빌드는 `dist/Clean Chat Preview.app`입니다. 배포용은 `CLEAN_CHAT_CODESIGN_IDENTITY`에 사용할 코드 서명 인증서를 지정하면 `dist/Clean Chat.app`으로 생성됩니다. 업데이트 간 권한을 유지하려면 같은 서명 ID로 빌드합니다. Windows 결과는 `dist/Clean Chat/Clean Chat.exe`입니다. Windows에서는 같은 폴더의 라이브러리도 함께 배포합니다. 후속 모듈이 요구하는 모델·엔진은 해당 모듈의 배포 조건을 따릅니다.

> 이 스타터에는 **모듈 구현이 없습니다.** 모듈 5개(`src/clean_chat/modules/<모듈>/impl.py`)는 함수 시그니처와 설명만 있고(`NotImplementedError`), **Mock 도 없어서** 실행하면 "구현 안 됨" 오류가 납니다(ADR-0017).
> 5명이 한 폴더씩 맡습니다: ① ocr · ② parse · ③ analyze · ④ rewrite · ⑤ report. 나머지는 구성(리드)입니다. 자세히: [docs/MODULES.md](docs/MODULES.md)

## 레포 구조
| 폴더 | 무엇 |
|---|---|
| `src/clean_chat/modules/` | **모듈 5개** (5명이 한 폴더씩) |
| `src/clean_chat/core/`, `ui/`, `session/` | 구성 (리드): 연결·정책표·게임 단계·화면 |
| `src/clean_chat/sim/` | **로컬 모듈 시뮬레이터** (`uv run sim`, 파이썬 서버 + HTML 화면, ADR-0019) |
| `fixtures/` | 모듈별 입력 → 기대값 예시 (= 명세, 시뮬레이터의 예시 입력) |
| `tests/` | 테스트 |

## 문서 지도
| 문서 | 내용 |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | 무엇을, 왜 (제품 명세, 정책표, 데모 시나리오) |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 왜 이렇게 정했나 (결정 기록) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 구조 (두 흐름, 게임 단계, 디자인 패턴, OS별 실행) |
| [docs/MODULES.md](docs/MODULES.md) | 모듈 5개 명세 + 배정, 구성(리드) |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | 모듈 사이 데이터 형식 |
| [docs/DATA.md](docs/DATA.md) | 데이터와 모델 공유 |
| [docs/LABELING_GUIDE.md](docs/LABELING_GUIDE.md) | 라벨링 기준 |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | 미정·실측 필요 항목 |
| [docs/SETUP.md](docs/SETUP.md) | 개발 환경 세팅 |
| [docs/GITHUB_SETTINGS.md](docs/GITHUB_SETTINGS.md) | GitHub 규칙 설정 (리드) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 브랜치, PR, 병합 규칙 |
| [AGENTS.md](AGENTS.md) | AI 에이전트 공통 규칙 |
| [HANDOFF.md](HANDOFF.md) | 인수인계 기록과 진행 상황 |

## 금지 사항
게임 메모리 읽기, 드라이버, 패킷 조작, 가상 키 입력, 자동 신고는 하지 않습니다. 자세한 내용은 [AGENTS.md](AGENTS.md) 4장을 참고하세요.

> Riot Games와 무관한 비공식 팬 프로젝트입니다. League of Legends는 Riot Games, Inc.의 상표입니다.
