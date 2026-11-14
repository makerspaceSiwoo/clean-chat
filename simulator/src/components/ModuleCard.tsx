import Link from "next/link";
import type { ModuleMeta } from "@/modules/registry";
import { getContract } from "@/shared/contracts";

export function ModuleCard({ meta, exampleCount }: { meta: ModuleMeta; exampleCount: number }) {
  const contract = getContract(meta.moduleId);
  return (
    <Link
      href={`/modules/${meta.moduleId}`}
      data-testid={`module-card-${meta.moduleId}`}
      className="group flex h-[188px] flex-col rounded-xl border border-slate-200 bg-white p-5 transition hover:border-slate-400 hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
    >
      <div className="flex items-baseline gap-2">
        <span className="text-lg text-slate-400">{meta.number}</span>
        <span className="font-mono text-sm font-semibold text-slate-900">{meta.moduleId}</span>
      </div>
      <h3 className="mt-1 text-sm font-medium text-slate-800">{contract.title}</h3>
      <p className="mt-2 line-clamp-2 text-sm text-slate-600">{meta.description}</p>
      <div className="mt-auto space-y-1 pt-3 text-xs text-slate-500">
        <p className="font-mono">
          {contract.input} → {contract.output}
        </p>
        <p>예시 입력 {exampleCount}개</p>
      </div>
    </Link>
  );
}
