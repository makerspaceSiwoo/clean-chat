# ② parse — 채팅 추출 — 시스템 메시지 제외 + 정규화

명세: `docs/MODULES.md`의 `parse` 절 · 계약: `docs/CONTRACTS.md` · 예시: `fixtures/parse/`

**할 일은 `impl.py` 의 `run(ParseRequest) -> ParseResult` 함수 하나입니다.** docstring 의 예시·순서·주의를 따라 본문을 채우세요.

| 파일 | 내용 | 수정 |
|---|---|---|
| `impl.py` | `run()` + 제안용 도우미 함수 (`_`로 시작, 바꿔도 됨) | ✅ |
| 그 밖의 파일 | 이 폴더 안에 자유롭게 추가 (사전, 프롬프트, 내부 모듈) | ✅ |
| `fixtures/parse/input.jsonl` | 입력 예시 추가 | ✅ |
| `fixtures/parse/expected.jsonl` | 기대값 (명세) | 리드 승인 |
| `tests/test_parse.py` | 내 테스트 추가 | ✅ |

- 규칙 모듈: fixtures 기대값과 **정확히 같아야** 합니다(`--check` 10/10).
- 우회어 사전은 `data/lexicon/` 에 둡니다. 내 입력(흐름 B)도 `source=self_input` 줄로 이 함수를 거칩니다.
- 다른 모듈 폴더는 import 하지 않습니다. 함수 이름 `run` 과 입출력 타입은 바꾸지 않습니다(바꿔야 하면 "계약 변경 요청" 이슈).

```bash
uv run clean-chat module parse              # fixtures 입력으로 내 함수 실행 (구현 전이면 "구현 안 됨")
uv run clean-chat module parse --check      # 기대값과 비교
uv run pytest tests/test_parse.py           # 자동 테스트 (구현 전이면 skip)
uv run clean-chat serve                  # 웹 시뮬레이터용 서버 → 다른 터미널에서 cd simulator && npm run dev
uv run python scripts/pack_context.py parse # 웹 AI 채팅에 첨부할 맥락 묶음
```
