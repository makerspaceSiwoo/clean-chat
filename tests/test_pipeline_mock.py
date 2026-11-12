"""전부 mock 으로 끝까지 돌렸을 때 시나리오 기대 결과와 같은지 (연결 구조 검증)."""

from clean_chat.core.config import FIXTURES
from clean_chat.core.engine import Engine
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.schemas import (
    Action,
    ComplaintDraft,
    ComplaintRequest,
    GamePhase,
    Incident,
    OutgoingText,
    Player,
    PostGameResult,
    RawLine,
    ReportDraft,
    ReportRequest,
)
from clean_chat.core.sources import DemoLineSource
from clean_chat.core.stage import read_jsonl
from clean_chat.session.fake import FakePhaseDetector

SCENARIO = FIXTURES / "scenario"


def _demo_engine() -> Engine:
    detector = FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl")
    return Engine(Pipelines(), DemoLineSource(SCENARIO / "lines.jsonl", delay_sec=0), detector)


def test_demo_game_end_to_end():
    """IDLE → IN_GAME(흐름 A, 세션 기록) → POST_GAME(배치: 신고 문구·고소장)"""
    eng = _demo_engine()
    phases: list[GamePhase] = []
    incidents: list[Incident] = []
    results: list[PostGameResult] = []
    eng.on_phase(lambda phase, _session: phases.append(phase))
    eng.subscribe(incidents.append)
    eng.on_result(results.append)
    eng.start(block=True)

    assert phases == [GamePhase.IN_GAME, GamePhase.POST_GAME]
    assert incidents == read_jsonl(SCENARIO / "expected_incidents.jsonl", Incident)
    # 세션 = 신고·고소장 fixtures 의 세션과 같아야 함 (같은 시나리오)
    session = eng.repository.load("20251112-125820")
    assert session == read_jsonl(FIXTURES / "report" / "input.jsonl", ReportRequest)[0].session
    (result,) = results
    assert result.reports == read_jsonl(FIXTURES / "report" / "expected.jsonl", ReportDraft)
    assert result.complaints == read_jsonl(FIXTURES / "complaint" / "expected.jsonl", ComplaintDraft)
    assert read_jsonl(FIXTURES / "complaint" / "input.jsonl", ComplaintRequest)[0].session == session


def test_dismiss_result_returns_to_idle():
    eng = _demo_engine()
    phases: list[GamePhase] = []
    eng.on_phase(lambda phase, _session: phases.append(phase))
    eng.start(block=True)
    eng.dismiss_result()
    assert phases[-1] == GamePhase.IDLE
    assert eng.phase == GamePhase.IDLE


def test_outgoing_flow_matches_scenario():
    """흐름 B: 내 입력 → 동기 요청-응답으로 Incident 1개씩 (게임 중이라 명단이 있음)"""
    p = Pipelines()
    p.set_players(read_jsonl(SCENARIO / "players.jsonl", Player))
    got = [
        p.outgoing.submit(o.text, msg_id=o.id, ts=o.ts) for o in read_jsonl(SCENARIO / "outgoing.jsonl", OutgoingText)
    ]
    assert got == read_jsonl(SCENARIO / "expected_outgoing.jsonl", Incident)
    assert [i.decision.action for i in got] == [Action.COPY_REWRITTEN, Action.BLOCK]


def test_my_sent_text_read_back_by_ocr_is_skipped():
    """흐름 B 로 복사한 문장이 게임 채팅창에 올라가 OCR 로 다시 읽히면 흐름 A 는 건너뛴다."""
    p = Pipelines()
    p.set_players(read_jsonl(SCENARIO / "players.jsonl", Player))
    echo = RawLine(
        id="L9", ts=1762920009.0, text="[팀] 나 (쓰레쉬): 정글 합류 부탁해요", source="ocr", ocr_confidence=0.93
    )
    assert p.incoming.process_line(echo) is not None  # 아직 보낸 적 없음 → 처리됨
    p.outgoing.submit("아 정글 ㅂㅅ 왜 안 와", msg_id="L7", ts=1762920007.0)  # → "정글 합류 부탁해요" 복사
    assert p.incoming.process_line(echo) is None
