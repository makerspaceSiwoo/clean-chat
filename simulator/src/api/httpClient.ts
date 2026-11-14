/**
 * 로컬 모듈 실행 서버 클라이언트. 실제 파이썬 모듈 함수를 부른다 (Mock 없음, ADR-0017).
 *
 * 계약: POST {baseUrl}/modules/{moduleId}/run, 본문 { input, image? } → 본문 { output, error? } (types/api.ts)
 * 어떤 실패도 예외로 던지지 않고 RunModuleResponse 로 바꿔 돌려준다(화면은 status/error 만 보면 됨). 취소만 AbortError.
 */
import type { ModuleApiClient, ModuleRunBody, RunModuleRequest, RunModuleResponse } from "@/types/api";

export interface HttpClientOptions {
  baseUrl: string;
  timeoutMs: number;
  fetchImpl?: typeof fetch;
  now?: () => number;
}

export class AbortError extends Error {
  constructor() {
    super("요청이 취소되었습니다");
    this.name = "AbortError";
  }
}

/** 서버가 꺼져 있을 때 보여 줄 안내 */
export function serverDownMessage(baseUrl: string): string {
  return `로컬 모듈 서버(${baseUrl})에 연결할 수 없습니다. 레포 루트에서 'uv run clean-chat serve' 를 먼저 실행하세요.`;
}

function isBody(value: unknown): value is ModuleRunBody {
  return typeof value === "object" && value !== null && "output" in value;
}

export function createHttpClient(options: HttpClientOptions): ModuleApiClient {
  const fetchImpl = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
  const now = options.now ?? (() => performance.now());
  return {
    async runModule(request: RunModuleRequest, opts?: { signal?: AbortSignal }): Promise<RunModuleResponse> {
      const started = now();
      const fail = (status: number, error: string): RunModuleResponse => ({ status, ok: false, output: null, error, durationMs: Math.round(now() - started) });
      const timeout = new AbortController();
      const timer = setTimeout(() => timeout.abort(), options.timeoutMs);
      const onAbort = () => timeout.abort();
      opts?.signal?.addEventListener("abort", onAbort, { once: true });
      try {
        const body = request.image ? { input: request.input, image: request.image } : { input: request.input };
        const res = await fetchImpl(`${options.baseUrl}/modules/${encodeURIComponent(request.moduleId)}/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(body),
          signal: timeout.signal,
        });
        const text = await res.text();
        let parsed: unknown;
        try {
          parsed = text ? JSON.parse(text) : null;
        } catch {
          return fail(res.status, `JSON 이 아닌 응답: ${text.slice(0, 200)}`);
        }
        if (!isBody(parsed)) return fail(res.status, "응답 형식이 계약({ output })과 다릅니다");
        return {
          status: res.status,
          ok: res.ok && parsed.output !== null && parsed.output !== undefined,
          output: parsed.output ?? null,
          error: parsed.error ?? (res.ok ? undefined : `HTTP ${res.status}`),
          durationMs: Math.round(now() - started),
        };
      } catch {
        if (opts?.signal?.aborted) throw new AbortError();
        return fail(0, timeout.signal.aborted ? `시간 초과 (${options.timeoutMs}ms) — 모듈이 너무 오래 걸립니다` : serverDownMessage(options.baseUrl));
      } finally {
        clearTimeout(timer);
        opts?.signal?.removeEventListener("abort", onAbort);
      }
    },
  };
}
