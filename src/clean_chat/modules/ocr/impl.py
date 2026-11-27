"""① ocr — 채팅창 이미지 → 읽은 줄 전부  (명세: docs/MODULES.md#ocr, 예시: fixtures/ocr/)

Mac 에서도 스크린샷 파일로 개발·테스트할 수 있다. 화면 캡처 자체와 프레임 사이 중복 제거는 구성(core)이 한다.
현재 구현은 한국어 Windows 내장 OCR을 사용한다. 엔진 준비는 functools.cache 로 한 번만 한다.
"""

from __future__ import annotations

import re
from functools import cache
from uuid import uuid4

from clean_chat.core.schemas import Frame, OcrResult, RawLine, Source

_MESSAGE_START = re.compile(r"^(?:\[[^\]]+\]|(?:\d{1,2}:\d{2}\s+)?[^:：\n]{1,80}[:：])")
_SYSTEM_LINE = re.compile(r"(?:님이|님께서|신호를|처치|접속|연결|항복|일시 정지|게임이|재개)")


def run(frame: Frame) -> OcrResult:
    """채팅창 이미지 1장 → 보이는 채팅 줄 전부 (위에서 아래 순서).

    입력: Frame(id, ts, image_path, region) → 출력: OcrResult(frame_id, lines=RawLine[])
    예) sample_01.png → ["[팀] 밤하늘별 (가렌): 다들 화이팅", "초코우유 (리신)님이 ... 신호를 보냈습니다", ...]
    순서: _load_image → _preprocess → _read_lines → _merge_wrapped_lines → _to_raw_lines
    주의: 프레임당 0.5초 이내 목표(최초 엔진 로딩 별도, 실제 게임 화면 실측 필요).
          읽을 줄이 없으면 빈 lines. 오버레이가 찍히면 안 됨(ADR-0003).
          앞 프레임과 겹치는 줄도 그대로 돌려준다(중복 제거는 구성 몫).
    관련: ADR-0002, OPEN-02, OPEN-03, OPEN-06
    """
    # image_path는 이미 채팅창 영역이다. 화면 좌표인 region으로 다시 자르지 않는다.
    image = _load_image(frame.image_path)
    try:
        processed = _preprocess(image)
        try:
            lines = _read_lines(processed)
        finally:
            processed.close()
    finally:
        image.close()
    return OcrResult(frame_id=frame.id, lines=_to_raw_lines(frame, _merge_wrapped_lines(lines)))


def _load_image(path: str) -> object:
    """PNG 경로 → 이미지 객체 (Pillow 또는 numpy 배열)."""
    from PIL import Image, ImageOps

    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _preprocess(image: object) -> object:
    """확대/행 분석 없이 원본을 유지한다. 매우 큰 입력만 엔진 제한 내로 줄인다."""
    from PIL import Image

    processed = image.copy()
    if max(processed.size) > 2600:
        processed.thumbnail((2600, 2600), Image.Resampling.BILINEAR)
    return processed


@cache
def _get_engine() -> object:
    """한국어 Windows OCR 프로세스는 최초 사용 시 한 번 준비한다."""
    from clean_chat.core.platform import require_windows

    require_windows("Windows 내장 OCR")
    from .windows import WindowsOcr

    return WindowsOcr()


def _read_lines(image: object) -> list[tuple[str, float | None]]:
    """채팅 이미지 전체를 단 한 번 인식한다. 재시도나 반복 자모 보조 분석은 하지 않는다."""
    return _get_engine().read(image)


def _merge_wrapped_lines(lines: list[tuple[str, float | None]]) -> list[tuple[str, float | None]]:
    """긴 채팅이 두 줄로 꺾여 보이면 한 줄로 합친다. 예) "[팀] 원딜러 (징크스): 야 정글" + "ㅂㅅ아 용 먼저 치라고"."""
    # 좌표 없는 텍스트만으로는 완전한 판별이 어렵다. 화자가 있는 채팅 뒤에서만 합친다.
    merged: list[tuple[str, float | None]] = []
    in_chat = False
    for text, confidence in lines:
        text = text.strip()
        if not text:
            continue
        starts_message = bool(_MESSAGE_START.match(text))
        suspected_header = bool(re.search(r"[\[\]()）]", text[:80]))
        system = bool(_SYSTEM_LINE.search(text)) and not starts_message
        if merged and in_chat and not starts_message and not suspected_header and not system:
            previous, previous_confidence = merged[-1]
            combined = (
                min(previous_confidence, confidence)
                if previous_confidence is not None and confidence is not None
                else None
            )
            merged[-1] = (f"{previous} {text}", combined)
        else:
            merged.append((text, confidence))
            in_chat = starts_message and (":" in text or "：" in text) and not system
    return merged


def _to_raw_lines(frame: Frame, lines: list[tuple[str, float | None]]) -> list[RawLine]:
    """(텍스트, 신뢰도) → RawLine(id, ts=frame.ts, text, source=ocr, ocr_confidence). id 는 앱 실행 중 유일하게."""
    from .alphabet import restrict

    return [
        RawLine(id=f"ocr-{uuid4().hex}", ts=frame.ts, text=restrict(text), source=Source.OCR, ocr_confidence=confidence)
        for text, confidence in lines
    ]
