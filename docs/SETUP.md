# 개발 환경 세팅 (처음 하는 사람 기준)

> 15분이면 끝납니다. 막히면 화면을 캡처해서 팀 채팅방에 올리세요.

## 0. 필요한 것
| 도구 | 용도 | 설치 |
|---|---|---|
| Git | 코드 공유 | Mac: `xcode-select --install` / Windows: https://git-scm.com |
| GitHub 계정 | 레포 접근 | 리드에게 아이디 전달 → 초대 수락 |
| **uv** | 파이썬과 패키지 관리 (npm 같은 역할) | 아래 명령 |
| VS Code 또는 Cursor | 편집기 | 레포를 열면 추천 확장 설치 안내가 뜹니다 |
| AI 도구 | 바이브 코딩 | Claude Code / Codex / Gemini CLI / 웹 채팅 중 편한 것 |

### uv 설치
```bash
# Mac / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
uv가 Python 3.11도 알아서 설치합니다. 따로 Python을 설치하지 않아도 됩니다.

## 1. 레포 받기 + 설치
```bash
git clone https://github.com/<팀>/clean-chat.git
cd clean-chat
uv sync                      # 기본 + 개발 도구 설치 (= npm install)
uv run pre-commit install    # 커밋할 때 자동 검사 켜기
uv run clean-chat run --source demo   # ✅ 8줄이 처리 결과와 함께 나오면 성공 (지금은 mock 응답)
uv run pytest -q                    # ✅ passed + skipped(미구현) 이면 정상
```

## 1-1. 어떤 OS에서 무엇이 되나
| 할 일 | Mac | Windows |
|---|---|---|
| clone, 설치(`uv sync`), 테스트 | ✅ | ✅ |
| 모듈 단독 실행 `python -m clean_chat.<모듈>` | ✅ | ✅ |
| 전체 흐름 `clean-chat run --source demo/screenshots` | ✅ | ✅ |
| UI 화면 개발 `clean-chat app --source demo` | ✅ | ✅ |
| **실제 게임 캡처 + 오버레이 데모** `clean-chat app --source screen` | ❌ | ✅ |

## 2. 내 모듈에 필요한 것 추가 설치
```bash
uv sync --extra ui         # ui 담당 (PySide6)
uv sync --extra capture    # capture 담당 (화면 캡처)
uv sync --extra ml         # classify 담당 (torch, transformers — 용량 큼)
uv sync --extra report     # report 담당 (PDF)
uv sync --all-extras       # 리드: 전부
```

## 3. 내 브랜치 만들기
```bash
git switch develop
git switch -c mod/<내모듈>      # 예: mod/capture
git push -u origin mod/<내모듈>
```

## 4. AI 도구 연결
| 도구 | 할 일 |
|---|---|
| Claude Code | 레포 폴더에서 `claude` 실행 → `CLAUDE.md` → `AGENTS.md` 자동으로 읽음 |
| Codex (GPT) | 레포 폴더에서 실행 → `AGENTS.md` 자동으로 읽음 |
| Gemini CLI | `.gemini/settings.json` 설정으로 `AGENTS.md`를 읽음 |
| Cursor | `AGENTS.md`를 읽음. 안 읽히면 채팅에 `@AGENTS.md` 첨부 |
| **웹 채팅** (claude.ai, ChatGPT, Gemini) | `uv run python scripts/pack_context.py <내모듈>` → 생성된 `context_<모듈>.md` 파일을 첨부 |

### 첫 프롬프트 예시 (복사해서 쓰세요)
```
나는 이 레포에서 <capture> 모듈 담당이야. AGENTS.md와 src/clean_chat/<capture>/README.md를 먼저 읽어.
이번 작업: <OcrSource.lines()를 구현해서 지정 영역을 캡처하고 OCR로 줄 단위 RawLine을 내보내기>.
내 모듈 폴더 밖은 수정하지 말고, 먼저 계획을 보여 줘. 끝나면 ruff와 pytest를 돌려 줘.
```

## 5. Windows 준비 (WP2 캡처, WP7 화면, 발표 PC)
- uv 설치(PowerShell 명령은 위) → `git clone` → `uv sync --extra ui --extra capture`
- 발표 PC: `scripts\run_windows.bat` 더블클릭 (필요한 extra 전부 설치 후 실제 모드 실행)
- 롤 그래픽 설정 → 창 모드: **테두리 없음** (전체 화면이면 오버레이가 안 보입니다)
- Windows 10 2004 버전 이상인지 확인 (오버레이 캡처 제외 기능, ADR-0003)
- **부계정**으로 테스트하고, 팀원끼리 **사용자 설정 게임**에서 채팅 실험을 합니다.

## 자주 막히는 곳
| 증상 | 해결 |
|---|---|
| `uv: command not found` | 터미널을 껐다 켜기 |
| 커밋이 막힘 (pre-commit) | 메시지대로 수정되었으면 `git add -A` 후 다시 커밋 |
| `no-commit-to-branch` 실패 | `main`에서 작업 중 → `git switch mod/<내모듈>` |
| PR에서 `모듈 경계` 실패 | 내 폴더 밖 파일 수정을 되돌리거나 리드에게 문의 |
| 한글이 깨짐 (Windows) | VS Code 오른쪽 아래 인코딩을 UTF-8로 |
