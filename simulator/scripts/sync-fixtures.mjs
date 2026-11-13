// 레포의 fixtures/<stage>/input.jsonl ↔ expected.jsonl 을 웹앱 Mock 데이터(JSON)로 바꾼다.
//
// - Mock 데이터의 유일한 기준은 파이썬 쪽과 같은 fixtures 폴더다(웹앱에 데이터를 따로 복사해 두지 않는다).
//   그래서 모듈이 develop 에 병합되며 fixtures 가 바뀌면, 다음 빌드에 웹앱 Mock 응답도 자동으로 바뀐다.
// - dev / build / test / typecheck 전에 자동 실행된다(package.json 의 pre* 스크립트). 결과 파일은 git 제외.
// - 입력/기대값 줄 수가 다르거나 JSON 이 깨져 있으면 빌드를 실패시킨다(잘못된 Mock 으로 QA 하지 않게).
import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURES = process.env.FIXTURES_DIR ?? join(here, "..", "..", "fixtures");
const OUT = join(here, "..", "src", "mocks", "generated", "fixtures.json");

function readJsonl(path) {
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf-8")
    .split(/\r?\n/)
    .map((line, i) => ({ line: line.trim(), no: i + 1 }))
    .filter(({ line }) => line && !line.startsWith("//"))
    .map(({ line, no }) => {
      try {
        return JSON.parse(line);
      } catch (e) {
        throw new Error(`${path}:${no} JSON 오류: ${e.message}`);
      }
    });
}

// 사람이 고르기 쉬운 케이스 이름 (입력의 대표 문장)
function labelOf(input, i) {
  const text = input?.text ?? input?.message?.text ?? input?.image_path;
  const speaker = input?.speaker ? `대상 ${input.speaker}` : undefined;
  const id = input?.id ?? input?.message?.id ?? input?.session?.id;
  return [`#${i + 1}`, id, text ?? speaker].filter(Boolean).join(" · ");
}

const stages = {};
if (!existsSync(FIXTURES)) {
  console.warn(`⚠️ fixtures 폴더 없음: ${FIXTURES} → 빈 Mock 데이터로 생성`);
} else {
  for (const name of readdirSync(FIXTURES).sort()) {
    const dir = join(FIXTURES, name);
    if (!statSync(dir).isDirectory() || name === "scenario") continue;
    const inputs = readJsonl(join(dir, "input.jsonl"));
    const expected = readJsonl(join(dir, "expected.jsonl"));
    if (inputs.length !== expected.length) {
      throw new Error(`fixtures/${name}: input ${inputs.length}줄 ≠ expected ${expected.length}줄`);
    }
    stages[name] = inputs.map((input, i) => ({ caseId: `${name}-${i + 1}`, label: labelOf(input, i), input, expected: expected[i] }));
  }
}

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, JSON.stringify({ source: "fixtures/", stages }, null, 2) + "\n", "utf-8");
const total = Object.values(stages).reduce((n, c) => n + c.length, 0);
console.log(`✅ Mock 데이터 생성: Stage ${Object.keys(stages).length}개, 케이스 ${total}개 → src/mocks/generated/fixtures.json`);
