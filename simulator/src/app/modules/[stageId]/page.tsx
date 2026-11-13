import Link from "next/link";
import { notFound } from "next/navigation";
import { StageSimulator } from "@/components/simulator/StageSimulator";
import { getFixtureCases } from "@/mocks/fixtures";
import { findModule, FLOW_LABEL, MODULES } from "@/modules/registry";

export function generateStaticParams() {
  return MODULES.map((m) => ({ stageId: m.stageId }));
}

export const dynamicParams = false; // 등록되지 않은 Stage 주소는 404

export default async function ModulePage({ params }: { params: Promise<{ stageId: string }> }) {
  const { stageId } = await params;
  const meta = findModule(stageId);
  if (!meta) notFound();
  return (
    <div>
      <nav className="mb-3 text-sm text-slate-500">
        <Link href="/" className="hover:underline">
          모듈 목록
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">{meta.title}</span>
      </nav>
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold">
            {meta.title} <span className="font-mono text-base font-normal text-slate-500">{meta.stageId}</span>
          </h1>
          <p className="mt-1 text-sm text-slate-600">{meta.description}</p>
        </div>
        <div className="text-right text-xs text-slate-500">
          <p>{FLOW_LABEL[meta.flow]}</p>
          <p className="font-mono">
            {meta.modulePath} · {meta.workPackage}
          </p>
        </div>
      </div>
      <StageSimulator meta={meta} cases={getFixtureCases(meta.stageId)} />
    </div>
  );
}
