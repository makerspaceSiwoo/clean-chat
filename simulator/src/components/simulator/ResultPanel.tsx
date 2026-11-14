"use client";
import type { RunState } from "@/hooks/useModuleRun";
import { JsonView } from "../JsonView";

/** 상태 코드 → 사람이 읽는 이름 (서버 계약: src/clean_chat/core/server.py) */
export function statusLabel(status: number): string {
  if (status === 0) return "서버 연결 안 됨";
  if (status === 501) return "501 구현 안 됨";
  if (status === 422) return "422 입력 형식 오류";
  if (status === 500) return "500 모듈 오류";
  return `HTTP ${status}`;
}

interface Props {
  state: RunState;
  outputType: string;
}

/** 실행 결과: 실제 모듈 함수가 돌려준 output JSON, 또는 오류(상태 코드 + 메시지). 기대값 비교는 하지 않는다. */
export function ResultPanel({ state, outputType }: Props) {
  if (state.phase === "idle") {
    return (
      <div data-testid="result-idle" className="flex h-[220px] items-center justify-center rounded-xl border border-dashed border-slate-300 text-sm text-slate-500">
        입력을 확인하고 &lsquo;실행&rsquo;을 누르면 모듈 함수의 output 이 여기에 나옵니다.
      </div>
    );
  }
  if (state.phase === "loading") {
    return (
      <div data-testid="result-loading" role="status" aria-live="polite" className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
        <p className="text-sm text-slate-600">모듈 실행 중…</p>
        <div className="h-3 w-2/3 animate-pulse rounded bg-slate-200" />
        <div className="h-24 animate-pulse rounded bg-slate-100" />
      </div>
    );
  }

  const response = state.response;
  const isError = state.phase === "error";
  return (
    <div data-testid={isError ? "result-error" : "result-success"} className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-center gap-3 text-sm">
        <span className={`rounded px-2 py-0.5 font-mono text-xs font-medium ${isError ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800"}`}>
          {response ? statusLabel(response.status) : "오류"}
        </span>
        {response && <span className="text-slate-500">{response.durationMs}ms</span>}
      </div>

      {isError && (
        <pre role="alert" className="whitespace-pre-wrap break-all rounded-md border border-red-200 bg-red-50 p-3 font-sans text-sm text-red-800">
          {state.message}
        </pre>
      )}

      {!isError && response && <JsonView label={`output (${outputType})`} value={response.output} testId="result-json" />}
    </div>
  );
}
