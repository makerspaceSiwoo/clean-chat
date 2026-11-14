"""python -m clean_chat.text parse        # parse     (흐름 A, OCR 줄 → 메시지)
python -m clean_chat.text compose      # compose   (흐름 B, 내 입력 → 메시지)
python -m clean_chat.text normalize    # normalize (공통, 우회 비속어 복원)
하위 이름을 빼면 parse."""

import sys

from clean_chat.core.runner import run_module

STAGES = ("parse", "compose", "normalize")
args = sys.argv[1:]
name = args.pop(0) if args and args[0] in STAGES else "parse"
sys.exit(run_module(name, args))
