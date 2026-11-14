"use client";
/**
 * API 클라이언트 주입 (의존성 주입). 컴포넌트는 useApi() 로만 API 를 부르고, 어떤 구현인지 모른다.
 * - 기본: 로컬 모듈 실행 서버(HTTP) 클라이언트
 * - 테스트: <ApiProvider client={가짜}> 로 바꿔 끼움
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import { appConfig, type AppConfig } from "@/config/env";
import { createHttpClient } from "./httpClient";
import type { ModuleApiClient } from "@/types/api";

interface ApiContextValue {
  client: ModuleApiClient;
  config: AppConfig;
}

const ApiContext = createContext<ApiContextValue | null>(null);

export function ApiProvider({ children, client, config = appConfig }: { children: ReactNode; client?: ModuleApiClient; config?: AppConfig }) {
  const resolved = useMemo(() => client ?? createHttpClient({ baseUrl: config.apiBaseUrl, timeoutMs: config.apiTimeoutMs }), [client, config]);
  const value = useMemo(() => ({ client: resolved, config }), [resolved, config]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiContextValue {
  const ctx = useContext(ApiContext);
  if (ctx === null) throw new Error("useApi 는 <ApiProvider> 안에서만 쓸 수 있습니다");
  return ctx;
}
