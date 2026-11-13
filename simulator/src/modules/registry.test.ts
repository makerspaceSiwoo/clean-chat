/**
 * 레포 fixtures(실제 Mock 데이터) ↔ 모듈 목록(registry) 어긋남 감지.
 * 모듈이 develop 에 병합되며 fixtures·스키마가 바뀌었는데 웹앱을 안 고치면 여기서 먼저 깨진다.
 */
import { hasPath } from "@/lib/json";
import { allFixtureCases } from "@/mocks/fixtures";
import { MODULES } from "./registry";

const fixtures = allFixtureCases();

describe("registry ↔ fixtures", () => {
  it("Stage 이름이 겹치지 않는다", () => {
    expect(new Set(MODULES.map((m) => m.stageId)).size).toBe(MODULES.length);
  });

  it("fixtures 의 모든 Stage 가 registry 에 등록되어 있다 (홈 카드 누락 방지)", () => {
    const registered = new Set<string>(MODULES.map((m) => m.stageId));
    expect(Object.keys(fixtures).filter((s) => !registered.has(s))).toEqual([]);
  });

  it.each(MODULES.map((m) => [m.stageId, m] as const))("%s: fixtures 가 있고 기대값이 필수 필드를 모두 가진다", (_id, meta) => {
    const cases = fixtures[meta.stageId] ?? [];
    expect(cases.length).toBeGreaterThan(0);
    for (const c of cases) {
      const missing = meta.requiredFields.filter((f) => !hasPath(c.expected, f));
      expect({ case: c.caseId, missing }).toEqual({ case: c.caseId, missing: [] });
    }
  });
});
