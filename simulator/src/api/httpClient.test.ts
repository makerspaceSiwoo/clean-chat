/** @jest-environment node */
import { createHttpClient } from "./httpClient";

function fakeFetch(status: number, body: string) {
  return jest.fn(async () => new Response(body, { status, headers: { "Content-Type": "application/json" } }));
}

const client = (fetchImpl: typeof fetch, timeoutMs = 1000) => createHttpClient({ baseUrl: "http://localhost:8765", timeoutMs, fetchImpl });

describe("httpClient (로컬 모듈 서버)", () => {
  const request = { moduleId: "parse" as const, input: { line: { id: "L0" } } };

  it("계약대로 POST 하고 output 을 돌려준다", async () => {
    const fetchImpl = fakeFetch(200, JSON.stringify({ output: { line_id: "L0" } }));
    const res = await client(fetchImpl).runModule(request);
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://localhost:8765/modules/parse/run",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ input: request.input }) }),
    );
    expect(res).toMatchObject({ status: 200, ok: true, output: { line_id: "L0" } });
  });

  it("첨부 이미지는 본문에 함께 보낸다", async () => {
    const fetchImpl = fakeFetch(200, JSON.stringify({ output: {} }));
    await client(fetchImpl).runModule({ moduleId: "ocr", input: { id: "F0" }, image: { name: "a.png", base64: "QUJD" } });
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body))).toEqual({ input: { id: "F0" }, image: { name: "a.png", base64: "QUJD" } });
  });

  it("구현 없음(501)과 서버 오류 문장을 그대로 전달한다", async () => {
    const res = await client(fakeFetch(501, JSON.stringify({ output: null, error: "모듈 'parse' 구현이 아직 없습니다" }))).runModule(request);
    expect(res).toMatchObject({ status: 501, ok: false, error: "모듈 'parse' 구현이 아직 없습니다" });
  });

  it("JSON 이 아니거나 계약과 다른 응답은 실패로 바꾼다", async () => {
    const html = await client(fakeFetch(502, "<html>bad gateway</html>")).runModule(request);
    expect(html).toMatchObject({ status: 502, ok: false });
    expect(html.error).toContain("JSON 이 아닌 응답");
    const wrong = await client(fakeFetch(200, JSON.stringify({ result: 1 }))).runModule(request);
    expect(wrong.error).toContain("계약");
  });

  it("서버가 꺼져 있으면 코드 0 + serve 실행 안내 (예외를 던지지 않음)", async () => {
    const down = jest.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const res = await client(down as unknown as typeof fetch).runModule(request);
    expect(res).toMatchObject({ status: 0, ok: false });
    expect(res.error).toContain("uv run clean-chat serve");
  });

  it("타임아웃은 코드 0 + 시간 초과", async () => {
    const hang = jest.fn(
      (_url: string, init?: RequestInit) => new Promise<Response>((_, reject) => init?.signal?.addEventListener("abort", () => reject(new Error("aborted")))),
    );
    const slow = await client(hang as unknown as typeof fetch, 20).runModule(request);
    expect(slow.error).toContain("시간 초과");
  });
});
