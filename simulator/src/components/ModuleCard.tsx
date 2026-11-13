import Link from "next/link";
import { FLOW_LABEL, type ModuleMeta } from "@/modules/registry";
import { getContract } from "@/shared/contracts";

const FLOW_STYLE: Record<ModuleMeta["flow"], string> = {
  A: "bg-sky-50 text-sky-800",
  B: "bg-violet-50 text-violet-800",
  common: "bg-slate-100 text-slate-700",
  post_game: "bg-rose-50 text-rose-800",
};

export function ModuleCard({ meta, caseCount }: { meta: ModuleMeta; caseCount: number }) {
  const contract = getContract(meta.stageId);
  return (
    <Link
      href={`/modules/${meta.stageId}`}
      data-testid={`module-card-${meta.stageId}`}
      className="group flex h-[172px] flex-col rounded-xl border border-slate-200 bg-white p-5 transition hover:border-slate-400 hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
    >
      <div className="flex items-center justify-between">
        <span className={`rounded px-2 py-0.5 text-[11px] font-medium ${FLOW_STYLE[meta.flow]}`}>{FLOW_LABEL[meta.flow].split(" · ")[0]}</span>
        <span className="text-[11px] text-slate-500">{meta.workPackage}</span>
      </div>
      <h3 className="mt-3 text-base font-semibold text-slate-900">{meta.title}</h3>
      <p className="font-mono text-xs text-slate-500">{meta.stageId}</p>
      <p className="mt-2 line-clamp-2 text-sm text-slate-600">{meta.description}</p>
      <div className="mt-auto flex items-center justify-between pt-3 text-xs text-slate-500">
        <span className="font-mono">
          {contract.input} → {contract.output}
        </span>
        <span className={caseCount === 0 ? "text-amber-700" : undefined}>Mock {caseCount}건</span>
      </div>
    </Link>
  );
}
