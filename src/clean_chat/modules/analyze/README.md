# ③ analyze — 분석 — 대상·등급·피드백

명세: `docs/MODULES.md`의 `analyze` 절 · 계약: `docs/CONTRACTS.md` · 예시: `fixtures/analyze/`

**할 일은 `impl.py` 의 `run(AnalyzeRequest) -> Analysis` 함수 하나입니다.** docstring 의 예시·순서·주의를 따라 본문을 채우세요.

| 파일 | 내용 | 수정 |
|---|---|---|
| `impl.py` | `run()` + 제안용 도우미 함수 (`_`로 시작, 바꿔도 됨) | ✅ |
| 그 밖의 파일 | 이 폴더 안에 자유롭게 추가 (사전, 프롬프트, 내부 모듈) | ✅ |
| `fixtures/analyze/input.jsonl` | 입력 예시 추가 | ✅ |
| `fixtures/analyze/expected.jsonl` | 기대값 (명세) | 리드 승인 |
| `tests/test_analyze.py` | 내 테스트 추가 | ✅ |

- **구현 방식: 로컬 소형 분류 모델 + 규칙** (LLM·외부 API 아님). 모든 채팅에 실행되므로 CPU 1문장 0.2초 이내가 목표입니다. 가중치는 `models/`(git 제외), 무거운 로딩은 `functools.cache` 로 한 번만.
- AI 모듈: 출력 형식만 자동 검사하고, 정확도는 `training/` 평가와 `data/eval/` 로 봅니다.
- 숨김·신고 같은 처리는 하지 않습니다. 정책표(`core/policy.py`)가 이 결과를 보고 정합니다. 라벨 기준: `docs/LABELING_GUIDE.md`.
- 브랜치는 `analyze/<작업 내용>` 으로 만듭니다(예: `analyze/first-try`). PR 에서 위 표의 범위 밖 파일을 바꾸면 CI `module-scope` 가 실패합니다(CONTRIBUTING.md).
- 다른 모듈 폴더는 import 하지 않습니다. 함수 이름 `run` 과 입출력 타입은 바꾸지 않습니다(바꿔야 하면 "계약 변경 요청" 이슈).

```bash
uv run sim analyze                         # 브라우저: 입력 | 디버깅 콘솔(print·logging·오류) | 반환값
uv run pytest tests/test_analyze.py        # 자동 테스트 (구현 전이면 skip)
uv run python scripts/pack_context.py analyze   # 웹 AI 채팅에 첨부할 맥락 묶음
```
모듈 코드를 고친 뒤 시뮬레이터에서 [실행]만 다시 누르면 됩니다(서버를 다시 켤 필요 없음).
