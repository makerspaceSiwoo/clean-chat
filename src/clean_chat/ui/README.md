# ui (WP7) — PySide6 클라이언트 + 오버레이

명세: `docs/MODULES.md`의 UI 절 · 구조: `docs/ARCHITECTURE.md` 4장(스레드)

| 파일 | 내용 | 상태 |
|---|---|---|
| `app.py` | 앱 조립 (QApplication + Engine + 창 2개) | 뼈대 |
| `bridge.py` | Engine 콜백 → Qt Signal | 뼈대(동작) |
| `client.py` | 클라이언트 창 | 빈 화면 + TODO |
| `overlay.py` | 오버레이 창 | 빈 화면 + TODO |
| `win32.py` | 🪟 캡처 제외 | 미구현 |

```bash
uv sync --extra ui
uv run clean-chat app --source demo      # Mac/Windows: fixtures 시나리오로 화면 개발
uv run clean-chat app --source screen    # 🪟 실제
```
웹 비유: `QWidget`은 div, `QVBoxLayout`은 flex-column, Signal/Slot은 이벤트 리스너와 같습니다. **화면 갱신은 메인 스레드에서만** 합니다.
