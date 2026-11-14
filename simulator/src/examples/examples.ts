/**
 * 입력 예시 = 레포의 fixtures/<모듈>/input.jsonl (scripts/sync-shared.mjs 가 generated/examples.json 으로 변환).
 * 입력만 가져온다. 기대값을 대신 돌려주는 Mock 은 없다 (ADR-0017) — 결과는 항상 실제 모듈 함수가 만든다.
 */
import data from "./generated/examples.json";
import type { ModuleId } from "@/types/contracts";

export interface InputExample {
  exampleId: string;
  /** 고르기 쉬운 이름 (예: "#4 · L3 · 야 정글 ㅂㅅ아 용 먼저 치라고") */
  label: string;
  input: unknown;
}

const modules = (data as { modules: Record<string, InputExample[]> }).modules;

export function getExamples(moduleId: ModuleId): InputExample[] {
  return modules[moduleId] ?? [];
}

export function allExamples(): Record<string, InputExample[]> {
  return modules;
}
