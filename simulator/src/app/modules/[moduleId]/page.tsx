import Link from "next/link";
import { notFound } from "next/navigation";
import { ModuleRunner } from "@/components/simulator/ModuleRunner";
import { getExamples } from "@/examples/examples";
import { findModule, MODULES } from "@/modules/registry";
import { getContract } from "@/shared/contracts";

export function generateStaticParams() {
  return MODULES.map((m) => ({ moduleId: m.moduleId }));
}

export const dynamicParams = false; // 등록되지 않은 모듈 주소는 404

export default async function ModulePage({ params }: { params: Promise<{ moduleId: string }> }) {
  const { moduleId } = await params;
  const meta = findModule(moduleId);
  if (!meta) notFound();
  const contract = getContract(meta.moduleId);
  return (
    <div>
      <nav className="mb-3 text-sm text-slate-500">
        <Link href="/" className="hover:underline">
          모듈 목록
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">{meta.moduleId}</span>
      </nav>
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold">
            {meta.number} {contract.title} <span className="font-mono text-base font-normal text-slate-500">{meta.moduleId}</span>
          </h1>
          <p className="mt-1 text-sm text-slate-600">{meta.description}</p>
        </div>
        <p className="font-mono text-xs text-slate-500">{contract.path}</p>
      </div>
      <ModuleRunner meta={meta} examples={getExamples(meta.moduleId)} />
    </div>
  );
}
