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
    "raw",
    ["", "@@ ㅡ ##", "옵션", "용 먼저", "[팀] 나 (가렌):   ", "초코우유 (리신)님이 점멸 쿨타임 신호를 보냈습니다"],
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


@pytest.mark.parametrize(
    ("tag", "channel"),
    [
        ("[팀]", Channel.TEAM),
        ("(팀)", Channel.TEAM),
        ("[팀)", Channel.TEAM),
        ("(팀]", Channel.TEAM),
        ("［ 팀 ］", Channel.TEAM),
        ("（전체）", Channel.ALL),
        ("[전체)", Channel.ALL),
        ("(전체]", Channel.ALL),
    ],
)
@pytest.mark.parametrize("source", [Source.OCR, Source.DEMO])
def test_channel_bracket_variants(tag: str, channel: Channel, source: Source) -> None:
    raw = f"{tag} 불꽃남자 (징크스): 합류 부탁해요"
    message = run(request(raw, source)).message
    assert message is not None
    assert (message.channel, message.speaker, message.champion) == (channel, "불꽃남자", "징크스")
    assert (message.text, message.raw) == ("합류 부탁해요", raw)


@pytest.mark.parametrize("separator", [":", ";", "：", "；"])
@pytest.mark.parametrize("champion", ["(징크스)", "（징크스）"])
def test_header_delimiter_variants_preserve_body(separator: str, champion: str) -> None:
    body = "용: 1분; (합류) [확인] ： 그대로；  "
    raw = f"[전체] 불꽃 남자 {champion}{separator} {body}"
    req = request(raw)
    original = req.model_dump()
    message = run(req).message
    assert message is not None
    assert (message.channel, message.speaker, message.champion) == (Channel.ALL, "불꽃 남자", "징크스")
    assert (message.text, message.text_norm, message.raw) == (body, body, raw)
    assert req.model_dump() == original


@pytest.mark.parametrize("separator", [":", ";", "：", "；"])
def test_delimiter_variants_without_champion(separator: str) -> None:
    message = run(request(f"나{separator} 합류 부탁해요")).message
    assert message is not None
    assert (message.speaker, message.champion, message.channel, message.is_me) == ("나", None, Channel.UNKNOWN, True)


@pytest.mark.parametrize(
    "raw",
    [
        "[팀 불꽃남자 (징크스): 합류 부탁해요",
        "팀] 불꽃남자 (징크스): 합류 부탁해요",
        "[파티] 불꽃남자 (징크스): 합류 부탁해요",
        "[팀] 불꽃남자 (징크스: 합류 부탁해요",
        "[팀] 불꽃남자 징크스): 합류 부탁해요",
        "[팀] 불꽃남자 (): 합류 부탁해요",
        "[팀] 불꽃남자 (   ): 합류 부탁해요",
        "[팀] (징크스): 합류 부탁해요",
        "[팀] 불꽃남자 (징크스) 합류 부탁해요",
        "[팀] 불꽃남자 (징크스): 첫 줄\n둘째 줄",
    ],
)
def test_malformed_header_is_not_used_as_speaker(raw: str) -> None:
    assert run(request(raw)).message is None


def test_self_input_does_not_repair_chat_headers() -> None:
    raw = "[팀) 불꽃남자 (징크스); 합류 부탁해요"
    message = run(request(raw, Source.SELF_INPUT)).message
    assert message is not None
    assert (message.speaker, message.champion, message.is_me) == ("나", None, True)
    assert (message.text, message.raw) == (raw, raw)


@pytest.mark.parametrize(
    "raw",
    [
        "초코우유 (리신)님이 점멸 쿨타임 신호를 보냈습니다",
        "초코우유（리신）님이 점멸: 30초 신호를 보냈습니다.",
        "초코우유님이 밤하늘별님을 처치했습니다!",
        "초코우유님이 게임을 종료했습니다",
        "초코우유님이 게임을 떠났습니다.",
        "알림: 초코우유님이 게임을 떠났습니다",
        "시스템； 초코우유 (리신)님이 점멸 쿨타임 신호를 보냈습니다",
        "게임 시간: 12:34",
        "남은 시간： 01：20",
    ],
)
def test_known_notifications_and_clock_labels_are_not_chat(raw: str) -> None:
    assert run(request(raw)).message is None


@pytest.mark.parametrize(
    ("header", "speaker"),
    [
        ("[팀] 불꽃남자 (징크스): ", "불꽃남자"),
        ("(팀) 불꽃남자 (징크스); ", "불꽃남자"),
        ("불꽃남자: ", "불꽃남자"),
        ("알림 (가렌): ", "알림"),
    ],
)
@pytest.mark.parametrize(
    "body",
    [
        "초코우유님이 게임을 떠났습니다",
        "초코우유님이 점멸 쿨타임 신호를 보냈습니다",
        "게임 시간: 12:34",
    ],
)
def test_notification_words_in_chat_body_are_preserved(header: str, speaker: str, body: str) -> None:
    raw = header + body
    message = run(request(raw)).message
    assert message is not None
    assert (message.speaker, message.text, message.raw) == (speaker, body, raw)


@pytest.mark.parametrize(
    "raw",
    [
        "[팀] 게임 시간: 12:34",
        "게임 시간 (가렌): 12:34",
        "게임 시간: 합류 부탁해요",
        "게임 시간: 12:34에 합류해요",
        "초코우유님이: 게임을 떠났습니다",
    ],
)
def test_clock_or_notice_like_player_names_are_not_blanket_filtered(raw: str) -> None:
    message = run(request(raw)).message
    assert message is not None
    assert message.raw == raw


@pytest.mark.parametrize("raw", ["게임 시간: 12:34", "알림: 초코우유님이 게임을 떠났습니다"])
def test_notification_detection_is_not_applied_to_self_input(raw: str) -> None:
    message = run(request(raw, Source.SELF_INPUT)).message
    assert message is not None
    assert (message.speaker, message.text, message.raw) == ("나", raw, raw)
