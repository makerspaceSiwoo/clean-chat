"""모든 처리 모듈의 공통 틀: Stage[입력 모델 → 출력 모델].

웹 비유: Stage = 요청 스키마와 응답 스키마가 정해진 API 엔드포인트 하나.
- 실제 구현(impl.py)과 목 구현(MockStage)이 같은 인터페이스를 가지므로,
  파이프라인은 모듈별로 'real' / 'mock'을 골라 끼울 수 있다.
- 통신 포맷: 입력과 출력 모두 pydantic 모델 → JSON 한 줄(JSONL)로 저장하거나 전달.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel

from clean_chat.core.config import FIXTURES

In = TypeVar("In", bound=BaseModel)
Out = TypeVar("Out", bound=BaseModel)


class Stage(ABC, Generic[In, Out]):
    """모듈 인터페이스. 각 모듈의 stage.py 에서 상속해 name/모델/mock_default 를 정한다."""

    name: ClassVar[str]  # fixtures/<name>/ 폴더 이름과 같음
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]
    windows_only: ClassVar[bool] = False

    def setup(self) -> None:  # noqa: B027  (모델 로딩 등 무거운 준비. 앱 시작 시 1번)
        pass

    @abstractmethod
    def run(self, item: In) -> Out: ...

    def close(self) -> None:  # noqa: B027
        pass

    @classmethod
    def mock_default(cls, item: In) -> Out:
        """fixtures에 없는 입력이 왔을 때 mock이 돌려줄 '형식만 맞는' 값. 로직 아님."""
        raise NotImplementedError


class MockStage(Stage[In, Out]):
    """fixtures/<name>/input.jsonl ↔ expected.jsonl 을 그대로 돌려주는 가짜 모듈."""

    def __init__(self, iface: type[Stage], fixtures_dir: Path | None = None) -> None:
        self.iface = iface
        self.name = iface.name  # type: ignore[misc]
        self.input_model = iface.input_model  # type: ignore[misc]
        self.output_model = iface.output_model  # type: ignore[misc]
        d = (fixtures_dir or FIXTURES) / iface.name
        self.table: dict[str, BaseModel] = {}
        if (d / "input.jsonl").exists():
            ins = read_jsonl(d / "input.jsonl", iface.input_model)
            outs = read_jsonl(d / "expected.jsonl", iface.output_model)
            self.table = {i.model_dump_json(): o for i, o in zip(ins, outs, strict=True)}

    def run(self, item: In) -> Out:
        hit = self.table.get(item.model_dump_json())
        return hit if hit is not None else self.iface.mock_default(item)  # type: ignore[return-value]


# ── JSONL 입출력 (통신 포맷) ────────────────────────────────
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
