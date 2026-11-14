"use client";
import type { ReactNode } from "react";
import type { MockScenario } from "@/api/mockClient";
import type { FixtureCase } from "@/mocks/fixtures";

export const CUSTOM_CASE = "__custom__";

const SCENARIOS: { value: MockScenario; label: string }[] = [
  { value: "normal", label: "정상 응답" },
  { value: "server-error", label: "서버 오류 (500)" },
  { value: "timeout", label: "타임아웃" },
  { value: "empty", label: "빈 응답 (200, 출력 없음)" },
];

interface Props {
  inputType: string;
  cases: FixtureCase[];
  selectedCaseId: string;
  onSelectCase: (caseId: string) => void;
  text: string;
  onTextChange: (text: string) => void;
  parseError?: string;
  /** 고른 케이스에서 입력을 고쳤는지 */
  edited: boolean;
  onFormat: () => void;
  onRestore: () => void;
  /** mock 모드일 때만 장애 흉내 선택 */
  mockScenario?: MockScenario;
  onMockScenario?: (s: MockScenario) => void;
  /** 입력 JSON 위에 끼우는 칸 (예: 이미지 첨부) */
  attachment?: ReactNode;
}

export function InputPanel(p: Props) {
  return (
    <section aria-label="입력 데이터" className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">입력 데이터</h2>
        <span className="font-mono text-xs text-slate-500">{p.inputType}</span>
      </div>

      <label className="mt-3 text-xs font-medium text-slate-600" htmlFor="case-select">
        Mock 케이스 (fixtures)
      </label>
      <select
        id="case-select"
        value={p.selectedCaseId}
        onChange={(e) => p.onSelectCase(e.target.value)}
        className="mt-1 h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
      >
        {p.cases.map((c) => (
          <option key={c.caseId} value={c.caseId}>
            {c.label}
          </option>
        ))}
        <option value={CUSTOM_CASE}>직접 입력</option>
      </select>
      {p.cases.length === 0 && <p className="mt-1 text-xs text-amber-700">이 Stage 의 fixtures 가 없습니다. 직접 입력만 가능합니다.</p>}

      {p.attachment}

      <div className="mt-3 flex items-center justify-between">
        <label className="text-xs font-medium text-slate-600" htmlFor="input-json">
          입력 JSON
        </label>
        <div className="flex gap-2">
          {p.edited && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-800">수정됨 · 기대값 비교 안 함</span>}
          <button type="button" onClick={p.onFormat} className="text-xs text-slate-600 underline-offset-2 hover:underline">
            정렬
          </button>
          <button type="button" onClick={p.onRestore} className="text-xs text-slate-600 underline-offset-2 hover:underline">
            원래대로
          </button>
        </div>
      </div>
      <textarea
        id="input-json"
        value={p.text}
        onChange={(e) => p.onTextChange(e.target.value)}
        spellCheck={false}
        aria-invalid={p.parseError !== undefined}
        className={`mt-1 min-h-[360px] flex-1 resize-none rounded-md border p-3 font-mono text-xs leading-relaxed ${
          p.parseError ? "border-red-400 bg-red-50/40" : "border-slate-300"
        }`}
      />
      {p.parseError && (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {p.parseError}
        </p>
      )}

      {p.mockScenario && p.onMockScenario && (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <label className="text-xs font-medium text-slate-600" htmlFor="mock-scenario">
            응답 흉내 (Mock 전용, 오류 화면 QA)
          </label>
          <select
            id="mock-scenario"
            value={p.mockScenario}
            onChange={(e) => p.onMockScenario?.(e.target.value as MockScenario)}
            className="mt-1 h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm"
          >
            {SCENARIOS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      )}
    </section>
  );
}
