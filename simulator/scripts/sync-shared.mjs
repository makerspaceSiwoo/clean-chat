// 공통 자료 동기화: 레포 루트의 공통 폴더 → 웹앱이 쓰는 생성 파일 (ADR-0015, ADR-0017)
//
//   ../fixtures/<모듈>/input.jsonl     → src/examples/generated/examples.json (입력 예시만. 기대값·Mock 응답은 없음)
//   ../contracts/modules.schema.json   → src/shared/generated/contracts.json  (런타임: 모듈 목록·입출력 모델 이름)
//                                      → src/shared/generated/contracts.ts    (TS 타입, json-schema-to-typescript)
//
// - 데스크톱 앱(Python)과 같은 원본을 쓰므로 웹앱에 손으로 베낀 사본이 없다. 생성 파일은 git 제외.
// - dev / build / test / typecheck 전에 자동 실행(package.json 의 pre* 스크립트). Vercel 빌드도 같다.
// - JSON·계약 파일이 깨져 있으면 빌드를 실패시킨다.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const REPO = join(here, "..", "..");
const FIXTURES = process.env.FIXTURES_DIR ?? join(REPO, "fixtures");
const CONTRACTS = process.env.CONTRACTS_FILE ?? join(REPO, "contracts", "modules.schema.json");
const OUT_EXAMPLES = join(here, "..", "src", "examples", "generated", "examples.json");
const OUT_SHARED = join(here, "..", "src", "shared", "generated");

function write(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text, "utf-8");
}

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

// 사람이 고르기 쉬운 예시 이름 (입력의 대표 문장)
function labelOf(input, i) {
  const msg = input?.line ?? input?.message;
  const id = input?.id ?? msg?.id ?? input?.session?.id;
  const text = msg?.text ?? input?.image_path ?? (input?.speaker ? `${input.kind ?? ""} · 대상 ${input.speaker}` : undefined);
  return [`#${i + 1}`, id, text].filter(Boolean).join(" · ");
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
  if (!doc.modules || !doc.$defs) throw new Error(`${CONTRACTS}: modules / $defs 가 없습니다`);

  const name = (ref) => ref.split("/").pop();
  const modules = Object.fromEntries(
    Object.entries(doc.modules).map(([id, m]) => {
      const input = name(m.input.$ref);
      const output = name(m.output.$ref);
      for (const model of [input, output]) if (!doc.$defs[model]) throw new Error(`계약에 ${model} 정의가 없습니다 (모듈 ${id})`);
      return [id, { title: m.title, path: m.path, input, output, inputFields: Object.keys(doc.$defs[input].properties ?? {}) }];
    }),
  );
  write(join(OUT_SHARED, "contracts.json"), JSON.stringify({ schemaVersion: doc.schema_version, modules }, null, 2) + "\n");

  // TS 타입: 모든 $defs 를 한 번에. 필드마다 붙은 title(pydantic 자동)을 지워야 군더더기 별칭이 안 생긴다.
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
  const banner = `/* 자동 생성 — 직접 고치지 마세요. 원본: contracts/modules.schema.json (schemas.py ${doc.schema_version}) */`;
  const ts = await compile(root, "SharedContracts", { bannerComment: banner, additionalProperties: false, unreachableDefinitions: true, format: true });
  const io = Object.entries(modules)
    .map(([id, m]) => `  ${id}: { input: ${m.input}; output: ${m.output} };`)
    .join("\n");
  write(
    join(OUT_SHARED, "contracts.ts"),
    `${ts}\nexport const SCHEMA_VERSION = ${JSON.stringify(doc.schema_version)};\n\n/** 모듈 이름 → 입력/출력 타입 */\nexport interface ModuleIO {\n${io}\n}\n`,
  );
  console.log(`✅ 공통 계약: 모듈 ${Object.keys(modules).length}개, 모델 ${Object.keys(doc.$defs).length}개 (schema ${doc.schema_version})`);
  return Object.keys(modules);
}

// ── 입력 예시 (fixtures 의 input 만) ─────────────────────────
function syncExamples(moduleIds) {
  const modules = {};
  for (const id of moduleIds) {
    const inputs = readJsonl(join(FIXTURES, id, "input.jsonl"));
    modules[id] = inputs.map((input, i) => ({ exampleId: `${id}-${i + 1}`, label: labelOf(input, i), input }));
  }
  write(OUT_EXAMPLES, JSON.stringify({ source: "fixtures/<모듈>/input.jsonl", modules }, null, 2) + "\n");
  const total = Object.values(modules).reduce((n, c) => n + c.length, 0);
  console.log(`✅ 입력 예시: 모듈 ${moduleIds.length}개, 예시 ${total}개`);
}

syncExamples(await syncContracts());
