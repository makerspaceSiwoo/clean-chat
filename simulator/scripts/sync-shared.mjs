// 공통 자료 동기화: 레포 루트의 공통 폴더 → 웹앱이 쓰는 생성 파일 (ADR-0015)
//
//   ../fixtures/<stage>/*.jsonl        → src/mocks/generated/fixtures.json    (Mock 응답 데이터)
//   ../contracts/stages.schema.json    → src/shared/generated/contracts.json  (런타임: Stage 목록·출력 필드)
//                                      → src/shared/generated/contracts.ts    (TS 타입, json-schema-to-typescript)
//
// - 데스크톱 앱(Python)과 같은 원본을 쓰므로 웹앱에 손으로 베낀 사본이 없다. 생성 파일은 git 제외.
// - dev / build / test / typecheck 전에 자동 실행(package.json 의 pre* 스크립트). Vercel 빌드도 같다.
// - fixtures 줄 수가 다르거나 JSON·계약 파일이 깨져 있으면 빌드를 실패시킨다(잘못된 Mock 으로 QA 하지 않게).
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const REPO = join(here, "..", "..");
const FIXTURES = process.env.FIXTURES_DIR ?? join(REPO, "fixtures");
const CONTRACTS = process.env.CONTRACTS_FILE ?? join(REPO, "contracts", "stages.schema.json");
const OUT_FIXTURES = join(here, "..", "src", "mocks", "generated", "fixtures.json");
const OUT_SHARED = join(here, "..", "src", "shared", "generated");

function write(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text, "utf-8");
}

// ── fixtures ────────────────────────────────────────────────
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

function syncFixtures() {
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
  write(OUT_FIXTURES, JSON.stringify({ source: "fixtures/", stages }, null, 2) + "\n");
  const total = Object.values(stages).reduce((n, c) => n + c.length, 0);
  console.log(`✅ Mock 데이터: Stage ${Object.keys(stages).length}개, 케이스 ${total}개`);
}

// ── contracts ───────────────────────────────────────────────
async function syncContracts() {
  if (!existsSync(CONTRACTS)) throw new Error(`공통 계약 파일 없음: ${CONTRACTS} → uv run python scripts/export_contracts.py`);
  let doc;
  try {
    doc = JSON.parse(readFileSync(CONTRACTS, "utf-8"));
  } catch (e) {
    throw new Error(`${CONTRACTS} JSON 오류: ${e.message}`);
  }
  if (!doc.stages || !doc.$defs) throw new Error(`${CONTRACTS}: stages / $defs 가 없습니다`);

  // 런타임용: Stage → 입력·출력 모델 이름, 출력 필드 목록 (pydantic 은 모든 필드를 직렬화 → 출력에 다 있어야 함)
  const name = (ref) => ref.split("/").pop();
  const stages = Object.fromEntries(
    Object.entries(doc.stages).map(([stage, io]) => {
      const output = name(io.output.$ref);
      const def = doc.$defs[output];
      if (!def) throw new Error(`계약에 ${output} 정의가 없습니다 (Stage ${stage})`);
      return [stage, { input: name(io.input.$ref), output, outputFields: Object.keys(def.properties ?? {}) }];
    }),
  );
  write(join(OUT_SHARED, "contracts.json"), JSON.stringify({ schemaVersion: doc.schema_version, stages }, null, 2) + "\n");

  // TS 타입: 모든 $defs 를 한 번에 (Stage 목록은 StageIO 로).
  // 필드마다 붙은 title(pydantic 자동) 을 지워야 Id1·Speaker2 같은 군더더기 별칭 없이 필드에 타입이 바로 들어간다.
  const defs = structuredClone(doc.$defs);
  for (const def of Object.values(defs)) {
    for (const prop of Object.values(def.properties ?? {})) delete prop.title;
  }
  const root = {
    title: "SharedContracts",
    type: "object",
    additionalProperties: false,
    properties: Object.fromEntries(Object.keys(defs).map((k) => [k, { $ref: `#/$defs/${k}` }])),
    required: Object.keys(defs),
    $defs: defs,
  };
  const banner = `/* 자동 생성 — 직접 고치지 마세요. 원본: contracts/stages.schema.json (schemas.py ${doc.schema_version}) */`;
  const ts = await compile(root, "SharedContracts", { bannerComment: banner, additionalProperties: false, unreachableDefinitions: true, format: true });
  const stageIO = Object.entries(stages)
    .map(([s, io]) => `  ${s}: { input: ${io.input}; output: ${io.output} };`)
    .join("\n");
  write(
    join(OUT_SHARED, "contracts.ts"),
    `${ts}\nexport const SCHEMA_VERSION = ${JSON.stringify(doc.schema_version)};\n\n/** Stage 이름 → 입력/출력 타입 */\nexport interface StageIO {\n${stageIO}\n}\n`,
  );
  console.log(`✅ 공통 계약: Stage ${Object.keys(stages).length}개, 모델 ${Object.keys(doc.$defs).length}개 (schema ${doc.schema_version})`);
}

syncFixtures();
await syncContracts();
