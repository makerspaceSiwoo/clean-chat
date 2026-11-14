"""설정값 모음. 하드코딩 대신 여기서 가져다 씁니다."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
FIXTURES = ROOT / "fixtures"


class Settings(BaseModel):
    my_name: str = "나"  # 내 소환사명 (클라이언트 설정에서 변경)
    llm_backend: str = "none"  # rewrite/report 모듈용: "local" | "api" (OPEN-04)
    store_dir: Path = ROOT / ".clean-chat"  # 처리 내역 로컬 저장 (git 제외)
    sessions_dir: Path = ROOT / ".clean-chat" / "sessions"  # 게임 세션 기록 <id>.jsonl (git 제외)
    complaint_output_dir: str = (
        ".clean-chat/complaints"  # 고소장 PDF 저장 폴더. 상대 경로 → resolve_repo_path 로 풀어 씀
    )
    phase_poll_sec: float = 1.5  # 🪟 LCU 게임 단계 확인 주기 (1~2초)
    idle_grace_sec: float = 10.0  # 게임 중 '대기' 보고가 이만큼 계속돼야 게임 종료로 봄 (재접속 대비, OPEN-12)
    capture_interval_sec: float = 0.4
    server_port: int = 8765  # clean-chat serve (시뮬레이터가 부르는 로컬 모듈 실행 서버)
    uploads_dir: Path = ROOT / ".clean-chat" / "uploads"  # serve 가 받은 첨부 이미지 (git 제외)


settings = Settings()


def resolve_repo_path(path: str | Path) -> Path:
    """상대 경로는 레포 루트(ROOT) 기준으로 푼다. 실행한 폴더(CWD)와 상관없이 같은 곳에 저장되게.

    예) ".clean-chat/complaints" → <레포>/.clean-chat/complaints, 절대 경로는 그대로
    """
    p = Path(path)
    return p if p.is_absolute() else ROOT / p
