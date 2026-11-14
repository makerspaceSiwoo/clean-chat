/**
 * 웹앱 ↔ 로컬 모듈 실행 서버(`uv run clean-chat serve`) 사이의 요청/응답 형식. 서버 쪽: src/clean_chat/core/server.py
 *
 *   POST {BASE_URL}/modules/{moduleId}/run
 *     요청 본문: { input, image?: { name, base64 } }
 *     응답 본문: { output, error? }   200 성공 · 501 구현 없음 · 422 입력 형식 오류 · 500 모듈 예외
 */
import type { ModuleId } from "./contracts";

export interface UploadImage {
  name: string;
  /** 파일 내용 (data: 접두사 없는 base64) */
  base64: string;
}

export interface RunModuleRequest {
  moduleId: ModuleId;
  /** 모듈 입력 모델 JSON */
  input: unknown;
  /** 첨부 이미지 (OCR). 서버가 저장하고 입력의 image_path 를 그 경로로 바꾼다 */
  image?: UploadImage;
}

/** 서버가 돌려주는 본문 */
export interface ModuleRunBody {
  /** 모듈 출력 모델 JSON. 실패면 null */
  output: unknown | null;
  /** 실패 이유 (사람이 읽는 문장) */
  error?: string;
}

export interface RunModuleResponse extends ModuleRunBody {
  /** HTTP 상태 코드. 서버 연결 실패·타임아웃은 0 */
  status: number;
  ok: boolean;
  /** 요청부터 응답까지 걸린 시간(ms), 화면에서 잰 값 */
  durationMs: number;
}

/** API 클라이언트 (포트). 화면은 이 인터페이스만 안다 → 테스트에서 가짜로 바꿔 끼운다 */
export interface ModuleApiClient {
  runModule(request: RunModuleRequest, options?: { signal?: AbortSignal }): Promise<RunModuleResponse>;
}
