/**
 * Mock API 클라이언트: 실제 모듈 로직 없이 fixtures 기대값을 그대로 돌려준다.
 *
 * 파이썬 MockStage 와 같은 규칙: 입력이 fixtures 의 어떤 케이스와 "구조까지 같을 때만" 그 기대값을 응답(200).
 * 다르면 404 와 안내 문장을 돌려준다(값을 지어내지 않음). 실제 Stage 결과는 API_MODE=http 로 확인한다.
 *
 * QA 용 장애 흉내(mockScenario): "server-error" → 500, "timeout" → 타임아웃, "empty" → 200 인데 출력 없음.
 */
import type { FixtureCase } from "@/mocks/fixtures";
import { deepEqual } from "@/lib/json";
import type { RunStageRequest, RunStageResponse, StageApiClient } from "@/types/api";

export type MockScenario = "normal" | "server-error" | "timeout" | "empty";

export interface MockClientOptions {
  /** Stage 이름 → fixtures 케이스 (주입 가능 — 테스트에서 가짜 데이터 사용) */
  cases: Record<string, FixtureCase[]>;
  latencyMs: number;
  timeoutMs: number;
  /** 다음 요청들에 적용할 장애 흉내 (화면에서 바꿈) */
  scenario?: () => MockScenario;
  now?: () => number;
}

export class AbortError extends Error {
  constructor() {
    super("요청이 취소되었습니다");
    this.name = "AbortError";
  }
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new AbortError());
    const onAbort = () => {
      clearTimeout(timer);
      reject(new AbortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export function createMockClient(options: MockClientOptions): StageApiClient {
  const now = options.now ?? (() => performance.now());
  return {
    kind: "mock",
    async runStage(request: RunStageRequest, opts?: { signal?: AbortSignal }): Promise<RunStageResponse> {
      const started = now();
      const scenario = options.scenario?.() ?? "normal";
      const done = (status: number, output: unknown | null, impl: string, error?: string): RunStageResponse => ({
        status,
        ok: status >= 200 && status < 300 && output !== null,
        output,
        impl,
        error,
        durationMs: Math.round(now() - started),
      });

      if (scenario === "timeout") {
        await wait(options.timeoutMs, opts?.signal);
        return done(0, null, "mock", `시간 초과 (${options.timeoutMs}ms) — Mock 장애 흉내`);
      }
      await wait(options.latencyMs, opts?.signal);
      if (scenario === "server-error") return done(500, null, "mock", "서버 내부 오류 — Mock 장애 흉내");
      if (scenario === "empty") return done(200, null, "mock", "출력이 비어 있음 — Mock 장애 흉내");

      const cases = options.cases[request.stageId];
      if (cases === undefined) return done(400, null, "mock", `알 수 없는 Stage: ${request.stageId}`);
      const hit = cases.find((c) => deepEqual(c.input, request.input));
      if (hit === undefined) {
        return done(
          404,
          null,
          "mock",
          "fixtures 에 없는 입력입니다. Mock 은 fixtures 와 구조까지 같은 입력에만 응답합니다 (실제 결과는 API_MODE=http).",
        );
      }
      return done(200, hit.expected, "mock-fixture");
    },
  };
}
