/**
 * 이미지 첨부(OCR 등) 규칙.
 * 첨부한 이미지는 실행할 때 base64 로 로컬 모듈 서버에 보낸다. 서버가 .clean-chat/uploads/ 에 저장하고
 * 입력의 경로 필드(image_path)를 그 경로로 바꿔 실제 모듈 함수에 넘긴다 (src/clean_chat/core/server.py).
 */
export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/bmp"] as const;
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

/** 첨부할 수 없는 파일이면 이유, 괜찮으면 undefined */
export function checkImageFile(file: { name: string; type: string; size: number }): string | undefined {
  if (!(IMAGE_TYPES as readonly string[]).includes(file.type)) return `이미지 파일만 첨부할 수 있습니다 (PNG·JPG·WEBP·BMP): ${file.name}`;
  if (file.size > MAX_IMAGE_BYTES) return `10MB 이하 이미지만 첨부할 수 있습니다: ${file.name}`;
  return undefined;
}

/** 입력 JSON 에 넣어 둘 표시용 경로 (실제 경로는 서버가 저장한 뒤 바꿔 넣는다) */
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

/** 파일 → data: 접두사 없는 base64 (서버로 보낼 본문) */
export function fileToBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("파일을 읽을 수 없습니다"));
    reader.onload = () => {
      const url = String(reader.result ?? "");
      resolve(url.slice(url.indexOf(",") + 1)); // "data:image/png;base64,...." → "...."
    };
    reader.readAsDataURL(file);
  });
}
