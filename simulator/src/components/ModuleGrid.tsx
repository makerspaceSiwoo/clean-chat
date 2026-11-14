import type { ModuleMeta } from "@/modules/registry";
import { ModuleCard } from "./ModuleCard";

/** 모듈 5개 카드 (PC 고정 5열, 처리 순서대로) */
export function ModuleGrid({ modules, exampleCounts }: { modules: readonly ModuleMeta[]; exampleCounts: Record<string, number> }) {
  if (modules.length === 0) {
    return <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">등록된 모듈이 없습니다.</p>;
  }
  return (
    <div className="grid grid-cols-5 gap-4">
      {modules.map((m) => (
        <ModuleCard key={m.moduleId} meta={m} exampleCount={exampleCounts[m.moduleId] ?? 0} />
      ))}
    </div>
  );
}
