"""시뮬레이터와 데스크톱 앱 진입점. 앱 본체는 clean_chat.desktop (설치 파일에는 시뮬레이터를 넣지 않는다).

uv run sim              모듈 시뮬레이터 (브라우저가 열림). 모듈 하나 골라 입력 → 디버깅 콘솔 → 반환값
uv run sim parse        그 모듈 화면으로 바로 열기 (ocr · parse · analyze · rewrite · report)
uv run sim flow         전체 흐름: 캡처 이미지 → ocr → parse → analyze → rewrite → 정책 → report (구현 전 모듈은 가정 응답)
uv run app              앱 전체 (macOS/Windows 게임 창 · --demo 시나리오 재생)

Mock 은 없습니다 (ADR-0017). app 은 모듈 5개가 모두 구현돼야 끝까지 돌고, 구현 없는 모듈을 만나면 이름을 알리고 멈춥니다.
"""

from __future__ import annotations

import sys

from clean_chat.core.platform import use_utf8_console
from clean_chat.desktop import app


def sim() -> None:
    """`uv run sim [모듈]`"""
    from clean_chat.sim.views import VIEW_NAMES  # 시뮬레이터는 개발용이라 앱 시작 때 불러오지 않는다

    use_utf8_console()
    args = sys.argv[1:]
    module = args[0] if args else None
    names = (*VIEW_NAMES, "flow")
    if len(args) > 1 or (module is not None and module not in names):
        print(f"사용법: uv run sim [{' | '.join(names)}]")
        raise SystemExit(2)
    from clean_chat.sim.server import serve

    serve(module)


main = app  # python -m clean_chat

if __name__ == "__main__":
    main()
