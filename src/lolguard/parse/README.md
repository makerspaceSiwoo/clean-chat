# parse (WP3)

명세: `docs/MODULES.md`의 `parse` 절 · 입출력 예시: `fixtures/parse/`

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `ParseStage`: RawLine → ParseResult | ❌ (리드) |
| `impl.py` | `Parser` — 실제 구현 (지금은 비어 있음) | ✅ |
| 그 밖의 파일 | 내부 구현용 파일은 자유롭게 추가 | ✅ |

```bash
uv run python -m lolguard.parse --impl mock --check   # 통신 포맷 확인
uv run python -m lolguard.parse --check               # 내 구현을 fixtures로 실행·비교
uv run lolguard run --real parse                      # 내 모듈만 실제로 전체 흐름
```
