# ⑤ report — 신고 문구 · 고소장 초안

명세: `docs/MODULES.md`의 `report` 절 · 계약: `docs/CONTRACTS.md` · 예시: `fixtures/report/`

**할 일은 `impl.py` 의 `run(ReportRequest) -> ReportDraft` 함수 하나입니다.** docstring 의 예시·순서·주의를 따라 본문을 채우세요.

| 파일 | 내용 | 수정 |
|---|---|---|
| `impl.py` | `run()` + 제안용 도우미 함수 (`_`로 시작, 바꿔도 됨) | ✅ |
| 그 밖의 파일 | 이 폴더 안에 자유롭게 추가 (사전, 프롬프트, 내부 모듈) | ✅ |
| `fixtures/report/input.jsonl` | 입력 예시 추가 | ✅ |
| `fixtures/report/expected.jsonl` | 기대값 (명세) | 리드 승인 |
| `tests/test_report.py` | 내 테스트 추가 | ✅ |

- 출력 형식을 자동 검사합니다.
- `kind=report` 는 복사용 신고 문구(자동 신고 금지), `kind=complaint` 는 고소장 초안 + 한글 PDF(`uv sync --extra report`). PDF 는 git 에 올리지 않습니다.
- 다른 모듈 폴더는 import 하지 않습니다. 함수 이름 `run` 과 입출력 타입은 바꾸지 않습니다(바꿔야 하면 "계약 변경 요청" 이슈).

```bash
uv run clean-chat module report              # fixtures 입력으로 내 함수 실행 (구현 전이면 "구현 안 됨")
uv run clean-chat module report --check      # 기대값과 비교
uv run pytest tests/test_report.py           # 자동 테스트 (구현 전이면 skip)
uv run clean-chat serve                  # 웹 시뮬레이터용 서버 → 다른 터미널에서 cd simulator && npm run dev
uv run python scripts/pack_context.py report # 웹 AI 채팅에 첨부할 맥락 묶음
```
