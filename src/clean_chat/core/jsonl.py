"""JSONL 입출력 (통신 포맷: JSON 한 줄 = 모델 1개). fixtures·세션 저장·모듈 실행기가 같이 쓴다."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def read_jsonl(path: Path, model: type[M]) -> list[M]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            rows.append(model.model_validate_json(line))
    return rows


def write_jsonl(path: Path, items: list[BaseModel]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(i.model_dump_json() + "\n" for i in items), encoding="utf-8")
