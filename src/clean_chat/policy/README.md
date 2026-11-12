# policy (WP1)

명세: `docs/MODULES.md`의 `policy` 절 · 입출력 예시: `fixtures/policy/`

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `PolicyStage`: PolicyRequest → Decision | ❌ (리드) |
| `impl.py` | `PolicyEngine` — 실제 구현 (지금은 비어 있음) | ✅ |
| 그 밖의 파일 | 내부 구현용 파일은 자유롭게 추가 | ✅ |

```bash
uv run python -m clean_chat.policy --impl mock --check   # 통신 포맷 확인
uv run python -m clean_chat.policy --check               # 내 구현을 fixtures로 실행·비교
uv run clean-chat run --real policy                      # 내 모듈만 실제로 전체 흐름
```
