"use client";
import type { ReactNode } from "react";
import type { InputExample } from "@/examples/examples";

export const CUSTOM_INPUT = "__custom__";

interface Props {
  inputType: string;
  examples: InputExample[];
  selectedExampleId: string;
  onSelectExample: (exampleId: string) => void;
  text: string;
  onTextChange: (text: string) => void;
  parseError?: string;
  onFormat: () => void;
  onRestore: () => void;
  /** 입력 JSON 위에 끼우는 칸 (예: 이미지 첨부) */
  attachment?: ReactNode;
}

export function InputPanel(p: Props) {
  return (
    <section aria-label="입력 데이터" className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">입력</h2>
        <span className="font-mono text-xs text-slate-500">{p.inputType}</span>
      </div>

      <label className="mt-3 text-xs font-medium text-slate-600" htmlFor="example-select">
        예시 입력 (fixtures)
      </label>
      <select
        id="example-select"
        value={p.selectedExampleId}
        onChange={(e) => p.onSelectExample(e.target.value)}
        className="mt-1 h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
      >
        {p.examples.map((c) => (
          <option key={c.exampleId} value={c.exampleId}>
            {c.label}
          </option>
        ))}
        <option value={CUSTOM_INPUT}>직접 입력</option>
      </select>

      {p.attachment}

      <div className="mt-3 flex items-center justify-between">
        <label className="text-xs font-medium text-slate-600" htmlFor="input-json">
          입력 JSON
        </label>
        <div className="flex gap-2">
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
        className={`mt-1 min-h-[420px] flex-1 resize-none rounded-md border p-3 font-mono text-xs leading-relaxed ${
          p.parseError ? "border-red-400 bg-red-50/40" : "border-slate-300"
        }`}
      />
      {p.parseError && (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {p.parseError}
        </p>
      )}
    </section>
  );
}
