"""본문 정규화. 증거 원문은 건드리지 않고 분석용 문자열과 보정 이력만 만든다."""

from __future__ import annotations

import csv
import re
from functools import cache

from clean_chat.core.config import DATA

_PROTECTED = re.compile(
    r"https?://[^\s<>]+|www\.[^\s<>]+|[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}",
    re.IGNORECASE | re.ASCII,
)


def normalize(text: str) -> tuple[str, list[str]]:
    """URL·이메일을 보존하고 나머지를 정규화한다. 학습 전처리에서도 같은 함수를 쓴다."""
    parts: list[str] = []
    hints: list[str] = []
    end = 0
    for protected in _PROTECTED.finditer(text):
        segment, changes = _normalize_segment(text[end : protected.start()])
        parts.extend((segment, protected[0]))
        hints.extend(changes)
        end = protected.end()
    segment, changes = _normalize_segment(text[end:])
    parts.append(segment)
    hints.extend(changes)
    return "".join(parts), list(dict.fromkeys(hints))


def _normalize_segment(text: str) -> tuple[str, list[str]]:
    """단계 순서를 고정하고 실제로 수행한 보정만 기록한다."""
    text, hints = _remove_noise_between_hangul(text)
    text, changes = _apply_lexicon(text)
    return text, hints + changes


def _remove_noise_between_hangul(text: str) -> tuple[str, list[str]]:
    """기본 숫자 삽입 우회어 복원. 추가 복원 규칙도 사전 안의 표현으로 제한한다."""
    result = re.sub(_bounded_variant("시발", r"시[0-9]+발"), "시발", text)
    return result, ["noise_removed"] if result != text else []


def _bounded_variant(variant: str, pattern: str) -> str:
    """영문 식별자 내부와 긴 자모열의 일부를 사전 단어로 오인하지 않는다."""
    adjacent = "A-Za-z0-9_"
    if all("ㄱ" <= char <= "ㅣ" for char in variant):
        adjacent += "ㄱ-ㅎㅏ-ㅣ"
    return rf"(?<![{adjacent}])(?:{pattern})(?![{adjacent}])"


def _apply_lexicon(text: str) -> tuple[str, list[str]]:
    """사전 항목만 한 번 치환한다. 영타 대소문자는 동일한 사전 키로 기록한다."""
    lexicon, pattern = _lexicon_rules()
    hints: list[str] = []

    def replace(match: re.Match[str]) -> str:
        variant = match[0].lower()
        hints.append(f"lexicon:{variant}")
        return lexicon[variant]

    return pattern.sub(replace, text), hints


@cache
def _load_lexicon() -> dict[str, str]:
    """공유 CSV는 읽기만 하며 실행 위치와 관계없이 저장소 기준으로 찾는다."""
    with (DATA / "lexicon" / "bypass.csv").open(encoding="utf-8-sig", newline="") as stream:
        return {row["variant"].lower(): row["canonical"] for row in csv.DictReader(stream) if row["variant"]}


@cache
def _lexicon_rules() -> tuple[dict[str, str], re.Pattern[str]]:
    """긴 항목부터 찾고, 사전 로딩과 정규식 컴파일은 프로세스당 한 번만 수행한다."""
    lexicon = _load_lexicon()
    variants = sorted(lexicon, key=lambda item: (-len(item), item))
    pattern = "|".join(_bounded_variant(variant, re.escape(variant)) for variant in variants)
    return lexicon, re.compile(pattern or r"(?!)", re.IGNORECASE | re.ASCII)
