import { DEFAULT_API_BASE_URL, parseConfig } from "./env";

describe("parseConfig", () => {
  it("값이 없으면 로컬 + 로컬 모듈 서버 기본 주소", () => {
    expect(parseConfig({})).toEqual({ appEnv: "local", apiBaseUrl: DEFAULT_API_BASE_URL, apiTimeoutMs: 30000, warnings: [] });
    expect(DEFAULT_API_BASE_URL).toBe("http://localhost:8765");
  });

  it("환경·서버 주소를 읽는다 (끝의 / 제거)", () => {
    const c = parseConfig({ NEXT_PUBLIC_APP_ENV: "develop", NEXT_PUBLIC_API_BASE_URL: "http://localhost:9000/", NEXT_PUBLIC_API_TIMEOUT_MS: "5000" });
    expect(c).toEqual({ appEnv: "develop", apiBaseUrl: "http://localhost:9000", apiTimeoutMs: 5000, warnings: [] });
  });

  it("잘못된 값은 멈추지 않고 기본값 + 경고", () => {
    const c = parseConfig({ NEXT_PUBLIC_APP_ENV: "prod", NEXT_PUBLIC_API_BASE_URL: "not a url", NEXT_PUBLIC_API_TIMEOUT_MS: "-5" });
    expect(c).toMatchObject({ appEnv: "local", apiBaseUrl: DEFAULT_API_BASE_URL, apiTimeoutMs: 30000 });
    expect(c.warnings).toHaveLength(3);
  });
});
