import { ModuleGrid } from "@/components/ModuleGrid";
import { allFixtureCases } from "@/mocks/fixtures";
import { MODULES } from "@/modules/registry";

export default function HomePage() {
  const fixtures = allFixtureCases();
  const caseCounts = Object.fromEntries(MODULES.map((m) => [m.stageId, fixtures[m.stageId]?.length ?? 0]));
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold">모듈 목록</h1>
        <p className="mt-1 text-sm text-slate-600">
          카드를 누르면 해당 Stage 를 Mock 데이터로 실행하고 결과·체크리스트를 확인할 수 있습니다. Mock 데이터는 레포의 <code className="font-mono">fixtures/</code> 입니다.
        </p>
      </div>
      <ModuleGrid modules={MODULES} caseCounts={caseCounts} />
    </div>
  );
}
