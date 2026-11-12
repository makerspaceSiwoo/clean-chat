# rewrite (WP5)

명세: `docs/MODULES.md`의 `rewrite` 절 · 입출력 예시: `fixtures/rewrite/`

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `RewriteStage`: RewriteRequest → Rewrite | ❌ (리드) |
| `impl.py` | `Rewriter` — 실제 구현 (지금은 비어 있음) | ✅ |
| 그 밖의 파일 | 내부 구현용 파일은 자유롭게 추가 | ✅ |

```bash
uv run python -m clean_chat.rewrite --impl mock --check   # 통신 포맷 확인
uv run python -m clean_chat.rewrite --check               # 내 구현을 fixtures로 실행·비교
uv run clean-chat run --real rewrite                      # 내 모듈만 실제로 전체 흐름
```

LLM 백엔드는 `rewrite/backends/` 같은 내부 폴더로 분리하고, 프롬프트는 `rewrite/prompts.md`에서 관리하세요. 키는 `.env`.
