# policy (WP1) — 정책 Stage 2개

명세: `docs/MODULES.md`의 `incoming_policy / outgoing_policy` 절 · 정책표: `docs/SPEC.md` 5장
입출력 예시: `fixtures/incoming_policy/`, `fixtures/outgoing_policy/`

| 파일 | 내용 | 수정 |
|---|---|---|
| `stage.py` | `IncomingPolicyStage`, `OutgoingPolicyStage`: PolicyRequest → Decision | ❌ (리드) |
| `impl.py` | `IncomingPolicy`(흐름 A, 타 유저 표), `OutgoingPolicy`(흐름 B, 내 채팅 표) — 시그니처·설명만 있음 | ✅ |
| 그 밖의 파일 | 내부 구현용 파일은 자유롭게 추가 | ✅ |

```bash
uv run python -m clean_chat.policy --impl mock --check            # incoming_policy 통신 포맷 확인
uv run python -m clean_chat.policy outgoing --impl mock --check   # outgoing_policy
uv run python -m clean_chat.policy --check                        # 내 구현을 fixtures로 실행·비교 (STRICT)
uv run clean-chat run --real incoming_policy                      # 내 Stage만 실제로 전체 흐름 A
uv run clean-chat say "정글 개새끼" --real outgoing_policy          # 흐름 B 1문장
```
