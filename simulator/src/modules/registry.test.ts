/**
 * 공통 계약(contracts/) ↔ 화면 메타(registry) ↔ 입력 예시(fixtures) 어긋남 감지 (ADR-0015, ADR-0017).
 */
import { allExamples } from "@/examples/examples";
import { contractModuleNames, getContract } from "@/shared/contracts";
import { MODULES } from "./registry";

describe("공통 계약 ↔ registry ↔ 입력 예시", () => {
  it("모듈은 5개이고, 계약의 모듈과 registry 가 빠짐없이 같다 (순서 포함)", () => {
    expect(contractModuleNames()).toEqual(["ocr", "parse", "analyze", "rewrite", "report"]);
    expect(MODULES.map((m) => m.moduleId)).toEqual(contractModuleNames());
  });

  it.each(MODULES.map((m) => [m.moduleId] as const))("%s: 입력 예시가 1개 이상 있다", (id) => {
    expect(allExamples()[id]?.length ?? 0).toBeGreaterThan(0);
  });

  it("계약에 구현 위치가 있다", () => {
    for (const m of MODULES) expect(getContract(m.moduleId).path).toBe(`src/clean_chat/modules/${m.moduleId}/impl.py`);
  });

  it("이미지 첨부 필드는 입력 모델에 있는 필드다", () => {
    const wrong = MODULES.filter((m) => m.imageField !== undefined && !getContract(m.moduleId).inputFields.includes(m.imageField));
    expect(wrong.map((m) => m.moduleId)).toEqual([]);
    expect(MODULES.find((m) => m.moduleId === "ocr")?.imageField).toBe("image_path");
  });
});
