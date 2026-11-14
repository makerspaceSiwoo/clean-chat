# session (구성 · 리드) — 게임 단계 감지 + 세션 저장소

명세: `docs/MODULES.md`의 구성 절 · 결정: ADR-0014 · 미정: OPEN-11(명단), OPEN-12(단계 이름)

| 파일 | 내용 | 상태 | 수정 |
|---|---|---|---|
| `fake.py` | `FakePhaseDetector`: `fixtures/scenario/phases.jsonl`, `players.jsonl` 재생 | 동작 | ✅ |
| `windows.py` | 🪟 `LcuPhaseDetector`: LCU `gameflow-phase` 읽기(읽기 전용) + Live Client Data 명단 | 시그니처·설명만 | ✅ |
| `store.py` | `JsonlSessionRepository`: `.clean-chat/sessions/<id>.jsonl` 저장·조회 | 시그니처·설명만 | ✅ |
| `core/game.py` | 상태 기계, 저장소 포트, 게임 종료 배치 (참고용) | 동작 | ✅ (리드) |

감지기는 단계를 **보고만** 합니다. 어떤 전환을 받아들일지는 `core/game.py`의 상태 기계가 정합니다.

```bash
uv run python -m clean_chat.session          # 가짜 감지기: 단계 이벤트와 명단 출력 (모든 OS)
uv run python -m clean_chat.session --real   # 🪟 롤 클라이언트를 켜고 실행, 로비 → 게임 → 종료하며 단계 이름 실측 (Ctrl+C)
uv run clean-chat run --source demo          # 단계 전환이 앱 전체 흐름에 어떻게 쓰이는지
```

금지: LCU로 채팅 읽기, POST/PUT 같은 조작 요청, lockfile 비밀번호를 로그·파일에 남기기 (ADR-0002, ADR-0014)
