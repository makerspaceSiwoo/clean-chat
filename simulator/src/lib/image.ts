/**
 * 이미지 첨부(OCR 등) 규칙. 순수 함수만 둔다.
 * 시뮬레이터는 이미지를 읽거나 서버로 보내지 않는다 — 입력 JSON 의 경로 필드에 파일 이름만 넣는다.
 */
export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/bmp"] as const;
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

/** 첨부할 수 없는 파일이면 이유, 괜찮으면 undefined */
export function checkImageFile(file: { name: string; type: string; size: number }): string | undefined {
  if (!(IMAGE_TYPES as readonly string[]).includes(file.type)) return `이미지 파일만 첨부할 수 있습니다 (PNG·JPG·WEBP·BMP): ${file.name}`;
  if (file.size > MAX_IMAGE_BYTES) return `10MB 이하 이미지만 첨부할 수 있습니다: ${file.name}`;
  return undefined;
}

/** 입력 JSON 에 넣을 경로 (브라우저는 실제 파일 경로를 알 수 없어 이름만) */
export function uploadPath(fileName: string): string {
  return `uploads/${fileName}`;
}

/** 입력 JSON(객체)의 경로 필드를 바꾼 새 객체. 객체가 아니면 undefined */
export function withImagePath(input: unknown, field: string, path: string): Record<string, unknown> | undefined {
  if (typeof input !== "object" || input === null || Array.isArray(input)) return undefined;
  return { ...(input as Record<string, unknown>), [field]: path };
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`;
  return `${(n / 1024 / 1024).toFixed(1)}MB`;
}
