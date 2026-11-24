"""① ocr 모듈 (담당자 소유). AI 모듈이라 출력 형식만 자동 검사하고, 정확도는 실측으로 본다."""

import sys
import time
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
    from PIL import Image

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


def test_load_failure_is_not_empty_result(frame):
    frame.image_path += ".missing"
    with pytest.raises(FileNotFoundError):
        impl.run(frame)


def test_corrupt_image_is_reported(frame):
    from PIL import UnidentifiedImageError

    Path(frame.image_path).write_bytes(b"invalid png")
    with pytest.raises(UnidentifiedImageError):
        impl.run(frame)


def test_engine_failure_is_reported(frame, monkeypatch):
    def fail(image):
        raise RuntimeError("OCR unavailable")

    monkeypatch.setattr(impl, "_read_lines", fail)
    with pytest.raises(RuntimeError, match="OCR unavailable"):
        impl.run(frame)


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


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows 내장 OCR 실측")
def test_windows_ocr_real_image(frame):
    """합성 한국어 이미지를 실제 엔진으로 두 번 읽어 초기 로딩·반복 처리까지 확인한다."""
    from PIL import Image, ImageDraw, ImageFont

    from clean_chat.modules.ocr.windows import WindowsOcr

    font_path = Path("C:/Windows/Fonts/malgun.ttf")
    if not font_path.exists():
        pytest.skip("합성 이미지용 맑은 고딕 없음")
    with Image.new("RGB", (700, 150), "black") as image:
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(font_path), 26)
        draw.text((12, 10), "안녕하세요 테스트 채팅입니다", fill="white", font=font)
        draw.text((12, 75), "다음 문장도 잘 읽어 주세요", fill="white", font=font)
        image.save(frame.image_path)
    engine = WindowsOcr()
    try:
        image = impl._load_image(frame.image_path)
        processed = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        try:
            for _ in range(2):
                started = time.perf_counter()
                lines = engine.read(processed)
                elapsed = time.perf_counter() - started
                assert len(lines) == 2
                assert "안녕하세요" in lines[0][0]
                assert "다음" in lines[1][0]
                assert all(confidence is None for _, confidence in lines)
                print(f"Windows OCR elapsed: {elapsed:.3f}s")
        finally:
            processed.close()
            image.close()
        with Image.new("L", (100, 100), "white") as blank:
            assert engine.read(blank) == []
    finally:
        engine.close()


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
