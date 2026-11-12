"""설정값 모음. 하드코딩 대신 여기서 가져다 씁니다."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
FIXTURES = ROOT / "fixtures"

STAGE_NAMES = (
    "ocr",
    "parse",
    "compose",
    "normalize",
    "classify",
    "rewrite",
    "incoming_policy",
    "outgoing_policy",
    "report",
    "complaint",
)
# Stage → 단독 실행 명령 (`uv run python -m clean_chat.<값>`). 한 모듈 폴더에 Stage 가 2개면 뒤에 하위 이름
STAGE_COMMANDS = {
    "ocr": "capture",
    "parse": "parse",
    "compose": "parse compose",
    "normalize": "normalize",
    "classify": "classify",
    "rewrite": "rewrite",
    "incoming_policy": "policy",
    "outgoing_policy": "policy outgoing",
    "report": "report",
    "complaint": "report complaint",
}


class Settings(BaseModel):
    my_name: str = "나"  # 내 소환사명 (클라이언트 설정에서 변경)
    # 모듈별로 real / mock 선택. 기본은 전부 mock → 구현이 끝난 모듈부터 real 로 바꿔 끼움
    impl: dict[str, str] = Field(default_factory=lambda: dict.fromkeys(STAGE_NAMES, "mock"))
    llm_backend: str = "none"  # rewrite/complaint 용: "local" | "api" (OPEN-04)
    store_dir: Path = ROOT / ".clean-chat"  # 처리 내역 로컬 저장 (git 제외)
    sessions_dir: Path = ROOT / ".clean-chat" / "sessions"  # 게임 세션 기록 <id>.jsonl (git 제외)
    complaint_output_dir: str = ".clean-chat/complaints"  # 고소장 PDF 저장 폴더 (레포 루트 기준 상대 경로)
    phase_poll_sec: float = 1.5  # 🪟 LCU 게임 단계 확인 주기 (1~2초)
    capture_interval_sec: float = 0.4


settings = Settings()
