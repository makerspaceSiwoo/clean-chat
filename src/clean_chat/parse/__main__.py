"""python -m clean_chat.parse            # parse (흐름 A, OCR 줄 → 메시지)
python -m clean_chat.parse compose    # compose (흐름 B, 내 입력 → 메시지)"""

import sys

from clean_chat.core.runner import run_module

name = "compose" if len(sys.argv) > 1 and sys.argv[1] == "compose" else "parse"
sys.exit(run_module(name, [a for a in sys.argv[1:] if a != "compose"]))
