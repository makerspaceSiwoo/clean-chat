"""대화 판단 — 게임이 끝난 뒤 전체 대화를 보고 "누가 누구에게, 특히 나에게 무엇을 했는가"를 화자별로 정리한다.

실시간 필터(impl.run)는 메시지 1개만 보고 가릴 욕설을 찾는다. 신고·고소처럼 무거운 결정은 한 문장으로 정하지 않고,
여기서 대화 흐름 전체(반복, 동조, 여러 명의 몰이)를 보고 정한다. 고소 후보에는 판례 요건 점검(precedents.py)을 붙인다.

    judge(JudgeRequest(messages=..., players=..., my_name="나")) → Judgment
    judge_session(game_session)                                  → Judgment   (세션 기록을 그대로 넣을 때)

아직 앱 흐름(core)에는 연결하지 않았다. 지금은 정책표(core/policy.py)가 실시간으로 신고·고소 후보를 표시한다.
연결하려면 계약 변경(모듈 추가, 게임 종료 배치가 이 함수를 부름)이 필요하다 → README 의 "다음 단계".

점수는 학습된 확률이 아니라 가중치를 더한 값이다. 아래 상수는 예문으로 조정해야 한다.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from clean_chat.core.schemas import Analysis, AnalyzeRequest, ChatMessage, GameSession, HarmType, Level, Player
from clean_chat.modules.analyze import impl, lexicon, precedents
from clean_chat.modules.analyze.champions import roles_of

VERSION = "judge-0.1"
HISTORY = 10  # 메시지를 다시 분석할 때 넘기는 앞 대화 수 (실시간과 같게)
DECAY_SEC = 300.0  # 누적 점수가 1/e 로 줄어드는 시간
WEIGHT_L2 = 1.0
WEIGHT_L3 = 3.0
WEIGHT_INSTIGATION = 0.5  # 정치질(몰이)이면 더한다
WEIGHT_AGREE = 0.5  # 남의 악성 채팅에 동조 ("ㅇㅈ")
PILE_ON = 1.25  # 같은 사람을 2명 이상이 공격했으면 곱한다
COMPLAINT_SCORE = 3.0  # 나를 향한 누적 점수가 이 이상이면 고소 후보 (L3 1번 또는 짧은 시간에 L2 반복)
AGREE_WINDOW_SEC = 20.0
AGREE = re.compile(r"^(ㅇㅈ|ㄹㅇ|ㅇㅇ|인정|맞음|맞네|맞말|그니까|그러니까|동의|팩트)[ㅋㅎ!?.~\s]*$")


class JudgeRequest(BaseModel):
    messages: list[ChatMessage]  # 게임 1판의 채팅 (시간순). 내 채팅이 섞여 있어도 된다
    analyses: dict[str, Analysis] = Field(default_factory=dict)  # 실시간 결과 (msg id → Analysis). 없으면 다시 분석
    players: list[Player] = Field(default_factory=list)
    my_name: str


class Evidence(BaseModel):
    msg_id: str
    ts: float
    channel: str
    text: str  # 원문 (증거)
    kind: Literal["direct", "agree"]  # 직접 한 말 / 남의 악성 채팅에 동조
    level: int
    harm_types: list[HarmType]
    target: str | None
    toward_me: bool


class SpeakerJudgment(BaseModel):
    speaker: str
    champion: str | None = None
    harm_types: list[HarmType]  # 이 사람이 한 말 전체의 유형
    targets: list[str]  # 공격한 대상들 (닉네임 또는 포지션 단어)
    toward_me: bool  # 나를 향한 표현이 있었나
    score: float  # 누적 점수의 최고값 (정렬·권고용)
    score_toward_me: float
    report: bool  # 신고 권고
    complaint_candidate: bool  # 고소 후보
    reasons: list[str]  # 사람이 읽는 판단 근거
    evidence: list[Evidence]
    legal: list[precedents.LegalReview] = Field(default_factory=list)  # 고소 후보일 때만


class Judgment(BaseModel):
    my_name: str
    speakers: list[SpeakerJudgment]  # 점수 높은 순. 문제없는 화자는 들어가지 않는다
    version: str = VERSION


def judge(req: JudgeRequest, index: precedents.PrecedentIndex | None = None) -> Judgment:
    """전체 대화 → 화자별 판단. index 는 판례 색인(없으면 기본 파일, 그것도 없으면 요건 점검표만)."""
    me = next((p for p in req.players if p.is_me or p.name == req.my_name), None) or Player(
        name=req.my_name, is_me=True
    )
    by_speaker: dict[str, list[Evidence]] = defaultdict(list)
    champions: dict[str, str | None] = {}
    recent: list[Evidence] = []  # 동조 판단용: 직전의 악성 채팅들
    speakers_of: dict[str, str] = {}  # msg_id → speaker
    for i, msg in enumerate(req.messages):
        if msg.is_me or msg.speaker == me.name:
            continue
        champions.setdefault(msg.speaker, msg.champion)
        analysis = req.analyses.get(msg.id) or impl.run(
            AnalyzeRequest(message=msg, history=req.messages[max(0, i - HISTORY) : i], players=req.players)
        )
        found = _direct(msg, analysis, me) or _agreement(msg, recent, speakers_of, me)
        if found is None:
            continue
        by_speaker[msg.speaker].append(found)
        speakers_of[found.msg_id] = msg.speaker
        if found.kind == "direct":
            recent.append(found)
    attackers: dict[str, set[str]] = defaultdict(set)  # 대상 → 공격한 화자들
    for speaker, items in by_speaker.items():
        for e in items:
            if e.target:
                attackers[e.target].add(speaker)
    result = [_summarize(s, champions.get(s), items, attackers, index) for s, items in by_speaker.items()]
    return Judgment(my_name=me.name, speakers=sorted(result, key=lambda j: -j.score))


def judge_session(session: GameSession, my_name: str | None = None) -> Judgment:
    """세션 기록(GameSession) → 판단. 실시간 필터가 이미 낸 Analysis 를 그대로 쓴다."""
    me = my_name or next((p.name for p in session.players if p.is_me), "나")
    return judge(
        JudgeRequest(
            messages=[i.msg for i in session.incidents],
            analyses={i.msg.id: i.analysis for i in session.incidents},
            players=session.players,
            my_name=me,
        )
    )


def _direct(msg: ChatMessage, analysis: Analysis, me: Player) -> Evidence | None:
    """특정인을 향한 악성 채팅(L2 이상)만 근거가 된다. 대상 없는 혼잣말 욕설(L1)은 숨김으로 끝난다."""
    if analysis.level < Level.L2_ABUSIVE:
        return None
    return Evidence(
        msg_id=msg.id,
        ts=msg.ts,
        channel=msg.channel.value,
        text=msg.text,
        kind="direct",
        level=int(analysis.level),
        harm_types=analysis.harm_types,
        target=analysis.target,
        toward_me=_is_me(analysis.target, me),
    )


def _agreement(msg: ChatMessage, recent: list[Evidence], speakers_of: dict[str, str], me: Player) -> Evidence | None:
    """남의 악성 채팅 바로 뒤의 짧은 맞장구("ㅇㅈ", "ㄹㅇ") → 그 대상을 향한 몰이에 가담한 것으로 본다."""
    if not AGREE.match(msg.text_norm.strip()):
        return None
    for prev in reversed(recent):
        if msg.ts - prev.ts > AGREE_WINDOW_SEC:
            break
        if speakers_of.get(prev.msg_id) != msg.speaker and prev.target and prev.target != msg.speaker:
            return Evidence(
                msg_id=msg.id,
                ts=msg.ts,
                channel=msg.channel.value,
                text=msg.text,
                kind="agree",
                level=int(Level.L2_ABUSIVE),
                harm_types=[HarmType.INSTIGATION],
                target=prev.target,
                toward_me=prev.toward_me,
            )
    return None


def _is_me(target: str | None, me: Player) -> bool:
    """대상이 나인가. 닉네임·챔피언이 같거나, 한 명으로 좁히지 못한 포지션 단어가 내 라인일 때."""
    if not target:
        return False
    if target in (me.name, me.champion):
        return True
    role = lexicon.POSITION_ROLES.get(target)
    return role is not None and role in (me.position, *roles_of(me.champion)[:1])


def _weight(e: Evidence) -> float:
    if e.kind == "agree":
        return WEIGHT_AGREE
    base = WEIGHT_L3 if e.level >= Level.L3_LEGAL else WEIGHT_L2
    return base + (WEIGHT_INSTIGATION if HarmType.INSTIGATION in e.harm_types else 0.0)


def _peak(items: list[Evidence]) -> float:
    """시간 감쇠를 둔 누적 점수의 최고값. 짧은 시간에 몰아서 한 말일수록 높다."""
    score = peak = 0.0
    last: float | None = None
    for e in sorted(items, key=lambda e: e.ts):
        if last is not None:
            score *= math.exp(-(e.ts - last) / DECAY_SEC)
        score += _weight(e)
        peak, last = max(peak, score), e.ts
    return peak


def _summarize(
    speaker: str,
    champion: str | None,
    items: list[Evidence],
    attackers: dict[str, set[str]],
    index: precedents.PrecedentIndex | None,
) -> SpeakerJudgment:
    mine = [e for e in items if e.toward_me]
    piled = sorted(t for t in {e.target for e in items if e.target} if len(attackers[t]) >= 2)
    factor = PILE_ON if piled else 1.0
    factor_me = PILE_ON if any(e.target in piled for e in mine) else 1.0
    score, score_me = round(_peak(items) * factor, 2), round(_peak(mine) * factor_me, 2)
    types = [t for t in HarmType if any(t in e.harm_types for e in items)]
    worst_me = max((e.level for e in mine), default=0)
    complaint = worst_me >= Level.L3_LEGAL or score_me >= COMPLAINT_SCORE
    reasons = [f"특정인을 향한 악성 채팅 {sum(e.kind == 'direct' for e in items)}건"]
    if any(e.kind == "agree" for e in items):
        reasons.append(f"다른 사람의 악성 채팅에 동조 {sum(e.kind == 'agree' for e in items)}건")
    if piled:
        reasons.append(f"여러 명이 같은 사람을 공격함 (대상: {', '.join(piled)})")
    if mine:
        reasons.append(f"나를 향한 표현 {len(mine)}건 (누적 점수 {score_me})")
    if worst_me >= Level.L3_LEGAL:
        reasons.append("나를 향한 패드립·성희롱 등 고강도 표현 → 고소 후보")
    elif complaint:
        reasons.append(f"나를 향한 악성 채팅이 반복됨 (누적 {score_me} ≥ {COMPLAINT_SCORE}) → 고소 후보")
    legal = []
    if complaint:
        facts = precedents.CaseFacts(
            speaker=speaker,
            toward_me=True,
            channels=sorted({e.channel for e in mine}),
            harm_types=[t for t in HarmType if any(t in e.harm_types for e in mine)],
            max_level=worst_me,
            count=len(mine),
            texts=[e.text for e in mine],
        )
        legal = precedents.review(facts, index)
    return SpeakerJudgment(
        speaker=speaker,
        champion=champion,
        harm_types=types,
        targets=sorted({e.target for e in items if e.target}),
        toward_me=bool(mine),
        score=score,
        score_toward_me=score_me,
        report=True,  # 근거가 하나라도 있으면(L2 이상 또는 동조) 신고 권고. 지금 정책표와 같은 기준
        complaint_candidate=complaint,
        reasons=reasons,
        evidence=items,
        legal=legal,
    )
