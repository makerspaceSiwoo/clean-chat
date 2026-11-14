"""① ocr — 채팅창 이미지 → 읽은 줄 전부  (명세: docs/MODULES.md#ocr, 예시: fixtures/ocr/)

Mac 에서도 스크린샷 파일로 개발·테스트할 수 있다. 화면 캡처 자체와 프레임 사이 중복 제거는 구성(core)이 한다.
OCR 엔진 선택은 OPEN-03. 엔진 로딩처럼 무거운 준비는 functools.cache 로 한 번만 한다.
"""

from __future__ import annotations

from clean_chat.core.schemas import Frame, OcrResult, RawLine


def run(frame: Frame) -> OcrResult:
    """채팅창 이미지 1장 → 보이는 채팅 줄 전부 (위에서 아래 순서).

    입력: Frame(id, ts, image_path, region) → 출력: OcrResult(frame_id, lines=RawLine[])
    예) sample_01.png → ["[팀] 탑솔장인 (가렌): 다들 화이팅", "정글러 (리신)님이 ... 신호를 보냈습니다", ...]
    순서: _load_image → _preprocess → _read_lines → _merge_wrapped_lines → _to_raw_lines
    주의: 프레임당 0.5초 이내. 읽을 줄이 없으면 빈 lines. 오버레이가 찍히면 안 됨(ADR-0003).
          앞 프레임과 겹치는 줄도 그대로 돌려준다(중복 제거는 구성 몫).
    관련: ADR-0002, OPEN-02, OPEN-03, OPEN-06
    """
    raise NotImplementedError("ocr 담당: run")


def _load_image(path: str) -> object:
    """PNG 경로 → 이미지 객체 (Pillow 또는 numpy 배열)."""
    raise NotImplementedError


def _preprocess(image: object) -> object:
    """OCR 이 잘 읽도록: 2~3배 확대, 흑백, 대비 강화, 채팅 글자 색만 남기기(롤 채팅 색 설정과 함께 조정, OPEN-06)."""
    raise NotImplementedError


def _read_lines(image: object) -> list[tuple[str, float]]:
    """OCR 엔진 실행 → [(줄 텍스트, 신뢰도 0~1), ...]. 엔진("windows" | "paddle" | "easyocr")은 OPEN-03."""
    raise NotImplementedError


def _merge_wrapped_lines(lines: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """긴 채팅이 두 줄로 꺾여 보이면 한 줄로 합친다. 예) "[팀] 원딜러 (징크스): 야 정글" + "ㅂㅅ아 용 먼저 치라고"."""
    raise NotImplementedError


def _to_raw_lines(frame: Frame, lines: list[tuple[str, float]]) -> list[RawLine]:
    """(텍스트, 신뢰도) → RawLine(id, ts=frame.ts, text, source=ocr, ocr_confidence). id 는 앱 실행 중 유일하게."""
    raise NotImplementedError
