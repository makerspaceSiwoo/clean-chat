# Clean Chat 🛡️

리그 오브 레전드 게임 중 **악성 채팅을 감지해 숨기고, 피드백만 남기고, 신고·고소장 초안까지 만들어 주는** macOS·Windows 데스크톱 앱 (해커톤형 데모).

```
게임 시작 ─▶ 게임 중: [🪟 화면 캡처] → ①ocr → ②parse → ③analyze → ④rewrite → 정책표 → 오버레이
                    [오버레이 입력] → ②parse → ③analyze → ④rewrite → 정책표 → 클립보드 복사 / 차단
게임 종료 ─▶ 이번 게임 기록 → ⑤report → 신고 문구 / 고소장 초안 PDF
```

## 빠른 시작 (Mac / Windows 공통, Node 불필요)
```bash
uv sync --extra ui --extra ocr --extra analyze --extra rewrite --extra report   # 앱까지 전부 설치 (처음 한 번)
uv run app                  # 클라이언트 창 열기 (macOS·Windows). 처음에는 준비 화면이 먼저 뜹니다
uv run app --demo           # 저장된 시나리오 재생 (게임 없이 흐름 확인)
uv run app --check          # 설치 점검: 필요한 패키지와 분류 모델을 불러 봅니다

uv sync                     # 시뮬레이터·테스트만 쓸 때 (모듈이 쓰는 패키지는 --extra <모듈> 로 추가)
uv run sim                  # 모듈 시뮬레이터 (브라우저가 열림: 입력 | 디버깅 콘솔 | 반환값)
uv run sim parse            # 모듈 하나만 바로 열기 (ocr · parse · analyze · rewrite · report)
uv run sim flow             # 전체 흐름: 캡처 이미지 → ocr → parse → analyze → rewrite → 정책 → report
uv run pytest -q            # 테스트
```
실행 명령은 `sim`, `app` 두 개뿐입니다. 발표 PC(Windows)는 `scripts\run_windows.bat` 더블클릭.

**처음 실행 (준비 화면)** · 앱을 처음 열면 아래 두 가지가 끝나야 시작합니다. 한 번만 하면 됩니다.
1. **Gemini API 키 입력 (필수)** — 욕설에 섞인 피드백을 순화하고 고소장 초안을 쓰는 데 씁니다. 키가 없으면 순화 결과가 비어 피드백까지 숨겨지므로 반드시 입력합니다. [Google AI Studio](https://aistudio.google.com/apikey)에서 발급하고, 나중에 설정 화면에서 바꿀 수 있습니다. 키는 이 PC에만 저장되고, 순화할 채팅 문장은 Google Gemini 로 전송됩니다.
2. **채팅 분석 모델 내려받기 (자동, 약 440MB)** — 파인튜닝한 분류 모델(`kcelectra-base-ft-0.5`)을 공개 Hugging Face 저장소에서 받습니다. 로그인은 필요 없고, 끊기면 **다시 시도**로 이어 받습니다. 모델이 있으면 봉인 검증 세트의 등급 정답률이 89.5%, 규칙만 쓰면 56.0%입니다.

저장 위치는 설치 파일이면 사용자 데이터 폴더(Windows `%LOCALAPPDATA%\Clean Chat\`, macOS `~/Library/Application Support/Clean Chat/`), 소스에서 실행하면 레포의 `.env` 와 `models/` 입니다. 소스 실행에서 `analyze` extra 를 빼고 설치하면 모델을 돌릴 수 없어 규칙만으로 판단합니다(준비 화면이 설치 명령을 알려 줍니다). 시뮬레이터에서 모델을 쓰려면 `uv run python -m clean_chat.modules.analyze.weights download` 로 받습니다.

**캡처 미리보기** · 홈의 **읽고 있는 영역 보기**를 켜 두면 오버레이 아래에서 가져온 이미지와 크기가 1초마다 표시됩니다. 표시만 켜고 끄는 것이라 실행 중에도 바꿀 수 있고, 꺼도 채팅은 계속 읽습니다. 위치를 잠그면 미리보기와 상관없이 항상 OCR로 읽습니다. macOS 14 이상에서 화면 기록 권한이 필요합니다. 오디오를 캡처하거나 저장하지 않습니다.

macOS에서 처음 위치를 잠글 때 화면 기록을 허용한 뒤 시스템이 요청하면 앱을 재실행하고 다시 잠급니다. 계속 대기하면 클라이언트의 **화면 기록 설정**과 **Finder에서 앱 보기**를 열고, 현재 실행 중인 앱을 설정 목록에 추가합니다. 이미 이전 확인용 빌드가 켜져 있으면 해당 항목을 제거하고 현재 앱을 추가합니다.

**실시간 사용** · 클라이언트 설정에서 내 소환사명을 입력하고, 홈에서 **오버레이 실행**을 누릅니다. 오버레이를 드래그하고 가장자리로 크기를 맞춰 채팅 5~6줄을 전부 가린 뒤 **위치 잠금**을 누릅니다. 잠근 순간부터 게임으로 보고 채팅을 읽으며, 게임에 클릭이 전달되고 다음 실행에 위치가 복원됩니다. **영역 다시 맞추기**로 보정하거나 입력칸을 사용할 수 있습니다. 게임이 끝나면 **오버레이 종료**를 누릅니다. 그때 이번 게임의 신고 메시지와 고소장 초안이 만들어집니다. macOS에서는 첫 캡처 때 화면 기록 권한이 필요합니다.

앱은 게임 창을 찾지 않고 **오버레이가 가린 사각형만** 1초마다 한 장 가져옵니다(우리 앱 창은 캡처에서 뺍니다). 창 모드 조건이 없고 가져오는 이미지가 작습니다. 대신 오버레이 아래에 있는 것은 무엇이든 읽으므로, 다른 창이 올라오거나 게임이 끝난 뒤에도 오버레이를 켜 두면 그 화면의 글자를 읽습니다. 가져온 영역은 홈의 **캡처 미리보기**에 크기와 함께 그대로 표시됩니다.

글자가 바뀐 화면만 OCR로 보냅니다. 새 채팅이 올라오면 다음 확인(1초 안)에 바로 읽고, 글자 변화 감지가 놓치는 경우를 대비해 채팅이 보이는 동안은 1초마다, 빈 화면은 3초마다 다시 읽습니다. 캡처한 이미지는 디스크에 저장하지 않고 메모리에서 바로 OCR에 넘기며, 남는 것은 읽은 채팅 줄뿐입니다. OCR 대기열은 최근 2장만 두고 넘친 횟수를 클라이언트에 표시합니다. 순화 중에도 다음 콜을 표시합니다.

앱을 열면 백그라운드에서 OCR 엔진과 분석 모델을 미리 준비합니다(OCR 모델 약 18MB는 처음 한 번 내려받습니다). 실시간 판독 기록은 사용자 데이터 폴더의 `logs/capture.log`에 남습니다(캡처 크기, OCR 시간, 읽은 줄 수, 새로 읽은 줄). 채팅 원문이 들어가므로 이 PC에만 두고 최근 3MB만 보관합니다.

새 채팅은 최근에 본 줄과 순서대로 맞춰 보고, 마지막으로 맞은 줄 아래의 줄만 고릅니다. 같은 줄인지는 글자가 "거의 같은지"로 봅니다(띄어쓰기·기호 무시, 화자와 내용을 따로 비교). 반투명 채팅창 뒤로 게임 화면이 움직여서 같은 줄도 OCR이 읽을 때마다 조금씩 다르게 읽기 때문입니다. OCR이 아무것도 읽지 못한 화면(채팅창 숨김, 인식 실패)은 비교 기준을 바꾸지 않습니다. 채팅으로 읽히지 않은 줄은 다음에 다르게 읽히면 한 번 더 확인합니다.

욕설은 `**`로 가려서 보여 주지 않습니다. 대상 없는 욕설(L1)은 욕설을 뺀 문장으로 보여 주고(`아 ㅅㅂ 내가 실수함` → `아 내가 실수함`), 욕설뿐이면 숨깁니다. 내 채팅도 같아서, 욕설뿐이면 복사할 내용이 없습니다.

신고·고소 대상은 **닉네임 + 챔피언**으로 구분합니다. 닉네임이 같아도 챔피언이 다르면 다른 사람으로 나누고, OCR이 같은 사람의 닉네임을 조금 다르게 읽으면(같은 챔피언, 거의 같은 닉네임) 한 사람으로 모읍니다.

**독립 앱 빌드** · 각 OS에서 `uv run --extra ui --extra ocr --extra analyze --extra rewrite --extra report --with "pyinstaller>=6.16,<7" python scripts/build_desktop.py`를 실행합니다. 설치 파일에는 게임 오버레이로 모듈을 실행하는 메인 앱만 들어가고 시뮬레이터는 빠집니다. 분류 모델을 돌리는 패키지(torch·transformers)가 들어가서 macOS 앱은 약 1.6GB입니다. 모델 가중치와 Gemini API 키는 넣지 않고, 받는 사람이 첫 실행 준비 화면에서 내려받고 입력합니다. `analyze` extra를 빼고 빌드하면 규칙만 쓰는 작은 앱이 되고, rewrite·report extra를 빼면 LLM 없이 로컬 규칙만 씁니다. 모델은 rewrite·report가 각자 기본 모델(`gemini/gemini-3.1-flash-lite`)을 쓰고, `LLM_MODEL`을 설정하면 그 값이 우선합니다. macOS 확인용 빌드는 `dist/Clean Chat Preview.app`입니다. 배포용은 `CLEAN_CHAT_CODESIGN_IDENTITY`에 사용할 코드 서명 인증서를 지정하면 `dist/Clean Chat.app`으로 생성됩니다. 업데이트 간 권한을 유지하려면 같은 서명 ID로 빌드합니다. Windows 결과는 `dist/Clean Chat/Clean Chat.exe`이고, 같은 폴더의 라이브러리도 함께 배포합니다. 빌드한 앱은 `--check` 인자로 필요한 패키지가 모두 들어갔는지 점검할 수 있습니다. GitHub Actions의 `build-desktop`(Actions 탭에서 수동 실행 또는 `test` 브랜치 push)이 두 OS의 설치 파일을 만들어 Artifacts에 올립니다.

> **모듈 5개가 모두 구현돼 있습니다.** ① ocr(RapidOCR) · ② parse · ③ analyze(규칙 + 파인튜닝 분류 모델) · ④ rewrite(Gemini + 예비 규칙) · ⑤ report(신고 문구 · 고소장 초안). Mock 은 없고(ADR-0017), 각 모듈은 `src/clean_chat/modules/<모듈>/impl.py` 의 `run()` 하나입니다.
> 5명이 한 폴더씩 맡고, 나머지(흐름 연결·정책표·화면·시뮬레이터)는 구성(리드)입니다. 자세히: [docs/MODULES.md](docs/MODULES.md)

## 레포 구조
| 폴더 | 무엇 |
|---|---|
| `src/clean_chat/modules/` | **모듈 5개** (5명이 한 폴더씩) |
| `src/clean_chat/core/`, `ui/`, `session/` | 구성 (리드): 연결·정책표·게임 단계·화면 |
| `src/clean_chat/sim/` | **로컬 시뮬레이터** (`uv run sim` 모듈별 · `uv run sim flow` 전체 흐름, 파이썬 서버 + HTML 화면, ADR-0019) |
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
