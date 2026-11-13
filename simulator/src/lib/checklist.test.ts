import { evaluateChecklist, summarize } from "./checklist";
import { META, okResponse } from "@/test/fixtures";

const byId = (items: ReturnType<typeof evaluateChecklist>) => Object.fromEntries(items.map((i) => [i.id, i.status]));

describe("evaluateChecklist", () => {
  const output = { action: "hide", display_text: null };

  it("정상 응답 + 기대값 일치면 모두 통과 (mock 모드는 응답 시간 건너뜀)", () => {
    const r = byId(evaluateChecklist({ meta: META, response: okResponse(output), expected: output, apiMode: "mock" }));
    expect(r).toMatchObject({ "status-200": "pass", "has-output": "pass", "field-action": "pass", "field-display_text": "pass", expected: "pass", latency: "skip" });
  });

  it("필수 필드가 빠지면 실패", () => {
    const r = byId(evaluateChecklist({ meta: META, response: okResponse({ action: "hide" }), apiMode: "mock" }));
    expect(r["field-display_text"]).toBe("fail");
    expect(r.expected).toBe("skip");
  });

  it("STRICT 모듈은 기대값과 다르면 실패, AI 모듈은 경고", () => {
    const strict = byId(evaluateChecklist({ meta: META, response: okResponse({ action: "show", display_text: "x" }), expected: output, apiMode: "mock" }));
    expect(strict.expected).toBe("fail");
    const ai = byId(evaluateChecklist({ meta: { ...META, strict: false }, response: okResponse({ action: "show", display_text: "x" }), expected: output, apiMode: "mock" }));
    expect(ai.expected).toBe("warn");
  });

  it("오류 응답이면 코드·출력 실패, 필드 검사는 건너뜀", () => {
    const res = { status: 500, ok: false, output: null, impl: "mock", error: "서버 오류", durationMs: 5 };
    const items = evaluateChecklist({ meta: META, response: res, apiMode: "mock" });
    expect(byId(items)).toMatchObject({ "status-200": "fail", "has-output": "fail", "field-action": "skip" });
    expect(summarize(items)).toEqual({ pass: 0, fail: 2, warn: 0, total: 2 });
  });

  it("http 모드에서는 응답 시간 목표를 넘으면 경고", () => {
    const fast = byId(evaluateChecklist({ meta: META, response: okResponse(output, { durationMs: 50 }), apiMode: "http" }));
    const slow = byId(evaluateChecklist({ meta: META, response: okResponse(output, { durationMs: 500 }), apiMode: "http" }));
    expect([fast.latency, slow.latency]).toEqual(["pass", "warn"]);
  });
});
