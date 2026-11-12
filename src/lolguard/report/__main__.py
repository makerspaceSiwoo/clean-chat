"""python -m lolguard.report             # 신고 문구
python -m lolguard.report complaint   # 고소장"""

import sys

from lolguard.core.runner import run_module

name = "complaint" if len(sys.argv) > 1 and sys.argv[1] == "complaint" else "report"
sys.exit(run_module(name, [a for a in sys.argv[1:] if a != "complaint"]))
