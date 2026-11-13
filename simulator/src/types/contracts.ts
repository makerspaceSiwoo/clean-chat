/**
 * Stage 계약 타입. 손으로 쓰지 않고 공통 계약에서 자동 생성한 타입을 다시 내보낸다 (ADR-0015).
 *
 *   src/clean_chat/core/schemas.py ─(scripts/export_contracts.py)→ contracts/stages.schema.json
 *     ─(simulator/scripts/sync-shared.mjs)→ src/shared/generated/contracts.ts (이 파일이 다시 내보냄)
 *
 * schemas.py 가 바뀌면 export_contracts.py 만 다시 실행하면 된다. 이 파일은 고칠 필요가 없다.
 */
export * from "@/shared/generated/contracts";
import type { StageIO } from "@/shared/generated/contracts";

/** Stage 이름 → 입력/출력 타입 */
export type StageContracts = StageIO;
export type StageId = keyof StageIO;
export type StageInput<S extends StageId> = StageIO[S]["input"];
export type StageOutput<S extends StageId> = StageIO[S]["output"];
