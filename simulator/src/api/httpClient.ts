/**
 * HTTP API 클라이언트: 실제 Stage 실행 서버를 부른다 (API_MODE=http).
 *
 * 계약: POST {baseUrl}/stages/{stageId}/run, 본문 { input } → 본문 { output, impl, error? } (types/api.ts)
 * 어떤 실패도 예외로 던지지 않고 RunStageResponse 로 바꿔 돌려준다(화면은 status/error 만 보면 됨). 취소만 AbortError.
 */
import { AbortError } from "./mockClient";
import type { RunStageRequest, RunStageResponse, StageApiClient, StageRunBody } from "@/types/api";

export interface HttpClientOptions {
  baseUrl: string;
  timeoutMs: number;
  fetchImpl?: typeof fetch;
  now?: () => number;
}

function isBody(value: unknown): value is StageRunBody {
  return typeof value === "object" && value !== null && "output" in value;
}

export function createHttpClient(options: HttpClientOptions): StageApiClient {
  const fetchImpl = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
  const now = options.now ?? (() => performance.now());
  return {
    kind: "http",
    async runStage(request: RunStageRequest, opts?: { signal?: AbortSignal }): Promise<RunStageResponse> {
      const started = now();
      const elapsed = () => Math.round(now() - started);
      const timeout = new AbortController();
      const timer = setTimeout(() => timeout.abort(), options.timeoutMs);
      const onAbort = () => timeout.abort();
      opts?.signal?.addEventListener("abort", onAbort, { once: true });
      try {
        const res = await fetchImpl(`${options.baseUrl}/stages/${encodeURIComponent(request.stageId)}/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ input: request.input }),
          signal: timeout.signal,
        });
        const text = await res.text();
        let body: unknown;
        try {
          body = text ? JSON.parse(text) : null;
        } catch {
          return { status: res.status, ok: false, output: null, impl: "unknown", error: `JSON 이 아닌 응답: ${text.slice(0, 200)}`, durationMs: elapsed() };
        }
        if (!isBody(body)) {
          return { status: res.status, ok: false, output: null, impl: "unknown", error: "응답 형식이 계약({ output, impl })과 다릅니다", durationMs: elapsed() };
        }
        return {
          status: res.status,
          ok: res.ok && body.output !== null && body.output !== undefined,
          output: body.output ?? null,
          impl: typeof body.impl === "string" ? body.impl : "unknown",
          error: body.error ?? (res.ok ? undefined : `HTTP ${res.status}`),
          durationMs: elapsed(),
        };
      } catch (e) {
        if (opts?.signal?.aborted) throw new AbortError();
        const timedOut = timeout.signal.aborted;
        return {
          status: 0,
          ok: false,
          output: null,
          impl: "unknown",
          error: timedOut ? `시간 초과 (${options.timeoutMs}ms)` : `네트워크 오류: ${e instanceof Error ? e.message : String(e)}`,
          durationMs: elapsed(),
        };
      } finally {
        clearTimeout(timer);
        opts?.signal?.removeEventListener("abort", onAbort);
      }
    },
  };
}
