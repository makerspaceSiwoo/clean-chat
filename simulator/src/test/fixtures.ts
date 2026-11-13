/** 테스트 공용 가짜 데이터 (레포 fixtures 와 무관하게 고정) */
import type { ModuleMeta } from "@/modules/registry";
import type { StageContract } from "@/shared/contracts";
import type { FixtureCase } from "@/mocks/fixtures";
import type { RunStageResponse } from "@/types/api";

export const META: ModuleMeta = {
  stageId: "incoming_policy",
  title: "수신 정책",
  modulePath: "src/clean_chat/policy/impl.py",
  workPackage: "WP1",
  flow: "A",
  description: "테스트용",
  summaryFields: [
    { label: "처리", path: "action" },
    { label: "표시 문장", path: "display_text" },
  ],
  latencyBudgetMs: 100,
  strict: true,
  manualChecks: ["SPEC 표와 같은가?"],
};

/** Decision 계약 모양을 모두 갖춘 기대값 (화면 통합 테스트는 실제 공통 계약으로 필드를 검사함) */
const decision = (msg_id: string, action: string, display_text: string | null) => ({
  msg_id,
  is_me: false,
  action,
  display_text,
  target: "정글",
  report: true,
  complaint_candidate: false,
  reason: "테스트",
});

export const CASES: FixtureCase[] = [
  { caseId: "c1", label: "#1 · L3 · 용 먼저", input: { message: { id: "L3", text: "용 먼저" } }, expected: decision("L3", "show_rewritten", "용 먼저 치자") },
  { caseId: "c2", label: "#2 · L4 · 숨김", input: { message: { id: "L4", text: "x" } }, expected: decision("L4", "hide", null) },
];

export function okResponse(output: unknown, extra: Partial<RunStageResponse> = {}): RunStageResponse {
  return { status: 200, ok: true, output, impl: "mock-fixture", durationMs: 12, ...extra };
}

/** 테스트용 계약 (실제 계약과 무관하게 고정) */
export const CONTRACT: StageContract = { input: "PolicyRequest", output: "Decision", outputFields: ["action", "display_text"] };
