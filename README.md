# Clean Chat 🛡️

리그 오브 레전드 게임 중 **악성 채팅을 감지해 숨기고, 피드백만 남기고, 신고·고소장 초안까지 만들어 주는** Windows 데스크톱 앱 (해커톤형 데모).

```
게임 시작 ─▶ 게임 중: [🪟 화면 캡처] → ocr → parse → 필터(normalize·classify·rewrite) → incoming_policy → 오버레이
                    [오버레이 입력] → compose → 필터 → outgoing_policy → 클립보드 복사 / 차단
게임 종료 ─▶ 이번 게임 기록 → 신고 문구 / 고소장 초안 PDF
```

## 빠른 시작 (Mac / Windows 공통)
```bash
uv sync
uv run clean-chat run --source demo          # 게임 단계 전환 + 채팅 처리 + 게임 결과 (지금은 전부 mock = fixtures 응답)
uv run clean-chat say "아 정글 ㅂㅅ 왜 안 와"   # 내 채팅 1문장 처리
uv run clean-chat modules                    # Stage별 단독 실행 명령
uv run python -m clean_chat.parse --impl mock --check
uv run pytest -q                             # 미구현 모듈은 skip
uv sync --extra ui && uv run clean-chat app --source demo   # UI
```
실제 데모(Windows): `scripts\run_windows.bat` 또는 `uv run clean-chat app --source screen`

> 이 스타터에는 **실제 구현이 없습니다.** 모든 `impl.py`는 함수 시그니처와 설명만 있고(`NotImplementedError`), 실행 결과는 `fixtures/`의 예시 데이터입니다.

## 레포 구조 (앱 2개 + 공통 2개, ADR-0015)
| 폴더 | 무엇 | 도구 | 배포 |
|---|---|---|---|
| `src/clean_chat/`, `tests/`, `pyproject.toml` | **데스크톱 앱** (Python, Windows 실행) | uv · CI `ci.yml` | 없음 |
| `simulator/` | **웹 시뮬레이터** (모듈별 Mock 실행·QA) | npm · CI `simulator.yml` | Vercel |
| `contracts/` | **공통 계약** — Stage 입출력 JSON Schema (`schemas.py` 에서 자동 생성) | `scripts/export_contracts.py` | – |
| `fixtures/` | **공통 예시 데이터** — Stage 별 입력 → 기대값 | 손으로 작성 | – |

## 문서 지도
| 문서 | 내용 |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | 무엇을, 왜 (제품 명세, 정책표, 데모 시나리오) |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 왜 이렇게 정했나 (결정 기록) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 구조 (두 흐름, 게임 단계, 디자인 패턴, OS별 실행) |
| [docs/MODULES.md](docs/MODULES.md) | 모듈 명세 + 작업 패키지(WP) 배정 |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | 모듈 사이 데이터 형식 |
| [docs/DATA.md](docs/DATA.md) | 데이터와 모델 공유 |
| [docs/LABELING_GUIDE.md](docs/LABELING_GUIDE.md) | 라벨링 기준 |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | 미정·실측 필요 항목 |
| [docs/SETUP.md](docs/SETUP.md) | 개발 환경 세팅 |
| [docs/GITHUB_SETTINGS.md](docs/GITHUB_SETTINGS.md) | GitHub 규칙 설정 (리드) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 브랜치, PR, 병합 규칙 |
| [simulator/README.md](simulator/README.md) | 모듈 시뮬레이션 웹앱 (Mock 데이터로 Stage 실행·QA) |
| [AGENTS.md](AGENTS.md) | AI 에이전트 공통 규칙 |
| [HANDOFF.md](HANDOFF.md) | 인수인계 기록과 진행 상황 |

## 금지 사항
게임 메모리 읽기, 드라이버, 패킷 조작, 가상 키 입력, 자동 신고는 하지 않습니다. 자세한 내용은 [AGENTS.md](AGENTS.md) 4장을 참고하세요.

> Riot Games와 무관한 비공식 팬 프로젝트입니다. League of Legends는 Riot Games, Inc.의 상표입니다.
