import { deepEqual, getPath, hasPath, safeParseJson } from "./json";

describe("json helpers", () => {
  it("safeParseJson 은 예외 대신 오류 문장을 돌려준다", () => {
    expect(safeParseJson('{"a":1}')).toEqual({ ok: true, value: { a: 1 } });
    expect(safeParseJson("")).toMatchObject({ ok: false, error: "입력이 비어 있습니다" });
    expect(safeParseJson("{a:1}")).toMatchObject({ ok: false });
  });

  it("deepEqual 은 키 순서를 무시하고 배열 순서는 지킨다", () => {
    expect(deepEqual({ a: 1, b: [1, { c: null }] }, { b: [1, { c: null }], a: 1 })).toBe(true);
    expect(deepEqual([1, 2], [2, 1])).toBe(false);
    expect(deepEqual({ a: undefined }, {})).toBe(false);
    expect(deepEqual(null, {})).toBe(false);
  });

  it("hasPath 는 null 값도 '있음' 으로 본다", () => {
    expect(hasPath({ a: { b: null } }, "a.b")).toBe(true);
    expect(hasPath({ a: {} }, "a.b")).toBe(false);
    expect(getPath({ lines: [{ text: "x" }] }, "lines.0.text")).toBe("x");
    expect(getPath({ lines: [1, 2] }, "lines.length")).toBe(2);
  });
});
