import { FLOW_LABEL, FLOW_ORDER, type ModuleMeta } from "@/modules/registry";
import { ModuleCard } from "./ModuleCard";

/** 흐름별로 묶은 카드 그리드 (PC 고정 4열) */
export function ModuleGrid({ modules, caseCounts }: { modules: readonly ModuleMeta[]; caseCounts: Record<string, number> }) {
  if (modules.length === 0) {
    return <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">등록된 모듈이 없습니다.</p>;
  }
  return (
    <div className="space-y-8">
      {FLOW_ORDER.map((flow) => {
        const items = modules.filter((m) => m.flow === flow);
        if (items.length === 0) return null;
        return (
          <section key={flow} aria-labelledby={`flow-${flow}`}>
            <h2 id={`flow-${flow}`} className="mb-3 text-sm font-semibold text-slate-700">
              {FLOW_LABEL[flow]}
            </h2>
            <div className="grid grid-cols-4 gap-4">
              {items.map((m) => (
                <ModuleCard key={m.stageId} meta={m} caseCount={caseCounts[m.stageId] ?? 0} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
