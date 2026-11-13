/**
 * Mock 데이터 = 레포의 fixtures/<stage>/*.jsonl (scripts/sync-fixtures.mjs 가 generated/fixtures.json 으로 변환).
 * 웹앱에 데이터를 따로 복사해 두지 않는다 → 파이썬 Stage 의 mock 과 웹앱 Mock 이 항상 같은 예시를 쓴다.
 */
import data from "./generated/fixtures.json";
import type { StageId } from "@/types/contracts";

export interface FixtureCase {
  caseId: string;
  /** 고르기 쉬운 이름 (예: "#4 · L3 · 야 정글 ㅂㅅ아 용 먼저 치라고") */
  label: string;
  input: unknown;
  expected: unknown;
}

const stages = (data as { stages: Record<string, FixtureCase[]> }).stages;

export function getFixtureCases(stageId: StageId): FixtureCase[] {
  return stages[stageId] ?? [];
}

export function allFixtureCases(): Record<string, FixtureCase[]> {
  return stages;
}
