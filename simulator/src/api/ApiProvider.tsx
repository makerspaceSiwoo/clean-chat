"use client";
/**
 * API 클라이언트 주입 (의존성 주입). 컴포넌트는 useApiClient() 로만 API 를 부르고, 어떤 구현인지 모른다.
 * - 기본: 환경 변수(API_MODE)에 따라 Mock / HTTP 클라이언트 생성
 * - 테스트: <ApiProvider client={가짜}> 로 바꿔 끼움
 * mock 모드의 장애 흉내(mockScenario)도 여기서 관리한다.
 */
import { createContext, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { appConfig, type AppConfig } from "@/config/env";
import { allFixtureCases } from "@/mocks/fixtures";
import { createHttpClient } from "./httpClient";
import { createMockClient, type MockScenario } from "./mockClient";
import type { StageApiClient } from "@/types/api";

interface ApiContextValue {
  client: StageApiClient;
  config: AppConfig;
  mockScenario: MockScenario;
  setMockScenario: (s: MockScenario) => void;
}

const ApiContext = createContext<ApiContextValue | null>(null);

export function createDefaultClient(config: AppConfig, scenario: () => MockScenario): StageApiClient {
  if (config.apiMode === "http") return createHttpClient({ baseUrl: config.apiBaseUrl, timeoutMs: config.apiTimeoutMs });
  return createMockClient({ cases: allFixtureCases(), latencyMs: config.mockLatencyMs, timeoutMs: config.apiTimeoutMs, scenario });
}

export function ApiProvider({ children, client, config = appConfig }: { children: ReactNode; client?: StageApiClient; config?: AppConfig }) {
  const [mockScenario, setMockScenario] = useState<MockScenario>("normal");
  const scenarioRef = useRef(mockScenario);
  scenarioRef.current = mockScenario;
  const resolved = useMemo(() => client ?? createDefaultClient(config, () => scenarioRef.current), [client, config]);
  const value = useMemo(() => ({ client: resolved, config, mockScenario, setMockScenario }), [resolved, config, mockScenario]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiContextValue {
  const ctx = useContext(ApiContext);
  if (ctx === null) throw new Error("useApi 는 <ApiProvider> 안에서만 쓸 수 있습니다");
  return ctx;
}
