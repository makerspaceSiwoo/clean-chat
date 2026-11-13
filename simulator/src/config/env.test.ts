import { parseConfig } from "./env";

describe("parseConfig", () => {
  it("값이 없으면 로컬 + mock 기본값", () => {
    expect(parseConfig({})).toMatchObject({ appEnv: "local", apiMode: "mock", apiTimeoutMs: 10000, mockLatencyMs: 500, warnings: [] });
  });

  it("develop 서버 + http 모드 설정을 읽는다 (끝의 / 제거)", () => {
    const c = parseConfig({ NEXT_PUBLIC_APP_ENV: "develop", NEXT_PUBLIC_API_MODE: "http", NEXT_PUBLIC_API_BASE_URL: "https://sim-dev.example.com/" });
    expect(c).toMatchObject({ appEnv: "develop", apiMode: "http", apiBaseUrl: "https://sim-dev.example.com", warnings: [] });
  });

  it("잘못된 값은 멈추지 않고 기본값 + 경고", () => {
    const c = parseConfig({ NEXT_PUBLIC_APP_ENV: "prod", NEXT_PUBLIC_MOCK_LATENCY_MS: "-5" });
    expect(c.appEnv).toBe("local");
    expect(c.mockLatencyMs).toBe(500);
    expect(c.warnings).toHaveLength(2);
  });

  it("http 모드인데 주소가 잘못되면 mock 으로 대신한다", () => {
    const c = parseConfig({ NEXT_PUBLIC_API_MODE: "http", NEXT_PUBLIC_API_BASE_URL: "not a url" });
    expect(c.apiMode).toBe("mock");
    expect(c.warnings[0]).toContain("mock 모드로 실행");
  });
});
