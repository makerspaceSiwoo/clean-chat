"""④ rewrite: 분석된 피드백만 공손한 문장으로 바꾸고 불확실한 결과는 버린다."""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata

from clean_chat.core.schemas import Rewrite, RewriteRequest
from clean_chat.modules.rewrite import backend
from clean_chat.modules.rewrite.tracing import preview

_LOG = logging.getLogger(__name__)
# 앱/시뮬레이터가 모듈을 불러오는 준비 단계. 생성 함수의 3초 예산과 구분한다.
backend.prepare()

_ROLES = ("정글", "미드", "탑", "원딜", "서폿", "서포터")
# 지원 어휘 목록이 아니라, 명확한 대상 교체만 잡는 소수의 개념 앵커다.
# 아이템명/CS/골드/미니언 등 임의의 게임 어휘를 허용/거절하는 기준으로 쓰지 않는다.
_TARGETS = {
    "baron": r"바론|내셔\s*남작",
    "dragon": r"(?<![가-힣A-Za-z])(?:용|드래곤)|원소용|장로용",
    "herald": r"전령",
    "turret": r"타워|포탑",
    "inhibitor": r"억제기",
    "nexus": r"넥서스",
    "jungle": r"정글",
    "mid": r"미드",
    "top": r"(?<![가-힣A-Za-z])탑",
    "carry": r"원딜",
    "support": r"서폿|서포터",
}


# 대상의 동의어를 허용하는 것과, 원문에 없는 하위 종류를 추가하는 것을 구분한다.
_DRAGON_DETAILS = {
    "ocean": r"바다(?:의)?\s*(?:드래곤|용)|물용|수룡|ocean\s+(?:dragon|drake)",
    "chemtech": r"(?:화공|화학공학)(?:의)?\s*(?:드래곤|용)|chemtech\s+(?:dragon|drake)",
    "hextech": r"마법공학(?:의)?\s*(?:드래곤|용)|hextech\s+(?:dragon|drake)",
    "infernal": r"화염(?:의)?\s*(?:드래곤|용)|불용|infernal\s+(?:dragon|drake)",
    "mountain": r"대지(?:의)?\s*(?:드래곤|용)|땅용|mountain\s+(?:dragon|drake)",
    "cloud": r"바람(?:의)?\s*(?:드래곤|용)|cloud\s+(?:dragon|drake)",
    "elder": r"장로(?:의)?\s*(?:드래곤|용)|elder\s+(?:dragon|drake)",
}

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


def _dragon_details(text: str) -> set[str]:
    return {kind for kind, pattern in _DRAGON_DETAILS.items() if re.search(pattern, text, re.IGNORECASE)}


def _targets(text: str) -> set[str]:
    result = {concept for concept, pattern in _TARGETS.items() if re.search(pattern, text, re.IGNORECASE)}
    if _dragon_details(text):
        result.add("dragon")
    return result


def _direct_reversal(source: str, rewritten: str) -> bool:
    """같은 동사의 명백한 금지↔실행 반전만 검출한다. 부정 단어 유무를 강제하지 않는다."""

    def forbidden(text: str) -> set[str]:
        return set(re.findall(r"([가-힣]+?)지\s*(?:말|마)", text))

    def positive(stem: str, text: str) -> bool:
        variants = {stem}
        if stem.endswith("하"):
            variants.add(stem[:-1] + "해")
        return any(
            re.search(re.escape(v) + r"\s*(?:자|세요|주세요|줘|라|라고|아\s*주세요|어\s*주세요)\s*[.!?]?$", text)
            for v in variants
        )

    source_bans, result_bans = forbidden(source), forbidden(rewritten)
    return any(stem not in result_bans and positive(stem, rewritten) for stem in source_bans) or any(
        stem not in source_bans and positive(stem, source) for stem in result_bans
    )


def _output_checks(text: str, source: str, names: list[str], profanity: list[str]) -> list[tuple[str, bool, str]]:
    source_targets, result_targets = _targets(source), _targets(text)
    new_numbers = set(re.findall(r"\d+", text)) - set(re.findall(r"\d+", source))
    source_details, result_details = _dragon_details(source), _dragon_details(text)
    return [
        ("문장 길이", bool(text) and len(text) <= 180, f"{len(text)}자 / 최대 180자"),
        (
            "용 종류·속성",
            source_details == result_details,
            f"원문={sorted(source_details)}, 결과={sorted(result_details)} — 없는 종류 추가/교체/삭제 금지",
        ),
        ("욕설", not _still_abusive(text, profanity), "사전 및 분석된 욕설 조각 확인"),
        ("개인정보", not any(_fold(name) in _fold(text) for name in names), "알려진 닉네임 포함 여부"),
        (
            "한 문장 형식",
            not re.search(r"[.!?。！？].*\S", text.rstrip(".!?。！？")) and not any(c in text for c in "\n`{}[]<>:："),
            "설명/복수 문장/코드 형식 확인",
        ),
        ("공손한 표현", bool(re.search(r"(?:요|죠|시다|자|니다)[.!?。！？]?$", text)), "존댓말/청유형/질문형 확인"),
        ("수치", not new_numbers, "새 숫자=" + repr(sorted(new_numbers))),
        (
            "명확한 대상",
            source_targets == result_targets,
            f"원문={sorted(source_targets)}, 결과={sorted(result_targets)}",
        ),
        ("직접 행동 반전", not _direct_reversal(source, text), "동일 동사의 명백한 실행/금지 반전 확인"),
    ]


def _acceptable(text: str, source: str, names: list[str], profanity: list[str]) -> bool:
    return all(ok for _, ok, _ in _output_checks(text, source, names, profanity))


def _log_checks(text: str, source: str, names: list[str], profanity: list[str]) -> list[str]:
    failures = []
    for label, ok, detail in _output_checks(text, source, names, profanity):
        _LOG.info("[로컬 검사/%s] %s — %s", label, "통과" if ok else "거절", detail)
        if not ok:
            failures.append(label)
    return failures


def run(req: RewriteRequest) -> Rewrite:
    """피드백만 순화. 예: 용 먼저 치라고 → 용 먼저 치자. 실패하면 None.

    입력/출력 계약은 유지한다. 전체 대기는 2.7초로 제한하고 API 실패 시 검토된 규칙만 쓴다.
    닉네임·raw는 보내지 않으며 원문/분석/정책을 변경하지 않는다.
    """
    started = time.monotonic()
    empty = Rewrite(msg_id=req.message.id, rewritten=None, backend="rule")
    _LOG.info(
        "[입력] 등급=L%s, 원문=%d자, 피드백=%d조각",
        req.analysis.level,
        len(req.message.text),
        len(req.analysis.feedback_spans),
    )
    if req.analysis.msg_id != req.message.id or req.analysis.level < 2:
        _LOG.info("[최종] null — 분석 ID 불일치 또는 L2 미만")
        return empty
    spans = list(dict.fromkeys(s.strip() for s in req.analysis.feedback_spans if s.strip()))
    original = req.message.text
    if not spans or len(spans) > 8 or len(original) > 4000 or any(s not in original for s in spans):
        _LOG.info("[최종] null — 피드백 없음/개수·길이 초과/원문에 없는 조각")
        return empty
    if any(_still_abusive(span, req.analysis.profanity_spans) for span in spans):
        _LOG.info("[최종] null — 선택된 피드백에 욕설이 포함됨")
        return empty
    names = [
        name for name in (req.message.speaker, req.analysis.target) if name and name not in {*_ROLES, "나", "본인"}
    ]
    # 개인정보가 들어간 피드백은 안전하게 포기하고, 맥락 본문의 이름만 익명화한다.
    if any(_fold(name) in _fold(span) for name in names for span in spans):
        _LOG.info("[최종] null — 피드백에 알려진 닉네임이 포함됨")
        return empty
    for name in sorted(names, key=len, reverse=True):
        original = original.replace(name, "[플레이어]")
    config = backend.options()
    mode = config["LLM_BACKEND"]
    secrets = (config.get("LLM_API_KEY", ""), config.get("GEMINI_API_KEY", ""))
    _LOG.info("[피드백] %s", preview(spans, secrets=secrets, names=names))
    _LOG.info(
        "[설정] backend=%s, model=%s, 키=%s",
        preview(mode, secrets=secrets),
        preview(config.get("LLM_MODEL", ""), secrets=secrets),
        "설정됨" if config.get("LLM_API_KEY") else "없음",
    )
    _LOG.info("[검사 방식] 일반 게임 단어 일치 검사는 사용하지 않음. Gemini 의미 확인 + 독립 안전 검사 사용")
    if mode not in {"api", "rule"}:
        _LOG.info("[최종] null — 지원하지 않는 백엔드 설정")
        return empty.model_copy(update={"backend": mode if mode == "local" else "rule"})
    source = " ".join(spans)
    if re.search(r"왜\s*안\s*와", source):
        source += " " + " ".join(role for role in _ROLES if role in original)
    if mode == "api":
        generated = backend.generate(_build_prompt(spans, source), max(0, 2.7 - (time.monotonic() - started)), config)
        if generated is not None:
            clean = _clean_output(generated)
            _LOG.info("[초안] %s", preview(generated, secrets=secrets, names=names))
            _LOG.info("[출력 정리] %s", preview(clean, secrets=secrets, names=names))
            failures = _log_checks(clean, source, names, req.analysis.profanity_spans)
            elapsed = time.monotonic() - started
            if elapsed >= 3:
                failures.append("3초 제한")
            if not failures:
                _LOG.info("[최종] backend=api, %.3f초, 결과=%s", elapsed, preview(clean, secrets=secrets, names=names))
                return Rewrite(msg_id=req.message.id, rewritten=clean, backend="api")
            _LOG.info("[최종] null — 거절 사유: %s (%.3f초)", ", ".join(failures), elapsed)
            return empty.model_copy(update={"backend": "api"})
    _LOG.info("[예비 규칙] API 결과가 없거나 rule 설정이어서 규칙을 확인합니다.")
    result = _rule(spans, original)
    if result:
        _LOG.info("[예비 규칙 초안] %s", preview(result, secrets=secrets, names=names))
        failures = _log_checks(result, source, names, req.analysis.profanity_spans)
        if not failures and time.monotonic() - started < 3:
            _LOG.info("[최종] backend=rule — AI 생성이 아닌 예비 규칙, %.3f초", time.monotonic() - started)
            return Rewrite(msg_id=req.message.id, rewritten=result, backend="rule")
        _LOG.info("[예비 규칙] 거절=%s", ", ".join(failures) or "3초 제한")
    _LOG.info("[최종] null — 규칙에 없는 표현 또는 안전한 변환 불가 (%.3f초)", time.monotonic() - started)
    return empty
