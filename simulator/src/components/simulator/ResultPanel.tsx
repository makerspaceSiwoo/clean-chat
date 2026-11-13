"use client";
import type { RunState } from "@/hooks/useStageRun";
import { getPath } from "@/lib/json";
import type { SummaryField } from "@/modules/registry";
import { JsonView } from "../JsonView";

function display(value: unknown): string {
  if (value === undefined) return "—";
  if (value === null) return "null";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

interface Props {
  state: RunState;
  outputType: string;
  summaryFields: SummaryField[];
  /** 고른 fixtures 케이스의 기대값 (없으면 비교 안 보여 줌) */
  expected?: unknown;
}

export function ResultPanel({ state, outputType, summaryFields, expected }: Props) {
  if (state.phase === "idle") {
    return (
      <div data-testid="result-idle" className="flex h-[220px] items-center justify-center rounded-xl border border-dashed border-slate-300 text-sm text-slate-500">
        입력을 확인하고 &lsquo;실행 (테스트)&rsquo;을 누르면 결과가 여기에 나옵니다.
      </div>
    );
  }
  if (state.phase === "loading") {
    return (
      <div data-testid="result-loading" role="status" aria-live="polite" className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
        <p className="text-sm text-slate-600">응답을 기다리는 중…</p>
        <div className="h-3 w-2/3 animate-pulse rounded bg-slate-200" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-slate-200" />
        <div className="h-24 animate-pulse rounded bg-slate-100" />
      </div>
    );
  }

  const response = state.response;
  const isError = state.phase === "error";
  return (
    <div data-testid={isError ? "result-error" : "result-success"} className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-center gap-3 text-sm">
        <span
          className={`rounded px-2 py-0.5 font-mono text-xs font-medium ${isError ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800"}`}
        >
          {response ? (response.status === 0 ? "응답 없음" : `HTTP ${response.status}`) : "오류"}
        </span>
        {response && <span className="text-slate-500">{response.durationMs}ms</span>}
        {response && <span className="font-mono text-xs text-slate-500">impl: {response.impl}</span>}
      </div>

      {isError && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {state.message}
        </div>
      )}

      {!isError && response && (
        <table className="w-full table-fixed text-sm">
          <caption className="mb-2 text-left text-xs font-medium text-slate-500">요약 ({outputType})</caption>
          <tbody>
            {summaryFields.map((f) => (
              <tr key={f.path} className="border-t border-slate-100">
                <th scope="row" className="w-[160px] py-1.5 pr-3 text-left font-normal text-slate-500">
                  {f.label}
                </th>
                <td className="whitespace-pre-wrap break-all py-1.5 text-slate-900">{display(getPath(response.output, f.path))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {response && (
        <div className={`grid gap-4 ${expected !== undefined ? "grid-cols-2" : "grid-cols-1"}`}>
          <JsonView label="실제 응답 output" value={response.output} testId="result-json" />
          {expected !== undefined && <JsonView label="기대값 (fixtures expected)" value={expected} testId="expected-json" />}
        </div>
      )}
    </div>
  );
}
