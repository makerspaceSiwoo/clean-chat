# text (WP3) — 문장 처리: parse · compose · normalize

명세: `docs/MODULES.md`의 `parse`, `compose`, `normalize` 절 · 입출력 예시: `fixtures/parse/`, `fixtures/compose/`, `fixtures/normalize/`

채팅 문장을 다루는 Stage 3개를 한 모듈에 둡니다(ADR-0016). Stage 이름·계약은 그대로이고, 파일 하나에 클래스 하나입니다.

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `ParseStage`(RawLine → ParseResult), `ComposeStage`(OutgoingText → ChatMessage), `NormalizeStage`(ChatMessage → NormalizedMessage) | ❌ (리드) |
| `parse.py` | `Parser` — 흐름 A, OCR 줄 분해 (STRICT) | ✅ |
| `compose.py` | `Composer` — 흐름 B, 내 입력 → 메시지 (STRICT) | ✅ |
| `normalize.py` | `Normalizer` — 공통, 우회 비속어 복원 | ✅ |
| 그 밖의 파일 | 내부 구현용 파일은 자유롭게 추가 | ✅ |

```bash
uv run python -m clean_chat.text parse --impl mock --check       # 통신 포맷 확인
uv run python -m clean_chat.text compose --impl mock --check
uv run python -m clean_chat.text normalize --impl mock --check
uv run python -m clean_chat.text parse --check                   # 내 구현을 fixtures로 실행·비교 (STRICT)
uv run clean-chat run --real parse,normalize                     # 내 Stage만 실제로 전체 흐름 A
uv run clean-chat say "아 정글 ㅂㅅ 왜 안 와" --real compose        # 흐름 B 1문장
```
