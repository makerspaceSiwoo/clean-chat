"""설정값 모음. 하드코딩 대신 여기서 가져다 씁니다."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, MutableMapping
from contextlib import suppress
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
STORE = ROOT / ".clean-chat"
if getattr(sys, "frozen", False):
    if sys.platform == "darwin":
        STORE = Path.home() / "Library" / "Application Support" / "Clean Chat"
    else:
        STORE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Clean Chat"
DATA = ROOT / "data"
FIXTURES = ROOT / "fixtures"
USER_ENV_KEYS = ("LLM_BACKEND", "LLM_MODEL", "LLM_API_KEY", "GEMINI_API_KEY")
# LLM 설정 파일: 빌드된 앱은 레포 루트가 없으므로 사용자 데이터 폴더, 개발 중에는 레포 루트의 .env
USER_ENV = STORE / ".env" if getattr(sys, "frozen", False) else ROOT / ".env"


def read_user_env(path: Path) -> dict[str, str]:
    """.env에서 LLM 설정 키만 읽는다. 다른 줄과 빈 값은 무시한다."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return {}
    values: dict[str, str] = {}
    for line in lines:
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        key, value = key.strip(), value.split(" #", 1)[0].strip().strip("'\"")
        if sep and key in USER_ENV_KEYS and value:
            values[key] = value
    return values


def load_user_env(path: Path, environ: MutableMapping[str, str] | None = None) -> None:
    """.env의 LLM 설정을 환경 변수로 올린다. 이미 설정된 환경 변수가 우선이다."""
    environ = os.environ if environ is None else environ
    for key, value in read_user_env(path).items():
        environ.setdefault(key, value)


def current_llm_key(path: Path, environ: Mapping[str, str] | None = None) -> str:
    """지금 적용되는 Gemini API 키. 환경 변수가 있으면 파일보다 우선한다. 모델은 각 모듈이 정한다."""
    environ = os.environ if environ is None else environ
    values = read_user_env(path) | {key: environ[key] for key in USER_ENV_KEYS if environ.get(key)}
    return values.get("GEMINI_API_KEY") or values.get("LLM_API_KEY", "")


def save_llm_settings(api_key: str, path: Path, environ: MutableMapping[str, str] | None = None) -> None:
    """설정 화면에서 입력한 API 키를 .env에 쓰고 실행 중인 앱에 바로 적용한다. 모델은 rewrite·report가 정한다."""
    environ = os.environ if environ is None else environ
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("API 키를 입력하세요.")
    if any(ch.isspace() or ch in "'\"#" for ch in api_key):
        raise ValueError("API 키에는 공백, 따옴표, #을 넣을 수 없습니다.")
    values = {"LLM_BACKEND": "api", "LLM_API_KEY": api_key}
    _write_user_env(path, values)
    environ.update(values)
    environ["GEMINI_API_KEY"] = api_key  # rewrite는 GEMINI_API_KEY를 먼저 본다


def clear_llm_settings(path: Path, environ: MutableMapping[str, str] | None = None) -> None:
    """.env와 실행 중인 앱에서 LLM 설정을 지운다. 이후에는 로컬 규칙만 쓴다."""
    environ = os.environ if environ is None else environ
    _write_user_env(path, {})
    for key in USER_ENV_KEYS:
        environ.pop(key, None)


def _write_user_env(path: Path, values: dict[str, str]) -> None:
    """LLM 키 줄만 바꾸고 다른 줄은 그대로 둔다. 본인 계정만 읽을 수 있게 저장한다."""
    try:
        old = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        old = []
    keep = [line for line in old if line.strip().removeprefix("export ").partition("=")[0].strip() not in USER_ENV_KEYS]
    lines = keep + [f"{key}={value}" for key, value in values.items()]
    if not any(line.strip() for line in lines):
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    os.replace(temp, path)
    with suppress(OSError):
        os.chmod(path, 0o600)


if getattr(sys, "frozen", False):
    load_user_env(USER_ENV)


class Settings(BaseModel):
    my_name: str = "나"  # 내 소환사명 (클라이언트 설정에서 변경)
    filter_strength: Literal["low", "normal", "high"] = "normal"
    llm_backend: str = "none"  # rewrite/report 모듈용: "local" | "api" (OPEN-04)
    store_dir: Path = STORE  # 처리 내역 로컬 저장 (git 제외)
    sessions_dir: Path = STORE / "sessions"  # 게임 세션 기록 <id>.jsonl (git 제외)
    complaint_output_dir: str = str(STORE / "complaints") if getattr(sys, "frozen", False) else ".clean-chat/complaints"
    phase_poll_sec: float = 1.5  # 🪟 LCU 게임 단계 확인 주기 (1~2초)
    idle_grace_sec: float = 10.0  # 게임 중 '대기' 보고가 이만큼 계속돼야 게임 종료로 봄 (재접속 대비, OPEN-12)
    capture_interval_sec: float = 0.4  # 고정 주기 비교 기준
    uploads_dir: Path = STORE / "uploads"  # 시뮬레이터에 첨부한 이미지 (git 제외)
    llm_env: Path = USER_ENV  # 설정 화면에서 입력한 Gemini API 키를 저장하는 .env
    sim_timeout_sec: float = 120.0  # 시뮬레이터에서 모듈 1번 실행 제한 시간 (모델 로딩 포함)


settings = Settings()


def resolve_repo_path(path: str | Path) -> Path:
    """상대 경로는 레포 루트(ROOT) 기준으로 푼다. 실행한 폴더(CWD)와 상관없이 같은 곳에 저장되게.

    예) ".clean-chat/complaints" → <레포>/.clean-chat/complaints, 절대 경로는 그대로
    """
    p = Path(path)
    return p if p.is_absolute() else ROOT / p
