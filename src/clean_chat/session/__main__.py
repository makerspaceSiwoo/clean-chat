"""단계 감지기 단독 실행.

uv run python -m clean_chat.session            # 가짜 감지기: fixtures/scenario/phases.jsonl 재생 (모든 OS)
uv run python -m clean_chat.session --real     # 🪟 LCU 감지기: 롤 클라이언트를 켜고 실행 (Ctrl+C로 종료)
"""

import argparse
import sys

from clean_chat.core.config import FIXTURES, settings
from clean_chat.core.platform import PlatformNotSupported, use_utf8_console
from clean_chat.session.fake import FakePhaseDetector


def main() -> int:
    use_utf8_console()
    ap = argparse.ArgumentParser(prog="python -m clean_chat.session")
    ap.add_argument("--real", action="store_true", help="Windows LCU 감지기 사용")
    a = ap.parse_args()
    if a.real:
        from clean_chat.session.windows import LcuPhaseDetector

        detector = LcuPhaseDetector(settings.phase_poll_sec)
    else:
        scenario = FIXTURES / "scenario"
        detector = FakePhaseDetector(scenario / "phases.jsonl", scenario / "players.jsonl")
    try:
        for ev in detector.events():
            print(ev.model_dump_json())
            if ev.phase == "in_game":
                for p in detector.players():
                    print(f"   player: {p.model_dump_json()}")
    except NotImplementedError as e:
        print(f"⏳ [session] 실제 구현이 아직 없습니다: {e}")
        return 2
    except PlatformNotSupported as e:
        print(f"🪟 [session] {e}")
        return 3
    except KeyboardInterrupt:
        detector.stop()
    print("✅ [session] 단계 이벤트 출력 끝", file=sys.stderr)
    return 0


sys.exit(main())
