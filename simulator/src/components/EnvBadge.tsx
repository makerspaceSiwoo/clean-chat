"use client";
import { useApi } from "@/api/ApiProvider";

const ENV_STYLE: Record<string, string> = {
  local: "bg-slate-100 text-slate-700 border-slate-300",
  develop: "bg-amber-50 text-amber-800 border-amber-300",
  main: "bg-emerald-50 text-emerald-800 border-emerald-300",
};

export function EnvBadge() {
  const { config } = useApi();
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={`rounded border px-2 py-0.5 font-medium ${ENV_STYLE[config.appEnv]}`}>{config.appEnv}</span>
      <span className="rounded border border-slate-300 bg-white px-2 py-0.5 font-mono text-slate-700">모듈 서버 {config.apiBaseUrl}</span>
    </div>
  );
}

export function ConfigWarnings() {
  const { config } = useApi();
  if (config.warnings.length === 0) return null;
  return (
    <div role="alert" className="border-b border-amber-200 bg-amber-50 px-8 py-2 text-xs text-amber-900">
      {config.warnings.map((w) => (
        <p key={w}>설정 경고: {w}</p>
      ))}
    </div>
  );
}
