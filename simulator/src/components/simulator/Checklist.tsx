"use client";
import { useState } from "react";
import { summarize, type CheckItem, type CheckStatus } from "@/lib/checklist";

const ICON: Record<CheckStatus, { mark: string; cls: string; sr: string }> = {
  pass: { mark: "✓", cls: "bg-emerald-100 text-emerald-700", sr: "통과" },
  fail: { mark: "✕", cls: "bg-red-100 text-red-700", sr: "실패" },
  warn: { mark: "!", cls: "bg-amber-100 text-amber-800", sr: "경고" },
  skip: { mark: "–", cls: "bg-slate-100 text-slate-500", sr: "건너뜀" },
};

interface Props {
  /** 자동 판정 결과. 아직 실행 전이면 null */
  items: CheckItem[] | null;
  manualChecks: string[];
}

/** 화면 오른쪽 E2E 응답 체크리스트. 새 실행마다 key 를 바꿔 수동 체크도 초기화한다(부모 책임). */
export function Checklist({ items, manualChecks }: Props) {
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const s = items ? summarize(items) : null;
  const manualDone = manualChecks.filter((_, i) => checked[i]).length;

  return (
    <aside aria-label="E2E 체크리스트" className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="text-sm font-semibold text-slate-800">E2E 응답 체크리스트</h2>
      {s ? (
        <p data-testid="checklist-summary" className="mt-1 text-xs text-slate-600">
          자동 {s.pass}/{s.total} 통과{s.fail > 0 && ` · 실패 ${s.fail}`}
          {s.warn > 0 && ` · 경고 ${s.warn}`}
        </p>
      ) : (
        <p className="mt-1 text-xs text-slate-500">실행하면 자동 판정이 채워집니다.</p>
      )}

      <h3 className="mt-4 text-xs font-medium text-slate-500">자동 확인</h3>
      <ul className="mt-2 space-y-1.5">
        {(items ?? []).map((it) => {
          const icon = ICON[it.status];
          return (
            <li key={it.id} data-testid={`check-${it.id}`} data-status={it.status} className="flex gap-2 text-sm">
              <span aria-hidden className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded text-xs font-bold ${icon.cls}`}>
                {icon.mark}
              </span>
              <span>
                <span className="sr-only">{icon.sr}: </span>
                <span className="text-slate-800">{it.label}</span>
                {it.detail && <span className="block text-xs text-slate-500">{it.detail}</span>}
              </span>
            </li>
          );
        })}
        {items === null && <li className="text-xs text-slate-400">—</li>}
      </ul>

      <h3 className="mt-5 text-xs font-medium text-slate-500">
        사람이 확인 ({manualDone}/{manualChecks.length})
      </h3>
      <ul className="mt-2 space-y-1.5">
        {manualChecks.map((label, i) => (
          <li key={label}>
            <label className="flex cursor-pointer gap-2 text-sm text-slate-800">
              <input
                type="checkbox"
                checked={checked[i] ?? false}
                onChange={(e) => setChecked((c) => ({ ...c, [i]: e.target.checked }))}
                className="mt-1"
              />
              {label}
            </label>
          </li>
        ))}
      </ul>
    </aside>
  );
}
