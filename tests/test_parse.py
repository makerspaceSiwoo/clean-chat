"""② parse 모듈 (담당자 소유). 규칙 모듈이라 fixtures 기대값과 정확히 같아야 한다."""

import pytest
from pydantic import ValidationError

from clean_chat.core.schemas import Channel, ParseRequest, ParseResult, RawLine, Source
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


@pytest.mark.parametrize(
    "text",
    [
        "mytlqkfbuild",
        "tlqkf123 qudtls_model _tlqkf_",
        "ㄱㅅㅂㅂ ㅂㅅㄱ",
        "https://example.test/tlqkf/시1발",
        "www.example.test/qudtls",
        "tlqkf@example.test",
        "용 1분 미드2차 12:34 1.5초",
        "LoL lol O0 l1 I1 모델 v1.0",
    ],
)
def test_normalization_preserves_identifiers_and_normal_text(text: str) -> None:
    assert normalize(text) == (text, [])


@pytest.mark.parametrize(
    ("text", "expected", "hints"),
    [
        ("TLQKF QUDTLS", "시발 병신", ["lexicon:tlqkf", "lexicon:qudtls"]),
        ("tlqkf야", "시발야", ["lexicon:tlqkf"]),
        ("ㅂㅅ아 ㅂㅅ", "병신아 병신", ["lexicon:ㅂㅅ"]),
        ("ㅄ 븅신", "병신 병신", ["lexicon:ㅄ", "lexicon:븅신"]),
        ("https://example.test/tlqkf 옆의 tlqkf", "https://example.test/tlqkf 옆의 시발", ["lexicon:tlqkf"]),
        ("tlqkf@example.test 다음 ㅂㅅ", "tlqkf@example.test 다음 병신", ["lexicon:ㅂㅅ"]),
    ],
)
def test_guarded_lexicon_replacements(text: str, expected: str, hints: list[str]) -> None:
    assert normalize(text) == (expected, hints)


@pytest.mark.parametrize(
    ("text", "expected", "hints"),
    [
        ("시.발", "시발", ["noise_removed"]),
        ("시*발 시_발", "시발 시발", ["noise_removed"]),
        ("시\u200b발", "시발", ["noise_removed"]),
        ("병1신아", "병신아", ["noise_removed"]),
        ("씨.발", "시발", ["noise_removed", "lexicon:씨발"]),
        ("ㅅ1ㅂ", "시발", ["noise_removed", "lexicon:ㅅㅂ"]),
        ("ㅅ ㅂ", "시발", ["jamo_joined", "lexicon:ㅅㅂ"]),
        ("ㅆ\tㅂ", "시발", ["jamo_joined", "lexicon:ㅆㅂ"]),
        ("ㅂ \tㅅ아", "병신아", ["jamo_joined", "lexicon:ㅂㅅ"]),
        ("ㅋㅋㅋㅋㅋ", "ㅋㅋ", ["repeats_squeezed"]),
        ("ㅎㅎㅎㅎ ㅠㅠㅠㅜㅜㅜ", "ㅎㅎ ㅠㅠㅜㅜ", ["repeats_squeezed"]),
        (
            "아 ㅅ ㅂ 시.발ㅋㅋㅋㅋ",
            "아 시발 시발ㅋㅋ",
            ["noise_removed", "jamo_joined", "repeats_squeezed", "lexicon:ㅅㅂ"],
        ),
    ],
)
def test_dictionary_scoped_noise_and_jamo_normalization(text: str, expected: str, hints: list[str]) -> None:
    assert normalize(text) == (expected, hints)


@pytest.mark.parametrize(
    "text",
    [
        "가가가 나나나 미미미",
        "111 000 !!! ???",
        "ㅋㅋ ㅎㅎ ㅠㅠ ㅜㅜ",
        "미드2차 용 1분 쿨타임 12:34",
        "시 1분 뒤에 발 묶어",
        "ㄱ ㅅ ㄴ ㄴ",
        "ㄱ ㅅ ㅂ",
        "ㅅ\nㅂ",
        "my시1발build",
        "https://example.test/시.발/ㅋㅋㅋㅋ",
    ],
)
def test_normalization_does_not_delete_unrecognized_content(text: str) -> None:
    assert normalize(text) == (text, [])


@pytest.mark.parametrize(
    ("text", "expected", "hints"),
    [
        ("시l발", "시발", ["ocr_fixed"]),
        ("시I발 시|발", "시발 시발", ["ocr_fixed"]),
        ("시o발 시O발", "시발 시발", ["ocr_fixed"]),
        ("병l신아", "병신아", ["ocr_fixed"]),
        ("시l1.발", "시발", ["ocr_fixed"]),
        ("ㅅlㅂ", "시발", ["ocr_fixed", "lexicon:ㅅㅂ"]),
        ("씨I발", "시발", ["ocr_fixed", "lexicon:씨발"]),
        ("시0발", "시발", ["noise_removed"]),
    ],
)
def test_ocr_corrections_are_scoped_to_dictionary_words(text: str, expected: str, hints: list[str]) -> None:
    assert normalize(text) == (expected, hints)


@pytest.mark.parametrize(
    "text",
    [
        "I love LoL O0 l1 I1",
        "미드0차 l초 O분 가l나 병원",
        "model시l발build",
        "myㅅ ㅂbuild",
        "ㅂ ㅅ123",
        "https://example.test/시l발/ㅋㅋㅋㅋ",
    ],
)
def test_ocr_and_jamo_corrections_preserve_non_dictionary_context(text: str) -> None:
    assert normalize(text) == (text, [])


@pytest.mark.parametrize("source", [Source.OCR, Source.DEMO, Source.SELF_INPUT])
def test_all_normalization_stages_preserve_evidence(source: Source) -> None:
    body = "아 ㅅ ㅂ 시l발ㅋㅋㅋㅋ 용 1분  "
    raw = body if source == Source.SELF_INPUT else f"[팀] 불꽃남자 (징크스): {body}"
    req = request(raw, source)
    before = req.model_dump()
    result = run(req)
    message = result.message
    assert message is not None
    assert (message.raw, message.text) == (raw, body)
    assert message.text_norm == "아 시발 시발ㅋㅋ 용 1분  "
    assert message.hints == ["jamo_joined", "repeats_squeezed", "ocr_fixed", "lexicon:ㅅㅂ"]
    assert (message.id, message.ts, message.source) == (req.line.id, req.line.ts, source)
    assert req.model_dump() == before
    assert run(req) == result


@pytest.mark.parametrize(
    "text",
    [
        "",
        "다들 화이팅",
        "시1발 씨.발 ㅅ1ㅂ",
        "ㅅ ㅂ 시l발ㅋㅋㅋㅋ 용 1분",
        "TLQKF QUDTLS ㅂㅅ아",
        "ㄱ ㅅ ㅂ",
        "https://example.test/시l발 다음 tlqkf",
        "tlqkf@example.test 옆의 ㅂ \tㅅ",
    ],
)
def test_normalization_result_is_stable_on_second_pass(text: str) -> None:
    normalized, hints = normalize(text)
    assert len(hints) == len(set(hints))
    assert normalize(normalized) == (normalized, [])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ㅅ1ㅂ ㅅ ㅂ", "시발 시발"),
        ("ㅅ ㅂ ㅅ1ㅂ", "시발 시발"),
        ("ㅅ ㅂ ㅄ", "시발 병신"),
        ("ㅄ ㅅ ㅂ", "병신 시발"),
        ("ㅂㅅ  \tㅅ ㅂ", "병신  \t시발"),
    ],
)
def test_existing_jamo_words_do_not_block_neighbor_normalization(text: str, expected: str) -> None:
    normalized, _ = normalize(text)
    assert normalized == expected
    assert normalize(normalized) == (expected, [])


def test_composed_normalization_is_stable() -> None:
    from itertools import product

    samples = ["ㅅ1ㅂ", "ㅅ ㅂ", "ㅂ\tㅅ", "ㅄ", "ㅂㅅ", "TLQKF", "시l발", "ㅋㅋㅋㅋ", "용 1분"]
    for left, separator, right in product(samples, [" ", "/", "\n"], samples):
        text = left + separator + right
        normalized, _ = normalize(text)
        assert normalize(normalized) == (normalized, []), text


@pytest.mark.parametrize("source", [Source.OCR, Source.DEMO])
@pytest.mark.parametrize("clock", ["17:02", "[13:23]", "0:00", "123:59"])
@pytest.mark.parametrize(("tag", "channel"), [("[팀]", Channel.TEAM), ("(전체)", Channel.ALL)])
def test_game_time_prefix_preserves_evidence(source: Source, clock: str, tag: str, channel: Channel) -> None:
    body = "합류 부탁해요: 17:02에 ㅅ ㅂ  "
    raw = f"{clock} {tag} 밤하늘별 (코그모): {body}"
    req = request(raw, source)
    before = req.model_dump()
    message = run(req).message
    assert message is not None
    assert (message.channel, message.speaker, message.champion, message.is_me) == (channel, "밤하늘별", "코그모", False)
    assert (message.raw, message.text) == (raw, body)
    assert message.text_norm == "합류 부탁해요: 17:02에 시발  "
    assert (message.id, message.ts, message.source) == (req.line.id, 123.0, source)
    assert req.model_dump() == before


@pytest.mark.parametrize("clock", ["13:35", "[13:35]"])
def test_game_time_without_channel_or_champion(clock: str) -> None:
    message = run(request(f"{clock} 나 : ****")).message
    assert message is not None
    assert (message.speaker, message.champion, message.channel, message.is_me) == ("나", None, Channel.UNKNOWN, True)
    assert (message.text, message.text_norm, message.hints) == ("****", "****", [])


@pytest.mark.parametrize("raw", ["17:02 초코우유님이 게임을 떠났습니다", "[17:02] 게임 시간: 12:34"])
def test_game_time_does_not_turn_notifications_into_chat(raw: str) -> None:
    assert run(request(raw)).message is None


@pytest.mark.parametrize(
    "raw",
    [
        "17:60 [팀] 밤하늘별 (코그모): 합류해요",
        "17:2 [팀] 밤하늘별 (코그모): 합류해요",
        "1234:02 [팀] 밤하늘별 (코그모): 합류해요",
        "17:02[팀] 밤하늘별 (코그모): 합류해요",
        "[17:02 밤하늘별 (코그모): 합류해요",
        "17:02:03 [팀] 밤하늘별 (코그모): 합류해요",
        "17:02",
        "17:02 [팀] 밤하늘별 (코그모):   ",
    ],
)
def test_invalid_or_incomplete_game_time_is_not_a_speaker(raw: str) -> None:
    assert run(request(raw)).message is None


def test_numeric_speaker_is_not_mistaken_for_game_time() -> None:
    message = run(request("17: 합류 부탁해요")).message
    assert message is not None
    assert (message.speaker, message.text) == ("17", "합류 부탁해요")


@pytest.mark.parametrize("command", ["", "/all "])
def test_self_input_keeps_game_time_as_body(command: str) -> None:
    body = "17:02 [팀] 밤하늘별 (코그모): 합류해요"
    raw = command + body
    message = run(request(raw, Source.SELF_INPUT)).message
    assert message is not None
    assert (message.speaker, message.champion, message.is_me) == ("나", None, True)
    assert (message.text, message.raw) == (body, raw)
    assert message.channel == (Channel.ALL if command else Channel.TEAM)


def test_parse_result_accepts_legacy_output() -> None:
    result = ParseResult.model_validate_json('{"line_id":"legacy","message":null}')
    assert result.model_dump() == {"line_id": "legacy", "message": None}


@pytest.mark.parametrize("invalid", [-1, 1.5, True, "17:02"])
def test_parse_result_game_time_requires_nonnegative_integer(invalid: object) -> None:
    message = run(request("밤하늘별: 합류해요")).message
    assert message is not None
    data = message.model_dump()
    data["game_time_sec"] = invalid
    with pytest.raises(ValidationError):
        ParseResult.model_validate({"line_id": "invalid", "message": data})


@pytest.mark.parametrize(
    ("clock", "seconds", "canonical"),
    [
        ("17:02", 1022, "17:02"),
        ("[13:23]", 803, "13:23"),
        ("0:00", 0, "00:00"),
        ("1:05", 65, "01:05"),
        ("123:59", 7439, "123:59"),
    ],
)
def test_game_time_is_returned_as_elapsed_seconds(clock: str, seconds: int, canonical: str) -> None:
    result = run(request(f"{clock} (팀) 밤하늘별 （코그모）； 시1발  "))
    assert result.message is not None
    assert result.message.game_time_sec == seconds
    assert result.message.raw_norm == f"{canonical} [팀] 밤하늘별 (코그모): 시1발  "
    assert result.message.text == "시1발  "
    assert result.message.text_norm == "시발  "
    assert result.message.ts == 123.0
    assert ParseResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    ("raw", "normalized", "seconds"),
    [
        ("[팀) 불꽃남자 (징크스); 합류해요", "[팀] 불꽃남자 (징크스): 합류해요", None),
        ("[13:35] 나 : ****", "13:35 나: ****", 815),
        ("[전체] 얼음땡: ㅋㅋㅋㅋㅋ", "[전체] 얼음땡: ㅋㅋㅋㅋㅋ", None),
        ("밤하늘별: 합류해요", "밤하늘별: 합류해요", None),
    ],
)
def test_raw_norm_repairs_structure_without_inventing_details(raw: str, normalized: str, seconds: int | None) -> None:
    result = run(request(raw))
    assert result.message is not None
    assert (result.message.raw_norm, result.message.game_time_sec) == (normalized, seconds)
    assert result.message.raw == raw


@pytest.mark.parametrize(
    "raw",
    ["@@ ㅡ ##", "17:60 [팀] 밤하늘별: 합류해요", "17:02 초코우유님이 게임을 떠났습니다", "17:02 [팀] 밤하늘별:   "],
)
def test_rejected_lines_do_not_return_reconstructed_chat(raw: str) -> None:
    result = run(request(raw))
    assert result.message is None
    assert result.model_dump() == {"line_id": "parse-test", "message": None}


def test_self_input_raw_norm_does_not_extract_time_from_body() -> None:
    raw = "/all 17:02 시1발"
    result = run(request(raw, Source.SELF_INPUT))
    assert result.message is not None
    assert result.message.raw_norm == "[전체] 나: 17:02 시1발"
    assert result.message.game_time_sec is None
    assert result.message.raw == raw
    assert result.message.text_norm == "17:02 시발"


@pytest.mark.parametrize(
    "raw",
    [
        "[00:00] (전체) 얼음땡 : ****",
        "17:02 [팀) 밤하늘별 （코그모）； 시1발  ",
        "나: 합류 부탁해요",
        "17: 합류해요",
    ],
)
def test_reconstructed_line_can_be_parsed_again(raw: str) -> None:
    result = run(request(raw))
    assert result.message is not None and result.message.raw_norm is not None
    reparsed = run(request(result.message.raw_norm))
    assert reparsed.message is not None
    assert (reparsed.message.raw_norm, reparsed.message.game_time_sec) == (
        result.message.raw_norm,
        result.message.game_time_sec,
    )
    assert (reparsed.message.speaker, reparsed.message.champion, reparsed.message.channel, reparsed.message.text) == (
        result.message.speaker,
        result.message.champion,
        result.message.channel,
        result.message.text,
    )


@pytest.mark.parametrize("typed_message", [False, True])
def test_legacy_top_level_metadata_moves_into_message_without_mutation(typed_message: bool) -> None:
    from copy import deepcopy

    from clean_chat.core.schemas import ChatMessage

    current = run(request("17:02 [팀] 밤하늘별 (코그모): 합류해요"))
    assert current.message is not None
    old_message = current.message.model_dump(exclude={"raw_norm", "game_time_sec"})
    payload = {
        "line_id": current.line_id,
        "message": ChatMessage.model_validate(old_message) if typed_message else old_message,
        "raw_norm": current.message.raw_norm,
        "game_time_sec": 1022,
    }
    before = deepcopy(payload)
    migrated = ParseResult.model_validate(payload)
    assert migrated == current
    assert payload == before
    assert set(migrated.model_dump()) == {"line_id", "message"}


def test_nested_metadata_takes_precedence_over_legacy_top_level_values() -> None:
    result = run(request("00:00 [팀] 밤하늘별 (코그모): 합류해요"))
    payload = result.model_dump()
    payload.update(raw_norm="이전 형식의 값", game_time_sec=1022)
    assert ParseResult.model_validate(payload) == result


def test_old_chat_message_defaults_metadata_to_none() -> None:
    from clean_chat.core.schemas import ChatMessage

    current = run(request("밤하늘별: 합류해요")).message
    assert current is not None
    old_message = current.model_dump(exclude={"raw_norm", "game_time_sec"})
    restored = ChatMessage.model_validate(old_message)
    assert restored.raw_norm is None and restored.game_time_sec is None


def test_message_metadata_reaches_session_serialization_and_report_input() -> None:
    from clean_chat.core.game import GameStateMachine, MemorySessionRepository, PostGameBatch
    from clean_chat.core.modules import ModuleSet
    from clean_chat.core.pipeline import Pipelines
    from clean_chat.core.schemas import (
        Analysis,
        AnalyzeRequest,
        GamePhase,
        GameSession,
        Level,
        PhaseEvent,
        ReportDraft,
        ReportRequest,
    )

    captured: list[ReportRequest] = []

    def analyze(req: AnalyzeRequest) -> Analysis:
        # 분류 정확도가 아니라 신고 대상으로 선택된 채팅의 전달 경로만 검증한다.
        return Analysis(msg_id=req.message.id, level=Level.L2_ABUSIVE, model_version="metadata-test")

    def report(req: ReportRequest) -> ReportDraft:
        captured.append(req)
        return ReportDraft(kind=req.kind, speaker=req.speaker, text="합성 보고서", incident_ids=["metadata-flow"])

    modules = ModuleSet({"parse": run, "analyze": analyze, "report": report})
    raw = "17:02 [팀] 밤하늘별 (코그모): 합성 채팅입니다"
    line = RawLine(id="metadata-flow", ts=1122.0, text=raw, source=Source.OCR)
    incident = Pipelines(modules).incoming.process_line(line)
    assert incident is not None

    game = GameStateMachine()
    game.handle(PhaseEvent(ts=100.0, phase=GamePhase.IN_GAME))
    assert game.record(incident)
    game.handle(PhaseEvent(ts=1200.0, phase=GamePhase.POST_GAME))
    assert game.session is not None
    repository = MemorySessionRepository()
    repository.save(game.session)
    stored = repository.load(game.session.id)
    restored = GameSession.model_validate_json(stored.model_dump_json())
    PostGameBatch(modules).run(restored)

    assert len(captured) == 1
    message = captured[0].session.incidents[0].msg
    assert (message.raw_norm, message.game_time_sec, message.ts, message.raw) == (raw, 1022, 1122.0, raw)
