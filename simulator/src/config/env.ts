/**
 * 환경 변수 → 앱 설정 (한곳에서만 읽는다).
 *
 * - main / develop 서버는 같은 코드를 쓰고 환경 변수만 다르게 띄운다(.env.example 참고).
 * - NEXT_PUBLIC_* 는 빌드 시점에 코드에 박히므로 process.env.NEXT_PUBLIC_X 형태로 "그대로" 써야 한다(동적 접근 금지).
 * - 값이 잘못돼도 앱을 멈추지 않는다: 기본값으로 대신하고 warnings 에 남겨 화면 상단에 보여 준다.
 */

export type AppEnv = "local" | "develop" | "main";
export type ApiMode = "mock" | "http";

export interface AppConfig {
  appEnv: AppEnv;
  apiMode: ApiMode;
  apiBaseUrl: string;
  apiTimeoutMs: number;
  mockLatencyMs: number;
  warnings: string[];
}

export interface RawEnv {
  NEXT_PUBLIC_APP_ENV?: string;
  NEXT_PUBLIC_API_MODE?: string;
  NEXT_PUBLIC_API_BASE_URL?: string;
  NEXT_PUBLIC_API_TIMEOUT_MS?: string;
  NEXT_PUBLIC_MOCK_LATENCY_MS?: string;
}

const APP_ENVS: readonly AppEnv[] = ["local", "develop", "main"];
const API_MODES: readonly ApiMode[] = ["mock", "http"];

function pick<T extends string>(value: string | undefined, allowed: readonly T[], fallback: T, name: string, warnings: string[]): T {
  if (value === undefined || value === "") return fallback;
  if ((allowed as readonly string[]).includes(value)) return value as T;
  warnings.push(`${name}="${value}" 은 쓸 수 없는 값이라 "${fallback}" 로 대신합니다 (허용: ${allowed.join(", ")})`);
  return fallback;
}

function int(value: string | undefined, fallback: number, name: string, warnings: string[], min = 0, max = 120_000): number {
  if (value === undefined || value === "") return fallback;
  const n = Number(value);
  if (Number.isInteger(n) && n >= min && n <= max) return n;
  warnings.push(`${name}="${value}" 은 ${min}~${max} 사이 정수가 아니라 ${fallback} 로 대신합니다`);
  return fallback;
}

/** 순수 함수 (테스트용으로 raw 값을 주입할 수 있음) */
export function parseConfig(raw: RawEnv): AppConfig {
  const warnings: string[] = [];
  const appEnv = pick(raw.NEXT_PUBLIC_APP_ENV, APP_ENVS, "local", "NEXT_PUBLIC_APP_ENV", warnings);
  let apiMode = pick(raw.NEXT_PUBLIC_API_MODE, API_MODES, "mock", "NEXT_PUBLIC_API_MODE", warnings);
  let apiBaseUrl = (raw.NEXT_PUBLIC_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
  if (apiMode === "http") {
    try {
      const url = new URL(apiBaseUrl);
      if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("protocol");
    } catch {
      warnings.push(`NEXT_PUBLIC_API_BASE_URL="${apiBaseUrl}" 이 올바른 http(s) 주소가 아니라 mock 모드로 실행합니다`);
      apiMode = "mock";
      apiBaseUrl = "";
    }
  }
  return {
    appEnv,
    apiMode,
    apiBaseUrl,
    apiTimeoutMs: int(raw.NEXT_PUBLIC_API_TIMEOUT_MS, 10_000, "NEXT_PUBLIC_API_TIMEOUT_MS", warnings, 100),
    mockLatencyMs: int(raw.NEXT_PUBLIC_MOCK_LATENCY_MS, 500, "NEXT_PUBLIC_MOCK_LATENCY_MS", warnings, 0, 30_000),
    warnings,
  };
}

export const appConfig: AppConfig = parseConfig({
  NEXT_PUBLIC_APP_ENV: process.env.NEXT_PUBLIC_APP_ENV,
  NEXT_PUBLIC_API_MODE: process.env.NEXT_PUBLIC_API_MODE,
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
  NEXT_PUBLIC_API_TIMEOUT_MS: process.env.NEXT_PUBLIC_API_TIMEOUT_MS,
  NEXT_PUBLIC_MOCK_LATENCY_MS: process.env.NEXT_PUBLIC_MOCK_LATENCY_MS,
});
