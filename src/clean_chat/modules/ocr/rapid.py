"""기본 OCR: RapidOCR + PP-OCRv5 한국어 mobile, CPU ONNX Runtime."""

from pathlib import Path
from threading import Lock


class RapidOcr:
    """최초 추론 시 모델을 Git 제외 캐시에 자동 다운로드한다."""

    def __init__(self) -> None:
        from rapidocr import EngineType, LangRec, ModelType, OCRVersion, RapidOCR

        root = Path(__file__).resolve().parents[4] / ".clean-chat" / "rapidocr"
        self._reader = RapidOCR(
            params={
                "Global.model_root_dir": str(root),
                "Global.log_level": "error",
                "Global.use_cls": False,
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.ocr_version": OCRVersion.PPOCRV5,
                "Det.model_type": ModelType.MOBILE,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.lang_type": LangRec.KOREAN,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
                "EngineConfig.onnxruntime.intra_op_num_threads": 4,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            }
        )
        self._lock = Lock()

    def read(self, image: object) -> list[tuple[str, float]]:
        """Pillow RGB → BGR. 행 조각을 왼쪽부터 합쳐 반환한다."""
        import numpy as np

        with self._lock:
            result = self._reader(np.asarray(image.convert("RGB"))[:, :, ::-1].copy())
        # SDK의 검출·인식 시간 합계만 사용한다. 다운로드·모델 로딩·락 대기는 제외된다.
        print(f"OCR 응답시간: {result.elapse:.3f}초", flush=True)
        if result.txts is None:
            return []
        from .layout import group_rows

        return group_rows(list(zip(result.boxes, result.txts, result.scores, strict=True)))
