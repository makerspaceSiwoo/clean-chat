/**
 * 공통 계약(contracts/) ↔ 화면 메타(registry) ↔ Mock 데이터(fixtures) 어긋남 감지 (ADR-0015).
 * 모듈이 develop 에 병합되며 schemas.py·fixtures 가 바뀌었는데 웹앱을 안 고치면 여기서 먼저 깨진다.
 */
import { hasPath } from "@/lib/json";
import { allFixtureCases } from "@/mocks/fixtures";
import { contractStageNames, getContract } from "@/shared/contracts";
import { MODULES } from "./registry";

const fixtures = allFixtureCases();

describe("공통 계약 ↔ registry ↔ fixtures", () => {
  it("계약의 Stage 와 registry 의 Stage 가 빠짐없이 같다 (순서 포함)", () => {
    expect(MODULES.map((m) => m.stageId)).toEqual(contractStageNames());
  });

  it("fixtures 의 모든 Stage 가 계약에 있다", () => {
    const known = new Set(contractStageNames());
    expect(Object.keys(fixtures).filter((s) => !known.has(s))).toEqual([]);
  });

  it.each(MODULES.map((m) => [m.stageId, m] as const))("%s: 요약 필드가 출력 모델에 있다", (_id, meta) => {
    const fields = new Set(getContract(meta.stageId).outputFields);
    const unknown = meta.summaryFields.map((f) => f.path.split(".")[0]!).filter((k) => !fields.has(k));
    expect(unknown).toEqual([]);
  });

  it("이미지 첨부 필드는 입력 모델에 있는 필드다", () => {
    const wrong = MODULES.filter((m) => m.imageField !== undefined && !getContract(m.stageId).inputFields.includes(m.imageField));
    expect(wrong.map((m) => m.stageId)).toEqual([]);
    expect(MODULES.find((m) => m.stageId === "ocr")?.imageField).toBe("image_path");
  });

  it.each(MODULES.map((m) => [m.stageId, m] as const))("%s: fixtures 기대값이 출력 모델 필드를 모두 가진다", (_id, meta) => {
    const cases = fixtures[meta.stageId] ?? [];
    expect(cases.length).toBeGreaterThan(0);
    const fields = getContract(meta.stageId).outputFields;
    for (const c of cases) {
      const missing = fields.filter((f) => !hasPath(c.expected, f));
      expect({ case: c.caseId, missing }).toEqual({ case: c.caseId, missing: [] });
    }
  });
});
