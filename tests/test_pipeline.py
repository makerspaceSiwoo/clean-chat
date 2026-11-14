"""연결 구조 (구성): 가짜 모듈로 흐름 A/B, 게임 세션, 종료 배치가 제대로 이어지는지. 모듈 로직은 보지 않는다."""

from clean_chat.core.config import FIXTURES
from clean_chat.core.engine import Engine
from clean_chat.core.jsonl import read_jsonl
from clean_chat.core.modules import ModuleSet
from clean_chat.core.pipeline import LineDedup, Pipelines
from clean_chat.core.schemas import (
    Action,
    Frame,
    GamePhase,
    Incident,
    Player,
    PostGameResult,
    RawLine,
    ReportKind,
    ReportRequest,
)
from clean_chat.core.sources import DemoLineSource
from clean_chat.session.fake import FakePhaseDetector
from helpers import SCENARIO, fixture_modules, fixture_pairs


def _engine(mods: ModuleSet | None = None) -> Engine:
    detector = FakePhaseDetector(SCENARIO / "phases.jsonl", SCENARIO / "players.jsonl")
    return Engine(Pipelines(mods or fixture_modules()), DemoLineSource(SCENARIO / "lines.jsonl", delay_sec=0), detector)


def test_demo_game_wiring():
    """IDLE → IN_GAME(흐름 A, 세션 기록) → POST_GAME(report 모듈을 kind 별로)"""
    eng = _engine()
    phases: list[GamePhase] = []
    incidents: list[Incident] = []
    results: list[PostGameResult] = []
    eng.on_phase(lambda phase, _session: phases.append(phase))
    eng.subscribe(incidents.append)
    eng.on_result(results.append)
    eng.start(block=True)

    assert eng.error is None
    assert phases == [GamePhase.IN_GAME, GamePhase.POST_GAME]
    assert [i.msg.id for i in incidents] == ["L0", "L2", "L3", "L4", "L5"]  # 핑(L1)·잡음(L6)은 parse 가 걸러냄
    assert [i.decision.action for i in incidents] == ["show", "show_masked", "show_rewritten", "hide", "hide"]
    session = eng.repository.load("20251112-125820")
    assert session == read_jsonl(FIXTURES / "report" / "input.jsonl", ReportRequest)[0].session  # 같은 시나리오
    (result,) = results
    assert [(r.kind, r.speaker) for r in result.reports] == [
        (ReportKind.REPORT, "원딜러"),
        (ReportKind.REPORT, "상대탑"),
    ]
    assert [(c.kind, c.speaker) for c in result.complaints] == [(ReportKind.COMPLAINT, "상대탑")]


def test_rewrite_only_for_l2_with_feedback():
    called: list[str] = []
    base = fixture_modules()
    mods = fixture_modules(rewrite=lambda req: called.append(req.message.id) or base.run("rewrite", req))
    _engine(mods).start(block=True)
    assert called == ["L3"]


def test_analyze_gets_history_and_players():
    seen = []
    base = fixture_modules()
    mods = fixture_modules(analyze=lambda req: seen.append(req) or base.run("analyze", req))
    _engine(mods).start(block=True)
    assert [m.id for m in seen[-1].history] == ["L0", "L2", "L3", "L4"]
    assert seen[-1].players == read_jsonl(SCENARIO / "players.jsonl", Player)


def test_outgoing_flow_uses_parse_with_self_input():
    p = Pipelines(fixture_modules())
    p.set_players(read_jsonl(SCENARIO / "players.jsonl", Player))
    got = [p.outgoing.submit(o["text"], msg_id=o["id"], ts=o["ts"]) for o in _outgoing()]
    assert [i.decision.action for i in got] == [Action.COPY_REWRITTEN, Action.BLOCK]
    assert got[0].decision.display_text == "정글 합류 부탁해요"


def test_my_sent_text_read_back_by_ocr_is_skipped():
    """흐름 B 로 복사한 문장이 게임 채팅창에 올라가 OCR 로 다시 읽히면 흐름 A 는 건너뛴다."""
    echo = RawLine(id="L9", ts=1762920009.0, text="[팀] 나 (쓰레쉬): 정글 합류 부탁해요", source="ocr")
    base = fixture_modules()
    p = Pipelines(fixture_modules(analyze=lambda req: _analysis_for(base, req)))
    assert p.incoming.process_line(echo) is not None  # 아직 보낸 적 없음 → 처리됨
    p.outgoing.submit("아 정글 ㅂㅅ 왜 안 와", msg_id="L7", ts=1762920007.0)  # → "정글 합류 부탁해요" 복사
    assert p.incoming.process_line(echo) is None


def test_frames_are_deduplicated_between_ocr_calls():
    lines = [RawLine(id=f"x{i}", ts=0, text=f"줄 {i}", source="ocr") for i in range(4)]
    dedup = LineDedup()
    assert [ln.id for ln in dedup.new_lines(lines[:3])] == ["x0", "x1", "x2"]
    assert [ln.id for ln in dedup.new_lines(lines[1:])] == ["x3"]  # 채팅창이 한 줄 밀려 올라감


def test_process_frame_runs_ocr_then_lines():
    frame: Frame = fixture_pairs("ocr")[0][0]
    p = Pipelines(fixture_modules())
    assert [i.msg.id for i in p.incoming.process_frame(frame)] == ["L0", "L2"]  # L1(핑)은 parse 가 None
    assert p.incoming.process_frame(frame) == []  # 같은 화면 다시 → 새 줄 없음


def test_unimplemented_module_stops_engine_with_its_name():
    """Mock 이 없으므로 구현 전 모듈을 만나면 멈추고 이름을 알린다 (실제 모듈 = 지금은 전부 미구현)."""
    eng = _engine(ModuleSet())
    errors: list[str] = []
    results: list[PostGameResult] = []
    eng.on_error(errors.append)
    eng.on_result(results.append)
    eng.start(block=True)
    assert eng.error is not None and eng.error.module == "parse"
    assert errors and "parse" in errors[0]
    assert results == []  # 배치까지 가지 않음


def _outgoing() -> list[dict]:
    import json

    return [json.loads(line) for line in (SCENARIO / "outgoing.jsonl").read_text(encoding="utf-8").splitlines()]


def _analysis_for(base: ModuleSet, req):
    """fixtures 에 없는 메시지(L9)는 정상(L0)으로 본다."""
    from clean_chat.core.schemas import Analysis

    if req.message.id == "L9":
        return Analysis(msg_id="L9", level=0, model_version="test")
    return base.run("analyze", req)
