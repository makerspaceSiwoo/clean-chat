"""전부 mock 으로 끝까지 돌렸을 때 시나리오 기대 결과와 같은지 (연결 구조 검증)."""

from clean_chat.core.config import FIXTURES
from clean_chat.core.engine import Engine
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.schemas import Action, Incident, OutgoingText, RawLine
from clean_chat.core.sources import DemoLineSource
from clean_chat.core.stage import read_jsonl

SCENARIO = FIXTURES / "scenario"


def test_incoming_flow_matches_scenario():
    """흐름 A: 다른 유저 채팅 시나리오 → Incident 스트림"""
    got: list[Incident] = []
    eng = Engine(Pipelines(), DemoLineSource(SCENARIO / "lines.jsonl", delay_sec=0))
    eng.subscribe(got.append)
    eng.start(block=True)
    assert got == read_jsonl(SCENARIO / "expected_incidents.jsonl", Incident)


def test_outgoing_flow_matches_scenario():
    """흐름 B: 내 입력 → 동기 요청-응답으로 Incident 1개씩"""
    p = Pipelines()
    got = [
        p.outgoing.submit(o.text, msg_id=o.id, ts=o.ts) for o in read_jsonl(SCENARIO / "outgoing.jsonl", OutgoingText)
    ]
    assert got == read_jsonl(SCENARIO / "expected_outgoing.jsonl", Incident)
    assert [i.decision.action for i in got] == [Action.COPY_REWRITTEN, Action.BLOCK]


def test_my_sent_text_read_back_by_ocr_is_skipped():
    """흐름 B 로 복사한 문장이 게임 채팅창에 올라가 OCR 로 다시 읽히면 흐름 A 는 건너뛴다."""
    p = Pipelines()
    echo = RawLine(
        id="L9", ts=1762920009.0, text="[팀] 나 (쓰레쉬): 정글 합류 부탁해요", source="ocr", ocr_confidence=0.93
    )
    assert p.incoming.process_line(echo) is not None  # 아직 보낸 적 없음 → 처리됨
    p.outgoing.submit("아 정글 ㅂㅅ 왜 안 와", msg_id="L7", ts=1762920007.0)  # → "정글 합류 부탁해요" 복사
    assert p.incoming.process_line(echo) is None
