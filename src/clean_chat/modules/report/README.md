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

- **구현 방식: 템플릿 + 외부 LLM API**. 고정 양식·원문 인용은 템플릿, 사건 경위 문장만 API 로 만듭니다. API 가 실패해도 템플릿만으로 결과를 돌려줍니다. 닉네임 등 개인정보는 API 에 보내지 않고 템플릿에서 채웁니다.
- 출력 형식을 자동 검사합니다.
- `kind=report` 는 복사용 신고 문구(자동 신고 금지), `kind=complaint` 는 고소장 초안 + 한글 PDF(`uv sync --extra report`). PDF 는 git 에 올리지 않습니다.
- 브랜치는 `report/<작업 내용>` 으로 만듭니다(예: `report/first-try`). PR 에서 위 표의 범위 밖 파일을 바꾸면 CI `module-scope` 가 실패합니다(CONTRIBUTING.md).
- 다른 모듈 폴더는 import 하지 않습니다. 함수 이름 `run` 과 입출력 타입은 바꾸지 않습니다(바꿔야 하면 "계약 변경 요청" 이슈).

```bash
uv run sim report                         # 브라우저: 입력 | 디버깅 콘솔(print·logging·오류) | 반환값
uv run pytest tests/test_report.py        # 자동 테스트 (구현 전이면 skip)
uv run python scripts/pack_context.py report   # 웹 AI 채팅에 첨부할 맥락 묶음
```
모듈 코드를 고친 뒤 시뮬레이터에서 [실행]만 다시 누르면 됩니다(서버를 다시 켤 필요 없음).
