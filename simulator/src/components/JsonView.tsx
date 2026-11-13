import { prettyJson } from "@/lib/json";

export function JsonView({ value, label, testId }: { value: unknown; label?: string; testId?: string }) {
  return (
    <div className="flex min-h-0 flex-col">
      {label && <p className="mb-1 text-xs font-medium text-slate-500">{label}</p>}
      <pre
        data-testid={testId}
        className="max-h-[360px] overflow-auto rounded-md border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-800"
      >
        {prettyJson(value)}
      </pre>
    </div>
  );
}
