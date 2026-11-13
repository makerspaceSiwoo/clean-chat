/**
 * 공통 계약(런타임). contracts/stages.schema.json 에서 생성된 요약을 읽는다 (scripts/sync-shared.mjs).
 * 화면·체크리스트는 Stage 목록, 입출력 모델 이름, 출력 필드를 여기서만 가져온다 → 손으로 베낀 목록이 없다.
 */
import data from "./generated/contracts.json";
import type { StageId } from "@/types/contracts";

export interface StageContract {
  /** 입력 모델 이름 (예: "PolicyRequest") */
  input: string;
  /** 출력 모델 이름 (예: "Decision") */
  output: string;
  /** 출력 모델의 모든 필드. pydantic 은 모든 필드를 직렬화하므로 응답에 다 있어야 한다 */
  outputFields: string[];
}

const doc = data as { schemaVersion: string; stages: Record<string, StageContract> };

export const SCHEMA_VERSION: string = doc.schemaVersion;

/** 계약에 있는 Stage 이름 (schemas.py 의 STAGE_NAMES 순서) */
export function contractStageNames(): string[] {
  return Object.keys(doc.stages);
}

export function getContract(stageId: StageId): StageContract {
  const c = doc.stages[stageId];
  if (c === undefined) throw new Error(`공통 계약에 없는 Stage: ${stageId} (contracts/stages.schema.json 을 다시 만드세요)`);
  return c;
}
