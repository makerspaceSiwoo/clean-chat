/**
 * 모듈 계약 타입. 손으로 쓰지 않고 공통 계약에서 자동 생성한 타입을 다시 내보낸다 (ADR-0015).
 *
 *   src/clean_chat/core/schemas.py ─(scripts/export_contracts.py)→ contracts/modules.schema.json
 *     ─(simulator/scripts/sync-shared.mjs)→ src/shared/generated/contracts.ts (이 파일이 다시 내보냄)
 */
export * from "@/shared/generated/contracts";
import type { ModuleIO } from "@/shared/generated/contracts";

export type ModuleId = keyof ModuleIO;
export type ModuleInput<M extends ModuleId> = ModuleIO[M]["input"];
export type ModuleOutput<M extends ModuleId> = ModuleIO[M]["output"];
