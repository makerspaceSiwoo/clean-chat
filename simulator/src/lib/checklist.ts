/**
 * E2E 응답 체크리스트 자동 판정 (순수 함수 — 화면과 분리해서 테스트).
 * 사람이 직접 보는 항목(manualChecks)은 화면에서 체크박스로 다룬다.
 */
import type { ModuleMeta } from "@/modules/registry";
import type { StageContract } from "@/shared/contracts";
import type { RunStageResponse } from "@/types/api";
import { deepEqual, hasPath } from "./json";

export type CheckStatus = "pass" | "fail" | "warn" | "skip";

export interface CheckItem {
  id: string;
  label: string;
  status: CheckStatus;
  detail?: string;
}

export interface ChecklistContext {
  meta: ModuleMeta;
  /** 공통 계약 (출력 모델 이름과 필드) */
  contract: StageContract;
  response: RunStageResponse;
  /** 고른 fixtures 케이스의 기대값. 입력을 고쳤거나 직접 입력이면 undefined */
  expected?: unknown;
  /** mock 모드면 응답 시간 검사는 건너뜀 (흉내 지연이라 의미 없음) */
  apiMode: "mock" | "http";
}

export function evaluateChecklist({ meta, contract, response, expected, apiMode }: ChecklistContext): CheckItem[] {
  const out = response.output;
  const hasOutput = out !== null && out !== undefined;
  const items: CheckItem[] = [
    {
      id: "status-200",
      label: "응답 코드가 200인가?",
      status: response.status === 200 ? "pass" : "fail",
      detail: `받은 코드: ${response.status === 0 ? "없음(네트워크·타임아웃)" : response.status}`,
    },
    {
      id: "has-output",
      label: `출력(${contract.output})이 비어 있지 않은가?`,
      status: hasOutput ? "pass" : "fail",
      detail: hasOutput ? undefined : response.error,
    },
  ];
  for (const field of contract.outputFields) {
    items.push({
      id: `field-${field}`,
      label: `'${field}' 필드가 포함되어 있는가?`,
      status: !hasOutput ? "skip" : hasPath(out, field) ? "pass" : "fail",
    });
  }
  items.push(expectedCheck(meta, out, expected, hasOutput));
  items.push({
    id: "latency",
    label: `응답 시간이 목표(${meta.latencyBudgetMs}ms) 이내인가?`,
    status: apiMode === "mock" ? "skip" : response.durationMs <= meta.latencyBudgetMs ? "pass" : "warn",
    detail: apiMode === "mock" ? "Mock 지연은 흉내라 검사하지 않음" : `${response.durationMs}ms`,
  });
  return items;
}

function expectedCheck(meta: ModuleMeta, out: unknown, expected: unknown, hasOutput: boolean): CheckItem {
  const label = meta.strict ? "fixtures 기대값과 정확히 같은가? (STRICT)" : "fixtures 기대값과 같은가? (AI 모듈: 다르면 경고)";
  if (expected === undefined) return { id: "expected", label, status: "skip", detail: "기대값 없음 (입력을 고쳤거나 직접 입력)" };
  if (!hasOutput) return { id: "expected", label, status: "skip" };
  if (deepEqual(out, expected)) return { id: "expected", label, status: "pass" };
  return { id: "expected", label, status: meta.strict ? "fail" : "warn", detail: "결과 화면에서 기대값과 비교해 보세요" };
}

export function summarize(items: CheckItem[]): { pass: number; fail: number; warn: number; total: number } {
  const counted = items.filter((i) => i.status !== "skip");
  return {
    pass: counted.filter((i) => i.status === "pass").length,
    fail: counted.filter((i) => i.status === "fail").length,
    warn: counted.filter((i) => i.status === "warn").length,
    total: counted.length,
  };
}
