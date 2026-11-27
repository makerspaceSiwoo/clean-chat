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
import os
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from clean_chat.core import modules
from clean_chat.core.config import FIXTURES, ROOT, settings
from clean_chat.core.game import GameStateMachine, PostGameBatch
from clean_chat.core.jsonl import read_jsonl
from clean_chat.core.modules import MODULE_NAMES, ModuleSet
from clean_chat.core.pipeline import Pipelines
from clean_chat.core.platform import use_utf8_console
from clean_chat.core.schemas import Frame, GamePhase, Incident, OcrResult, PhaseEvent, Player, Region
from clean_chat.sim import fallback, flow_log
from clean_chat.sim.flow_log import FlowLog

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
    step_delay_ms: int = Field(
        default=0, ge=0, le=3000
    )  # 단계 사이 쉬는 시간 (화면에서 한 단계씩 보려고). 계산은 그대로


class FlowStopped(RuntimeError):
    """흐름이 중간에 멈춤: 가정 응답을 끈 상태의 모듈 실패, 또는 모듈 밖 구성 단계의 예외. stage = 멈춘 단계."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"[{stage}] {message}")
        self.stage = stage


def default_players() -> list[Player]:
    return read_jsonl(FLOW_DIR / "players.jsonl", Player)


def _dump(x: Any) -> Any:
    return x.model_dump(mode="json") if isinstance(x, BaseModel) else x


def _item_id(item: BaseModel) -> str | None:
    """로그에 남길 처리 대상 id (줄·메시지·프레임·화자). 원문은 남기지 않는다."""
    for path in (("line", "id"), ("message", "id"), ("id",), ("speaker",)):
        x: Any = item
        for key in path:
            x = getattr(x, key, None)
        if isinstance(x, str):
            return x
    return None


class TracingModules:
    """모듈 5개를 감싸 실제 함수 → (실패하면) 가정 응답 순서로 부르고, 부를 때마다 call 이벤트를 낸다.

    실패는 flow_log.classify 로 종류(kind)를 나누고, 이벤트와 오류 로그(FlowLog)에 같은 내용을 남긴다.
    where = 지금 흐름이 있는 단계 (모듈 이름 또는 구성 단계) → 모듈 밖에서 멈추면 어디서 멈췄는지 알 수 있다.
    """

    def __init__(self, req: FlowRequest, emit: Emit, log: FlowLog | None = None) -> None:
        self.req, self.emit, self.log = req, emit, log
        self.seq = 0
        self.where = "game"
        self.status: dict[str, set[str]] = {name: set() for name in MODULE_NAMES}
        self._real: dict[str, Callable[[Any], Any] | tuple[Exception, str]] = {}

    def pause(self) -> None:
        if self.req.step_delay_ms:
            time.sleep(self.req.step_delay_ms / 1000)

    def module_set(self) -> ModuleSet:
        return ModuleSet({name: self._wrap(name) for name in MODULE_NAMES})

    def _load(self, name: str) -> Callable[[Any], Any] | tuple[Exception, str]:
        """모듈 함수를 한 번만 불러온다. 실패하면 (예외, traceback) 을 기억해 호출할 때마다 같은 실패로 처리."""
        if name not in self._real:
            try:
                self._real[name] = modules.load(name)
            except Exception as e:  # 모듈 파일 문법 오류, 없는 패키지 import 등
                tb = traceback.format_exc()
                print(tb, file=sys.stderr, end="", flush=True)
                self._real[name] = (e, tb)
        return self._real[name]

    def _fallback(self, name: str, item: BaseModel) -> BaseModel:
        if name == "ocr":
            return fallback.ocr(item, self.req.ocr_text)  # type: ignore[arg-type]
        return getattr(fallback, name)(item)

    def _record(self, name: str, kind: str, message: str, tb: str, item: BaseModel) -> dict[str, Any]:
        severity = flow_log.SEVERITY.get(kind, "error")
        if self.log is not None:
            self.log.failure(name, kind, message, tb, _item_id(item))
        return {"kind": kind, "severity": severity, "message": message, "traceback": tb}

    def _wrap(self, name: str) -> Callable[[BaseModel], BaseModel]:
        def call(item: BaseModel) -> BaseModel:
            self.seq += 1
            self.where = name
            self.emit({"event": "call_start", "seq": self.seq, "module": name, "input": _dump(item)})
            self.pause()  # 화면에 "지금 실행 중" 을 먼저 보여 준다
            started = time.perf_counter()
            loaded = self._load(name)
            mode, reason, problem = "real", "", None
            try:
                if isinstance(loaded, tuple):
                    raise loaded[0]
                out = modules.invoke(name, loaded, item)
            except Exception as e:  # 구현 전, 모듈 안 오류, 출력 형식 오류, Windows 전용, 패키지 없음
                is_load = isinstance(loaded, tuple)
                tb = loaded[1] if is_load else traceback.format_exc()
                kind = flow_log.classify(e, loading=is_load and not isinstance(e, NotImplementedError))
                if kind not in ("not_implemented", "platform") and not is_load:
                    print(tb, file=sys.stderr, end="", flush=True)
                label = "구현 전" if kind == "not_implemented" else "오류"
                mode, reason = "fallback", f"{label}: {type(e).__name__}: {e}{_hint(name, e)}"
                problem = self._record(name, kind, reason, "" if kind == "not_implemented" else tb, item)
                print(f"✖ [{name}] {kind} ({problem['severity']}) — {reason}", file=sys.stderr, flush=True)
                if not self.req.use_fallback:
                    raise FlowStopped(name, reason) from e
                out = self._fallback(name, item)
                print(f"  → [{name}] 가정 응답으로 대신하고 계속합니다", file=sys.stderr, flush=True)
            else:
                empty = _empty_result(name, out)
                if empty:
                    problem = self._record(name, "empty_result", empty, "", item)
                    print(f"⚠ [{name}] empty_result — {empty}", file=sys.stderr, flush=True)
            self.status[name].add(mode)
            if self.log is not None:
                self.log.count(name, "calls")
                self.log.count(name, mode)
            self.emit(
                {
                    "event": "call",
                    "seq": self.seq,
                    "module": name,
                    "mode": mode,
                    "reason": reason,
                    "problem": problem,
                    "input": _dump(item),
                    "output": _dump(out),
                    "ms": round((time.perf_counter() - started) * 1000),
                }
            )
            self.where = "pipeline"  # 모듈이 끝나면 다음은 구성(중복 제거·정책·세션 기록)
            return out

        return call


def _empty_result(name: str, out: BaseModel) -> str | None:
    """오류는 아니지만 다음 단계가 할 일이 없어지는 결과 → 경고로 남긴다."""
    if name == "ocr" and not getattr(out, "lines", None):
        return "OCR 이 읽은 줄이 없습니다 (이미지가 채팅창이 아니거나 글자를 못 읽음)"
    if name == "rewrite" and getattr(out, "rewritten", "x") is None:
        return f"순화 결과가 없습니다 (backend={getattr(out, 'backend', '?')}) → 정책표가 원문을 숨깁니다"
    return None


def _hint(name: str, e: Exception) -> str:
    """모듈 추가 패키지가 없어서 난 오류면 설치 방법을 덧붙인다 (pyproject.toml 의 모듈 extra)."""
    if isinstance(e, ModuleNotFoundError):
        return f" → 모듈 패키지가 없습니다: uv run --extra {name} sim flow (또는 uv sync --extra {name})"
    return ""


def run_flow(req: FlowRequest, emit: Emit, log: FlowLog | None = None) -> dict[str, Any]:
    """흐름 1번: 게임 시작 → 이미지 1장 처리(흐름 A) → 게임 종료 → 신고 문구·고소장. 마지막 요약을 돌려준다.

    모듈 밖(구성)에서 예외가 나면 그 단계 이름을 붙여 FlowStopped 로 바꾼다 → 어디서 멈췄는지 기록.
    """
    tracer = TracingModules(req, emit, log)
    try:
        return _run(req, emit, tracer)
    except FlowStopped:
        raise
    except Exception as e:
        stage = tracer.where
        tb = traceback.format_exc()
        print(tb, file=sys.stderr, end="", flush=True)
        if log is not None:
            log.failure(stage, "stage_exception", f"{type(e).__name__}: {e}", tb)
        raise FlowStopped(stage, f"{type(e).__name__}: {e}") from e


def _run(req: FlowRequest, emit: Emit, tracer: TracingModules) -> dict[str, Any]:
    mods = tracer.module_set()
    players = req.players or default_players()
    now = time.time()

    tracer.where = "game"
    game = GameStateMachine(idle_grace_sec=0)
    game.handle(PhaseEvent(ts=now, phase=GamePhase.IN_GAME, raw="sim"))
    game.set_players(players)
    pipes = Pipelines(mods)
    pipes.set_players(players)
    emit({"event": "phase", "phase": GamePhase.IN_GAME.value, "sessionId": game.session.id if game.session else None})

    frame = Frame(id="F0", ts=now, image_path=req.image_path, region=REGION)
    print(f"▶ 흐름 A: 캡처 이미지 1장 ({req.image_path})", flush=True)
    # IncomingPipeline.process_frame 과 같은 순서 (ocr → 줄 중복 제거 → 줄마다 process_line).
    # 줄 하나가 끝날 때마다 바로 화면에 보내려고 풀어서 부른다.
    incoming = pipes.incoming
    ocr: OcrResult = incoming.modules.run("ocr", frame)
    incidents: list[Incident] = []
    for line in incoming.dedup.new_lines(ocr.lines):
        inc = incoming.process_line(line)
        if inc is None:
            continue
        incidents.append(inc)
        game.record(inc)
        emit({"event": "incident", "incident": _dump(inc)})
    print(f"  채팅 {len(incidents)}건 처리", flush=True)
    tracer.pause()

    tracer.where = "post_game"
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


def _module_files() -> dict[str, dict[str, Any]]:
    """이번 실행이 불러올 모듈 파일과 수정 시각 → 화면에서 "지금 디스크에 있는 코드를 돌렸다"를 확인."""
    out = {}
    for name in MODULE_NAMES:
        path = modules.MODULES[name].path
        try:
            mtime = os.path.getmtime(ROOT / path)
        except OSError:
            mtime = None
        out[name] = {"path": path, "mtime": mtime}
    return out


def main(argv: list[str]) -> int:
    use_utf8_console()
    with open(argv[0], encoding="utf-8") as f:
        req = FlowRequest.model_validate(json.load(f))
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    log = FlowLog(run_id, req.sample_id or "upload")
    _emit_stdout(
        {
            "event": "start",
            "pid": os.getpid(),
            "runId": run_id,
            "logPath": str(log.path),
            "files": _module_files(),
            "stepDelayMs": req.step_delay_ms,
        }
    )
    print(
        f"▶ 전체 흐름 시작 (가정 응답 {'켬' if req.use_fallback else '끔'}, 내 닉네임 '{settings.my_name}')", flush=True
    )
    try:
        run_flow(req, _emit_stdout, log)
    except FlowStopped as e:
        print(f"✖ 멈춤: {e}", file=sys.stderr, flush=True)
        log.finish("stopped", e.stage)
        _emit_stdout({"event": "stopped", "error": str(e), "stage": e.stage})
    else:
        log.finish("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
