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
- 브랜치는 `parse/<작업 내용>` 으로 만듭니다(예: `parse/first-try`). PR 에서 위 표의 범위 밖 파일을 바꾸면 CI `module-scope` 가 실패합니다(CONTRIBUTING.md).
- 다른 모듈 폴더는 import 하지 않습니다. 함수 이름 `run` 과 입출력 타입은 바꾸지 않습니다(바꿔야 하면 "계약 변경 요청" 이슈).

```bash
uv run sim parse                         # 브라우저: 입력 | 디버깅 콘솔(print·logging·오류) | 반환값
uv run pytest tests/test_parse.py        # 자동 테스트 (구현 전이면 skip)
uv run python scripts/pack_context.py parse   # 웹 AI 채팅에 첨부할 맥락 묶음
```
모듈 코드를 고친 뒤 시뮬레이터에서 [실행]만 다시 누르면 됩니다(서버를 다시 켤 필요 없음).
