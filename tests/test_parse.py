"""② parse 모듈 (담당자 소유). 규칙 모듈이라 fixtures 기대값과 정확히 같아야 한다."""

import pytest

from clean_chat.core.schemas import Channel, ParseRequest, RawLine, Source
from clean_chat.modules.parse.impl import normalize, run
from helpers import check_module


def test_parse_fixtures():
    check_module("parse", strict=True)


def request(text: str, source: Source = Source.OCR, my_name: str = "나") -> ParseRequest:
    return ParseRequest(line=RawLine(id="parse-test", ts=123.0, text=text, source=source), my_name=my_name)


@pytest.mark.parametrize("source", [Source.OCR, Source.DEMO])
def test_parse_preserves_evidence_and_input(source: Source) -> None:
    raw = "[전체] 테스트 닉네임 (가렌): 용: 1분  남았어  "
    req = request(raw, source)
    original = req.model_dump()
    message = run(req).message
    assert message is not None
    assert (message.id, message.ts, message.source) == (req.line.id, req.line.ts, source)
    assert (message.channel, message.speaker, message.champion) == (Channel.ALL, "테스트 닉네임", "가렌")
    assert message.text == "용: 1분  남았어  "
    assert message.text_norm == message.text
    assert message.raw == raw
    assert req.model_dump() == original


@pytest.mark.parametrize(
    ("raw", "channel", "body"),
    [("같이 가요", Channel.TEAM, "같이 가요"), ("/all 잘했어요", Channel.ALL, "잘했어요"), ("?", Channel.TEAM, "?")],
)
def test_self_input(raw: str, channel: Channel, body: str) -> None:
    message = run(request(raw, Source.SELF_INPUT)).message
    assert message is not None
    assert (message.channel, message.speaker, message.champion, message.is_me) == (channel, "나", None, True)
    assert (message.text, message.raw) == (body, raw)


@pytest.mark.parametrize("raw", ["", "   ", "/all", "/all   "])
def test_empty_self_input(raw: str) -> None:
    assert run(request(raw, Source.SELF_INPUT)).message is None


@pytest.mark.parametrize(
    "raw", ["", "@@ ㅡ ##", "옵션", "용 먼저", "[팀] 나 (가렌):   ", "정글러 (리신)님이 점멸 쿨타임 신호를 보냈습니다"]
)
def test_non_chat(raw: str) -> None:
    assert run(request(raw)).message is None


def test_unknown_channel_and_optional_champion() -> None:
    message = run(request("나: 정글 합류 부탁해요")).message
    assert message is not None
    assert (message.channel, message.champion, message.is_me) == (Channel.UNKNOWN, None, True)


def test_system_phrase_in_player_chat_is_preserved() -> None:
    message = run(request("[팀] 테스트 (가렌): 누가 신호를 보냈습니다")).message
    assert message is not None
    assert message.text == "누가 신호를 보냈습니다"


@pytest.mark.parametrize(
    ("text", "expected", "hints"),
    [
        ("다들 화이팅", "다들 화이팅", []),
        ("시1발", "시발", ["noise_removed"]),
        ("ㅂㅅ아", "병신아", ["lexicon:ㅂㅅ"]),
        ("tlqkf", "시발", ["lexicon:tlqkf"]),
        ("용 1분 미드2차", "용 1분 미드2차", []),
    ],
)
def test_basic_normalization(text: str, expected: str, hints: list[str]) -> None:
    assert normalize(text) == (expected, hints)
