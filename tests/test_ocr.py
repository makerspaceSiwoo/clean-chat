"""① ocr 모듈 (담당자 소유). AI 모듈이라 출력 형식만 자동 검사하고, 정확도는 실측으로 본다."""

from pathlib import Path

import pytest

from clean_chat.core.config import FIXTURES
from clean_chat.core.schemas import Frame, Region, Source
from clean_chat.modules.ocr import impl
from helpers import check_module


def test_fast_path_uses_original_size_and_exactly_one_ocr_call(frame, monkeypatch):
    """작은 컬러 글자·반복 자모도 분석/재시도 없이 이미지 전체를 한 번 전달한다."""
    from PIL import Image, ImageDraw

    with Image.new("RGB", (400, 160), "black") as image:
        ImageDraw.Draw(image).rectangle((10, 10, 150, 20), fill=(50, 200, 80))
        image.save(frame.image_path)
    calls = []

    class Engine:
        def read(self, image):
            calls.append((image.size, image.mode))
            return [("ㅋㅋㅋㅋ ㅗㅗㅗ ㅅㅂ", None)]

    monkeypatch.setattr(impl, "_get_engine", Engine)
    result = impl.run(frame)
    assert calls == [((400, 160), "RGB")]
    assert result.lines[0].text == "ㅋㅋㅋㅋ ㅗㅗㅗ ㅅㅂ"


def test_fast_preprocess_only_shrinks_oversized_input():
    Image = pytest.importorskip("PIL.Image")

    with Image.new("RGB", (3000, 600)) as image, impl._preprocess(image) as processed:
        assert processed.size == (2600, 520)


def test_ocr_fixtures():
    if not (FIXTURES / "ocr" / "images" / "sample_01.png").exists():
        pytest.skip("OCR 테스트 이미지 없음 (fixtures/ocr/images/README.md)")
    check_module("ocr", strict=False)


@pytest.fixture
def frame(tmp_path):
    """실제 사용자 정보 없는 합성 이미지. 화면 좌표로 다시 자르면 안 된다."""
    image_module = pytest.importorskip("PIL.Image")
    path = tmp_path / "chat.png"
    with image_module.new("RGB", (400, 160), "black") as image:
        image.save(path)
    return Frame(id="F-test", ts=1762920000, image_path=str(path), region=Region(x=0, y=600, w=400, h=160))


def test_run_preserves_order_system_lines_and_duplicates(frame, monkeypatch):
    """실제 이미지 처리부터 계약 변환까지 실행하고 OCR 인식 결과만 고정한다."""
    observed = []

    def read(image):
        observed.append((image.mode, image.size))
        return [
            ("[팀] 테스트 (가렌): 야 정글", 0.9),
            ("용 먼저 가자", 0.8),
            ("테스트 (리신)님이 신호를 보냈습니다", 0.7),
            ("[팀] 테스트 (가렌): 화이팅", None),
        ]

    monkeypatch.setattr(impl, "_read_lines", read)
    first, second = impl.run(frame), impl.run(frame)
    assert observed == [("RGB", (400, 160)), ("RGB", (400, 160))]
    assert first.frame_id == frame.id
    assert [line.text for line in first.lines] == [
        "[팀] 테스트 (가렌): 야 정글 용 먼저 가자",
        "테스트 (리신)님이 신호를 보냈습니다",
        "[팀] 테스트 (가렌): 화이팅",
    ]
    assert [line.ocr_confidence for line in first.lines] == [0.8, 0.7, None]
    assert all(line.ts == frame.ts and line.source == Source.OCR for line in first.lines)
    assert [line.text for line in first.lines] == [line.text for line in second.lines]
    assert len({line.id for line in first.lines + second.lines}) == 6


def test_empty_result(frame, monkeypatch):
    monkeypatch.setattr(impl, "_read_lines", lambda image: [("  ", None)])
    assert impl.run(frame).lines == []


@pytest.mark.parametrize(
    "failure, error_type",
    [("missing", FileNotFoundError), ("corrupt", None), ("engine", RuntimeError), ("preprocess", RuntimeError)],
)
def test_failure_returns_empty_result_and_logs_cause(frame, monkeypatch, caplog, failure, error_type):
    """파일·전처리·엔진 실패는 원인을 기록하고 다음 프레임 처리를 막지 않는다."""
    import logging

    from PIL import UnidentifiedImageError

    if failure == "missing":
        frame.image_path += ".missing"
    elif failure == "corrupt":
        Path(frame.image_path).write_bytes(b"invalid png")
        error_type = UnidentifiedImageError
    else:

        def fail(image):
            raise RuntimeError("OCR unavailable")

        target = "_read_lines" if failure == "engine" else "_preprocess"
        monkeypatch.setattr(impl, target, fail)

    with caplog.at_level(logging.ERROR, logger=impl.__name__):
        result = impl.run(frame)
    assert result.frame_id == frame.id
    assert result.lines == []
    record = next(record for record in caplog.records if record.name == impl.__name__)
    assert frame.id in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[0] is error_type

    monkeypatch.setattr(impl, "_load_image", lambda path: FakeImage())
    monkeypatch.setattr(impl, "_preprocess", lambda image: FakeImage())
    monkeypatch.setattr(impl, "_read_lines", lambda image: [("다음 프레임", 0.9)])
    assert impl.run(frame).lines[0].text == "다음 프레임"


class FakeImage:
    def close(self):
        pass


def test_merge_keeps_messages_and_unknown_confidence():
    lines = [
        ("단독 줄", 0.9),
        ("다른 단독 줄", 0.8),
        ("[팀] 테스트: 첫 줄", None),
        ("둘째 줄", 0.9),
        ("[전체] 다른 사람: 새 메시지", 0.8),
    ]
    assert impl._merge_wrapped_lines(lines) == [
        ("단독 줄", 0.9),
        ("다른 단독 줄", 0.8),
        ("[팀] 테스트: 첫 줄 둘째 줄", None),
        ("[전체] 다른 사람: 새 메시지", 0.8),
    ]


def test_layout_groups_fragments_and_sorts_rows():
    """닉네임·본문을 같은 행에 묶고 행 순서를 유지한다."""
    from clean_chat.modules.ocr.layout import group_rows

    results = [
        ([[80, 10], [150, 10], [150, 30], [80, 30]], "안녕하세요", 0.8),
        ([[0, 50], [100, 50], [100, 70], [0, 70]], "다음 줄", 0.9),
        ([[0, 10], [70, 10], [70, 30], [0, 30]], "[팀] 테스트:", 0.95),
    ]
    assert group_rows(results) == [("[팀] 테스트: 안녕하세요", 0.8), ("다음 줄", 0.9)]


@pytest.fixture
def jamo_font_path():
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    path = Path("C:/Windows/Fonts/malgun.ttf")
    if not path.exists():
        pytest.skip("반복 자모 기준 글꼴 없음")
    return path


@pytest.mark.parametrize("size", [14, 24, 40])
@pytest.mark.parametrize("background,foreground", [("black", "white"), ("white", "black")])
@pytest.mark.parametrize("text", ["ㅋㅋㅋㅋ", "ㅎㅎㅎㅎ", "ㅗㅗㅗㅗ"])
def test_repeated_jamo_pixels(jamo_font_path, size, background, foreground, text):
    """글자 크기·배경·자모를 바꿔도 실제 보이는 글자 수만 복원한다."""
    from PIL import Image, ImageDraw, ImageFont

    from clean_chat.modules.ocr.repeats import find_repeat_rows

    with Image.new("RGB", (500, 120), background) as image:
        font = ImageFont.truetype(str(jamo_font_path), size)
        ImageDraw.Draw(image).text((30, 20), text, font=font, fill=foreground)
        processed = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        try:
            spans = [span.text for row in find_repeat_rows(processed) for span in row.spans]
            assert spans == [text]
        finally:
            processed.close()


@pytest.mark.parametrize(
    "text",
    [
        "1111",
        "7777",
        "ㄱㄱㄱㄱ",
        "ㅌㅌㅌㅌ",
        "ㅍㅍㅍㅍ",
        "----",
        "====",
        "ㅠㅠㅠㅠ",
        "ㅋㅋ",
        "안녕하세요",
        "크크크크",
        "하하하하",
        "ㅋ ㅋ ㅋ",
        "ㅎ ㅎ ㅎ",
        "ㅗ ㅗ ㅗ",
        "ㅜㅜㅜㅜ",
        "ㅛㅛㅛㅛ",
        "TTTT",
        "++++",
    ],
)
def test_other_repetitions_are_not_rewritten(jamo_font_path, text):
    """비슷한 획·단어·짧은 자모를 웃음 표현으로 임의 치환하지 않는다."""
    from PIL import Image, ImageDraw, ImageFont

    from clean_chat.modules.ocr.repeats import find_repeat_rows

    with Image.new("RGB", (500, 120), "black") as image:
        ImageDraw.Draw(image).text((30, 20), text, font=ImageFont.truetype(str(jamo_font_path), 24), fill="white")
        processed = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        try:
            assert not any(row.spans for row in find_repeat_rows(processed))
        finally:
            processed.close()


def test_output_alphabet_keeps_jamo_english_and_marks_unknown():
    from clean_chat.modules.ocr.alphabet import restrict

    assert restrict("한글 English 123 ㅋㅋㅎㅎㅗㅗ [팀]:!? ₩") == "한글 English 123 ㅋㅋㅎㅎㅗㅗ [팀]:!? ₩"
    assert restrict("안녕碧신 丁 刁 合 あ ア β ß") == "안녕�신 � � � � � � �"


def test_retry_requires_preserved_content():
    from clean_chat.modules.ocr.alphabet import prefer_retry

    assert prefer_retry("안녕碧신", "안녕병신")
    assert not prefer_retry("안녕碧신", "안녕신")
    assert not prefer_retry("안녕碧신", "안녕하세요")
    assert not prefer_retry("안녕 Hello", "안녕 Helo")


def test_damaged_next_header_is_not_merged():
    lines = [("[팀] 테스트: 첫 문장", None), ("[71111 테스트 (가렌 ㅋㅋㅋㅋ", None)]
    assert impl._merge_wrapped_lines(lines) == lines


def test_benchmark_metrics_preserve_jamo_counts_and_spatial_context():
    from clean_chat.modules.ocr.benchmark import compare

    exact = compare("테스트: ㅅㅂ ㅋㅋㅋㅋ ㅗㅗ", "테스트: ㅅㅂ ㅋㅋㅋㅋ ㅗㅗ")
    assert exact == {
        "edits": 0,
        "characters": 15,
        "jamo_total": 3,
        "jamo_correct": 3,
        "abuse_total": 2,
        "abuse_correct": 2,
    }
    missing = compare("테스트: ㅅㅂ ㅋㅋㅋㅋ ㅗㅗ", "테스트: ㅅㅂ ㅋㅋㅋ ㅗ")
    assert missing["edits"] == 2
    assert missing["jamo_correct"] == 1
    assert missing["abuse_correct"] == 1
    assert compare("ㅅㅂ", "ㅅㅂㅂ")["abuse_correct"] == 0
    assert compare("가", "가")["edits"] == 0


def test_rapid_candidate_config_cache_and_bgr(monkeypatch, capsys):
    import sys
    from types import SimpleNamespace

    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("numpy")
    from clean_chat.modules.ocr.rapid import RapidOcr

    configs = []

    class Reader:
        def __init__(self, params):
            configs.append(params)

        def __call__(self, image):
            assert image[0, 0].tolist() == [0, 0, 255]
            return SimpleNamespace(
                boxes=[[[0, 0], [10, 0], [10, 10], [0, 10]]], txts=["ㅅㅂ"], scores=[0.9], elapse=0.1234
            )

    enums = SimpleNamespace(ONNXRUNTIME="onnxruntime", PPOCRV5="PP-OCRv5", MOBILE="mobile", KOREAN="korean")
    monkeypatch.setitem(
        sys.modules,
        "rapidocr",
        SimpleNamespace(EngineType=enums, LangRec=enums, ModelType=enums, OCRVersion=enums, RapidOCR=Reader),
    )
    engine = RapidOcr()
    with Image.new("RGB", (20, 20), "red") as image:
        assert engine.read(image) == [("ㅅㅂ", 0.9)]
    assert configs[0]["Rec.lang_type"] == "korean"
    assert configs[0]["Rec.ocr_version"] == "PP-OCRv5"
    assert configs[0]["Global.log_level"] == "error"
    assert capsys.readouterr().out == "OCR 응답시간: 0.123초\n"
    assert ".clean-chat" in Path(configs[0]["Global.model_root_dir"]).parts


def test_default_rapid_engine_is_cached_without_windows_dependency(monkeypatch):
    from clean_chat.modules.ocr import rapid

    class Engine:
        pass

    monkeypatch.delenv("CLEAN_CHAT_OCR_ENGINE", raising=False)
    monkeypatch.setattr(rapid, "RapidOcr", Engine)
    impl._get_engine.cache_clear()
    try:
        first = impl._get_engine()
        assert isinstance(first, Engine)
        assert impl._get_engine() is first
    finally:
        impl._get_engine.cache_clear()


@pytest.mark.parametrize("text", ["ㅋㅋㅋㅋㅋㅋ", "ㅎㅎㅎㅎㅎㅎ", "ㅗㅗㅗㅗㅗㅗ"])
def test_compressed_stretched_repetitions(jamo_font_path, text):
    """UI 글꼴과 종횡비가 다른 작은 JPEG 글자도 묶음 근거로 검증한다."""
    import io

    from PIL import Image, ImageDraw, ImageFont

    from clean_chat.modules.ocr.repeats import find_repeat_rows

    with Image.new("RGB", (300, 65), (20, 30, 15)) as image:
        ImageDraw.Draw(image).text(
            (20, 12), text, font=ImageFont.truetype(str(jamo_font_path), 14), fill=(220, 220, 210)
        )
        with image.resize((300, 90), Image.Resampling.BICUBIC) as stretched:
            buffer = io.BytesIO()
            stretched.save(buffer, format="JPEG", quality=75)
            buffer.seek(0)
            with Image.open(buffer) as jpeg:
                processed = jpeg.convert("RGB").resize((jpeg.width * 4, jpeg.height * 4), Image.Resampling.LANCZOS)
                try:
                    assert [span.text for row in find_repeat_rows(processed) for span in row.spans] == [text]
                finally:
                    processed.close()


def test_in_memory_frame_is_read_without_touching_disk(monkeypatch):
    """앱의 실시간 캡처는 파일을 만들지 않고 Frame.image(메모리)로 넘긴다."""
    pytest.importorskip("PIL")
    from PIL import Image

    from clean_chat.modules.ocr import impl

    seen = []
    monkeypatch.setattr(impl, "_load_image", lambda path: pytest.fail(f"디스크에서 읽으려 함: {path!r}"))
    monkeypatch.setattr(impl, "_read_lines", lambda image: seen.append(image.size) or [])
    with Image.new("RGB", (320, 90), "black") as image:
        frame = Frame(id="F-mem", ts=0, image_path="", region=Region(x=0, y=0, w=320, h=90), image=image)
        assert impl.run(frame).lines == []
        assert seen == [(320, 90)]
        assert image.getpixel((0, 0)) == (0, 0, 0)  # 넘겨받은 이미지는 닫지 않는다 (복사본만 닫는다)
    assert "image" not in Frame.model_json_schema()["properties"]  # 주고받는 JSON 형식은 그대로
