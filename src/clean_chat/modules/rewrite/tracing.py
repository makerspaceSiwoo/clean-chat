"""콘솔 디버깅용 마스킹. 키와 알려진 닉네임을 출력하기 전에 제거한다."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any


def preview(value: Any, *, secrets: Iterable[str] = (), names: Iterable[str] = (), limit: int = 700) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    for sensitive in sorted({v for v in (*secrets, *names) if v}, key=len, reverse=True):
        text = text.replace(sensitive, "[마스킹]")
    text = re.sub(r"(?:AIza[A-Za-z0-9_-]{15,}|AQ\.[A-Za-z0-9._-]{15,}|sk-[A-Za-z0-9_-]{15,})", "[키 마스킹]", text)
    return text if len(text) <= limit else text[:limit] + "…(생략)"
