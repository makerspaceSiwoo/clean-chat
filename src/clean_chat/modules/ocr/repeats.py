"""반복 자모의 픽셀 기반 보조 인식. 텍스트 치환이나 단어 추측을 하지 않는다."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

_TARGETS = "ㅋㅎㅗ"
# 비슷한 획도 함께 비교해 모양이 모호하면 보정을 포기한다.
_CHARACTERS = _TARGETS + "ㄱㄴㄷㄹㅌㅍㅁㅅㅇㅜㅠㅛ크키카하허호히12379TIltFHE-="


@dataclass(frozen=True)
class RepeatSpan:
    left: int
    right: int
    text: str


@dataclass(frozen=True)
class TextRow:
    top: int
    bottom: int
    spans: tuple[RepeatSpan, ...]


def _segments(active: object) -> list[tuple[int, int]]:
    """참인 구간을 반열림 좌표로 반환한다."""
    import numpy as np

    edges = np.diff(np.pad(np.asarray(active, dtype=np.int8), (1, 1)))
    return [
        (int(start), int(end))
        for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True)
    ]


def _normalise(mask: object) -> tuple[object, float] | None:
    """글자 외곽을 자르고 같은 격자로 맞춘다. 종횡비는 별도로 보존한다."""
    import numpy as np
    from PIL import Image

    ys, xs = np.nonzero(mask)
    if len(xs) < 4:
        return None
    cropped = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    height, width = cropped.shape
    with (
        Image.fromarray(cropped.astype(np.uint8) * 255) as image,
        image.resize((32, 32), Image.Resampling.LANCZOS) as resized,
    ):
        return np.asarray(resized) >= 128, width / height


@cache
def _templates() -> tuple:
    """설치된 Windows 한글 글꼴로 기준 획을 만든다. 글꼴이 없으면 보조 인식을 끈다."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    templates = []
    for filename in ("malgun.ttf", "malgunbd.ttf", "gulim.ttc"):
        path = Path("C:/Windows/Fonts") / filename
        if not path.exists():
            continue
        for size in (14, 24, 40):
            font = ImageFont.truetype(str(path), size)
            for char in _CHARACTERS:
                with Image.new("L", (96, 96), 0) as image:
                    ImageDraw.Draw(image).text((8, 4), char, font=font, fill=255)
                    normalised = _normalise(np.asarray(image) >= 128)
                    if normalised is not None:
                        shape, ratio = normalised
                        templates.append((char, shape, ratio))
    return tuple(templates)


def _k_strokes(shape: object) -> bool:
    """ㅋ의 두 가로획·오른쪽 세로획을 확인한다. ㄱ·=·F·ㅍ과 구별한다."""
    bars = _segments(shape.mean(axis=1) >= 0.65)
    return (
        len(bars) == 2
        and bars[0][0] <= 3
        and 10 <= bars[1][0] <= 22
        and float(shape[:, 26:].mean()) >= 0.5
        and float(shape[:, :6].mean()) <= 0.4
    )


def _classify(mask: object, templates: tuple) -> tuple[str, float, float, bool] | None:
    """획 후보와 모양 점수·혼동 문자 대비 차이를 반환한다. 확정은 반복 묶음에서 한다."""
    import numpy as np

    normalised = _normalise(mask)
    if normalised is None:
        return None
    shape, ratio = normalised
    scores: dict[str, float] = {}
    for char, reference, reference_ratio in templates:
        # 게임 글꼴의 자모는 UI 글꼴보다 세로로 길다. 묶음 검증 전 후보 단계에서는 이 차이를 허용한다.
        if abs(ratio / reference_ratio - 1) > 0.5:
            continue
        dice = float(2 * np.count_nonzero(shape & reference) / (shape.sum() + reference.sum()))
        scores[char] = max(scores.get(char, 0), dice)
    if not scores:
        return None
    best = max(_TARGETS, key=lambda char: scores.get(char, 0))
    competitor = max((score for char, score in scores.items() if char != best), default=0)
    score = scores.get(best, 0)
    margin = score - competitor
    if score >= 0.74 and margin >= -0.02:
        return best, score, margin, best == "ㅋ" and _k_strokes(shape)
    return None


def find_repeat_rows(image: object) -> list[TextRow]:
    """같은 자모가 비슷한 크기·간격으로 3개 이상 보이는 구간만 찾는다."""
    import numpy as np

    templates = _templates()
    if not templates:
        return []
    pixels = np.asarray(image.convert("RGB"), dtype=float)
    border = np.concatenate((pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]))
    background = np.median(border, axis=0)
    contrast = np.abs(pixels - background).max(axis=2)
    threshold = max(45.0, float(np.percentile(contrast, 99)) * 0.5)
    mask = contrast >= threshold
    bands: list[list[int]] = []
    for top, bottom in _segments(mask.any(axis=1)):
        # ㅎ의 점·가로획·원처럼 서로 떨어진 획도 같은 글자 높이 안에서 묶는다.
        if bands and top - bands[-1][1] <= 16:
            bands[-1][1] = bottom
        else:
            bands.append([top, bottom])
    if image.info.get("ocr_rows"):
        bands = image.info["ocr_rows"]
    rows = []
    for top, bottom in bands:
        row = mask[top:bottom]
        glyphs = _segments(row.any(axis=0))
        spans = []
        group: list[tuple[int, int, float, float, bool]] = []
        previous_char = None

        for left, right in glyphs:
            candidate = _classify(row[:, left:right], templates)
            char = candidate[0] if candidate else None
            # 간격 허용치(글자 폭 대비). 띄어쓰기 한 칸이 글자 폭의 약 0.9 라서 그보다 작아야 "ㅋ ㅋ ㅋ" 를 묶지 않는다.
            compatible = (
                group
                and char == previous_char
                and left - group[-1][1]
                <= (group[-1][1] - group[-1][0]) * {"ㅋ": 0.75, "ㅎ": 0.65, "ㅗ": 0.5}.get(char, 0)
                and 0.8 <= (right - left) / (group[-1][1] - group[-1][0]) <= 1.25
            )
            if not compatible:
                _append_repeat(spans, group, previous_char)
                group = []
            if char:
                group.append((left, right, candidate[1], candidate[2], candidate[3]))
            previous_char = char
        _append_repeat(spans, group, previous_char)
        if image.info.get("ocr_rows"):
            rows.append(TextRow(top, bottom, tuple(spans)))
        else:
            rows.append(TextRow(max(0, top - 2), min(image.height, bottom + 2), tuple(spans)))
    return rows


def _append_repeat(spans: list[RepeatSpan], group: list[tuple[int, int, float, float, bool]], char: str | None) -> None:
    """개별 획이 흐려도 묶음의 모양·간격·혼동 문자 대비 근거가 충분해야 확정한다."""
    from statistics import mean

    if len(group) < 3 or char is None:
        return
    pitches = [group[index][0] - group[index - 1][0] for index in range(1, len(group))]
    regular = max(pitches) / min(pitches) <= 1.2
    clear_structure = char == "ㅋ" and len(group) >= 5 and all(item[4] for item in group)
    minimum_score = 0.78 if len(group) >= 5 else 0.80
    if (
        regular
        and mean(item[2] for item in group) >= minimum_score
        and (mean(item[3] for item in group) >= 0.07 or clear_structure)
    ):
        spans.append(RepeatSpan(group[0][0], group[-1][1], char * len(group)))
