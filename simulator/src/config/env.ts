/**
 * 환경 변수 → 앱 설정 (한곳에서만 읽는다).
 *
 * - 시뮬레이터는 로컬 모듈 실행 서버(`uv run clean-chat serve`)의 실제 함수만 부른다. Mock 은 없다 (ADR-0017).
 * - NEXT_PUBLIC_* 는 빌드 시점에 코드에 박히므로 process.env.NEXT_PUBLIC_X 형태로 "그대로" 써야 한다(동적 접근 금지).
 * - 값이 잘못돼도 앱을 멈추지 않는다: 기본값으로 대신하고 warnings 에 남겨 화면 상단에 보여 준다.
 */

export type AppEnv = "local" | "develop" | "main";

export const DEFAULT_API_BASE_URL = "http://localhost:8765";

export interface AppConfig {
  appEnv: AppEnv;
  apiBaseUrl: string;
  apiTimeoutMs: number;
  warnings: string[];
}

export interface RawEnv {
  NEXT_PUBLIC_APP_ENV?: string;
  NEXT_PUBLIC_API_BASE_URL?: string;
  NEXT_PUBLIC_API_TIMEOUT_MS?: string;
}

const APP_ENVS: readonly AppEnv[] = ["local", "develop", "main"];

/** 순수 함수 (테스트용으로 raw 값을 주입할 수 있음) */
export function parseConfig(raw: RawEnv): AppConfig {
  const warnings: string[] = [];
  let appEnv: AppEnv = "local";
  if (raw.NEXT_PUBLIC_APP_ENV) {
    if ((APP_ENVS as readonly string[]).includes(raw.NEXT_PUBLIC_APP_ENV)) appEnv = raw.NEXT_PUBLIC_APP_ENV as AppEnv;
    else warnings.push(`NEXT_PUBLIC_APP_ENV="${raw.NEXT_PUBLIC_APP_ENV}" 은 쓸 수 없는 값이라 "local" 로 대신합니다 (허용: ${APP_ENVS.join(", ")})`);
  }

  let apiBaseUrl = (raw.NEXT_PUBLIC_API_BASE_URL ?? "").trim().replace(/\/+$/, "") || DEFAULT_API_BASE_URL;
  try {
    const url = new URL(apiBaseUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("protocol");
  } catch {
    warnings.push(`NEXT_PUBLIC_API_BASE_URL="${apiBaseUrl}" 이 올바른 http(s) 주소가 아니라 ${DEFAULT_API_BASE_URL} 로 대신합니다`);
    apiBaseUrl = DEFAULT_API_BASE_URL;
  }

  let apiTimeoutMs = 30_000;
  if (raw.NEXT_PUBLIC_API_TIMEOUT_MS) {
    const n = Number(raw.NEXT_PUBLIC_API_TIMEOUT_MS);
    if (Number.isInteger(n) && n >= 100 && n <= 600_000) apiTimeoutMs = n;
    else warnings.push(`NEXT_PUBLIC_API_TIMEOUT_MS="${raw.NEXT_PUBLIC_API_TIMEOUT_MS}" 은 100~600000 사이 정수가 아니라 30000 으로 대신합니다`);
  }
  return { appEnv, apiBaseUrl, apiTimeoutMs, warnings };
}

export const appConfig: AppConfig = parseConfig({
  NEXT_PUBLIC_APP_ENV: process.env.NEXT_PUBLIC_APP_ENV,
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
  NEXT_PUBLIC_API_TIMEOUT_MS: process.env.NEXT_PUBLIC_API_TIMEOUT_MS,
});
