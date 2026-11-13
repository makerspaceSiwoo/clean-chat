"use client";
/**
 * Stage 실행 상태 관리: idle → loading → success | error.
 * - 실행 중 다시 누르면 이전 요청을 취소하고 새 요청만 반영 (늦게 도착한 옛 응답이 화면을 덮지 않게)
 * - 화면을 떠나면(unmount) 진행 중 요청 취소
 * - 클라이언트가 예외를 던져도(버그) 화면을 깨지 않고 error 상태로 보여 줌
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { RunStageResponse, StageApiClient } from "@/types/api";
import type { StageId } from "@/types/contracts";

export type RunState =
  | { phase: "idle" }
  | { phase: "loading"; startedAt: number }
  | { phase: "success"; response: RunStageResponse }
  | { phase: "error"; response?: RunStageResponse; message: string };

export function useStageRun(client: StageApiClient, stageId: StageId) {
  const [state, setState] = useState<RunState>({ phase: "idle" });
  const controller = useRef<AbortController | null>(null);
  const requestNo = useRef(0);

  useEffect(() => () => controller.current?.abort(), []);

  const run = useCallback(
    async (input: unknown) => {
      controller.current?.abort();
      const ac = new AbortController();
      controller.current = ac;
      const myNo = ++requestNo.current;
      setState({ phase: "loading", startedAt: Date.now() });
      try {
        const response = await client.runStage({ stageId, input }, { signal: ac.signal });
        if (myNo !== requestNo.current) return; // 더 새 요청이 있음 → 무시
        setState(
          response.ok
            ? { phase: "success", response }
            : { phase: "error", response, message: response.error ?? `요청 실패 (코드 ${response.status})` },
        );
      } catch (e) {
        if (myNo !== requestNo.current || ac.signal.aborted) return;
        setState({ phase: "error", message: `클라이언트 오류: ${e instanceof Error ? e.message : String(e)}` });
      }
    },
    [client, stageId],
  );

  const cancel = useCallback(() => {
    controller.current?.abort();
    requestNo.current++;
    setState({ phase: "idle" });
  }, []);

  const reset = useCallback(() => {
    requestNo.current++;
    controller.current?.abort();
    setState({ phase: "idle" });
  }, []);

  return { state, run, cancel, reset };
}
