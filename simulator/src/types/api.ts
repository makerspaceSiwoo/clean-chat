/**
 * 웹앱 ↔ 시뮬레이션 API 사이의 요청/응답 형식.
 *
 * HTTP 계약 (API_MODE=http):  POST {BASE_URL}/stages/{stageId}/run
 *   요청 본문: RunStageRequest   응답 본문: StageRunBody (HTTP 상태 코드는 RunStageResponse.status 로 옮겨 담음)
 * Mock 모드도 같은 RunStageResponse 를 돌려준다 → 화면 코드는 어느 쪽인지 모른다.
 */
import type { StageId } from "./contracts";

export interface RunStageRequest {
  stageId: StageId;
  /** Stage 입력 모델 JSON (StageContracts[stageId]["input"]) */
  input: unknown;
}

/** 서버가 돌려주는 본문 */
export interface StageRunBody {
  /** Stage 출력 모델 JSON. 실패면 null */
  output: unknown | null;
  /** 어떤 구현이 응답했나: "mock-fixture" | "mock" | "real" 등 */
  impl: string;
  /** 실패 이유 (사람이 읽는 문장) */
  error?: string;
}

export interface RunStageResponse extends StageRunBody {
  /** HTTP 상태 코드. 네트워크 오류·타임아웃은 0 */
  status: number;
  ok: boolean;
  /** 요청부터 응답까지 걸린 시간(ms), 화면에서 잰 값 */
  durationMs: number;
}

/** API 클라이언트 (포트). Mock 과 HTTP 구현을 바꿔 끼운다 — UI 는 이 인터페이스만 안다. */
export interface StageApiClient {
  readonly kind: "mock" | "http";
  runStage(request: RunStageRequest, options?: { signal?: AbortSignal }): Promise<RunStageResponse>;
}
