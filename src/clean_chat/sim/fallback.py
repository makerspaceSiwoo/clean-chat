"""가정 응답 (시뮬레이터 전용, 구성 · 리드): 모듈이 아직 구현 전이거나 오류가 나면 "이런 응답이 왔다"고 치고
전체 흐름을 끝까지 이어 간다. `uv run sim` 의 **전체 흐름** 화면에서만 쓴다. 앱(`uv run app`)은 쓰지 않는다 (ADR-0017).

⚠️ 진짜 판단 로직이 아니다. 단어 목록·정규식으로 계약(core/schemas.py) 모양의 출력만 만든다.
   - 결과에는 항상 backend / model_version = "sim-fallback" 을 남겨 실제 모듈 결과와 구분한다.
   - 모듈 담당자는 이 파일이 아니라 fixtures/<모듈>/expected.jsonl 과 run() docstring 을 명세로 삼는다.
"""

from __future__ import annotations

import re
from datetime import datetime

from clean_chat.core.game import KST
from clean_chat.core.schemas import (
    Analysis,
    AnalyzeRequest,
    Channel,
    ChatMessage,
    Frame,
    HarmType,
    Level,
    OcrResult,
    ParseRequest,
    ParseResult,
    Player,
    RawLine,
    ReportDraft,
    ReportKind,
    ReportRequest,
    Rewrite,
    RewriteRequest,
    Source,
)

FALLBACK = "sim-fallback"


# ── ① ocr: 화면 대신 "읽었다고 칠 텍스트" ─────────────────────
def ocr(frame: Frame, text: str) -> OcrResult:
    """이미지는 보지 않는다. 화면에서 넘겨준 텍스트(한 줄 = 채팅 한 줄)를 읽은 줄로 돌려준다."""
    rows = [t.strip() for t in text.splitlines() if t.strip()]
    lines = [
        RawLine(id=f"{frame.id}-{i:02d}", ts=frame.ts + i, text=t, source=Source.OCR, ocr_confidence=None)
        for i, t in enumerate(rows)
    ]
    return OcrResult(frame_id=frame.id, lines=lines)


# ── ② parse: "[03:08] [전체] 닉네임 (챔피언): 내용" ──────────────
TIME = re.compile(r"^\[\d{1,2}:\d{2}\]\s*")
CHAT = re.compile(r"^(?:\[(팀|전체|team|all)\]\s*)?([^()\[\]:：]+?)\s*\(([^()]+)\)\s*[:：]\s*(.*)$", re.IGNORECASE)


def parse(req: ParseRequest) -> ParseResult:
    """채팅 줄이면 ChatMessage, 시스템 메시지(콜론 없음: "~님이 전설적입니다!")·빈 줄이면 None. 정규화는 하지 않는다."""
    line = req.line
    raw = line.text.strip()
    if line.source == Source.SELF_INPUT:
        if not raw:
            return ParseResult(line_id=line.id, message=None)
        return ParseResult(line_id=line.id, message=_message(line, Channel.TEAM, req.my_name, None, raw, True, []))
    body = TIME.sub("", raw)
    m = CHAT.match(body)
    if m is None or not m.group(4).strip():
        return ParseResult(line_id=line.id, message=None)
    tag, speaker, champion, text = m.groups()
    # 롤 채팅창: [전체] 표시가 없으면 팀 채팅
    channel = Channel.ALL if (tag or "").lower() in ("전체", "all") else Channel.TEAM
    hints = ["timestamp_removed"] if body != raw else []
    speaker = speaker.strip()
    return ParseResult(
        line_id=line.id,
        message=_message(line, channel, speaker, champion.strip(), text.strip(), speaker == req.my_name, hints),
    )


def _message(
    line: RawLine, channel: Channel, speaker: str, champion: str | None, text: str, is_me: bool, hints: list[str]
) -> ChatMessage:
    return ChatMessage(
        id=line.id,
        ts=line.ts,
        source=line.source,
        channel=channel,
        speaker=speaker,
        champion=champion,
        text=text,
        text_norm=text,
        hints=[*hints, FALLBACK],
        is_me=is_me,
        raw=line.text,
    )


# ── ③ analyze: 단어 목록으로 등급·대상·조각 ──────────────────────
PROFANITY = ("시1발", "ㅅ1발", "씨발", "시발", "ㅅㅂ", "tlqkf", "병신", "ㅂㅅ", "개새끼", "새끼", "존나", "ㅈㄴ")
PROFANITY += ("ㅁㅊ", "미친", "바보", "꺼져", "닥쳐", "개못", "시*", "ㅅ*")
FAMILY = ("니애미", "느금", "니엄마", "애미", "애비", "니미")
SEXUAL = ("따먹", "몸매", "가슴")
THREAT = ("찾아간다", "찾아가서", "죽여", "신상", "주소 깐")
BLAME = ("탈주", "차이", "못하", "뭐함", "던짐", "던지", "트롤", "노답", "손가락", "혼자 들어")
INSTIGATION = ("신고해", "신고 ㄱ", "다 같이 신고")
FEEDBACK = ("와드", "시야", "용", "드래곤", "바론", "타워", "갱", "합류", "cs", "한타", "궁", "핑", "같이 가자", "먹자")
SECOND_PERSON = re.compile(r"(^|\s)(넌|너|니가|너네|님아)(\s|$)")
LANE_WORDS = {"탑": "TOP", "정글": "JUNGLE", "미드": "MIDDLE", "원딜": "BOTTOM", "바텀": "BOTTOM", "서폿": "UTILITY"}
CHAMPION_LANE = {  # 데모 명단(fixtures/flow/players.jsonl)에 나오는 챔피언만
    "가렌": "TOP",
    "다리우스": "TOP",
    "리신": "JUNGLE",
    "카직스": "JUNGLE",
    "제드": "MIDDLE",
    "아리": "MIDDLE",
    "징크스": "BOTTOM",
    "이즈리얼": "BOTTOM",
    "쓰레쉬": "UTILITY",
    "룰루": "UTILITY",
}
SCORE = 0.9  # 가정 응답이라 점수는 고정값


def _found(text: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if w in text]


def _lane_target(msg: ChatMessage, players: list[Player]) -> tuple[str, str] | None:
    """문장 속 포지션 단어 → (단어, 닉네임 또는 단어). 말한 사람과 같은 팀을 먼저 찾는다 (ADR-0020)."""
    for word, lane in LANE_WORDS.items():
        if word not in msg.text:
            continue
        me = next((p for p in players if p.name == msg.speaker), None)
        cands = [
            p for p in players if p.name != msg.speaker and (p.position or CHAMPION_LANE.get(p.champion or "")) == lane
        ]
        cands.sort(key=lambda p: me is None or p.team != me.team)
        return word, (cands[0].name if cands else word)
    return None


def analyze(req: AnalyzeRequest) -> Analysis:
    msg, text = req.message, req.message.text
    profanity = _found(text, PROFANITY)
    family, sexual, threat = _found(text, FAMILY), _found(text, SEXUAL), _found(text, THREAT)
    blame, instigation = _found(text, BLAME), _found(text, INSTIGATION)

    lane = _lane_target(msg, req.players)
    second_person = bool(SECOND_PERSON.search(text))
    target = lane[1] if lane else None
    if target is None and second_person:  # "넌", "니가" → 바로 앞에 말한 다른 사람
        target = next((h.speaker for h in reversed(req.history) if h.speaker != msg.speaker), None)
    aimed = lane is not None or second_person

    harms: list[HarmType] = []
    if profanity:
        harms.append(HarmType.PROFANITY)
    if family or sexual or threat:
        harms += [h for h, hit in ((HarmType.FAMILY_INSULT, family), (HarmType.SEXUAL_HARASSMENT, sexual)) if hit]
        harms += [HarmType.THREAT] if threat else []
        level = Level.L3_LEGAL
    elif aimed and (profanity or blame):
        harms += [HarmType.BLAME] if blame else []
        level = Level.L2_ABUSIVE
    elif instigation:
        harms.append(HarmType.INSTIGATION)
        level = Level.L2_ABUSIVE
    elif profanity:
        level = Level.L1_MILD
    else:
        level = Level.L0_CLEAN

    bad = profanity + family + sexual + threat + blame + ([lane[0]] if lane else [])
    feedback = _feedback_span(text, bad) if level >= Level.L2_ABUSIVE else None
    return Analysis(
        msg_id=msg.id,
        target=target if level >= Level.L2_ABUSIVE else None,
        level=level,
        harm_types=harms,
        profanity_spans=profanity + family,
        feedback_spans=[feedback] if feedback else [],
        scores={h.value: SCORE for h in harms},
        model_version=FALLBACK,
    )


def _feedback_span(text: str, bad: list[str]) -> str | None:
    """처음 나온 게임 용어부터, 그 뒤 첫 비속어·비난·포지션 단어 앞까지. 예) "용 앞 시야 없음 원딜 뭐함" → "용 앞 시야 없음"."""
    starts = [i for w in FEEDBACK if (i := text.find(w)) >= 0]
    if not starts:
        return None
    start = text.rfind(" ", 0, min(starts)) + 1  # 단어 처음부터
    ends = [i for w in bad if (i := text.find(w, start)) > start]
    span = text[start : min(ends) if ends else len(text)]
    span = re.sub(r"[\sㅋㅎㅠㅜ~!?.^;♡ㅇ]+$", "", span).strip()
    return span or None


# ── ④ rewrite: 끝말만 공손하게 ───────────────────────────────
ENDINGS = (("치라고", "쳐 주세요"), ("박아", "박아 주세요"), ("가자", "가요"), ("없음", "없어요"), ("좀", "부탁해요"))


def rewrite(req: RewriteRequest) -> Rewrite:
    """L1 은 욕설을 뺀 문장, L2 이상은 피드백 조각을 이어 붙이고 끝말만 바꾼다. 예) "서폿 와드 좀" → "서폿 와드 부탁해요"."""
    if req.analysis.level == 1:  # L1: 욕설이 든 낱말만 지운다. 남는 말이 없으면 None (→ 숨김)
        spans = [span for span in req.analysis.profanity_spans if span]
        kept = " ".join(word for word in req.message.text.split() if not any(span in word for span in spans))
        worded = any("가" <= ch <= "힣" or (ch.isascii() and ch.isalnum()) for ch in kept)  # ㅠㅠ 만 남으면 말이 아니다
        return Rewrite(msg_id=req.message.id, rewritten=kept if worded else None, backend=FALLBACK)
    text = " ".join(req.analysis.feedback_spans).strip()
    if not text:
        return Rewrite(msg_id=req.message.id, rewritten=None, backend=FALLBACK)
    for old, new in ENDINGS:
        if text.endswith(old):
            text = text[: -len(old)].rstrip() + " " + new
            break
    else:
        text += " 부탁해요"
    return Rewrite(msg_id=req.message.id, rewritten=text.strip(), backend=FALLBACK)


# ── ⑤ report: 신고 문구 / 고소장 경위 (PDF 없음) ──────────────────
HARM_KO = {
    HarmType.PROFANITY: "욕설",
    HarmType.FAMILY_INSULT: "패드립",
    HarmType.SEXUAL_HARASSMENT: "성희롱",
    HarmType.BLAME: "비난",
    HarmType.INSTIGATION: "정치질",
    HarmType.THREAT: "협박",
}
GAME_TIME = re.compile(r"^\[(\d{1,2}:\d{2})\]")


def report(req: ReportRequest) -> ReportDraft:
    flag = (lambda d: d.report) if req.kind == ReportKind.REPORT else (lambda d: d.complaint_candidate)
    incs = [i for i in req.session.incidents if i.msg.speaker == req.speaker and flag(i.decision)]
    rows = []
    for inc in incs:
        m = GAME_TIME.match(inc.msg.raw)
        when = (
            f"게임 시간 {m.group(1)}" if m else datetime.fromtimestamp(inc.msg.ts, tz=KST).strftime("%Y-%m-%d %H:%M:%S")
        )
        kinds = ", ".join(HARM_KO[h] for h in inc.analysis.harm_types) or "비매너"
        rows.append(f"[{when}] {inc.msg.text} ({kinds})")
    if req.kind == ReportKind.REPORT:
        text = "\n".join([f"신고 대상: {req.speaker}", f"사유: 언어 폭력 {len(incs)}건", *rows])
    else:
        text = "\n".join(
            [
                f"고소인: {req.complainant or '(미입력)'} / 피고소인(닉네임): {req.speaker}",
                f"사건 경위: 게임 {req.session.id} 중 피고소인이 채팅으로 아래 {len(incs)}건의 발언을 했습니다.",
                *rows,
                "※ 시뮬레이터 가정 응답입니다. PDF 는 report 모듈 구현 후 만들어집니다. 법률 자문이 아닙니다.",
            ]
        )
    return ReportDraft(kind=req.kind, speaker=req.speaker, text=text, incident_ids=[i.msg.id for i in incs])
