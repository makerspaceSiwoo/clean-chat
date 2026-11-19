"""모듈 사이에 주고받는 데이터 형식(계약). 이 파일이 유일한 기준입니다.

⚠️ 이 파일은 리드만 수정합니다(CODEOWNERS). 바꿔야 하면 이슈를 올려 주세요.
사람이 읽기 쉬운 설명은 docs/CONTRACTS.md 에 있습니다.

모듈 5개 = 함수 5개 (ADR-0017). 각 모듈은 "입력 모델 1개 → 출력 모델 1개" 함수 run() 하나만 공개합니다.
  ① ocr      Frame          → OcrResult     채팅창 이미지 → 읽은 줄 전부
  ② parse    ParseRequest   → ParseResult   줄 → 채팅만(시스템·핑 제외) + 정규화(text_norm)
  ③ analyze  AnalyzeRequest → Analysis      누가 누구에게(target), 등급, 유형, 비속어·피드백 조각
  ④ rewrite  RewriteRequest → Rewrite       피드백만 공손한 문장으로
  ⑤ report   ReportRequest  → ReportDraft   신고 문구 / 고소장 초안(PDF)

그 밖의 처리(정책표, 흐름 연결, 줄 중복 제거, 게임 단계, 세션 기록)는 구성(core/, 리드)이 합니다.
  흐름 A (다른 유저): Frame → ocr → (중복 제거) → parse → analyze → (L2 이상 & 피드백) rewrite → 정책 → Incident
  흐름 B (내 입력):   RawLine(source=self_input) → parse → analyze → rewrite → 정책 → 복사 / 차단
  게임 종료:          GameSession → report(kind=report | complaint)
"""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0.0"
# 1.0.0: 모듈 5개로 축소 (ADR-0017). NormalizedMessage → ChatMessage 에 합침, Classification → Analysis,
#        parse 가 내 입력(compose)·정규화(normalize)까지, 정책(policy)은 구성으로. Mock 제거
# 0.6.0: PostGameResult 추가 (게임 종료 배치 처리 결과)
# 0.5.0: 흐름 A/B 분리 — OutgoingText 추가(compose 입력), policy → incoming_policy / outgoing_policy
# 0.4.0: GamePhase·PhaseEvent·GameSession 추가, report/complaint 입력을 세션 기반으로


# ── 공통 열거형 ─────────────────────────────────────────────
class Source(StrEnum):
    OCR = "ocr"  # 실제 게임 화면에서 읽음
    DEMO = "demo"  # 시나리오 JSONL 재생 (fixtures/scenario, data/demo)
    SELF_INPUT = "self_input"  # 오버레이 입력칸에 내가 쓴 문장 (흐름 B). 채널 표기·화자 없이 본문만


class Channel(StrEnum):
    """채팅 채널. 시스템 메시지·핑은 채팅이 아니라서 parse 가 걸러낸다(message=None)."""

    TEAM = "team"
    ALL = "all"
    UNKNOWN = "unknown"


class HarmType(StrEnum):
    PROFANITY = "profanity"  # 욕설
    FAMILY_INSULT = "family_insult"  # 패드립
    SEXUAL_HARASSMENT = "sexual_harassment"  # 성희롱
    BLAME = "blame"  # 비난
    INSTIGATION = "instigation"  # 정치질(팀원 몰이)


class Level(IntEnum):
    L0_CLEAN = 0  # 정상
    L1_MILD = 1  # 경미 (대상 없는 혼잣말 비속어 등)
    L2_ABUSIVE = 2  # 악성 (특정인 대상 비난/욕설/정치질)
    L3_LEGAL = 3  # 법적 대응 후보


class Action(StrEnum):
    # 타 유저 채팅
    SHOW = "show"
    SHOW_MASKED = "show_masked"
    SHOW_REWRITTEN = "show_rewritten"
    HIDE = "hide"
    # 내 채팅
    COPY = "copy"
    COPY_MASKED = "copy_masked"
    COPY_REWRITTEN = "copy_rewritten"
    BLOCK = "block"


class GamePhase(StrEnum):
    """앱이 보는 게임 단계. 실제 LCU 단계 이름은 PhaseEvent.raw 에 남기고, 여기서는 3개로만 나눈다."""

    IDLE = "idle"  # 대기: 클라이언트 창만 (지난 처리 내역, 설정)
    IN_GAME = "in_game"  # 게임 중: 오버레이 표시, 흐름 A·B 실행, GameSession 에 기록
    POST_GAME = "post_game"  # 게임 종료: 오버레이 숨김, 세션 배치 처리 → 신고 문구·고소장 초안


class ReportKind(StrEnum):
    REPORT = "report"  # 게임 안 신고 창에 붙여넣을 문구 (자동 신고 금지, ADR-0007)
    COMPLAINT = "complaint"  # 고소장 초안 + PDF (ADR-0008)


# ── 게임 정보 ──────────────────────────────────────────────
class Player(BaseModel):
    """게임 참가자. 로컬 Live Client Data API(127.0.0.1:2999) 또는 설정값에서 얻음."""

    name: str
    champion: str | None = None
    team: str | None = None  # "ORDER" | "CHAOS"
    position: str | None = None  # TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY
    is_me: bool = False


# ── ① ocr: 채팅창 이미지 → 줄 ─────────────────────────────
class Region(BaseModel):
    x: int
    y: int
    w: int
    h: int


class Frame(BaseModel):
    """캡처한 채팅창 이미지 1장. Mac에서는 저장된 스크린샷 파일로 대체해서 테스트."""

    id: str
    ts: float
    image_path: str  # PNG 파일 경로
    region: Region


class RawLine(BaseModel):
    """채팅창에 보이는 한 줄(가공 전). OCR 결과이거나, 흐름 B 에서는 내가 입력한 문장."""

    id: str
    ts: float  # 유닉스 시간(초)
    text: str  # 예: "[팀] Hide on bush (아리): 미드 ㅂㅅ아"
    source: Source
    ocr_confidence: float | None = None


class OcrResult(BaseModel):
    """Frame 1장에서 읽은 줄 전부(위에서 아래 순서). 앞 프레임과 겹치는 줄 제거는 구성(core)이 한다."""

    frame_id: str
    lines: list[RawLine]


# ── ② parse: 줄 → 채팅 메시지 (+ 정규화) ─────────────────────
class ParseRequest(BaseModel):
    line: RawLine
    my_name: str  # 내 소환사명. 화자가 나이면 is_me=True. source=self_input 이면 화자 = my_name


class ChatMessage(BaseModel):
    id: str
    ts: float
    source: Source
    channel: Channel
    speaker: str  # 닉네임
    champion: str | None = None
    text: str  # 화자 부분을 뗀 본문 (증거라서 고치지 않음)
    text_norm: str  # 우회어 복원, OCR 오타 보정, 반복 축약 후 문장 (분석용)
    hints: list[str] = Field(default_factory=list)  # 어떤 보정을 했나. 예: ["lexicon:ㅂㅅ", "noise_removed"]
    is_me: bool = False
    raw: str  # 원본 줄 (증거용)


class ParseResult(BaseModel):
    line_id: str
    message: ChatMessage | None  # 채팅이 아닌 줄(시스템 메시지, 핑, 잡음)은 None


# ── ③ analyze: 관계·등급·피드백 ──────────────────────────────
class AnalyzeRequest(BaseModel):
    message: ChatMessage  # 분석할 메시지
    history: list[ChatMessage] = Field(default_factory=list)  # 바로 앞 대화 (오래된 것부터, 대상 추정용)
    players: list[Player] = Field(default_factory=list)  # 이번 게임 명단 (없으면 빈 목록)


class Analysis(BaseModel):
    """판단만 한다(얼마나 나쁜가, 누구를 향하나). 숨김·신고·차단 같은 처리는 구성(core/policy.py)이 정한다."""

    msg_id: str
    target: str | None = None  # 공격 대상 (닉네임·포지션·챔피언). 모르거나 대상이 없으면 None
    level: Level
    harm_types: list[HarmType] = Field(default_factory=list)
    profanity_spans: list[str] = Field(default_factory=list)  # text 에서 가릴 비속어 조각 (원문 그대로)
    feedback_spans: list[str] = Field(default_factory=list)  # text 에서 뽑은 게임 피드백 조각 (원문 그대로)
    scores: dict[str, float] = Field(default_factory=dict)
    model_version: str


# ── ④ rewrite: 피드백만 공손하게 (L2 이상 & feedback_spans 있을 때만) ──
class RewriteRequest(BaseModel):
    message: ChatMessage
    analysis: Analysis


class Rewrite(BaseModel):
    msg_id: str
    rewritten: str | None  # 다듬은 문장 1개 (실패·욕설이 남으면 None)
    backend: str  # "rule" | "local" | "api"


# ── 구성: 처리 결정 (core/policy.py) ─────────────────────────
class Decision(BaseModel):
    msg_id: str
    is_me: bool
    action: Action
    display_text: str | None  # 화면에 보여 주거나 복사할 문장 (HIDE/BLOCK이면 None)
    target: str | None = None  # Analysis.target 그대로
    report: bool = False  # 신고 목록에 올림
    complaint_candidate: bool = False  # 고소장 후보
    reason: str = ""  # 사람이 읽는 판단 근거 (디버그/발표용)


class Incident(BaseModel):
    """클라이언트 '처리 내역'에 보이는 기록 한 건. 로컬 저장만 허용."""

    msg: ChatMessage
    analysis: Analysis
    decision: Decision
    rewrite: Rewrite | None = None


# ── 구성: 게임 단계와 세션 ───────────────────────────────
class PhaseEvent(BaseModel):
    """단계 감지기가 내보내는 단계 변화 1건.

    Windows: LCU /lol-gameflow/v1/gameflow-phase 값을 GamePhase 로 바꿈 (단계 이름은 실측 필요).
    Mac: 시나리오 JSONL 의 {"phase": ...} 이벤트를 그대로 읽음 (가짜 감지기).
    """

    ts: float
    phase: GamePhase
    raw: str | None = None  # 원본 단계 값 (예: LCU "InProgress"). 가짜 감지기는 None 가능


class GameSession(BaseModel):
    """게임 1판의 기록. IN_GAME 동안 쌓고, POST_GAME 에서 report/complaint 의 입력이 된다.

    로컬 저장만 허용: .clean-chat/sessions/<id>.jsonl (git 제외).
    incidents 에는 다른 유저 채팅(흐름 A)만 들어간다. 내 채팅(흐름 B)은 복사/차단으로 끝나고 기록하지 않는다.
    """

    id: str  # 예: "20251112-125820" (시작 시각)
    started_at: float
    ended_at: float | None = None  # 게임 중이면 None
    players: list[Player] = Field(default_factory=list)  # Live Client Data API 명단 (없으면 빈 목록)
    incidents: list[Incident] = Field(default_factory=list)


# ── ⑤ report: 신고 문구 / 고소장 (게임 종료 후에만) ──────────────
class ReportRequest(BaseModel):
    kind: ReportKind
    session: GameSession  # 이번 게임 기록 전체. report → decision.report, complaint → complaint_candidate 기록만 쓴다
    speaker: str  # 대상 닉네임
    complainant: str | None = None  # 고소인(사용자) 이름. complaint 일 때만
    output_dir: str | None = None  # PDF 저장 폴더. complaint 일 때만. 상대 경로면 레포 루트 기준 (resolve_repo_path)


class ReportDraft(BaseModel):
    kind: ReportKind
    speaker: str
    text: str  # report: 그대로 붙여넣을 신고 문구 / complaint: 사건 경위
    incident_ids: list[str]
    pdf_path: str | None = None  # complaint 일 때 저장한 PDF 경로


# ── 구성: 게임 종료 결과 (POST_GAME 배치 처리 → "이번 게임 결과" 화면) ──
class PostGameResult(BaseModel):
    """게임 1판이 끝난 뒤 세션 전체를 한 번에 처리한 결과. UI 는 보여 주기만 한다."""

    session_id: str
    reports: list[ReportDraft] = Field(default_factory=list)  # report=True 기록이 있는 화자마다 1개
    complaints: list[ReportDraft] = Field(default_factory=list)  # complaint_candidate=True 기록이 있는 화자마다 1개
