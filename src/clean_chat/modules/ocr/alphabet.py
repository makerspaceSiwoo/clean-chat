"""한국어·영어 OCR 출력 범위와 보수적인 재인식 후보 선택."""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher


def allowed(char: str) -> bool:
    """한글·영문·숫자·문장부호·수학/통화 기호를 허용한다. 판독 불가 표시는 보존한다."""
    code = ord(char)
    return (
        char == "�"
        or char.isspace()
        or 0x20 <= code <= 0x7E
        or 0xAC00 <= code <= 0xD7A3
        or 0x1100 <= code <= 0x11FF
        or 0x3131 <= code <= 0x318E
        or 0xA960 <= code <= 0xA97F
        or 0xD7B0 <= code <= 0xD7FF
        or unicodedata.category(char).startswith("P")
        or unicodedata.category(char) in {"Sc", "Sm"}
    )


def unsupported(text: str) -> int:
    return sum(not allowed(char) or char == "�" for char in text)


def restrict(text: str) -> str:
    """지원하지 않는 문자를 삭제하거나 추측해 바꾸지 않고 판독 불가로 표시한다."""
    return "".join(char if allowed(char) else "�" for char in text)


def prefer_retry(original: str, candidate: str) -> bool:
    """기존 판독 내용 대부분을 유지하면서 잘못된 문자만 줄인 후보만 채택한다."""
    if unsupported(candidate) >= unsupported(original):
        return False
    baseline = "".join(char for char in original if not char.isspace())
    alternative = "".join(char for char in candidate if not char.isspace())
    if len(alternative) < len(baseline) * 0.85 or len(alternative) > len(baseline) * 1.2:
        return False
    if SequenceMatcher(None, baseline, alternative, autojunk=False).ratio() < 0.7:
        return False
    # 허용된 원래 글자의 순서도 유지해야 한다. 단순히 외국 문자가 없는 짧은 후보는 탈락한다.
    known = "".join(char for char in baseline if allowed(char) and char != "�")
    iterator = iter(alternative)
    return all(any(value == char for value in iterator) for char in known)
