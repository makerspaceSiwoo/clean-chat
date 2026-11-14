import { ModuleGrid } from "@/components/ModuleGrid";
import { allExamples } from "@/examples/examples";
import { MODULES } from "@/modules/registry";

export default function HomePage() {
  const examples = allExamples();
  const exampleCounts = Object.fromEntries(MODULES.map((m) => [m.moduleId, examples[m.moduleId]?.length ?? 0]));
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold">모듈 5개</h1>
        <p className="mt-1 text-sm text-slate-600">
          카드를 누르고 입력을 넣어 실행하면 <b>실제 파이썬 모듈 함수</b>의 output 이 나옵니다. 구현 전인 모듈은 &lsquo;501 구현 안 됨&rsquo; 오류가 납니다.
        </p>
        <p className="mt-1 text-sm text-slate-600">
          먼저 레포 루트에서 <code className="rounded bg-slate-100 px-1 font-mono">uv run clean-chat serve</code> 로 로컬 모듈 서버를 켜세요.
        </p>
      </div>
      <ModuleGrid modules={MODULES} exampleCounts={exampleCounts} />
    </div>
  );
}
