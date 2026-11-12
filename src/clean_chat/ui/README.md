# ui (WP7) — PySide6 클라이언트 + 오버레이

명세: `docs/MODULES.md`의 UI 절 · 구조: `docs/ARCHITECTURE.md`(스레드, 게임 단계)

| 파일 | 내용 | 상태 |
|---|---|---|
| `app.py` | 앱 조립. 게임 단계 신호 → 클라이언트 화면 전환, 오버레이 표시(게임 중)/숨김 | 동작 |
| `bridge.py` | Engine 콜백 → Qt Signal, 흐름 B를 작업 스레드에서 실행(`OutgoingRunner`) | 동작 |
| `client.py` | 클라이언트 창: 대기 / 게임 중 / **이번 게임 결과** 화면 | 배치 완료, 동작 메서드는 스텁 |
| `overlay.py` | 오버레이 창: 필터된 채팅, 내 채팅 입력 → 클립보드 | 배치 완료, 동작 메서드는 스텁 |
| `win32.py` | 🪟 캡처 제외 (ADR-0003, OPEN-02) | 미구현 |

- 스텁(`NotImplementedError`) 메서드는 `app.py`의 `guard`로 감싸져 있어서, 미구현이어도 앱이 멈추지 않고 한 번만 안내합니다.
- 화면은 **판단하지 않습니다.** `Decision`과 `PostGameResult`를 그대로 보여 주기만 합니다.

```bash
uv sync --extra ui
uv run clean-chat app --source demo      # Mac/Windows: 시나리오로 대기 → 게임 중 → 게임 결과 화면 확인
uv run clean-chat app --source screen    # 🪟 실제
uv run pytest tests/test_ui_smoke.py     # 화면 없이 조립 확인
```
웹 비유: `QWidget`은 div, `QVBoxLayout`은 flex-column, Signal/Slot은 이벤트 리스너와 같습니다. **화면 갱신은 메인 스레드에서만** 합니다.
