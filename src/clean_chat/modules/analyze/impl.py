"""③ analyze — 누가 누구에게 얼마나 나쁜 말을 했나 + 피드백 조각  (명세: docs/MODULES.md#analyze, 예시: fixtures/analyze/)

**판단만** 한다. 숨김·신고·차단 같은 처리는 구성(core/policy.py)이 Analysis 를 보고 정한다.
모든 채팅에 실행되므로 빠른 소형 모델(KcBERT/KcELECTRA 계열) 또는 사전 규칙을 쓴다(ADR-0005).
모델 로딩처럼 무거운 준비는 functools.cache 로 한 번만, 무거운 import(torch 등)는 함수 안에서 한다.

규칙(사전: lexicon.py)에 파인튜닝 모델 점수(model.py, 없으면 규칙만)를 더한다. 모델은 `_predict_harm` 에서만 쓰고 —
대상·등급·조각은 모델과 상관없이 아래 규칙이 정한다.
"""

from __future__ import annotations

import logging
import re
from itertools import permutations

from clean_chat.core.schemas import Analysis, AnalyzeRequest, ChatMessage, HarmType, Level, Player
from clean_chat.modules.analyze import lexicon, model
from clean_chat.modules.analyze.champions import AMBIGUOUS, CHAMPION_ROLES, canonical, names_of, roles_of

logger = logging.getLogger(__name__)

MODEL_VERSION = "rule-0.2"  # 규칙 버전. 파인튜닝 모델이 있으면 "rule-0.2+<모델 버전>" 으로 기록된다
THRESHOLD = 0.5  # 이 점수 이상이면 해당 유형으로 본다
_RULE_SCORE = 0.9  # 규칙이 걸렸을 때 주는 점수
# 모델 점수를 쓰지 않는 유형. 욕설은 사전이 정확하고(가릴 조각도 사전이 찾는다), 모델만 걸린 욕설은 가릴 조각이 없는 데다
# 검증 문장에서 정상 문장 오탐("와 개쩐다 방금")의 대부분이 여기서 나왔다 (README "모델 비교" 참고).
_RULE_ONLY = frozenset({HarmType.PROFANITY.value})
_MASKABLE = tuple(sorted({*lexicon.PROFANITY, *lexicon.FAMILY_INSULT, *lexicon.SEXUAL}, key=len, reverse=True))
_TOKEN = re.compile(r"\S+")
# 이름 앞에 붙어도 부르는 말로 보는 낱말 ("상대 럭스 …", "다들 야스 신고해")
_LEAD_WORDS = frozenset(
    {"우리", "상대", "저", "이", "쟤", "ㅋㅋ", "ㅋㅋㅋ", "와", "다들", "얘들아", "다", "같이", "끝나고"}
)


def run(req: AnalyzeRequest) -> Analysis:
    """메시지 1개(+ 앞 대화, 명단) → 대상(target), 등급 L0~L3, 유해 유형, 비속어 조각, 피드백 조각.

    입력: AnalyzeRequest(message, history, players) → 출력: Analysis
    예) 불꽃남자(징크스): "야 정글 ㅂㅅ아 용 먼저 치라고" (text_norm "야 정글 병신아 용 먼저 치라고")
        → target="초코우유"(리신 = 정글 챔피언), level=2, harm_types=[profanity, blame], profanity_spans=["ㅂㅅ"], feedback_spans=["용 먼저 치라고"]
    예) 달빛고양이(제드): "아 ㅅㅂ 내가 실수함" → target=None, level=1 (대상 없는 혼잣말), profanity_spans=["ㅅㅂ"]
    예) 얼음땡(다리우스, 전체 채팅): "탑 니애미 tlqkf" → target="밤하늘별"(상대 팀 탑 가렌), level=3, harm_types=[profanity, family_insult]
    예) 밤하늘별(가렌): "다들 화이팅" → level=0, 나머지 빈 값
    순서: _predict_harm → _guess_target → _decide_level → _find_profanity → _extract_feedback
    주의: 내 채팅과 다른 유저 채팅에 같은 기준. CPU 1문장 0.2초 이내. model_version 기록.
          profanity_spans·feedback_spans 는 message.text(원문)에 있는 그대로의 조각이어야 한다.
    관련: SPEC 4장, ADR-0005, docs/LABELING_GUIDE.md
    """
    msg = req.message
    try:
        scores = _predict_harm(msg.text_norm)
        target = _guess_target(msg, req.history, req.players)
        level, harm_types = _decide_level(scores, target)
        if level == Level.L0_CLEAN:  # 정상이면 나머지는 빈 값
            return Analysis(msg_id=msg.id, level=level, model_version=_model_version())
        return Analysis(
            msg_id=msg.id,
            target=target,
            level=level,
            harm_types=harm_types,
            profanity_spans=_find_profanity(msg),
            feedback_spans=_extract_feedback(msg, level),
            scores={t.value: scores[t.value] for t in harm_types},
            model_version=_model_version(),
        )
    except Exception:  # 앱을 멈추지 않는다: 판단 못 하면 정상(L0)으로 돌려준다
        logger.exception("analyze 실패 (msg_id=%s) → L0 으로 돌려줌", msg.id)
        return Analysis(msg_id=msg.id, level=Level.L0_CLEAN, model_version=_model_version())


def _predict_harm(text_norm: str) -> dict[str, float]:
    """유해 유형별 점수 0~1. 예) {"profanity": 0.9, "blame": 0.9}

    규칙 점수와 파인튜닝 모델 점수(model.py, 모델이 없으면 빈 값) 중 유형별 큰 값.
    명시적인 욕설은 규칙이, 욕설 없는 비난·정치질·패드립·성희롱·협박은 모델이 잡는다. 욕설(profanity)은 규칙 점수만 쓴다.
    """
    scores = _rule_scores(text_norm)
    for name, score in model.predict(text_norm).items():
        if name == HarmType.THREAT.value and lexicon.GAME_TALK.search(text_norm):
            continue  # 게임 안의 말("다음 용 때 다 죽인다")은 모델이 협박이라 해도 받지 않는다. 명시적 협박은 규칙이 잡는다
        if name not in _RULE_ONLY and score > scores.get(name, 0.0):
            scores[name] = round(score, 4)
    return scores


def _rule_scores(text_norm: str) -> dict[str, float]:
    """사전 규칙만으로 낸 점수. 걸린 유형만 들어 있다."""
    checks = {
        HarmType.PROFANITY: any(w in text_norm for w in lexicon.PROFANITY),
        HarmType.FAMILY_INSULT: any(w in text_norm for w in lexicon.FAMILY_INSULT),
        HarmType.SEXUAL_HARASSMENT: any(w in text_norm for w in lexicon.SEXUAL),
        HarmType.BLAME: bool(lexicon.BLAME.search(text_norm)),
        HarmType.INSTIGATION: bool(lexicon.INSTIGATION.search(text_norm)),
        HarmType.THREAT: bool(lexicon.THREAT.search(text_norm)),
    }
    return {t.value: _RULE_SCORE for t, hit in checks.items() if hit}


def _model_version() -> str:
    extra = model.version()
    return f"{MODEL_VERSION}+{extra}" if extra else MODEL_VERSION


def _guess_target(message: ChatMessage, history: list[ChatMessage], players: list[Player]) -> str | None:
    """공격 대상 추정 → 닉네임. 포지션 단어(탑/정글/미드/원딜/서폿) → 닉네임·챔피언 언급 → 직전 대화 상대. 모르면 None.

    채팅에는 `닉네임 (챔피언)` 만 있어서 "정글" 이 누구인지는 챔피언의 주 라인으로 추정한다(champions.py).
    한 명으로 좁히지 못하면 문장에 쓰인 포지션 단어("정글")를 그대로 돌려준다.
    """
    text = message.text_norm
    speaker = next((p for p in players if p.name == message.speaker or (p.is_me and message.is_me)), None)
    people = _people(message, history, players)
    found = _position_token(text)
    named = next((p for p in people if _addressed(p, message, speaker)), None)
    if found:
        resolved = _resolve_position(found[0], message, speaker, people)
        # 이름으로 부른 사람이 있으면 포지션 낱말보다 먼저다: 포지션을 한 명으로 못 좁혔거나(말한 사람 자신의 라인 등),
        # 이름이 문장에서 먼저 나올 때. 예) 탑이 한 말 "세주 너 일부러 탑 안 오지" → 대상은 세주아니, "탑" 은 라인 이름
        if named is not None and (resolved is None or _name_index(named, text) < found[1]):
            return named.name
        return resolved or found[0]
    if named is not None:
        return named.name
    if lexicon.SECOND_PERSON.search(text):
        for prev in reversed(history):
            if prev.speaker != message.speaker:
                return prev.speaker
    if not players:  # 명단을 모를 때: 문장에서 부른 챔피언 이름을 그대로 대상으로 둔다 (포지션 단어와 같은 방식)
        return _champion_token(text)
    return None


def _addressed(p: Player, message: ChatMessage, speaker: Player | None) -> bool:
    """문장이 이 사람을 (닉네임이나 챔피언 이름으로) 부르고 있는가.

    이름이 나온다고 다 대상은 아니다. "마이부터 잡으라고" 의 마이는 잡을 상대이지 욕하는 대상이 아니다.
    - 팀 채팅에서 상대 팀 챔피언은 콜의 목적어로 본다 ("상대 마이 ㅂㅅ" 처럼 "상대" 가 붙으면 대상).
    - 이름 뒤에 "부터 / 를 / 을" 이 붙으면 목적어로 본다.
    """
    text = message.text_norm.replace(" ", "")  # 띄어쓰기는 무시한다 (명단 "리 신" ↔ 채팅 "리신")
    enemy = speaker is not None and speaker.team and p.team and p.team != speaker.team
    if enemy and message.channel != "all" and "상대" not in text:
        return False
    for word in (p.name, p.champion):
        word = (word or "").replace(" ", "")
        if len(word) >= 2 and word in text and not re.search(re.escape(word) + r"(부터|를|을)", text):
            return True
    # 줄임말("이즈", "케틀")은 짧아서 다른 낱말 속에 들어 있기 쉽다 → 낱말 단위로만 본다
    return any(_called(alias, message.text_norm) for alias in names_of(p.champion)[1:])


def _name_index(p: Player, text: str) -> int:
    """문장에서 이 사람의 이름(닉네임·챔피언·줄임말)이 처음 나오는 위치. 못 찾으면 문장 끝."""
    spots = [text.find(w) for w in (p.name, *names_of(p.champion)) if w and text.find(w) >= 0]
    return min(spots, default=len(text))


def _people(message: ChatMessage, history: list[ChatMessage], players: list[Player]) -> list[Player]:
    """대상이 될 수 있는 사람들(말한 사람 제외): 명단 + 명단에 없지만 앞 대화에 나온 `닉네임 (챔피언)`."""
    people = [p for p in players if p.name != message.speaker and not (p.is_me and message.is_me)]
    known = {p.name for p in players} | {message.speaker}
    for prev in history:
        if prev.speaker not in known:
            known.add(prev.speaker)
            people.append(Player(name=prev.speaker, champion=prev.champion))
    return people


def _resolve_position(word: str, message: ChatMessage, speaker: Player | None, people: list[Player]) -> str | None:
    """포지션 단어 → 그 라인을 간 사람의 닉네임. 한 명으로 좁히지 못하면 None.

    팀 채팅이면 같은 팀, 전체 채팅이거나 "상대 정글" 이면 상대 팀에서 찾는다(팀을 모르면 전원).
    명단에 포지션이 있으면 그것을, 없으면 챔피언의 주 라인을 쓴다.
    """
    role = lexicon.POSITION_ROLES[word]
    enemy = message.channel == "all" or "상대" in message.text_norm
    pool = people
    if speaker is not None and speaker.team:
        sided = [p for p in people if p.team and (p.team != speaker.team) == enemy]
        pool = sided or [p for p in people if not p.team]
    exact = [p for p in pool if p.position == role]
    if len(exact) == 1:
        return exact[0].name
    team = pool if enemy or speaker is None else [*pool, speaker]  # 같은 팀이면 말한 사람도 한 자리를 차지한다
    if len(team) == 5 and all(roles_of(p.champion) for p in team):
        holders = _lineup_holders(team, role)
        if len(holders) == 1:
            return None if speaker is not None and holders == {speaker.name} else next(iter(holders))
    for rank in (0, 1, 2):  # 주 라인이 맞는 사람이 한 명이면 그 사람, 없으면 두 번째로 자주 가는 라인 …
        match = [p for p in pool if roles_of(p.champion)[rank : rank + 1] == (role,)]
        if match:
            return match[0].name if len(match) == 1 else None
    return None


def _lineup_holders(team: list[Player], role: str) -> set[str]:
    """5명을 다섯 라인에 가장 자연스럽게 배치했을 때 role 을 맡는 사람(동점 배치가 여럿이면 여러 명)."""
    order = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")

    def fit(p: Player, r: str) -> int:
        roles = roles_of(p.champion)
        return 3 - roles.index(r) if r in roles[:3] else -3

    best, holders = None, set()
    for lineup in permutations(team):
        score = sum(fit(p, r) for p, r in zip(lineup, order, strict=True))
        if best is None or score > best:
            best, holders = score, set()
        if score == best:
            holders.add(lineup[order.index(role)].name)
    return holders


def _decide_level(scores: dict[str, float], target: str | None) -> tuple[Level, list[HarmType]]:
    """점수 + 대상 여부 → 등급과 유형 목록. 기준은 SPEC 4-2 (대상 없는 비속어 = L1, 특정인 비난 = L2, 패드립·성희롱·협박 = L3)."""
    hit = [t for t in HarmType if scores.get(t.value, 0.0) >= THRESHOLD]
    if HarmType.FAMILY_INSULT in hit or HarmType.SEXUAL_HARASSMENT in hit or HarmType.THREAT in hit:
        return Level.L3_LEGAL, hit
    if target and hit:
        return Level.L2_ABUSIVE, hit
    # 대상이 없으면 비난·정치질은 성립하지 않는다 ("내가 못했네") → 비속어만 남긴다
    if HarmType.PROFANITY in hit:
        return Level.L1_MILD, [HarmType.PROFANITY]
    return Level.L0_CLEAN, []


def _find_profanity(message: ChatMessage) -> list[str]:
    """원문(text)에서 가릴 비속어 조각. 예) "아 ㅅㅂ 내가 실수함" → ["ㅅㅂ"]. hints 로 원문 위치를 찾는다."""
    text = message.text
    found: list[tuple[int, int]] = []
    # 1) parse 가 사전으로 복원한 우회어: hints "lexicon:<원문 표기>"
    for hint in message.hints:
        variant = hint.removeprefix("lexicon:")
        if variant != hint and variant:
            found += _find_all(re.escape(variant), text)
    # 2) 원문에 그대로 있는 낱말
    for word in _MASKABLE:
        found += _find_all(re.escape(word), text)
    # 3) 정규화 뒤에만 보이는 낱말 ("시1발" → "시발"): 글자 사이에 낀 숫자·기호를 허용해 원문에서 찾는다
    for word in _MASKABLE:
        if word in message.text_norm and word not in text:
            found += _find_all(r"[\d\W_]{0,3}".join(map(re.escape, word)), text)
    # 4) 그래도 못 찾은 낱말 ("ㅅ1ㅂ" → "시발"): 원문과 정규화 문장을 낱말끼리 맞대어, 바뀐 낱말에서 찾는다
    found += _changed_word_spans(text, message.text_norm, found)
    spans: list[str] = []
    end = 0
    for start, stop in sorted(found, key=lambda s: (s[0], s[0] - s[1])):  # 앞에서부터, 같은 자리면 긴 것
        if start >= end and text[start:stop] not in spans:
            spans.append(text[start:stop])
        end = max(end, stop)
    return spans


def _extract_feedback(message: ChatMessage, level: Level) -> list[str]:
    """L2 이상일 때 게임 지시·지적 부분(용, 합류, 와드 등)만. 예) "야 정글 ㅂㅅ아 용 먼저 치라고" → ["용 먼저 치라고"]"""
    if level < Level.L2_ABUSIVE:
        return []
    text = message.text
    position = _position_token(text)
    profanity = _find_profanity(message)
    groups: list[list[re.Match[str]]] = [[]]
    for tok in _TOKEN.finditer(text):
        word = tok.group()
        drop = (
            word in lexicon.INTERJECTIONS
            or (position is not None and tok.start() == position[1])  # 부른 대상 ("정글")
            or any(span in word for span in profanity)  # 욕이 든 낱말 ("ㅂㅅ아")
        )
        if drop:
            groups.append([])
        else:
            groups[-1].append(tok)
    return [text[g[0].start() : g[-1].end()] for g in groups if g and any(_is_action(t.group()) for t in g)]


# ── 내부 도우미 ──────────────────────────────────────────────
def _find_all(pattern: str, text: str) -> list[tuple[int, int]]:
    return [m.span() for m in re.finditer(pattern, text)]


def _changed_word_spans(text: str, text_norm: str, known: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """정규화로 바뀐 낱말 중 비속어가 된 것의 원문 위치. 낱말 수가 같을 때만 맞댄다.

    예) "ㅅ1ㅂ아" ↔ "시발아" → 뒤에 똑같이 붙은 "아" 는 빼고 "ㅅ1ㅂ" 만 돌려준다.
    """
    originals, norms = list(_TOKEN.finditer(text)), _TOKEN.findall(text_norm)
    if len(originals) != len(norms):
        return []
    out: list[tuple[int, int]] = []
    for tok, norm in zip(originals, norms, strict=True):
        word = tok.group()
        hit = next((w for w in _MASKABLE if w in norm), None)
        if word == norm or hit is None or any(tok.start() <= s < tok.end() for s, _ in known):
            continue
        head, tail = norm.index(hit), len(norm) - norm.index(hit) - len(hit)  # 비속어 앞뒤에 붙은 글자 수
        cut_head = next((i for i in range(min(head, len(word))) if word[i] != norm[i]), min(head, len(word)))
        cut_tail = next((i for i in range(min(tail, len(word))) if word[-1 - i] != norm[-1 - i]), min(tail, len(word)))
        if cut_head + cut_tail < len(word):
            out.append((tok.start() + cut_head, tok.end() - cut_tail))
    return out


def _position_token(text: str) -> tuple[str, int] | None:
    """문장에서 처음 나오는 포지션 낱말 → (대표 단어, 낱말 시작 위치). 예) "야 정글아 용 쳐" → ("정글", 2)"""
    for tok in _TOKEN.finditer(text):
        for name, aliases in lexicon.POSITIONS.items():
            if any(re.fullmatch(re.escape(a) + lexicon.PARTICLES + r"[!?.,~]*", tok.group()) for a in aliases):
                return name, tok.start()
    return None


def _called(name: str, text: str) -> bool:
    """문장이 이 이름을 부르는가: 낱말이 `이름 + 조사` 꼴이고 목적어("이즈를", "이즈부터")가 아닐 때."""
    pattern = re.compile(re.escape(name) + lexicon.PARTICLES + r"[!?.,~]*")
    for tok in _TOKEN.finditer(text):
        m = pattern.fullmatch(tok.group())
        if m and m.group(1) not in ("을", "를"):
            return True
    return False


def _champion_token(text: str) -> str | None:
    """문장 맨 앞에서 부른 챔피언 → 정식 이름. 예) "이즈야 궁 써" → "이즈리얼", "상대 럭스 허접" → "럭스"

    맨 앞(군말·"우리"·"상대" 뒤 포함)에 올 때만 부른 것으로 본다. 문장 중간의 챔피언은 대개 이야기의 소재다
    ("아 시발 블츠 그랩에 또 끌렸네" 는 혼잣말). 일상 낱말과 겹치는 이름(AMBIGUOUS)은 보지 않는다.
    """
    for tok in _TOKEN.finditer(text):
        word = tok.group()
        for name in sorted(CHAMPION_ROLES, key=len, reverse=True):
            if len(name) >= 2 and name not in AMBIGUOUS and word.startswith(name) and _called(name, word):
                return canonical(name)
        if word not in lexicon.INTERJECTIONS and word not in _LEAD_WORDS:
            return None
    return None


def _is_action(word: str) -> bool:
    """게임에서 할 수 있는 행동을 가리키는 낱말인가 (용, 와드, 합류, 와 …)."""
    word = word.lower()
    return word.startswith(lexicon.ACTION_NOUNS) or "템" in word or bool(lexicon.ACTION_VERBS.match(word))
