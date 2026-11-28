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
        (ReportKind.REPORT, "불꽃남자"),
        (ReportKind.REPORT, "얼음땡"),
    ]
    assert [(c.kind, c.speaker) for c in result.complaints] == [(ReportKind.COMPLAINT, "얼음땡")]


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


def test_empty_frame_keeps_previous_lines_for_overlap():
    """채팅창이 잠깐 숨겨져 글자가 하나도 안 읽히면 겹침 기준을 바꾸지 않는다."""
    lines = [RawLine(id=f"x{i}", ts=0, text=f"줄 {i}", source="ocr") for i in range(4)]
    blank = RawLine(id="b", ts=0, text="   ", source="ocr")
    dedup = LineDedup()
    assert [ln.id for ln in dedup.new_lines(lines[:3])] == ["x0", "x1", "x2"]
    assert dedup.new_lines([]) == [] and dedup.new_lines([blank]) == []  # 채팅창 숨김
    assert dedup.new_lines(lines[:3]) == []  # 다시 보여도 이미 처리한 줄
    assert [ln.id for ln in dedup.new_lines(lines[1:])] == ["x3"]


def test_frame_without_overlap_is_all_new_and_empty_ocr_keeps_baseline():
    """겹침 없는 화면은 보이는 줄을 모두 새 줄로 본다. OCR 결과가 비면 비교 기준을 덮어쓰지 않는다."""

    def frame(*texts: str) -> list[RawLine]:
        return [RawLine(id=t, ts=0, text=t, source="ocr") for t in texts]

    dedup = LineDedup()
    assert [ln.id for ln in dedup.new_lines(frame("A", "B", "C"))] == ["A", "B", "C"]
    assert [ln.id for ln in dedup.new_lines(frame("C", "D", "E"))] == ["D", "E"]
    assert [ln.id for ln in dedup.new_lines(frame("X", "Y"))] == ["X", "Y"]  # 연속성 검사 없이 바로 받아들인다
    baseline = list(dedup.previous)
    assert baseline[-2:] == ["X", "Y"]
    for empty in ([], frame(" "), frame("", "\t")):  # OCR 이 아무것도 못 읽은 화면이 여러 번 이어져도
        assert dedup.new_lines(empty) == []
        assert dedup.previous == baseline  # 비교 기준은 그대로
    assert dedup.new_lines(frame("X", "Y")) == []  # 다시 보여도 이미 처리한 줄
    assert [ln.id for ln in dedup.new_lines(frame("Y", "Z"))] == ["Z"]


# 실제 게임에서 같은 채팅 한 줄을 OCR 이 읽은 결과들 (2026-11-28, 반투명 채팅창 뒤로 게임 화면이 움직임).
REAL_VARIANTS = [
    "[전체] 오른은 죽었다(나서스): 야 정글 글인*아 ㅇㅇ 치라고",
    "[전체]오른은 죽었다 (나서스): 야 정글 ㅇ치라고",
    "[전체]오른은 죽었다 (나서스): 야 정글 *기*아 ㅇㅇ치라고",
    "[전체] 오른은 죽었다 (나서스): 야 정글 글**아 ㅇㅇ 치라고",
    "[전체] 오른은 죽었다(나서스): 야 정글 글*아 ㅇㅇ치라고",
    "[전체] 오른은 죽었다(나서스): 야 정글 *1*아 ㅇ치라고",
    "[전체] 오른은 ’  죽었다(나서스): 야 정글 글*1*아 ㅇㅇ치라고",
    "[전체] 오른은 ‘  죽었다(나서스): 야 정글 글**아 ㅇㅇ 치라고",
]
REAL_NOTICE = "다시하기 가능: 상대가 킬을 달성하기 전까지 누군가 님이 55초 동안 활동하지 않았습니다."


def _frame(*texts: str) -> list[RawLine]:
    return [RawLine(id=f"{i}:{t}", ts=0, text=t, source="ocr") for i, t in enumerate(texts)]


def test_same_line_read_differently_is_not_new_again():
    """같은 줄을 OCR 이 매번 다르게 읽어도 한 번만 새 줄로 본다. 똑같이 읽힌 다른 줄도 다시 내지 않는다."""
    from clean_chat.core.pipeline import line_similarity

    assert all(line_similarity(a, b) > 0 for a in REAL_VARIANTS for b in REAL_VARIANTS)
    dedup = LineDedup()
    seen = [ln.text for text in REAL_VARIANTS * 3 for ln in dedup.new_lines(_frame(REAL_NOTICE, text))]
    assert seen == [REAL_NOTICE, REAL_VARIANTS[0]]
    # 그 아래에 올라온 진짜 새 채팅은 놓치지 않는다.
    new = "[전체] 오른은 죽었다(나서스): 바론 가자"
    assert [ln.text for ln in dedup.new_lines(_frame(REAL_NOTICE, REAL_VARIANTS[3], new))] == [new]
    assert dedup.new_lines(_frame(REAL_VARIANTS[5], new)) == []


def test_different_messages_from_same_speaker_are_different_lines():
    from clean_chat.core.pipeline import line_similarity

    head = "[전체] 밤하늘별 (가렌): "
    assert line_similarity(head + "ㅇㅇ", head + "ㄴㄴ") == 0
    assert line_similarity(head + "미드 와", head + "미드 가") == 0
    assert line_similarity(head + "용 가자", "[전체] 초코우유 (리신): 용 가자") == 0  # 다른 사람의 같은 말
    assert line_similarity(REAL_NOTICE, REAL_VARIANTS[0]) == 0


def test_line_missed_in_one_frame_is_not_emitted_again():
    """OCR 이 한 화면에서 줄을 빠뜨리거나 화면이 통째로 비어도, 다음 화면에서 이미 본 줄을 새 줄로 내지 않는다."""
    dedup = LineDedup()
    assert [ln.text for ln in dedup.new_lines(_frame("A: 하나", "B: 둘둘", "C: 셋셋셋"))] == [
        "A: 하나",
        "B: 둘둘",
        "C: 셋셋셋",
    ]
    assert dedup.new_lines(_frame("A: 하나", "B: 둘둘")) == []  # 마지막 줄을 못 읽음
    assert dedup.new_lines(_frame("A: 하나", "C: 셋셋셋")) == []  # 가운데 줄을 못 읽음
    assert dedup.new_lines([]) == []
    assert dedup.new_lines(_frame("A: 하나", "B: 둘둘", "C: 셋셋셋")) == []
    assert [ln.text for ln in dedup.new_lines(_frame("B: 둘둘", "C: 셋셋셋", "D: 넷"))] == ["D: 넷"]


def test_line_not_read_as_chat_is_retried_when_read_differently():
    """첫 판독이 깨져 채팅으로 읽히지 않은 줄은, 다르게 읽혔을 때 한 번 더 내보낸다 (같은 판독이면 다시 내지 않는다)."""
    dedup = LineDedup()
    broken, fixed = (
        "[03:35][전체]별빛라면(이즈리얼):넌 그냥 탈주해",
        "[03:35] [전체] 별빛라면 (이즈리얼): 넌 그냥 탈주해",
    )
    first = dedup.new_lines(_frame("A: 하나", broken, "C: 셋셋셋"))
    assert [ln.text for ln in first] == ["A: 하나", broken, "C: 셋셋셋"]
    dedup.retry(first[1])  # parse 가 채팅이 아니라고 함
    assert dedup.new_lines(_frame("A: 하나", broken, "C: 셋셋셋")) == []  # 똑같이 읽히면 그대로
    assert [ln.text for ln in dedup.new_lines(_frame("A: 하나", fixed, "C: 셋셋셋"))] == [fixed]
    assert dedup.new_lines(_frame("A: 하나", broken, "C: 셋셋셋")) == []  # 한 번 다시 본 뒤에는 또 내지 않는다


def test_process_frame_runs_ocr_then_lines():
    frame: Frame = fixture_pairs("ocr")[0][0]
    p = Pipelines(fixture_modules())
    assert [i.msg.id for i in p.incoming.process_frame(frame)] == ["L0", "L2"]  # L1(핑)은 parse 가 None
    assert p.incoming.process_frame(frame) == []  # 같은 화면 다시 → 새 줄 없음


def test_unimplemented_module_stops_engine_with_its_name():
    """미구현 모듈을 만나면 엔진이 멈추고 해당 모듈 이름을 알린다."""
    from clean_chat.core.schemas import ParseRequest, ParseResult

    def unimplemented_parse(req: ParseRequest) -> ParseResult:
        raise NotImplementedError("테스트용 미구현 모듈")

    eng = _engine(ModuleSet({"parse": unimplemented_parse}))
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
