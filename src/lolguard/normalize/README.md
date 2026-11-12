# normalize (WP3)

명세: `docs/MODULES.md`의 `normalize` 절 · 입출력 예시: `fixtures/normalize/`

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `NormalizeStage`: ChatMessage → NormalizedMessage | ❌ (리드) |
| `impl.py` | `Normalizer` — 실제 구현 (지금은 비어 있음) | ✅ |
| 그 밖의 파일 | 내부 구현용 파일은 자유롭게 추가 | ✅ |

```bash
uv run python -m lolguard.normalize --impl mock --check   # 통신 포맷 확인
uv run python -m lolguard.normalize --check               # 내 구현을 fixtures로 실행·비교
uv run lolguard run --real normalize                      # 내 모듈만 실제로 전체 흐름
```
