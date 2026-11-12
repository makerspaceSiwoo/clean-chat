"""모듈 사이에 주고받는 데이터 형식(계약). 이 파일이 유일한 기준입니다.

⚠️ 이 파일은 리드만 수정합니다(CODEOWNERS). 바꿔야 하면 이슈를 올려 주세요.
사람이 읽기 쉬운 설명은 docs/CONTRACTS.md 에 있습니다.

흐름 (모든 단계는 "입력 모델 1개 → 출력 모델 1개", 통신 포맷은 JSON 한 줄 = 모델 1개):
  [Win] ScreenGrabber ─Frame→ ocr ─OcrResult(RawLine[])→ parse ─ParseResult→ normalize ─NormalizedMessage→
  classify ─Classification→ rewrite(RewriteRequest) ─Rewrite→ policy(PolicyRequest) ─Decision→ Incident → ui / report
"""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.3.0"


# ── 공통 열거형 ─────────────────────────────────────────────
class Source(StrEnum):
    OCR = "ocr"  # 실제 게임 화면에서 읽음
    DEMO = "demo"  # 시나리오 JSONL 재생 (fixtures/scenario, data/demo)
    SELF_INPUT = "self_input"  # 오버레이 입력칸에 내가 쓴 문장


class Channel(StrEnum):
    TEAM = "team"
    ALL = "all"
    SYSTEM = "system"  # "~님이 처치했습니다" 같은 시스템 메시지
    PING = "ping"  # 채팅창에 글자로 찍히는 핑 / 스펠 체크
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


# ── 게임 정보 ──────────────────────────────────────────────
class Player(BaseModel):
    """게임 참가자. 로컬 Live Client Data API(127.0.0.1:2999) 또는 설정값에서 얻음."""

    name: str
    champion: str | None = None
    team: str | None = None  # "ORDER" | "CHAOS"
    position: str | None = None  # TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY
    is_me: bool = False


# ── 0. capture: 화면 → 이미지 (Windows 전용) ────────────────
class Region(BaseModel):
    x: int
    y: int
    w: int
    h: int


class Frame(BaseModel):
    """캡처한 채팅창 이미지 1장. Mac에서는 저장된 스크린샷 파일로 대체해서 테스트."""

    id: str
    ts: float
    image_path: str  # PNG 파일 경로 (메모리 전달 시에도 디버그용으로 저장 가능)
    region: Region


# ── 1. ocr → parse ────────────────────────────────────────
class RawLine(BaseModel):
    """OCR이 읽은 채팅 한 줄(가공 전). 중복 제거는 capture 책임."""

    id: str
    ts: float  # 유닉스 시간(초)
    text: str  # 예: "[팀] Hide on bush (아리): 미드 ㅂㅅ아"
    source: Source
    ocr_confidence: float | None = None


class OcrResult(BaseModel):
    """Frame 1장에서 읽은 '새로운' 줄들 (이전 프레임과 중복된 줄은 제외)."""

    frame_id: str
    lines: list[RawLine]


# ── 2. parse → normalize ──────────────────────────────────
class ChatMessage(BaseModel):
    id: str
    ts: float
    source: Source
    channel: Channel
    speaker: str | None  # 시스템/핑은 None 가능
    champion: str | None = None
    text: str  # 화자 부분을 뗀 본문
    is_me: bool = False
    raw: str  # 원본 줄 (증거용)


class ParseResult(BaseModel):
    line_id: str
    message: ChatMessage | None  # 채팅이 아닌 줄(잡음)은 None


# ── 3. normalize → classify ───────────────────────────────
class NormalizedMessage(ChatMessage):
    text_norm: str  # 우회어 복원, OCR 오타 보정, 반복 축약 후 문장
    hints: list[str] = Field(default_factory=list)  # 예: ["leet", "jamo", "eng_typo"]


# ── 4. classify → policy ──────────────────────────────────
class Classification(BaseModel):
    """분류만 한다. 처리(숨김/신고 등)는 policy가 결정."""

    msg_id: str
    level: Level
    harm_types: list[HarmType] = Field(default_factory=list)
    has_feedback: bool = False
    scores: dict[str, float] = Field(default_factory=dict)
    model_version: str


# ── 5. rewrite (L2 이상 & has_feedback 일 때만 호출) ────────
class RewriteRequest(BaseModel):
    message: NormalizedMessage
    classification: Classification


# ── 5-1. rewrite → policy ─────────────────────────────────
class Rewrite(BaseModel):
    msg_id: str
    feedback_spans: list[str] = Field(default_factory=list)  # 원문에서 뽑은 피드백 조각
    rewritten: str | None  # 자연스럽게 다듬은 문장 (실패 시 None)
    backend: str  # "rule" | "local" | "api"


# ── 6. policy → ui / report ───────────────────────────────
class PolicyRequest(BaseModel):
    message: NormalizedMessage
    classification: Classification
    rewrite: Rewrite | None = None
    players: list[Player] = Field(default_factory=list)  # 대상 추정용 명단 (없으면 빈 목록)


class Decision(BaseModel):
    msg_id: str
    is_me: bool
    action: Action
    display_text: str | None  # 화면에 보여 주거나 복사할 문장 (HIDE/BLOCK이면 None)
    target: str | None = None  # 공격 대상(닉네임/포지션). 모르면 None
    report: bool = False  # 신고 목록에 올림
    complaint_candidate: bool = False  # 고소장 후보
    reason: str = ""  # 사람이 읽는 판단 근거 (디버그/발표용)


class Incident(BaseModel):
    """클라이언트 '처리 내역'에 보이는 기록 한 건. 로컬 저장만 허용."""

    msg: NormalizedMessage
    classification: Classification
    decision: Decision
    rewrite: Rewrite | None = None


# ── 7. report ─────────────────────────────────────────────
class ReportRequest(BaseModel):
    incidents: list[Incident]
    speaker: str  # 신고 대상 닉네임


class ReportDraft(BaseModel):
    speaker: str
    text: str  # 그대로 복사해 붙여넣을 신고 문구
    incident_ids: list[str]


class ComplaintRequest(BaseModel):
    incidents: list[Incident]
    speaker: str
    complainant: str  # 고소인 (사용자) 이름
    output_dir: str  # PDF 저장 폴더


class ComplaintDraft(BaseModel):
    speaker: str
    summary: str  # 사건 경위 (LLM 또는 규칙)
    incident_ids: list[str]
    pdf_path: str | None = None
