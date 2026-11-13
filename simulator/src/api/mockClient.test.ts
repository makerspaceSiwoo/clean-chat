import { AbortError, createMockClient, type MockScenario } from "./mockClient";
import { CASES } from "@/test/fixtures";

const make = (scenario: MockScenario = "normal") =>
  createMockClient({ cases: { incoming_policy: CASES }, latencyMs: 0, timeoutMs: 5, scenario: () => scenario });

describe("mockClient", () => {
  it("fixtures 와 구조가 같은 입력이면 기대값을 200 으로 돌려준다 (키 순서 무관)", async () => {
    const res = await make().runStage({ stageId: "incoming_policy", input: { message: { text: "용 먼저", id: "L3" } } });
    expect(res).toMatchObject({ status: 200, ok: true, output: CASES[0]!.expected, impl: "mock-fixture" });
  });

  it("fixtures 에 없는 입력은 값을 지어내지 않고 404", async () => {
    const res = await make().runStage({ stageId: "incoming_policy", input: { message: { id: "?" } } });
    expect(res).toMatchObject({ status: 404, ok: false, output: null });
    expect(res.error).toContain("fixtures 에 없는 입력");
  });

  it("케이스가 없는 Stage 는 400", async () => {
    const res = await make().runStage({ stageId: "ocr", input: {} });
    expect(res.status).toBe(400);
  });

  it.each([
    ["server-error", 500],
    ["timeout", 0],
    ["empty", 200],
  ] as const)("장애 흉내 %s → 코드 %i, ok=false", async (scenario, status) => {
    const res = await make(scenario).runStage({ stageId: "incoming_policy", input: CASES[0]!.input });
    expect(res).toMatchObject({ status, ok: false, output: null });
  });

  it("취소하면 AbortError", async () => {
    const client = createMockClient({ cases: {}, latencyMs: 1000, timeoutMs: 10 });
    const ac = new AbortController();
    const p = client.runStage({ stageId: "parse", input: {} }, { signal: ac.signal });
    ac.abort();
    await expect(p).rejects.toBeInstanceOf(AbortError);
  });
});
