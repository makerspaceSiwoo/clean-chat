/** 테스트 공용 가짜 데이터 (레포 fixtures 와 무관하게 고정) */
import type { InputExample } from "@/examples/examples";
import type { ModuleMeta } from "@/modules/registry";
import type { RunModuleResponse } from "@/types/api";

export const META: ModuleMeta = { moduleId: "parse", number: "②", description: "테스트용 설명" };
export const OCR_META: ModuleMeta = { moduleId: "ocr", number: "①", description: "테스트용 OCR", imageField: "image_path" };

export const EXAMPLES: InputExample[] = [
  { exampleId: "e1", label: "#1 · L3 · 용 먼저", input: { line: { id: "L3", text: "용 먼저" }, my_name: "나" } },
  { exampleId: "e2", label: "#2 · L4 · 숨김", input: { line: { id: "L4", text: "x" }, my_name: "나" } },
];

export const OCR_EXAMPLES: InputExample[] = [
  { exampleId: "o1", label: "#1 · F0", input: { id: "F0", ts: 1, image_path: "fixtures/ocr/images/sample_01.png", region: { x: 0, y: 0, w: 1, h: 1 } } },
];

export function okResponse(output: unknown, extra: Partial<RunModuleResponse> = {}): RunModuleResponse {
  return { status: 200, ok: true, output, durationMs: 12, ...extra };
}

export function errorResponse(status: number, error: string): RunModuleResponse {
  return { status, ok: false, output: null, error, durationMs: 3 };
}
