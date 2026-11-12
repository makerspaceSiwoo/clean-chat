# parse (WP3) — parse + compose

명세: `docs/MODULES.md`의 `parse`, `compose` 절 · 입출력 예시: `fixtures/parse/`, `fixtures/compose/`

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `ParseStage`(RawLine → ParseResult), `ComposeStage`(OutgoingText → ChatMessage) | ❌ (리드) |
| `impl.py` | `Parser`(흐름 A, OCR 줄 분해), `Composer`(흐름 B, 내 입력) — 시그니처·설명만 있음 | ✅ |
| 그 밖의 파일 | 내부 구현용 파일은 자유롭게 추가 | ✅ |

```bash
uv run python -m clean_chat.parse --impl mock --check           # parse 통신 포맷 확인
uv run python -m clean_chat.parse compose --impl mock --check   # compose
uv run python -m clean_chat.parse --check                       # 내 구현을 fixtures로 실행·비교 (STRICT)
uv run clean-chat run --real parse                              # 내 Stage만 실제로 전체 흐름 A
uv run clean-chat say "아 정글 ㅂㅅ 왜 안 와" --real compose        # 흐름 B 1문장
```
