/**
 * 모듈 5개의 화면용 설명만 둔다. 제목·구현 위치·입출력 모델은 공통 계약(shared/contracts.ts)에서 가져온다 (ADR-0015).
 * 기준 문서: docs/MODULES.md (ADR-0017)
 */
import type { ModuleId } from "@/types/contracts";

export interface ModuleMeta {
  moduleId: ModuleId;
  /** 화면용 번호 (①~⑤) */
  number: string;
  /** 한 줄 설명 */
  description: string;
  /** 입력 JSON 중 이미지 파일 경로 필드. 있으면 입력 칸에 이미지 첨부가 생기고, 서버로 이미지를 보낸다 */
  imageField?: string;
}

export const MODULES: readonly ModuleMeta[] = [
  { moduleId: "ocr", number: "①", description: "채팅창 이미지 → 읽은 줄 전부", imageField: "image_path" },
  { moduleId: "parse", number: "②", description: "줄 → 채팅만 (시스템 메시지·핑 제외) + 우회어 정규화" },
  { moduleId: "analyze", number: "③", description: "누가 누구에게(대상) · 욕설 등급 L0~L3 · 비속어·피드백 조각" },
  { moduleId: "rewrite", number: "④", description: "피드백 조각 → 공손한 문장 1개" },
  { moduleId: "report", number: "⑤", description: "게임 기록 → 신고 문구 / 고소장 초안 (PDF)" },
];

export function findModule(moduleId: string): ModuleMeta | undefined {
  return MODULES.find((m) => m.moduleId === moduleId);
}
