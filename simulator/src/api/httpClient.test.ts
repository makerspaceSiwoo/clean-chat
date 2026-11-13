/** @jest-environment node */
import { createHttpClient } from "./httpClient";

function fakeFetch(status: number, body: string) {
  return jest.fn(async () => new Response(body, { status, headers: { "Content-Type": "application/json" } }));
}

describe("httpClient", () => {
  const request = { stageId: "parse" as const, input: { id: "L0" } };

  it("계약대로 POST 하고 본문을 응답으로 옮긴다", async () => {
    const fetchImpl = fakeFetch(200, JSON.stringify({ output: { line_id: "L0" }, impl: "real" }));
    const res = await createHttpClient({ baseUrl: "http://api", timeoutMs: 1000, fetchImpl }).runStage(request);
    expect(fetchImpl).toHaveBeenCalledWith("http://api/stages/parse/run", expect.objectContaining({ method: "POST", body: JSON.stringify({ input: { id: "L0" } }) }));
    expect(res).toMatchObject({ status: 200, ok: true, output: { line_id: "L0" }, impl: "real" });
  });

  it("서버 오류 코드와 오류 문장을 그대로 전달한다", async () => {
    const res = await createHttpClient({ baseUrl: "http://api", timeoutMs: 1000, fetchImpl: fakeFetch(500, JSON.stringify({ output: null, impl: "real", error: "NotImplementedError" })) }).runStage(request);
    expect(res).toMatchObject({ status: 500, ok: false, error: "NotImplementedError" });
  });

  it("JSON 이 아니거나 계약과 다른 응답은 실패로 바꾼다", async () => {
    const html = await createHttpClient({ baseUrl: "http://api", timeoutMs: 1000, fetchImpl: fakeFetch(502, "<html>bad gateway</html>") }).runStage(request);
    expect(html).toMatchObject({ status: 502, ok: false });
    expect(html.error).toContain("JSON 이 아닌 응답");
    const wrong = await createHttpClient({ baseUrl: "http://api", timeoutMs: 1000, fetchImpl: fakeFetch(200, JSON.stringify({ result: 1 })) }).runStage(request);
    expect(wrong.error).toContain("계약");
  });

  it("네트워크 오류와 타임아웃은 코드 0 으로 돌려준다 (예외를 던지지 않음)", async () => {
    const down = jest.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const res = await createHttpClient({ baseUrl: "http://api", timeoutMs: 1000, fetchImpl: down }).runStage(request);
    expect(res).toMatchObject({ status: 0, ok: false });
    expect(res.error).toContain("네트워크 오류");

    const hang = jest.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_, reject) => init?.signal?.addEventListener("abort", () => reject(new Error("aborted")))),
    );
    const slow = await createHttpClient({ baseUrl: "http://api", timeoutMs: 20, fetchImpl: hang as unknown as typeof fetch }).runStage(request);
    expect(slow.error).toContain("시간 초과");
  });
});
