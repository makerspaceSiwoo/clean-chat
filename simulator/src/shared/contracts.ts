/**
 * 공통 계약(런타임). contracts/modules.schema.json 에서 생성된 요약을 읽는다 (scripts/sync-shared.mjs).
 * 모듈 목록, 제목, 구현 위치, 입출력 모델 이름은 여기서만 가져온다 → 손으로 베낀 목록이 없다.
 */
import data from "./generated/contracts.json";
import type { ModuleId } from "@/types/contracts";

export interface ModuleContract {
  /** 예: "채팅 추출 · 시스템 메시지 제외 + 정규화" */
  title: string;
  /** 레포 안 구현 파일 (예: "src/clean_chat/modules/parse/impl.py") */
  path: string;
  /** 입력 모델 이름 (예: "ParseRequest") */
  input: string;
  /** 출력 모델 이름 (예: "ParseResult") */
  output: string;
  /** 입력 모델의 필드 (예: Frame → id, ts, image_path, region) */
  inputFields: string[];
}

const doc = data as { schemaVersion: string; modules: Record<string, ModuleContract> };

export const SCHEMA_VERSION: string = doc.schemaVersion;

/** 계약에 있는 모듈 이름 (core/modules.py 의 순서) */
export function contractModuleNames(): string[] {
  return Object.keys(doc.modules);
}

export function getContract(moduleId: ModuleId): ModuleContract {
  const c = doc.modules[moduleId];
  if (c === undefined) throw new Error(`공통 계약에 없는 모듈: ${moduleId} (contracts/modules.schema.json 을 다시 만드세요)`);
  return c;
}
