"""설정값 모음. 하드코딩 대신 여기서 가져다 씁니다."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
FIXTURES = ROOT / "fixtures"

STAGE_NAMES = ("ocr", "parse", "normalize", "classify", "rewrite", "policy", "report", "complaint")


class Settings(BaseModel):
    my_name: str = "나"  # 내 소환사명 (클라이언트 설정에서 변경)
    # 모듈별로 real / mock 선택. 기본은 전부 mock → 구현이 끝난 모듈부터 real 로 바꿔 끼움
    impl: dict[str, str] = Field(default_factory=lambda: dict.fromkeys(STAGE_NAMES, "mock"))
    llm_backend: str = "none"  # rewrite/complaint 용: "local" | "api" (OPEN-04)
    store_dir: Path = ROOT / ".clean-chat"  # 처리 내역 로컬 저장 (git 제외)
    capture_interval_sec: float = 0.4


settings = Settings()
