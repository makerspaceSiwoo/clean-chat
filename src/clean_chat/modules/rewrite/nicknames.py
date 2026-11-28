"""요청별 닉네임 코드 치환·보존 검사·복원. 모델 호출이나 파일 저장은 하지 않는다."""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterable

_CODES = re.compile(r"플레이어_[0-9]{4}(?![0-9])")
_MARKER = re.compile(r"플레이어\s*[_＿-]")


def without_codes(text: str) -> str:
    """별도 검증하는 닉네임 코드는 게임 수치/대상 검사에서 제외한다."""
    return _CODES.sub("", text)


class NicknameCodec:
    """한 요청의 명단을 고유한 랜덤 코드로 치환하고 검증 후 로컬에서만 복원한다."""

    def __init__(self, names: Iterable[str], texts: Iterable[str] = ()) -> None:
        canonical: dict[str, str] = {}
        for name in names:
            if name:
                canonical.setdefault(name.casefold(), name)
        self.names = sorted(canonical.values(), key=len, reverse=True)
        occupied = set(_CODES.findall(" ".join(texts)))
        available = [f"플레이어_{number:04d}" for number in range(10000) if f"플레이어_{number:04d}" not in occupied]
        if len(self.names) > len(available):
            raise ValueError("닉네임 코드 공간 초과")
        codes = secrets.SystemRandom().sample(available, len(self.names))
        self._encode_map = {name.casefold(): code for name, code in zip(self.names, codes, strict=True)}
        self._decode_map = dict(zip(codes, self.names, strict=True))
        self._names = re.compile("|".join(re.escape(n) for n in self.names), re.IGNORECASE) if self.names else None

    def encode(self, text: str) -> str:
        """동일한 대응표로 대소문자 차이와 겹치는 닉네임을 일관되게 치환한다."""

        def replace(match: re.Match[str]) -> str:
            direct = self._encode_map.get(match.group().casefold())
            if direct is not None:
                return direct
            # re.IGNORECASE와 casefold가 다르게 취급하는 일부 유니코드 글자도 안전하게 처리한다.
            name = next(n for n in self.names if re.fullmatch(re.escape(n), match.group(), re.IGNORECASE))
            return self._encode_map[name.casefold()]

        return self._names.sub(replace, text) if self._names else text

    def preserves(self, text: str, spans: list[str]) -> bool:
        """선택된 코드의 누락·변형·추가와 원래 닉네임 유출을 거절한다."""
        expected = set(_CODES.findall(" ".join(spans)))
        actual = set(_CODES.findall(text))
        remainder = without_codes(text)
        return (
            expected == actual
            and actual <= self._decode_map.keys()
            and not _MARKER.search(remainder)
            and not (self._names and self._names.search(remainder))
        )

    def restore(self, text: str) -> str:
        """검증된 코드만 원래 명단 표기의 닉네임으로 복원한다. 재귀 치환하지 않는다."""
        return _CODES.sub(lambda match: self._decode_map.get(match.group(), match.group()), text)
