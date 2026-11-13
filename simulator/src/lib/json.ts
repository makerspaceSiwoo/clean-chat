/** JSON 도우미 (UI·API 공용, 로직 없는 순수 함수) */

export type ParseResult = { ok: true; value: unknown } | { ok: false; error: string };

/** 사용자가 입력한 JSON 문자열을 안전하게 파싱. 예외 대신 오류 문장을 돌려준다. */
export function safeParseJson(text: string): ParseResult {
  if (text.trim() === "") return { ok: false, error: "입력이 비어 있습니다" };
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (e) {
    return { ok: false, error: `JSON 형식 오류: ${e instanceof Error ? e.message : String(e)}` };
  }
}

export function prettyJson(value: unknown): string {
  try {
    const text = JSON.stringify(value, null, 2);
    return text === undefined ? String(value) : text;
  } catch {
    return String(value);
  }
}

/** 구조 비교 (객체 키 순서 무시). fixtures 의 "같은 입력" 판단과 기대값 비교에 쓴다. */
export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b || a === null || b === null || typeof a !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((v, i) => deepEqual(v, b[i]));
  }
  const ao = a as Record<string, unknown>;
  const bo = b as Record<string, unknown>;
  const ak = Object.keys(ao);
  const bk = Object.keys(bo);
  return ak.length === bk.length && ak.every((k) => Object.prototype.hasOwnProperty.call(bo, k) && deepEqual(ao[k], bo[k]));
}

/** "a.b.0.c" 경로가 객체에 "있는지" (값이 null 이어도 키가 있으면 true) */
export function hasPath(value: unknown, path: string): boolean {
  let cur: unknown = value;
  for (const key of path.split(".")) {
    if (cur === null || typeof cur !== "object") return false;
    if (!Object.prototype.hasOwnProperty.call(cur, key)) return false;
    cur = (cur as Record<string, unknown>)[key];
  }
  return true;
}

/** 경로의 값 (없으면 undefined) */
export function getPath(value: unknown, path: string): unknown {
  let cur: unknown = value;
  for (const key of path.split(".")) {
    if (cur === null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[key];
  }
  return cur;
}
