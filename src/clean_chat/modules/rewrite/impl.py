"""④ rewrite: 분석된 피드백만 공손한 문장으로 바꾸고 불확실한 결과는 버린다."""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata

from clean_chat.core.schemas import Rewrite, RewriteRequest
from clean_chat.modules.rewrite import backend

_LOG = logging.getLogger(__name__)
# 앱/시뮬레이터가 모듈을 불러오는 준비 단계. 생성 함수의 3초 예산과 구분한다.
backend.prepare()

_ROLES = ("정글", "미드", "탑", "원딜", "서폿", "서포터")
_TERMS = (
    *_ROLES,
    "용",
    "바론",
    "전령",
    "공허",
    "유충",
    "장로",
    "타워",
    "포탑",
    "억제기",
    "넥서스",
    "와드",
    "미니맵",
    "시야",
    "갱",
    "합류",
    "한타",
    "라인",
    "CS",
    "씨에스",
    "점멸",
    "텔",
    "궁",
    "스펠",
    "다이브",
    "로밍",
    "리콜",
    "귀환",
    "레드",
    "블루",
    "스틸",
    "백도어",
    "킬",
    "데스",
    "아이템",
)
_ABUSE = (
    "씨발",
    "시발",
    "씨팔",
    "시팔",
    "ㅅㅂ",
    "ㅆㅂ",
    "병신",
    "븅신",
    "ㅂㅅ",
    "지랄",
    "ㅈㄹ",
    "좆",
    "존나",
    "ㅈㄴ",
    "새끼",
    "ㅅㄲ",
    "개새",
    "애미",
    "애비",
    "느금",
    "니엄마",
    "니애미",
    "뒤져",
    "뒤지",
    "죽어",
    "자살",
    "멍청",
    "쓰레기",
    "트롤",
    "못하",
    "못해",
    "못함",
    "노답",
    "fuck",
    "bitch",
    "idiot",
    "retard",
    "ㅗ",
)
_RULES = {
    "용 먼저 치라고": "용 먼저 치자",
    "용 먼저 쳐": "용 먼저 치자",
    "왜 안 와": "합류 부탁해요",
    "왜 안와": "합류 부탁해요",
    "와드 좀 박아": "와드 설치 부탁해요",
    "와드 박아": "와드 설치 부탁해요",
    "빼라고": "뒤로 빠져 주세요",
    "빼": "뒤로 빠져 주세요",
    "들어가지 마": "들어가지 말아 주세요",
    "용 치지 마": "용 치지 말아 주세요",
    "용 치지 말라고": "용 치지 말아 주세요",
    "바론 치지 마": "바론 치지 말아 주세요",
    "바론 치지 말라고": "바론 치지 말아 주세요",
    "합류해": "합류 부탁해요",
}


def _fold(text: str) -> str:
    """띄어쓰기·기호·제로폭 문자를 제거해 우회 욕설도 비교한다."""
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def _build_prompt(spans: list[str], original: str) -> str:
    """본문과 확인된 피드백만 JSON 데이터로 보낸다. raw·닉네임 필드는 넣지 않는다."""
    return json.dumps({"text": original, "feedback_spans": spans}, ensure_ascii=False)


def _clean_output(generated: str) -> str:
    """설명 접두어와 감싼 따옴표만 제거한다. 여러 문장을 임의로 잘라 쓰지 않는다."""
    text = generated.strip()
    text = re.sub(r"^(?:순화(?:된)?\s*문장|순화\s*결과|결과)\s*[:：]\s*", "", text)
    return " ".join(text.strip("\"'“”‘’").split())


def _still_abusive(text: str, profanity: list[str] | None = None) -> bool:
    folded = _fold(text)
    return any(_fold(word) in folded for word in (*_ABUSE, *(profanity or [])) if _fold(word))


def _rule(spans: list[str], original: str) -> str | None:
    """검토한 표현만 변환한다. 모르는 표현·복수 지시는 새 내용을 만들지 않고 포기한다."""
    if len(spans) != 1:
        return None
    span = spans[0].strip().rstrip(".!? ")
    result = _RULES.get(span)
    if result is None:
        question = re.fullmatch(
            r"(바론|용|전령|포탑|타워|억제기|넥서스)(?:을|를)?\s*왜\s*(?:쳐|치냐|치니|치는 거야|공격해)", span
        )
        if question:
            objective = question.group(1)
            particle = "을" if (ord(objective[-1]) - 0xAC00) % 28 else "를"
            return f"{objective}{particle} 공격하시는 이유가 있나요?"
    if result is None:
        # 제한 시간 안에 API 결과가 없을 때, 확인한 목표/동작만 보존하는 일반 예비 규칙.
        attack = re.fullmatch(
            r"(바론|용|전령|포탑|타워|억제기|넥서스)(?:을|를)?\s*"
            r"(?:(먼저|같이|함께|지금)\s*)?"
            r"(치라고|치라니까|치자|쳐|치세요|공격해|공격하라고|공격하자|공격해줘|"
            r"치지 말라고|치지 마|공격하지 말라고|공격하지 마)",
            span,
        )
        if attack:
            objective, priority, action = attack.groups()
            verb = "공격하지 말아 주세요" if re.search(r"지\s*(?:마|말)", action) else "공격해 주세요"
            result = " ".join(part for part in (objective, priority, verb) if part)
    if span in {"왜 안 와", "왜 안와"}:
        roles = [role for role in _ROLES if role in original]
        if len(roles) == 1:
            result = f"{roles[0]} 합류 부탁해요"
    return result


def _has_term(term: str, text: str) -> bool:
    """짧은 게임 용어를 일반 단어의 일부와 혼동하지 않는다(궁금/사용/스탑 등)."""
    if term in {"용", "궁", "탑", "텔", "갱", "킬"}:
        suffix = "(?!금)" if term == "궁" else ""
        return bool(re.search(r"(?<![가-힣A-Za-z])" + re.escape(term) + suffix, text))
    if term == "CS":
        return bool(re.search(r"(?<![a-z])cs(?![a-z])", text, re.IGNORECASE))
    return term.casefold() in text.casefold()


def _acceptable(text: str, source: str, names: list[str], profanity: list[str]) -> bool:
    """욕설·개인정보·복수 문장·새 게임 대상/수치/부정 반전을 보수적으로 거절한다."""
    if not text or len(text) > 180 or _still_abusive(text, profanity):
        return False
    if any(_fold(name) in _fold(text) for name in names):
        return False
    if re.search(r"[.!?。！？].*\S", text.rstrip(".!?。！？")) or any(c in text for c in "\n`{}[]<>:："):
        return False
    if not re.search(r"(?:요|죠|시다|자|니다)[.!?。！？]?$", text):
        return False
    if set(re.findall(r"\d+", text)) - set(re.findall(r"\d+", source)):
        return False
    if any(_has_term(term, source) and not _has_term(term, text) for term in _TERMS):
        return False
    added = [term for term in _TERMS if _has_term(term, text) and not _has_term(term, source)]
    # 왜 안 와 → 합류는 명시적인 동의어다.
    if any(term != "합류" or not re.search(r"왜\s*안\s*와", source) for term in added):
        return False
    negative = r"(?:\S+지\s*(?:마|말)|말라고|말아|말자|말고|삼가|자제)"
    return bool(re.search(negative, source)) == bool(re.search(negative, text))


def run(req: RewriteRequest) -> Rewrite:
    """피드백만 순화. 예: 용 먼저 치라고 → 용 먼저 치자. 실패하면 None.

    입력/출력 계약은 유지한다. 전체 대기는 2.7초로 제한하고 API 실패 시 검토된 규칙만 쓴다.
    닉네임·raw는 보내지 않으며 원문/분석/정책을 변경하지 않는다.
    """
    started = time.monotonic()
    empty = Rewrite(msg_id=req.message.id, rewritten=None, backend="rule")
    if req.analysis.msg_id != req.message.id or req.analysis.level < 2:
        return empty
    spans = list(dict.fromkeys(s.strip() for s in req.analysis.feedback_spans if s.strip()))
    original = req.message.text
    if not spans or len(spans) > 8 or len(original) > 4000 or any(s not in original for s in spans):
        return empty
    if any(_still_abusive(span, req.analysis.profanity_spans) for span in spans):
        return empty
    names = [
        name for name in (req.message.speaker, req.analysis.target) if name and name not in {*_ROLES, "나", "본인"}
    ]
    # 개인정보가 들어간 피드백은 안전하게 포기하고, 맥락 본문의 이름만 익명화한다.
    if any(_fold(name) in _fold(span) for name in names for span in spans):
        return empty
    for name in sorted(names, key=len, reverse=True):
        original = original.replace(name, "[플레이어]")
    config = backend.options()
    mode = config["LLM_BACKEND"]
    if mode not in {"api", "rule"}:
        return empty.model_copy(update={"backend": mode if mode == "local" else "rule"})
    source = " ".join(spans)
    if re.search(r"왜\s*안\s*와", source):
        source += " " + " ".join(role for role in _ROLES if role in original)
    if mode == "api":
        generated = backend.generate(_build_prompt(spans, source), max(0, 2.7 - (time.monotonic() - started)), config)
        if generated is not None:
            clean = _clean_output(generated)
            if time.monotonic() - started < 3 and _acceptable(clean, source, names, req.analysis.profanity_spans):
                _LOG.info("[rewrite] Gemini API 순화 문장을 반환합니다.")
                return Rewrite(msg_id=req.message.id, rewritten=clean, backend="api")
            _LOG.info("[rewrite] 생성 결과가 안전/의미 검사를 통과하지 못해 null을 반환합니다.")
            return empty.model_copy(update={"backend": "api"})
    result = _rule(spans, original)
    if result and time.monotonic() - started < 3 and _acceptable(result, source, names, req.analysis.profanity_spans):
        _LOG.info("[rewrite] AI 생성이 아닌, 등록된 규칙으로 변환했습니다.")
        return Rewrite(msg_id=req.message.id, rewritten=result, backend="rule")
    _LOG.info("[rewrite] 규칙에 없는 표현이거나 안전한 변환이 어려워 null을 반환합니다.")
    return empty
