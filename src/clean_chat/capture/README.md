# capture (WP2) — 🪟 화면 캡처 + OCR

명세: `docs/MODULES.md`의 `ocr` 절 · 입출력 예시: `fixtures/ocr/`

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `OcrStage`: `Frame → OcrResult` | ❌ (리드) |
| `impl.py` | `OcrEngine` — OCR + 중복 제거 | ✅ 구현 |
| `grabber.py` | `ScreenGrabber` — 🪟 화면 영역 → Frame 스트림 | ✅ 구현 (Windows) |

```bash
uv run python -m clean_chat.capture --impl mock --check      # 형식 확인
uv run python -m clean_chat.capture                          # 내 구현 실행 (fixtures/ocr/images 필요)
uv run clean-chat run --source screenshots --real ocr        # 스크린샷 폴더로 전체 흐름 (Mac 가능)
uv run clean-chat run --source screen --real ocr             # 🪟 실제 화면
```
첫 작업: 채팅창 스크린샷을 `fixtures/ocr/images/sample_01.png`로 넣고 `expected.jsonl` 줄 내용을 맞춤 → OCR 엔진 비교(OPEN-03) → `docs/modules/capture.md`에 기록
