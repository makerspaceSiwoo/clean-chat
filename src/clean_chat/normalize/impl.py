"""[구현 · WP3] NormalizeStage: ChatMessage → NormalizedMessage  (명세: docs/MODULES.md#normalize)

우회 비속어를 원래 형태로 되돌려 분류기가 잡을 수 있게 한다. 학습 데이터(training/)에도 같은 함수를 쓴다.
"""

from __future__ import annotations

from clean_chat.core.schemas import ChatMessage, NormalizedMessage
from clean_chat.normalize.stage import NormalizeStage


class Normalizer(NormalizeStage):
    """[구현 · WP3] ChatMessage → NormalizedMessage"""

    def setup(self) -> None:
        """우회어 사전(data/lexicon/bypass.csv)과 OCR 오인식 보정표 로딩. 앱 시작 시 1번."""
        raise NotImplementedError("normalize 담당: setup")

    def run(self, item: ChatMessage) -> NormalizedMessage:
        """본문(text)을 정리한 text_norm 과, 어떤 보정을 했는지 hints 를 붙인다.

        입력: ChatMessage → 출력: NormalizedMessage(원래 필드 그대로 + text_norm + hints)
        예) "미드 시1발 개못하네" → text_norm="미드 시발 개못하네", hints=["noise_removed"]
        예) "탑 니애미 tlqkf" → text_norm="탑 니애미 시발", hints=["lexicon:tlqkf"]
        예) "야 정글 ㅂㅅ아 용 먼저 치라고" → text_norm="야 정글 병신아 용 먼저 치라고", hints=["lexicon:ㅂㅅ"]
        순서: _remove_noise_between_hangul → _join_spaced_jamo → _squeeze_repeats → _fix_ocr_errors → _apply_lexicon
        주의: text 와 raw 는 증거라서 절대 바꾸지 않는다(text_norm 만). 정상 문장은 그대로(과잉 보정 금지).
        관련: SPEC 2장 페인 포인트 2
        """
        raise NotImplementedError("normalize 담당: run")

    def _remove_noise_between_hangul(self, text: str) -> tuple[str, list[str]]:
        """한글 사이 숫자·특수문자 제거. 예) "시1발" → "시발". (바뀐 문장, 붙일 hints)"""
        raise NotImplementedError

    def _join_spaced_jamo(self, text: str) -> tuple[str, list[str]]:
        """자모 사이 공백 제거. 예) "ㅅ ㅂ" → "ㅅㅂ"."""
        raise NotImplementedError

    def _squeeze_repeats(self, text: str) -> tuple[str, list[str]]:
        """같은 글자 반복 축약. 예) "ㅋㅋㅋㅋㅋ" → "ㅋㅋ"."""
        raise NotImplementedError

    def _fix_ocr_errors(self, text: str) -> tuple[str, list[str]]:
        """OCR 오인식 보정표 적용. 예) "l" ↔ "1", "0" ↔ "o" (한글 맥락에서만)."""
        raise NotImplementedError

    def _apply_lexicon(self, text: str) -> tuple[str, list[str]]:
        """우회어 사전 치환. 예) "tlqkf" → "시발" (hints: "lexicon:tlqkf"). 영타 변환 포함."""
        raise NotImplementedError

    def _load_lexicon(self) -> dict[str, str]:
        """bypass.csv(variant, canonical, harm_type, note) → {variant: canonical}."""
        raise NotImplementedError
