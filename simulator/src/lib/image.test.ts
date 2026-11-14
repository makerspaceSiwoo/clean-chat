import { checkImageFile, fileToBase64, formatBytes, MAX_IMAGE_BYTES, uploadPath, withImagePath } from "./image";

describe("이미지 첨부 규칙", () => {
  it("PNG·JPG 는 통과, 이미지가 아니거나 너무 크면 이유를 돌려준다", () => {
    expect(checkImageFile({ name: "a.png", type: "image/png", size: 100 })).toBeUndefined();
    expect(checkImageFile({ name: "a.jpg", type: "image/jpeg", size: 100 })).toBeUndefined();
    expect(checkImageFile({ name: "a.txt", type: "text/plain", size: 100 })).toMatch(/이미지 파일만/);
    expect(checkImageFile({ name: "big.png", type: "image/png", size: MAX_IMAGE_BYTES + 1 })).toMatch(/10MB/);
  });

  it("입력 객체의 경로 필드만 바꾸고, 객체가 아니면 undefined", () => {
    const input = { id: "F0", image_path: "fixtures/ocr/images/sample_01.png", region: { x: 0 } };
    expect(withImagePath(input, "image_path", uploadPath("chat.png"))).toEqual({ ...input, image_path: "uploads/chat.png" });
    expect(input.image_path).toBe("fixtures/ocr/images/sample_01.png");
    expect(withImagePath([1], "image_path", "x")).toBeUndefined();
    expect(withImagePath(null, "image_path", "x")).toBeUndefined();
  });

  it("크기를 읽기 쉽게", () => {
    expect(formatBytes(500)).toBe("500B");
    expect(formatBytes(2048)).toBe("2.0KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0MB");
  });

  it("파일을 data: 접두사 없는 base64 로", async () => {
    await expect(fileToBase64(new Blob(["ABC"], { type: "image/png" }))).resolves.toBe("QUJD");
  });
});
