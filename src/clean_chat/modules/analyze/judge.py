"""대화 판단 — 게임이 끝난 뒤 전체 대화를 보고 "누가 누구에게, 특히 나에게 무엇을 했는가"를 화자별로 정리한다.

실시간 필터(impl.run)는 메시지 1개만 보고 가릴 욕설을 찾는다. 신고·고소처럼 무거운 결정은 한 문장으로 정하지 않고,
여기서 대화 흐름 전체(반복, 동조, 여러 명의 몰이)를 보고 정한다. 고소 후보에는 판례 요건 점검(precedents.py)을 붙인다.

    judge(JudgeRequest(messages=..., players=..., my_name="나")) → Judgment
    judge_session(game_session)                                  → Judgment   (세션 기록을 그대로 넣을 때)

아직 앱 흐름(core)에는 연결하지 않았다. 지금은 정책표(core/policy.py)가 실시간으로 신고·고소 후보를 표시한다.
연결하려면 계약 변경(모듈 추가, 게임 종료 배치가 이 함수를 부름)이 필요하다 → README 의 "다음 단계".

실시간 필터와 과제가 다르다 (README "용도 2개"):
  impl   문장 1개 → 가릴 조각 · 피드백 유무. 0.5초 미만.
  judge  게임 1판(최대 10명 = 나 + 팀원 4 + 상대 5)의 채팅을 **유저별로 모아** 누적 점수와 흐름으로
         신고 권고 · 고소 후보를 정한다. 1~5초 (5초 이상이면 화면에서 로딩 창).

흐름으로 보는 것: 반복(누적 점수), 맞장구("ㅇㅈ 정글 차이")로 가담, 여러 명의 몰이, 말리는 말("그만해라")은 가해가 아님.
점수는 학습된 확률이 아니라 가중치를 더한 값이다. 상수는 게임 단위 데이터(fixtures/analyze/judge_games.jsonl 의 train)로
맞췄고 judge_evaluate.py 로 잰다.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from clean_chat.core.schemas import Analysis, AnalyzeRequest, ChatMessage, GameSession, HarmType, Level, Player
from clean_chat.modules.analyze import impl, judge_model, lexicon, precedents
from clean_chat.modules.analyze.champions import roles_of

VERSION = "judge-0.2"
HISTORY = 10  # 메시지를 다시 분석할 때 넘기는 앞 대화 수 (실시간과 같게)
DECAY_SEC = 1800.0  # 누적 점수가 1/e 로 줄어드는 시간. 한 판(약 30분) 안에서는 거의 그대로 쌓인다
WEIGHT_L2 = 1.0
WEIGHT_L3 = 3.0
WEIGHT_INSTIGATION = 0.5  # 정치질(몰이)이면 더한다
WEIGHT_AGREE = 0.5  # 남의 악성 채팅에 동조 ("ㅇㅈ")
PILE_ON = 1.25  # 같은 사람을 2명 이상이 공격했으면 곱한다
REPORT_SCORE = 1.5  # 누적 점수가 이 이상이면 신고 권고 (욕설 없는 거친 말 한 번 = 1.0 은 권고하지 않는다)
COMPLAINT_SCORE = 3.0  # 나를 향한 누적 점수가 이 이상이고 욕설이 섞였으면 고소 후보 (모욕 3번 정도)
COMPLAINT_SCORE_NO_PROFANITY = 4.0  # 욕설 없이 비난·조롱만 반복된 경우의 기준
AGREE_WINDOW_SEC = 20.0
# 맞장구: 짧은 동의 말로 시작하면 뒤에 말이 더 붙어도 가담으로 본다 ("ㅇㅈ 정글 차이 심하네", "ㄹㅇ ㅋㅋ")
AGREE = re.compile(r"^(ㅇㅈ|ㄹㅇ|인정|맞음|맞네|맞말|그니까|그러니까|동의|팩트)([ㅋㅎ!?.~\s].*)?$")
AGREE_SHORT = re.compile(r"^(ㅇㅇ)[ㅋㅎ!?.~\s]*$")  # "ㅇㅇ" 은 대답으로도 쓰여서 단독일 때만
# 말리는 말: 이미 남을 공격한 사람에게 하는 "그만해라", "선 넘지 마라" 는 가해가 아니다
SELF_TALK = re.compile(r"(^|\s)(내가|내|나|제가)(\s|$)|내\s?(실수|잘못|탓)")
VEILED_THREAT_SEC = 900.0  # 암시적 협박을 "앞서 공격하던 사람에게 한 말"로 보는 시간
FOLLOW_UP_SEC = 600.0  # 대상을 생략한 욕설을 "앞서 공격하던 사람에게 이어서 한 말"로 보는 시간
MODEL_THRESHOLD = 0.5  # judge 모델 점수가 이 이상이면 그 판단(신고 권고·고소 후보)으로 본다
# hybrid(기본): 신고 권고 = 규칙 또는 모델, 고소 후보 = 규칙 / rules: 규칙만 / model: 모델만 (비교용)
Mode = Literal["hybrid", "rules", "model"]
DEFEND = re.compile(r"그만|적당히|선\s?넘|곱게|조용히|하지\s?마|싸우지|신경\s?쓰지")


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
    total_messages: int = 0  # 이 유저가 이 판에서 한 말의 수 (악성 아닌 말 포함)
    model_scores: dict[str, float] = Field(
        default_factory=dict
    )  # judge 모델 점수 {"report", "complaint"} (모델이 있을 때)
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


def judge(req: JudgeRequest, index: precedents.PrecedentIndex | None = None, mode: Mode = "hybrid") -> Judgment:
    """전체 대화 → 화자별 판단. index 는 판례 색인(없으면 기본 파일, 그것도 없으면 요건 점검표만).

    순서: ① 메시지마다 실시간 필터 결과로 근거를 모은다 → ② 유저별 누적 점수·흐름 규칙으로 판단한다
    → ③ judge 모델(judge_model.py, `models/analyze-judge/`)이 그 유저가 쓴 채팅을 모아 읽고 낸 점수로 신고 권고를 보완한다.
    모델 파일이 없으면 규칙만으로 돈다. 고소 후보는 모델을 쓰지 않고 규칙으로만 정한다 (README "대화 판단").
    """
    me = next((p for p in req.players if p.is_me or p.name == req.my_name), None) or Player(
        name=req.my_name, is_me=True
    )
    by_speaker: dict[str, list[Evidence]] = defaultdict(list)
    champions: dict[str, str | None] = {}
    recent: list[Evidence] = []  # 동조 판단용: 직전의 악성 채팅들
    speakers_of: dict[str, str] = {}  # msg_id → speaker
    aggressors: set[str] = set()  # 지금까지 남을 직접 공격한 화자
    joiners: set[str] = set()  # 남의 악성 채팅에 맞장구친 화자
    totals: dict[str, int] = defaultdict(int)  # 화자별 전체 발화 수
    for i, msg in enumerate(req.messages):
        if msg.is_me or msg.speaker == me.name:
            continue
        champions.setdefault(msg.speaker, msg.champion)
        totals[msg.speaker] += 1
        analysis = req.analyses.get(msg.id) or impl.run(
            AnalyzeRequest(message=msg, history=req.messages[max(0, i - HISTORY) : i], players=req.players)
        )
        found = _follow_up(msg, analysis, by_speaker.get(msg.speaker, []), me) or _direct(msg, analysis, me)
        if found is not None and _defending(msg, found, aggressors, recent):
            found = None
        agreed = _agreement(msg, recent, speakers_of, me)
        if agreed is not None:
            joiners.add(msg.speaker)  # 맞장구로 시작한 말은 그 자체가 비난이어도 가담으로 센다
        found = found or agreed
        if found is None:
            continue
        by_speaker[msg.speaker].append(found)
        speakers_of[found.msg_id] = msg.speaker
        if found.kind == "direct":
            recent.append(found)
            aggressors.add(msg.speaker)
    attackers: dict[str, set[str]] = defaultdict(set)  # 대상 → 공격한 화자들
    for speaker, items in by_speaker.items():
        for e in items:
            if e.target:
                attackers[e.target].add(speaker)
    result = [
        _summarize(s, champions.get(s), items, attackers, index, totals[s], s in joiners)
        for s, items in by_speaker.items()
    ]
    version = VERSION
    scores = judge_model.predict(req.messages, req.players, me.name) if mode != "rules" else {}
    if scores:
        version = f"{VERSION}+{judge_model.version()}"
        known = {j.speaker: j for j in result}
        result = []
        for speaker in {**dict.fromkeys(known), **dict.fromkeys(scores)}:
            base = known.get(speaker) or _empty(speaker, champions.get(speaker), totals[speaker])
            merged = _with_model(base, scores.get(speaker, {}), mode)
            if merged.evidence or merged.report:
                result.append(merged)
    return Judgment(my_name=me.name, speakers=sorted(result, key=lambda j: (-j.report, -j.score)), version=version)


def _empty(speaker: str, champion: str | None, total_messages: int) -> SpeakerJudgment:
    """규칙으로는 근거가 없는 유저의 빈 판단 (모델 점수를 붙일 자리)."""
    return SpeakerJudgment(
        speaker=speaker,
        champion=champion,
        harm_types=[],
        targets=[],
        toward_me=False,
        total_messages=total_messages,
        score=0.0,
        score_toward_me=0.0,
        report=False,
        complaint_candidate=False,
        reasons=[],
        evidence=[],
    )


def _with_model(base: SpeakerJudgment, scores: dict[str, float], mode: Mode) -> SpeakerJudgment:
    """규칙 판단에 모델 점수를 합친다. hybrid 는 신고 권고만 "규칙 또는 모델", model 은 모델만 따른다."""
    said_report = scores.get("report", 0.0) >= MODEL_THRESHOLD
    said_complaint = scores.get("complaint", 0.0) >= MODEL_THRESHOLD
    # hybrid: 신고 권고는 규칙 또는 모델, 고소 후보는 규칙만 (모델의 고소 후보 판단은 오탐이 많았다 — README)
    complaint = said_complaint if mode == "model" else base.complaint_candidate
    report = (said_report if mode == "model" else base.report or said_report) or complaint
    reasons = list(base.reasons)
    if said_report and not base.report:
        reasons.append(
            f"대화 흐름 모델이 신고 권고로 판단 (점수 {scores['report']:.2f}) — 한 문장씩으로는 잡히지 않은 표현"
        )
    if said_complaint and not base.complaint_candidate and mode == "model":
        reasons.append(
            f"대화 흐름 모델이 고소 후보로 판단 (점수 {scores['complaint']:.2f}) — 근거 문장은 직접 확인 필요"
        )
    return base.model_copy(
        update={
            "report": report,
            "complaint_candidate": complaint,
            "toward_me": base.toward_me or complaint,
            "reasons": reasons,
            "model_scores": scores,
        }
    )


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


def _follow_up(msg: ChatMessage, analysis: Analysis, earlier: list[Evidence], me: Player) -> Evidence | None:
    """한 문장으로는 대상이 없지만 흐름으로는 이어지는 말: 대상을 생략한 협박과, 나를 공격하던 사람이 이어서 한 욕설.

    예) "서폿 병신" 뒤의 "꺼져 쓰레기야", "끝나고 보자 어디 사는지 찾아낸다". 자책("아 시발 내 실수")은 뺀다.
    """
    last = next((e for e in reversed(earlier) if e.kind == "direct" and e.target), None)
    text = msg.text_norm
    if HarmType.THREAT in analysis.harm_types and analysis.target is None and last is not None:
        # 협박(ADR-0021)인데 문장에 대상이 없으면 앞서 공격하던 사람에게 한 말로 본다
        return _evidence(msg, int(Level.L3_LEGAL), analysis.harm_types, last.target, last.toward_me)
    veiled = lexicon.THREAT_VEILED.search(text) and not lexicon.GAME_TALK.search(text) and not SELF_TALK.search(text)
    if veiled and last is not None and msg.ts - last.ts <= VEILED_THREAT_SEC:
        # 암시적 협박("끝나고 보자", "각오해라"): 문장만으로는 알 수 없고, 그 사람을 공격하던 유저가 이어서 했을 때만 협박
        types = [t for t in HarmType if t in analysis.harm_types or t == HarmType.THREAT]
        return _evidence(msg, int(Level.L3_LEGAL), types, last.target, last.toward_me)
    if last is None or not last.toward_me or msg.ts - last.ts > FOLLOW_UP_SEC or SELF_TALK.search(text):
        return None  # 이어받기는 나를 향하던 말에만 쓴다 (친한 사이의 장난까지 쌓지 않게)
    if analysis.level == Level.L1_MILD and analysis.target is None:
        return _evidence(msg, int(Level.L2_ABUSIVE), analysis.harm_types, last.target, last.toward_me)
    return None


def _evidence(msg: ChatMessage, level: int, types: list[HarmType], target: str | None, toward_me: bool) -> Evidence:
    return Evidence(
        msg_id=msg.id,
        ts=msg.ts,
        channel=msg.channel.value,
        text=msg.text,
        kind="direct",
        level=level,
        harm_types=types,
        target=target,
        toward_me=toward_me,
    )


def _agreement(msg: ChatMessage, recent: list[Evidence], speakers_of: dict[str, str], me: Player) -> Evidence | None:
    """남의 악성 채팅 바로 뒤의 짧은 맞장구("ㅇㅈ", "ㄹㅇ") → 그 대상을 향한 몰이에 가담한 것으로 본다."""
    text = msg.text_norm.strip()
    if not (AGREE.match(text) or AGREE_SHORT.match(text)):
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


def _defending(msg: ChatMessage, found: Evidence, aggressors: set[str], recent: list[Evidence]) -> bool:
    """말리는 말인가: 욕설 없이 "그만해라"·"선 넘지 마라" 를, 직전까지 남을 공격하던 사람이 있는 흐름에서 한 경우."""
    if HarmType.PROFANITY in found.harm_types or found.level >= Level.L3_LEGAL:
        return False
    if not DEFEND.search(msg.text_norm) or msg.speaker in aggressors:
        return False
    return any(msg.ts - prev.ts <= 300 for prev in recent)


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
    total_messages: int = 0,
    joined_in: bool = False,
) -> SpeakerJudgment:
    mine = [e for e in items if e.toward_me]
    piled = sorted(t for t in {e.target for e in items if e.target} if len(attackers[t]) >= 2)
    factor = PILE_ON if piled else 1.0
    factor_me = PILE_ON if any(e.target in piled for e in mine) else 1.0
    score, score_me = round(_peak(items) * factor, 2), round(_peak(mine) * factor_me, 2)
    types = [t for t in HarmType if any(t in e.harm_types for e in items)]
    worst_me = max((e.level for e in mine), default=0)
    swore_at_me = any(HarmType.PROFANITY in e.harm_types for e in mine)
    repeated = score_me >= (COMPLAINT_SCORE if swore_at_me else COMPLAINT_SCORE_NO_PROFANITY)
    complaint = worst_me >= Level.L3_LEGAL or repeated
    worst = max((e.level for e in items), default=0)
    swore = any(e.kind == "direct" and HarmType.PROFANITY in e.harm_types for e in items)
    joined = joined_in or any(e.kind == "agree" for e in items)
    report = complaint or worst >= Level.L3_LEGAL or swore or joined or score >= REPORT_SCORE
    reasons = [f"특정인을 향한 악성 채팅 {sum(e.kind == 'direct' for e in items)}건"]
    if any(e.kind == "agree" for e in items):
        reasons.append(f"다른 사람의 악성 채팅에 동조 {sum(e.kind == 'agree' for e in items)}건")
    if piled:
        reasons.append(f"여러 명이 같은 사람을 공격함 (대상: {', '.join(piled)})")
    if mine:
        reasons.append(f"나를 향한 표현 {len(mine)}건 (누적 점수 {score_me})")
    if worst_me >= Level.L3_LEGAL:
        reasons.append("나를 향한 패드립·성희롱·협박 등 고강도 표현 → 고소 후보")
    elif complaint:
        reasons.append(f"나를 향한 악성 채팅이 반복됨 (누적 {score_me}) → 고소 후보")
    if not report:
        reasons.append(f"욕설 없는 거친 말 한 번 (누적 {score} < {REPORT_SCORE}) → 신고 권고 안 함")
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
        total_messages=total_messages,
        report=report,  # 욕설·고강도 표현·몰이 가담이 있거나 누적 점수가 기준 이상일 때
        complaint_candidate=complaint,
        reasons=reasons,
        evidence=items,
        legal=legal,
    )
