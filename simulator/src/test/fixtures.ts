/** 테스트 공용 가짜 데이터 (레포 fixtures 와 무관하게 고정) */
import type { ModuleMeta } from "@/modules/registry";
import type { FixtureCase } from "@/mocks/fixtures";
import type { RunStageResponse } from "@/types/api";

export const META: ModuleMeta = {
  stageId: "incoming_policy",
  title: "수신 정책",
  modulePath: "src/clean_chat/policy/impl.py",
  workPackage: "WP1",
  flow: "A",
  description: "테스트용",
  inputType: "PolicyRequest",
  outputType: "Decision",
  requiredFields: ["action", "display_text"],
  summaryFields: [
    { label: "처리", path: "action" },
    { label: "표시 문장", path: "display_text" },
  ],
  latencyBudgetMs: 100,
  strict: true,
  manualChecks: ["SPEC 표와 같은가?"],
};

export const CASES: FixtureCase[] = [
  { caseId: "c1", label: "#1 · L3 · 용 먼저", input: { message: { id: "L3", text: "용 먼저" } }, expected: { action: "show_rewritten", display_text: "용 먼저 치자" } },
  { caseId: "c2", label: "#2 · L4 · 숨김", input: { message: { id: "L4", text: "x" } }, expected: { action: "hide", display_text: null } },
];

export function okResponse(output: unknown, extra: Partial<RunStageResponse> = {}): RunStageResponse {
  return { status: 200, ok: true, output, impl: "mock-fixture", durationMs: 12, ...extra };
}
