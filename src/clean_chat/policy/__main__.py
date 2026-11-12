"""python -m clean_chat.policy            # incoming_policy (흐름 A, 다른 유저 채팅)
python -m clean_chat.policy outgoing   # outgoing_policy (흐름 B, 내 입력)"""

import sys

from clean_chat.core.runner import run_module

name = "outgoing_policy" if len(sys.argv) > 1 and sys.argv[1] == "outgoing" else "incoming_policy"
sys.exit(run_module(name, [a for a in sys.argv[1:] if a != "outgoing"]))
