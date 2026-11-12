"""python -m clean_chat.report             # 신고 문구
python -m clean_chat.report complaint   # 고소장"""

import sys

from clean_chat.core.runner import run_module

name = "complaint" if len(sys.argv) > 1 and sys.argv[1] == "complaint" else "report"
sys.exit(run_module(name, [a for a in sys.argv[1:] if a != "complaint"]))
