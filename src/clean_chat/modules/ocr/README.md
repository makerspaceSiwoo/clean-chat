# ① ocr — OCR — 채팅창 이미지 → 텍스트 줄

명세: `docs/MODULES.md`의 `ocr` 절 · 계약: `docs/CONTRACTS.md` · 예시: `fixtures/ocr/`

**할 일은 `impl.py` 의 `run(Frame) -> OcrResult` 함수 하나입니다.** docstring 의 예시·순서·주의를 따라 본문을 채우세요.

| 파일 | 내용 | 수정 |
|---|---|---|
| `impl.py` | `run()` + 제안용 도우미 함수 (`_`로 시작, 바꿔도 됨) | ✅ |
| 그 밖의 파일 | 이 폴더 안에 자유롭게 추가 (사전, 프롬프트, 내부 모듈) | ✅ |
| `fixtures/ocr/input.jsonl` | 입력 예시 추가 | ✅ |
| `fixtures/ocr/expected.jsonl` | 기대값 (명세) | 리드 승인 |
| `tests/test_ocr.py` | 내 테스트 추가 | ✅ |

- AI 모듈: 출력 형식만 자동 검사합니다. 테스트 이미지는 `fixtures/ocr/images/` (README 참고, 실제 채팅·닉네임이 보이는 스크린샷은 커밋 금지).
- Mac 에서 스크린샷 파일로 개발하고, 실제 게임 화면은 Windows 에서 실측합니다. 화면 캡처와 프레임 사이 중복 제거는 구성(리드)이 합니다.
- 브랜치는 `ocr/<작업 내용>` 으로 만듭니다(예: `ocr/first-try`). PR 에서 위 표의 범위 밖 파일을 바꾸면 CI `module-scope` 가 실패합니다(CONTRIBUTING.md).
- 다른 모듈 폴더는 import 하지 않습니다. 함수 이름 `run` 과 입출력 타입은 바꾸지 않습니다(바꿔야 하면 "계약 변경 요청" 이슈).

```bash
uv run sim ocr                         # 브라우저: 입력 | 디버깅 콘솔(print·logging·오류) | 반환값
uv run pytest tests/test_ocr.py        # 자동 테스트 (구현 전이면 skip)
uv run python scripts/pack_context.py ocr   # 웹 AI 채팅에 첨부할 맥락 묶음
```
모듈 코드를 고친 뒤 시뮬레이터에서 [실행]만 다시 누르면 됩니다(서버를 다시 켤 필요 없음).
