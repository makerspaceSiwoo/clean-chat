"""④ rewrite: 욕설을 빼고 남은 말만 보여 줄 문장으로 만든다. 불확실한 결과는 버린다.

L1(대상 없는 욕설)은 욕설이 든 낱말을 지운 문장, L2 이상은 분석된 피드백만 팀원끼리 쓰는 담백한 말투로 다듬은 문장이다.
지나치게 공손한 말("~님, ~부탁드립니다")은 쓰지 않는다. 원문이 반말이면 부드러운 반말("~해 줘", "~하자")로 둔다.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import threading
import time
import unicodedata
from collections import Counter, OrderedDict
from functools import cache
from pathlib import Path

from clean_chat.core.schemas import Rewrite, RewriteRequest
from clean_chat.modules.rewrite import backend
from clean_chat.modules.rewrite.nicknames import NicknameCodec, without_codes
from clean_chat.modules.rewrite.tracing import preview

_LOG = logging.getLogger(__name__)

# 현재 프로세스 메모리에만 보관한다. 동일한 입력/모델/키의 검증된 성공 결과만 재사용한다.
_CACHE_TTL = 120.0
_CACHE_LIMIT = 128
_CACHE: OrderedDict[str, tuple[float, str]] = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _cache_key(prompt: str, names: list[str], profanity: list[str], config: dict[str, str]) -> str:
    payload = json.dumps(
        [prompt, names, profanity, config, backend._SYSTEM_INSTRUCTION], ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cached(key: str) -> str | None:
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry[0] >= _CACHE_TTL:
            del _CACHE[key]
            return None
        _CACHE.move_to_end(key)
        return entry[1]


def _remember(key: str, text: str) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), text)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_LIMIT:
            _CACHE.popitem(last=False)


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

_EXPLICIT_ABUSE = (
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
    "자살",
    "멍청",
    "노답",
    # 사람을 깎아내리는 말: 피드백 조각에 섞여 와도 화면에 그대로 내보내지 않는다 ("이 쓰레기 서폿아 시야 좀")
    "쓰레기",
    "등신",
    "머저리",
    "찐따",
    "버러지",
    "한심",
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


def _feedback_in_original(span: str, original: str) -> bool:
    """띄어쓰기와 명백한 거친 접두어 정리는 허용하되 행동·부정은 보존한다."""

    def normalized(text: str) -> str:
        return re.sub(r"쳐(?=먹)", "", _fold(text))

    return normalized(span) in normalized(original)


def _build_prompt(original: str, cleaned: str, spans: list[str]) -> str:
    """알려진 닉네임을 익명화한 원문·욕설 제거 원문·선택된 피드백을 데이터로 전송한다."""
    return json.dumps({"original": original, "cleaned": cleaned, "feedback_spans": spans}, ensure_ascii=False)


@cache
def _profanity_words() -> tuple[str, ...]:
    """공용 우회어 사전을 첫 검사 때 읽고, 명백한 비속어만 보완한다."""
    words = set(_EXPLICIT_ABUSE)
    path = Path(backend.ROOT) / "data" / "lexicon" / "bypass.csv"
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("harm_type") in {"profanity", "family_insult", "sexual_harassment"}:
                    words.update(row.get(key, "") for key in ("variant", "canonical"))
    except (OSError, UnicodeError, csv.Error):
        _LOG.warning("[욕설 사전] 공용 사전을 읽지 못해 내장 비속어 목록으로 검사합니다.")
    return tuple(sorted(word for word in words if word))


def _clean_output(generated: str) -> str:
    """설명 접두어와 감싼 따옴표만 제거한다. 여러 문장을 임의로 잘라 쓰지 않는다."""
    text = generated.strip()
    text = re.sub(r"^(?:순화(?:된)?\s*문장|순화\s*결과|결과)\s*[:：]\s*", "", text)
    return " ".join(text.strip("\"'“”‘’").split())


def _still_abusive(text: str, profanity: list[str] | None = None) -> bool:
    folded = _fold(text)
    if any(_fold(word) in folded for word in (*_profanity_words(), *(profanity or [])) if _fold(word)):
        return True
    # 문맥이 필요한 비난/위협은 단어 전체를 금지하지 않고 명확한 표현만 검사한다.
    return bool(
        re.search(
            unicodedata.normalize(
                "NFKC",
                r"못하네|못함[ㅋㅎ]|뭐하(?:냐|노|니|는거)|뭐함|트롤(?:이네|이냐|새끼|놈)|(?:너|넌|니가)트롤|^(?:너|넌|그냥)?죽어(?:라|버려)?$",
            ),
            folded,
        )
    )


_MASKED = re.compile(r"\*+")  # 게임 자체 필터나 OCR 이 남긴 가림 표시


def _without_profanity(original: str, profanity: list[str]) -> str | None:
    """욕설이 든 낱말을 통째로 지우고 남은 말을 돌려준다. 남는 말이 없거나 여전히 거칠면 None.

    예) "아 ㅅㅂ 내가 실수함" → "아 내가 실수함" / "아 ㅅㅂ" → None / "ㅅ1발 새끼들아" → None
    조사·어미가 붙은 낱말("새끼들아", "ㅂㅅ아")은 욕설만 빼면 부스러기가 남으므로 낱말째 지운다.
    """
    spans = [span for span in dict.fromkeys(profanity) if span.strip()]
    kept = [
        word
        for word in original.split()
        if not any(span in word for span in spans) and not _MASKED.search(word) and not _still_abusive(word)
    ]
    text = " ".join(kept)
    letters = sum(ch.isalnum() for ch in text)
    if (len(kept) < 2 and letters < 3) or not any("가" <= ch <= "힣" or ch.isascii() and ch.isalnum() for ch in text):
        return None  # "아", "ㅋㅋ" 처럼 뜻 있는 말이 남지 않음
    return None if _still_abusive(text, spans) else text


def _rule(spans: list[str], original: str, champions: list[str] | None = None) -> str | None:
    """검토한 표현만 변환한다. 모르는 표현·복수 지시는 새 내용을 만들지 않고 포기한다."""
    if len(spans) != 1:
        return None
    span = spans[0].strip().rstrip(".!? ")
    # 이름/챔피언으로 이루어진 명확한 참가자 접두어만 기존 단일 지시 규칙 앞에 보존한다.
    champion_pattern = "|".join(re.escape(c) for c in sorted(champions or [], key=len, reverse=True))
    participant = r"플레이어_[0-9]{4}(?:님)?"
    if champion_pattern:
        participant += rf"|(?:{champion_pattern})"
    member = rf"(?:{participant})(?:이랑|랑|과|와)?"
    prefixed = re.fullmatch(rf"({member}(?:\s+{member})*)\s+(.+)", span)
    if prefixed:
        tail = _rule([prefixed.group(2)], original, champions)
        return f"{prefixed.group(1)} {tail}" if tail else None
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


_TONE = re.compile(r"(?:요|죠|시다|니다|자|줘|주라|줄래|래|까|봐|야|해|지|게|지 ?마)[.!?~]?$|\?$")


def _output_checks(
    text: str, source: str, names: list[str], profanity: list[str], context: str = ""
) -> list[tuple[str, bool, str]]:
    """context = 원문 문장 (닉네임 코드로 바꾼 것). 피드백 조각 밖이어도 원문에 있던 대상은 호칭으로 붙일 수 있다.

    예) "정글 ㅂㅅ아 와드 좀 박아", 조각 "와드 좀 박아" → "정글 와드 좀 박아 줘" 는 통과 (정글은 원문에 있음)
        조각 "용 먼저 치라고" → "바론 먼저 치자" 는 거절 (바론은 원문에 없음)
    """
    source_targets, result_targets = _targets(source), _targets(text)
    allowed_targets = source_targets | _targets(context)
    source_numbers = Counter(re.findall(r"\d+(?:[.,]\d+)*", without_codes(source)))
    result_numbers = Counter(re.findall(r"\d+(?:[.,]\d+)*", without_codes(text)))
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
        ("말투", bool(_TONE.search(text)), "존댓말·부드러운 반말 요청(~줘/~하자)·질문형 확인"),
        (
            "수치",
            source_numbers == result_numbers,
            f"원문={dict(source_numbers)}, 결과={dict(result_numbers)} — 추가/누락/변경 금지",
        ),
        (
            "명확한 대상",
            source_targets <= result_targets <= allowed_targets,
            f"피드백={sorted(source_targets)}, 결과={sorted(result_targets)}, 원문 문장={sorted(allowed_targets)}"
            " — 피드백의 대상은 빠지면 안 되고, 원문에 없던 대상은 추가 금지",
        ),
        ("직접 행동 반전", not _direct_reversal(source, text), "동일 동사의 명백한 실행/금지 반전 확인"),
    ]


def _acceptable(text: str, source: str, names: list[str], profanity: list[str], context: str = "") -> bool:
    return all(ok for _, ok, _ in _output_checks(text, source, names, profanity, context))


def _log_checks(text: str, source: str, names: list[str], profanity: list[str], context: str = "") -> list[str]:
    failures = []
    for label, ok, detail in _output_checks(text, source, names, profanity, context):
        _LOG.info("[로컬 검사/%s] %s — %s", label, "통과" if ok else "거절", detail)
        if not ok:
            failures.append(label)
    return failures


def _request_checks(
    text: str,
    source: str,
    names: list[str],
    profanity: list[str],
    codec: NicknameCodec,
    spans: list[str],
    champions: list[str],
    context: str = "",
) -> list[str]:
    failures = _log_checks(text, source, names, profanity, context)
    code_ok = codec.preserves(text, spans)
    _LOG.info("[로컬 검사/닉네임 코드] %s — 선택된 코드 누락/변형/추가 검사", "통과" if code_ok else "거절")
    if not code_ok:
        failures.append("닉네임 코드")
    # 피드백의 챔피언은 빠지면 안 되고, 원문 문장에 있던 챔피언은 호칭으로 붙일 수 있다 ("리신 바텀 갱 와 줘")
    in_source, in_text = {c for c in champions if c in source}, {c for c in champions if c in text}
    champion_ok = in_source <= in_text <= in_source | {c for c in champions if c in context}
    _LOG.info("[로컬 검사/챔피언명] %s — 피드백=%s, 결과=%s", "통과" if champion_ok else "거절", in_source, in_text)
    if not champion_ok:
        failures.append("챔피언명")
    if len(codec.restore(text)) > 180:
        failures.append("복원 후 문장 길이")
    return failures


def run(req: RewriteRequest) -> Rewrite:
    """악성 문장의 피드백 조각만 롤 용어를 살린 담백한 문장 1개로 다듬는다 (과한 존댓말 없이).

    입력: RewriteRequest(message, analysis) → 출력: Rewrite(msg_id, rewritten, backend)
    예) "야 정글 ㅂㅅ아 용 먼저 치라고", feedback_spans=["용 먼저 치라고"] → "용 먼저 치자"
    예) "아 정글 ㅂㅅ 왜 안 와", feedback_spans=["왜 안 와"] → "정글 합류 부탁해요"
    예) L1 "아 ㅅㅂ 내가 실수함", profanity_spans=["ㅅㅂ"] → "아 내가 실수함" (로컬 처리, 남는 말이 없으면 None)
    순서: 입력 검사 → 원문/욕설 제거 본문/피드백 전송 → 생성/출력 검사 → 실패 시 예비 규칙
    주의: 3초 제한. 원문/분석을 수정하지 않고, 알려진 닉네임·raw는 전송하지 않는다.
          API 실패·거절·지연 시 안전한 예비 규칙 또는 None. 원문에 없는 내용을 지어내지 않는다.
    관련: ADR-0005, ADR-0017, OPEN-04, SPEC 8장(리라이트 3초)
    """
    started = time.monotonic()
    empty = Rewrite(msg_id=req.message.id, rewritten=None, backend="rule")
    _LOG.info(
        "[입력] 등급=L%s, 원문=%d자, 피드백=%d조각",
        req.analysis.level,
        len(req.message.text),
        len(req.analysis.feedback_spans),
    )
    if req.analysis.msg_id != req.message.id or req.analysis.level < 1:
        _LOG.info("[최종] null — 분석 ID 불일치 또는 L0")
        return empty
    if req.analysis.level == 1:
        # L1(대상 없는 욕설)은 자주 나온다. 외부 호출 없이 욕설만 지워서 바로 돌려준다.
        result = _without_profanity(req.message.text, req.analysis.profanity_spans)
        _LOG.info("[최종] backend=rule — L1 욕설 제거, 결과=%s", "있음" if result else "null (남는 말이 없음)")
        return empty.model_copy(update={"rewritten": result})
    spans = list(dict.fromkeys(s.strip() for s in req.analysis.feedback_spans if s.strip()))
    original = req.message.text
    if not spans:
        _LOG.info("[최종] null — 비어 있지 않은 피드백 조각이 없음")
        return empty
    if len(spans) > 8 or len(original) > 4000:
        _LOG.info("[최종] null — 입력 제한 초과 (피드백 최대 8조각, 원문 최대 4000자)")
        return empty
    unmatched = [index + 1 for index, span in enumerate(spans) if not _feedback_in_original(span, original)]
    if unmatched:
        _LOG.info("[최종] null — 원문에서 확인되지 않는 피드백 조각 번호=%s (띄어쓰기·쳐먹→먹 정리 후 비교)", unmatched)
        return empty
    _LOG.info("[입력 검사] 피드백 출처 확인 통과 (띄어쓰기·쳐먹→먹 정리 허용)")
    raw_original, raw_spans = original, spans
    roster_names = [player.name for player in req.players if player.name not in {"나", "본인"}]
    known = [
        name for name in (req.message.speaker, req.analysis.target) if name and name not in {*_ROLES, "나", "본인"}
    ]
    codec = NicknameCodec([*roster_names, *known], [original, *spans])
    names = codec.names
    champions = list(dict.fromkeys(p.champion for p in req.players if p.champion))
    original = codec.encode(original)
    spans = [codec.encode(span) for span in spans]
    profanity = [codec.encode(word) for word in req.analysis.profanity_spans]
    span_abusive = any(_still_abusive(span, profanity) for span in spans)
    if span_abusive:
        # 피드백 조각에 깎아내리는 말이 섞여 왔다 ("이 쓰레기 서폿아 시야 좀"). Gemini 가 빼고 다듬게 하고,
        # 결과는 아래 욕설 검사를 다시 거친다. Gemini 도 못 하면 조각을 그대로 보이지 않고 숨긴다.
        _LOG.info("[입력 검사] 선택된 피드백에 욕설·비하어가 섞임 — 다듬은 결과만 쓰고 조각 그대로 표시는 하지 않음")
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
        cleaned = original
        for word in sorted(profanity, key=len, reverse=True):
            if word:
                cleaned = cleaned.replace(word, "")
        cleaned = " ".join(cleaned.split())
        prompt = _build_prompt(original, cleaned, spans)
        # 요청마다 코드는 달라도 같은 문맥의 검증된 결과는 로컬에서 다시 치환해 재사용할 수 있다.
        raw_cleaned = raw_original
        for word in sorted(req.analysis.profanity_spans, key=len, reverse=True):
            if word:
                raw_cleaned = raw_cleaned.replace(word, "")
        cache_key = _cache_key(
            _build_prompt(raw_original, " ".join(raw_cleaned.split()), raw_spans),
            names,
            req.analysis.profanity_spans,
            {**config, "_champions": "|".join(champions)},
        )
        cached = _cached(cache_key)
        generated = codec.encode(cached) if cached is not None else None
        cache_hit = generated is not None
        if cache_hit:
            _LOG.info("[캐시] 120초 내 동일 입력의 검증된 결과 재사용 — API 호출 없음, 추가 사용량 0토큰")
        else:
            _LOG.info("[캐시] 재사용할 결과 없음 — Gemini 호출")
            generated = backend.generate(prompt, max(0, 2.7 - (time.monotonic() - started)), config)
        if generated is not None:
            clean = _clean_output(generated)
            _LOG.info("[초안] %s", preview(generated, secrets=secrets, names=names))
            _LOG.info("[출력 정리] %s", preview(clean, secrets=secrets, names=names))
            failures = _request_checks(clean, source, names, profanity, codec, spans, champions, original)
            elapsed = time.monotonic() - started
            if elapsed >= 3:
                failures.append("3초 제한")
            if not failures:
                if not cache_hit:
                    _remember(cache_key, codec.restore(clean))
                restored = codec.restore(clean)
                _LOG.info(
                    "[최종] backend=api, %.3f초, 결과=%s", elapsed, preview(restored, secrets=secrets, names=names)
                )
                return Rewrite(msg_id=req.message.id, rewritten=restored, backend="api")
            _LOG.info("[API 결과 거절] 사유: %s (%.3f초) — 예비 규칙을 확인합니다.", ", ".join(failures), elapsed)
    _LOG.info("[예비 규칙] API 실패/거절 또는 rule 설정 — 안전한 규칙을 확인합니다.")
    result = _rule(spans, original, champions)
    if result:
        _LOG.info("[예비 규칙 초안] %s", preview(result, secrets=secrets, names=names))
        failures = _request_checks(result, source, names, profanity, codec, spans, champions, original)
        if not failures and time.monotonic() - started < 3:
            _LOG.info("[최종] backend=rule — AI 생성이 아닌 예비 규칙, %.3f초", time.monotonic() - started)
            return Rewrite(msg_id=req.message.id, rewritten=codec.restore(result), backend="rule")
        _LOG.info("[예비 규칙] 거절=%s", ", ".join(failures) or "3초 제한")
    # 다듬지 못했어도 피드백 조각 자체는 욕설이 없고(위에서 확인) 원문에 있던 말이다. 숨기지 않고 그대로 보여 준다.
    # 숨기면 "욕설에 섞인 게임 피드백만 남긴다"는 기능이 Gemini 응답 하나에 좌우된다.
    plain = " ".join(spans)
    if plain.strip() and not span_abusive and not _still_abusive(plain, profanity) and len(plain) <= 180:
        _LOG.info("[최종] backend=rule — 다듬지 못해 피드백 조각을 그대로 사용 (%.3f초)", time.monotonic() - started)
        return Rewrite(msg_id=req.message.id, rewritten=codec.restore(plain), backend="rule")
    _LOG.info("[최종] null — 규칙에 없는 표현 또는 안전한 변환 불가 (%.3f초)", time.monotonic() - started)
    return empty
