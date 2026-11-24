"""전체 흐름 시뮬레이션 (구성 · 리드): 캡처 이미지 1장 → ① ocr → ② parse → ③ analyze → ④ rewrite → 정책 → ⑤ report.

실제 앱과 같은 코드로 흐름을 잇는다 — 흐름 A(core/pipeline.py IncomingPipeline), 게임 단계·세션(core/game.py),
게임 종료 배치(PostGameBatch). 다른 점은 두 가지뿐이다.
  1. 실시간 화면 캡처 대신 **저장된 캡처 이미지**(fixtures/flow/*.png 또는 첨부 이미지)를 한 장 넣는다.
  2. 모듈이 구현 전(NotImplementedError)이거나 오류가 나면 **가정 응답**(sim/fallback.py)으로 대신하고 계속 간다.
     어떤 모듈이 실제로 돌았고 어떤 모듈이 가정 응답이었는지 단계마다 이벤트로 알린다.

시뮬레이터 서버가 실행마다 새 프로세스로 띄운다 (모듈 코드를 고치면 바로 반영):
  python -u -m clean_chat.sim.flow <입력.json>
  stdout 의 "\\x1eFLOW " 로 시작하는 줄 = 단계 이벤트(JSON), 그 밖의 stdout·stderr = 디버깅 콘솔
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from clean_chat.core import modules
from clean_chat.core.config import FIXTURES, settings
from clean_chat.core.game import GameStateMachine, PostGameBatch
from clean_chat.core.jsonl import read_jsonl
from clean_chat.core.modules import MODULE_NAMES, ModuleSet
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.platform import use_utf8_console
from clean_chat.core.schemas import Frame, GamePhase, Incident, PhaseEvent, Player, Region
from clean_chat.sim import fallback

FLOW_DIR = FIXTURES / "flow"
MARKER = "\x1eFLOW "
REGION = Region(x=0, y=600, w=500, h=250)

Emit = Callable[[dict[str, Any]], None]


class FlowRequest(BaseModel):
    image_path: str  # 캡처 이미지 경로 (실제 ocr 모듈이 읽음)
    ocr_text: str = ""  # ocr 가정 응답: 이 이미지에서 읽었다고 칠 줄들 (한 줄 = 채팅 한 줄)
    players: list[Player] = Field(default_factory=list)
    use_fallback: bool = True  # False 면 구현 전·오류 모듈에서 멈춘다 (실제 앱과 같음)
    sample_id: str | None = None


class FlowStopped(RuntimeError):
    """가정 응답을 끈 상태에서 모듈이 구현 전이거나 오류가 남."""


def default_players() -> list[Player]:
    return read_jsonl(FLOW_DIR / "players.jsonl", Player)


def _dump(x: Any) -> Any:
    return x.model_dump(mode="json") if isinstance(x, BaseModel) else x


class TracingModules:
    """모듈 5개를 감싸 실제 함수 → (실패하면) 가정 응답 순서로 부르고, 부를 때마다 call 이벤트를 낸다."""

    def __init__(self, req: FlowRequest, emit: Emit) -> None:
        self.req, self.emit = req, emit
        self.seq = 0
        self.status: dict[str, set[str]] = {name: set() for name in MODULE_NAMES}
        self._real: dict[str, Callable[[Any], Any] | Exception] = {}

    def module_set(self) -> ModuleSet:
        return ModuleSet({name: self._wrap(name) for name in MODULE_NAMES})

    def _load(self, name: str) -> Callable[[Any], Any] | Exception:
        if name not in self._real:
            try:
                self._real[name] = modules.load(name)
            except Exception as e:  # 모듈 파일 문법 오류, 없는 패키지 import 등
                traceback.print_exc()
                self._real[name] = e
        return self._real[name]

    def _fallback(self, name: str, item: BaseModel) -> BaseModel:
        if name == "ocr":
            return fallback.ocr(item, self.req.ocr_text)  # type: ignore[arg-type]
        return getattr(fallback, name)(item)

    def _wrap(self, name: str) -> Callable[[BaseModel], BaseModel]:
        def call(item: BaseModel) -> BaseModel:
            self.seq += 1
            started = time.perf_counter()
            fn = self._load(name)
            mode, reason = "real", ""
            try:
                if isinstance(fn, Exception):
                    raise fn
                out = modules.invoke(name, fn, item)
            except modules.ModuleNotImplemented as e:
                mode, reason = "fallback", f"구현 전: {e}"
            except Exception as e:  # 모듈 안 오류, 출력 형식 오류, Windows 전용 등
                if not isinstance(fn, Exception):
                    traceback.print_exc()
                mode, reason = "fallback", f"오류: {type(e).__name__}: {e}{_hint(name, e)}"
            if mode == "fallback":
                if not self.req.use_fallback:
                    raise FlowStopped(f"[{name}] {reason}")
                print(f"⚠ [{name}] 가정 응답으로 대신합니다 — {reason}", file=sys.stderr, flush=True)
                out = self._fallback(name, item)
            self.status[name].add(mode)
            self.emit(
                {
                    "event": "call",
                    "seq": self.seq,
                    "module": name,
                    "mode": mode,
                    "reason": reason,
                    "input": _dump(item),
                    "output": _dump(out),
                    "ms": round((time.perf_counter() - started) * 1000),
                }
            )
            return out

        return call


def _hint(name: str, e: Exception) -> str:
    """모듈 추가 패키지가 없어서 난 오류면 설치 방법을 덧붙인다 (pyproject.toml 의 모듈 extra)."""
    if isinstance(e, ModuleNotFoundError):
        return f" → 모듈 패키지가 없습니다: uv run --extra {name} sim flow (또는 uv sync --extra {name})"
    return ""


def run_flow(req: FlowRequest, emit: Emit) -> dict[str, Any]:
    """흐름 1번: 게임 시작 → 이미지 1장 처리(흐름 A) → 게임 종료 → 신고 문구·고소장. 마지막 요약을 돌려준다."""
    tracer = TracingModules(req, emit)
    mods = tracer.module_set()
    players = req.players or default_players()
    now = time.time()

    game = GameStateMachine(idle_grace_sec=0)
    game.handle(PhaseEvent(ts=now, phase=GamePhase.IN_GAME, raw="sim"))
    game.set_players(players)
    pipes = Pipelines(mods)
    pipes.set_players(players)
    emit({"event": "phase", "phase": GamePhase.IN_GAME.value, "sessionId": game.session.id if game.session else None})

    frame = Frame(id="F0", ts=now, image_path=req.image_path, region=REGION)
    print(f"▶ 흐름 A: 캡처 이미지 1장 ({req.image_path})", flush=True)
    incidents: list[Incident] = pipes.incoming.process_frame(frame)
    for inc in incidents:
        game.record(inc)
        emit({"event": "incident", "incident": _dump(inc)})
    print(f"  채팅 {len(incidents)}건 처리", flush=True)

    game.handle(PhaseEvent(ts=time.time(), phase=GamePhase.POST_GAME, raw="sim"))
    emit({"event": "phase", "phase": GamePhase.POST_GAME.value, "sessionId": game.session.id if game.session else None})
    print("▶ 게임 종료: 신고 문구 · 고소장 초안 (report)", flush=True)
    result = PostGameBatch(mods).run(game.session) if game.session else None
    emit({"event": "post_game", "result": _dump(result)})

    summary = {"modules": {name: sorted(modes) for name, modes in tracer.status.items()}, "incidents": len(incidents)}
    emit({"event": "done", "summary": summary})
    return summary


def _emit_stdout(event: dict[str, Any]) -> None:
    print(MARKER + json.dumps(event, ensure_ascii=False), flush=True)


def main(argv: list[str]) -> int:
    use_utf8_console()
    with open(argv[0], encoding="utf-8") as f:
        req = FlowRequest.model_validate(json.load(f))
    print(
        f"▶ 전체 흐름 시작 (가정 응답 {'켬' if req.use_fallback else '끔'}, 내 닉네임 '{settings.my_name}')", flush=True
    )
    try:
        run_flow(req, _emit_stdout)
    except FlowStopped as e:
        print(f"✖ 멈춤: {e}", file=sys.stderr, flush=True)
        _emit_stdout({"event": "stopped", "error": str(e)})
    except Exception as e:
        traceback.print_exc()
        _emit_stdout({"event": "stopped", "error": f"{type(e).__name__}: {e}"})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
