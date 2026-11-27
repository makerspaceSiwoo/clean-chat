// Clean Chat 전체 흐름 화면 (빌드 없음, 바닐라 JS). 서버: src/clean_chat/sim/flow_api.py
// 캡처 이미지 1장 → ①ocr → ②parse → ③analyze → ④rewrite → 정책 → ⑤report.
// 실행은 POST /api/flow/run → NDJSON 스트림(log · flow 단계 이벤트 · result).
"use strict";

const $ = (id) => document.getElementById(id);
const MODULES = [
  ["ocr", "①", "이미지 → 줄"],
  ["parse", "②", "채팅만 골라냄"],
  ["analyze", "③", "대상·등급"],
  ["rewrite", "④", "피드백 순화"],
  ["report", "⑤", "신고·고소장"],
];
const NOT_CALLED = {
  ocr: "부르지 않음",
  parse: "읽은 줄이 없음",
  analyze: "채팅이 없음",
  rewrite: "L2 이상 + 피드백 조각이 없어 부르지 않음",
  report: "신고·고소 대상 기록이 없어 부르지 않음",
};
const ACTION_KO = {
  show: "그대로 표시",
  show_masked: "비속어 가림",
  show_rewritten: "피드백만 표시",
  hide: "숨김",
};
const HARM_KO = {
  profanity: "욕설",
  family_insult: "패드립",
  sexual_harassment: "성희롱",
  blame: "비난",
  instigation: "정치질",
  threat: "협박",
};
const BADGE = { idle: "실행 전", running: "실행 중…", ok: "끝까지 실행", stopped: "멈춤", error: "오류", timeout: "시간 초과", invalid_input: "입력 오류" };
const KIND_KO = {
  not_implemented: "구현 전",
  platform: "이 OS 미지원",
  empty_result: "빈 결과",
  missing_package: "패키지 없음",
  import_error: "불러오기 실패",
  bad_output: "출력 형식 오류",
  exception: "예외",
  stage_exception: "구성 단계 예외",
  mismatch: "정답과 다름",
};
const STAGE_KO = { game: "게임 시작 (구성)", pipeline: "흐름 연결 (구성)", policy: "정책표 (구성)", post_game: "게임 종료 배치 (구성)" };
const FIELD_KO = { line: "줄", chat: "구분", speaker: "화자", channel: "채널", level: "등급", target: "대상", action: "처리", reports: "신고 대상", complaints: "고소 대상" };
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/bmp"];
const MAX_IMAGE = 10 * 1024 * 1024;

const state = { samples: [], players: [], sample: null, upload: null, controller: null, timer: null, run: null };

// ── 작은 도우미 ─────────────────────────────────────────
function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e[k] = v;
    else e.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null && c !== false) e.append(c instanceof Node ? c : String(c));
  return e;
}
function chip(text, cls = "") {
  return el("span", { class: "chip " + cls }, text);
}
function fbChip(call) {
  if (!call) return null;
  const p = call.problem;
  const out = [];
  if (p) {
    const c = chip(KIND_KO[p.kind] || p.kind, p.severity === "error" ? "err" : "warn");
    c.title = p.message;
    out.push(c);
  }
  if (call.mode === "fallback") out.push(chip("가정", "fb"));
  return out;
}
function fmtTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleString() : "";
}
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = el("textarea", { style: "position:fixed;opacity:0" });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}
function log(text, cls = "") {
  const box = $("console");
  box.append(el("span", cls ? { class: cls } : {}, text + "\n"));
  box.scrollTop = box.scrollHeight;
}

// ── 입력 ───────────────────────────────────────────────
function renderSamples() {
  const box = $("samples");
  box.innerHTML = "";
  for (const s of state.samples) {
    const on = state.sample && state.sample.id === s.id && !state.upload;
    box.append(
      el(
        "button",
        { type: "button", class: "sample", role: "radio", "aria-checked": String(Boolean(on)), onclick: () => pickSample(s.id) },
        el("img", { src: s.imageUrl, alt: "" }),
        el("div", {}, el("b", {}, s.title), el("span", {}, s.description)),
      ),
    );
  }
}
function pickSample(id) {
  if (state.controller) return;
  state.sample = state.samples.find((s) => s.id === id) || state.samples[0];
  state.upload = null;
  $("upload").value = "";
  $("ocr-text").value = state.sample.lines.join("\n");
  $("preview").src = state.sample.imageUrl;
  $("preview").alt = `예시 캡처: ${state.sample.title}`;
  $("preview").hidden = false;
  $("input-error").textContent = "";
  renderSamples();
}
function attachUpload(file) {
  if (!file) return;
  if (!IMAGE_TYPES.includes(file.type)) return ($("input-error").textContent = `이미지 파일만 첨부할 수 있습니다: ${file.name}`);
  if (file.size > MAX_IMAGE) return ($("input-error").textContent = `10MB 이하 이미지만 첨부할 수 있습니다: ${file.name}`);
  const reader = new FileReader();
  reader.onload = () => {
    const url = String(reader.result);
    state.upload = { name: file.name, base64: url.slice(url.indexOf(",") + 1), url };
    $("preview").src = url;
    $("preview").alt = `첨부한 캡처: ${file.name}`;
    $("preview").hidden = false;
    $("ocr-text").value = "";
    $("ocr-text").placeholder = "ocr 모듈이 아직 없으면 이 이미지에서 읽었다고 칠 줄을 여기에 적으세요.\n예) [03:43] [전체] 감자튀김 (룰루): ㅂㅅ같이 하네";
    $("input-error").textContent = "";
    renderSamples();
  };
  reader.readAsDataURL(file);
}
function renderPlayers() {
  $("players").replaceChildren(
    ...state.players.map((p) =>
      el("tr", {}, el("td", {}, p.name + (p.is_me ? " (나)" : "")), el("td", {}, p.champion || ""), el("td", {}, p.team === "ORDER" ? "우리 팀" : "상대 팀")),
    ),
  );
}

// ── 실행 결과 상태 ─────────────────────────────────────
function newRun() {
  return { calls: [], incidents: {}, postGame: null, phase: "idle", done: false, stopped: null, summary: null, current: null, proc: null, expect: null, checks: [] };
}
function callsOf(name) {
  return state.run.calls.filter((c) => c.module === name);
}
function byKey(name, key) {
  const m = {};
  for (const c of callsOf(name)) m[key(c)] = c;
  return m;
}

// ── 그리기 ─────────────────────────────────────────────
// 왜 가정 응답으로 바꿨는지 짧게: 구현 전 / Windows 전용 / 패키지 없음 / 모듈 오류 (구현된 모듈을 "구현 안 됨"으로 읽지 않게)
function fallbackStatus(calls) {
  const reason = (calls.find((c) => c.mode === "fallback") || {}).reason || "";
  if (reason.startsWith("구현 전")) return "구현 전 → 가정 응답";
  if (reason.includes("PlatformNotSupported")) return "구현됨 · Windows 전용 → 가정 응답";
  if (reason.includes("ModuleNotFoundError")) return "구현됨 · 패키지 없음 → 가정 응답";
  return "구현됨 · 실행 오류 → 가정 응답";
}

// 이번 실행에서 이 단계의 오류·경고 수
function stageProblems(name) {
  const ps = callsOf(name).map((c) => c.problem).filter(Boolean);
  const errs = ps.filter((p) => p.severity === "error").length;
  const warns = ps.length - errs;
  if (!ps.length) return null;
  return el("span", { class: "cnt" }, errs ? chip(`오류 ${errs}`, "err") : null, warns ? chip(`경고 ${warns}`, "warn") : null);
}

// ── 정답 비교 (기대값이 있는 예시만, sim/flow_check.py) ──
function fmtExpected(field, v) {
  if (Array.isArray(v) && field !== "reports" && field !== "complaints") return v.map((x) => fmtExpected(field, x)).join(" 또는 ");
  if (field === "level") return `L${v}`;
  if (field === "action") return ACTION_KO[v] || v;
  if (field === "chat") return v ? "채팅" : "시스템";
  if (field === "channel") return v === "all" ? "전체" : "팀";
  if (field === "reports" || field === "complaints") return v.length ? v.join(", ") : "없음";
  if (field === "line") return v == null ? "(없음)" : v;
  return v == null ? "없음" : String(v);
}
function checksFor(stage, itemIds) {
  return state.run.checks.filter((c) => c.stage === stage && itemIds.includes(c.itemId));
}
// 셀에 붙일 비교 결과: 틀리면 빨간 "기대: …", 맞으면 작은 ✓
function checkMarks(checks) {
  if (!checks.length) return { bad: false, nodes: [] };
  const bad = checks.filter((c) => !c.ok);
  const nodes = bad.length
    ? bad.map((c) => {
        const sim = c.similarity != null ? ` · 유사도 ${Math.round(c.similarity * 100)}%` : "";
        const d = el("div", { class: "expect" }, `✗ 기대 ${FIELD_KO[c.field] || c.field}: ${fmtExpected(c.field, c.expected)} (결과: ${fmtExpected(c.field, c.actual)}${sim})`);
        if (c.note) d.title = c.note;
        return d;
      })
    : [el("span", { class: "okmark", title: checks.map((c) => FIELD_KO[c.field] || c.field).join(", ") + " 정답" }, "✓ 정답")];
  return { bad: bad.length > 0, nodes };
}
function accuracyChip(stage) {
  const cs = state.run.checks.filter((c) => c.stage === stage);
  if (!cs.length) return null;
  const ok = cs.filter((c) => c.ok).length;
  return el("span", { class: "cnt" }, chip(`정답 ${ok}/${cs.length}`, ok === cs.length ? "okc" : "err"));
}

function renderStages() {
  const r = state.run;
  const items = MODULES.map(([name, num, title]) => {
    const modes = new Set(callsOf(name).map((c) => c.mode));
    let cls = "",
      status = r.done || r.stopped ? NOT_CALLED[name] : "대기";
    if (modes.size === 2) [cls, status] = ["mixed", "실제 + 가정 응답"];
    else if (modes.has("real")) [cls, status] = ["real", "실제 모듈"];
    else if (modes.has("fallback")) [cls, status] = ["fallback", fallbackStatus(callsOf(name))];
    if (r.stopped && r.stopped.includes(`[${name}]`)) [cls, status] = ["stopped", "여기서 멈춤"];
    if (r.current && r.current.module === name) [cls, status] = [cls + " running", "실행 중…"];
    const n = callsOf(name).length;
    // 가정 응답으로 바꾼 이유 (구현 전 / Windows 전용 / 패키지 없음 등) — 처음 하나만, 전체는 마우스를 올리면
    const why = (callsOf(name).find((c) => c.mode === "fallback") || {}).reason || "";
    const backends = [...new Set(callsOf(name).filter((c) => c.mode === "real").map((c) => c.output.backend).filter(Boolean))];
    return el(
      "li",
      { class: cls, title: why || status },
      el("b", {}, `${num} ${name}`),
      el("span", { class: "muted" }, title + (n ? ` · ${n}번` : "")),
      el("span", {}, status + (backends.length ? ` · backend=${backends.join(",")}` : "")),
      why ? el("span", { class: "why" }, why.replace(/^(구현 전|오류): /, "")) : null,
      stageProblems(name),
      accuracyChip(name),
    );
  });
  if (r.expect) {
    const i = items.findIndex((li) => li.textContent.startsWith("⑤"));
    items.splice(i, 0, el("li", { class: "phase" }, el("b", {}, "정책표"), el("span", { class: "muted" }, "core/policy.py"), el("span", {}, "표시·가림·순화·숨김"), accuracyChip("policy")));
  }
  const phaseKo = { idle: "대기", in_game: "게임 중", post_game: "게임 종료" }[r.phase] || r.phase;
  items.unshift(el("li", { class: "phase" }, el("b", {}, "게임 단계"), el("span", { class: "muted" }, "core/game.py"), el("span", {}, phaseKo)));
  $("stages").replaceChildren(...items);
}

// 지금 실행 중인 호출이 몇 번째 줄을 처리하는지 (parse 는 줄 id, analyze·rewrite 는 메시지 id → 줄 id)
function lineIdOf(call) {
  if (!call) return null;
  if (call.module === "parse") return call.input.line.id;
  if (call.module === "analyze" || call.module === "rewrite") {
    const msgId = call.input.message.id;
    const p = callsOf("parse").find((c) => c.output.message && c.output.message.id === msgId);
    return p ? p.input.line.id : msgId;
  }
  return null;
}

function renderNow() {
  const r = state.run;
  const box = $("now");
  const c = r.current;
  box.classList.toggle("live", Boolean(c));
  if (c) {
    const [, num] = MODULES.find(([n]) => n === c.module);
    const lines = (callsOf("ocr")[0] || { output: { lines: [] } }).output.lines;
    const idx = lines.findIndex((l) => l.id === lineIdOf(c)) + 1;
    const what = {
      ocr: () => "캡처 이미지에서 채팅 줄을 읽는 중",
      parse: () => `줄 ${idx}/${lines.length} — 채팅인지 시스템 메시지인지 나누는 중`,
      analyze: () => `줄 ${idx}/${lines.length} — ${c.input.message.speaker}: "${c.input.message.text}" 대상·등급 판단 중`,
      rewrite: () => `줄 ${idx}/${lines.length} — 피드백 조각 "${c.input.analysis.feedback_spans.join(" / ")}" 순화 중`,
      report: () => `${c.input.speaker} — ${c.input.kind === "report" ? "신고 문구" : "고소장 초안"} 만드는 중`,
    }[c.module]();
    box.textContent = `▶ ${num} ${c.module} 실행 중 · ${what}`;
  } else if (r.done) {
    const real = r.calls.filter((x) => x.mode === "real").length;
    box.textContent = `■ 끝 — 모듈 호출 ${r.calls.length}번 (실제 ${real}번 · 가정 응답 ${r.calls.length - real}번)`;
  } else if (r.stopped) {
    box.textContent = `✖ ${STAGE_KO[r.stoppedStage] || r.stoppedStage || ""} 단계에서 멈춤 — ${r.stopped}`;
  }
  const p = r.proc;
  const bad = r.checks.filter((c) => !c.ok).length;
  $("expect-info").textContent = r.expect
    ? `정답 비교: 검사 ${r.checks.length}개 · 다름 ${bad}개 — 기대값 ${r.expect.status === "draft" ? "초안(검수 전)" : r.expect.status} · fixtures/flow/samples.jsonl 의 expect`
    : r.proc
      ? "정답 비교 없음 — 기대값은 예시 이미지에만 있습니다 (첨부 이미지는 비교하지 않음)"
      : "";
  $("expect-info").className = "small " + (bad ? "expect" : "muted");
  $("proc").textContent = p
    ? `새 프로세스 PID ${p.pid} 에서 디스크의 모듈 코드를 불러 실제 run() 을 호출합니다 (저장된 결과 아님)` +
      (p.stepDelayMs ? ` · 단계 사이 ${p.stepDelayMs / 1000}초 멈춤 (보여 주기용, 계산 시간은 각 단계 ms 로 따로 표시)` : "")
    : "";
  $("proc").title = p ? Object.entries(p.files).map(([n, f]) => `${n}: ${f.path} (수정 ${f.mtime ? new Date(f.mtime * 1000).toLocaleString() : "?"})`).join("\n") : "";
}

function renderOverlay() {
  const ocr = callsOf("ocr")[0];
  const box = $("overlay");
  if (!ocr) return;
  const parse = byKey("parse", (c) => c.input.line.id);
  const rows = [];
  for (const line of ocr.output.lines) {
    const msg = parse[line.id] && parse[line.id].output.message;
    const inc = msg && state.run.incidents[msg.id];
    if (!inc) continue;
    const d = inc.decision;
    const cls = [msg.channel === "all" ? "all" : "", msg.is_me ? "me" : ""];
    const who = el("span", { class: "who" }, `${msg.channel === "all" ? "[전체] " : ""}${msg.speaker}${msg.champion ? ` (${msg.champion})` : ""}: `);
    if (d.action === "hide") {
      rows.push(el("div", { class: "hidden" }, `🚫 ${msg.speaker}의 채팅을 숨겼습니다`, el("span", { class: "tag" }, "신고 목록" + (d.complaint_candidate ? " · 고소 후보" : ""))));
    } else {
      if (d.action === "show_masked") cls.push("masked");
      if (d.action === "show_rewritten") cls.push("rewritten");
      const tag = d.action === "show" ? null : el("span", { class: "tag" }, ACTION_KO[d.action] || d.action);
      rows.push(el("div", { class: cls.join(" ") }, who, el("span", { class: "txt" }, d.display_text || ""), tag));
    }
  }
  box.replaceChildren(...(rows.length ? rows : [el("span", { class: "muted" }, "표시할 채팅이 없습니다")]));
}

function analysisCell(call) {
  if (!call) return "";
  const a = call.output;
  return [
    chip(`L${a.level}`, `L${a.level}`),
    fbChip(call),
    a.target ? el("div", {}, `대상: ${a.target}`) : null,
    a.harm_types.length ? el("div", {}, a.harm_types.map((h) => HARM_KO[h] || h).join(", ")) : null,
    a.profanity_spans.length ? el("div", { class: "muted" }, `비속어: ${a.profanity_spans.join(", ")}`) : null,
    a.feedback_spans.length ? el("div", { class: "muted" }, `피드백: ${a.feedback_spans.join(" / ")}`) : null,
  ];
}

function detailRow(calls) {
  const pres = calls.filter(Boolean).flatMap((c) => [
    el("div", { class: "small muted" }, `${c.module} · ${c.mode === "fallback" ? "가정 응답 — " + c.reason : "실제 모듈"} · ${c.ms}ms`),
    el("pre", { class: "json" }, JSON.stringify({ input: c.input, output: c.output }, null, 2)),
  ]);
  return el("tr", { class: "detail", hidden: "" }, el("td", { colspan: "5" }, pres));
}

function renderRows() {
  const ocr = callsOf("ocr")[0];
  const body = $("rows");
  if (!ocr) return;
  const parse = byKey("parse", (c) => c.input.line.id);
  const analyze = byKey("analyze", (c) => c.input.message.id);
  const rewrite = byKey("rewrite", (c) => c.input.message.id);
  const rows = [];
  const r = state.run;
  const finished = r.done || Boolean(r.stopped);
  const activeLine = lineIdOf(r.current);
  const spin = (module, id) => (r.current && r.current.module === module && activeLine === id ? el("span", { class: "spin" }, "실행 중…") : null);
  const wait = () => (finished ? "" : el("span", { class: "wait" }, "대기"));
  for (const line of ocr.output.lines) {
    const p = parse[line.id];
    const msg = p && p.output.message;
    const a = msg && analyze[msg.id];
    const rw = msg && rewrite[msg.id];
    const inc = msg && state.run.incidents[msg.id];
    const parseCell = !p
      ? spin("parse", line.id) || (finished ? chip("중복 줄 · 건너뜀", "muted") : wait())
      : msg
        ? [el("div", {}, `${msg.speaker} · ${msg.channel === "all" ? "전체" : "팀"}${msg.is_me ? " · 나" : ""}`), el("div", { class: "muted" }, msg.text), fbChip(p)]
        : [chip("채팅 아님 (시스템)", "muted"), fbChip(p)];
    const rwCell = rw
      ? [rw.output.rewritten ? el("div", {}, rw.output.rewritten) : chip("순화 실패 → 숨김", "L2"), fbChip(rw), el("div", { class: "muted small" }, `backend=${rw.output.backend}`)]
      : "";
    const decision = inc ? [el("b", {}, ACTION_KO[inc.decision.action] || inc.decision.action), el("div", { class: "muted small" }, inc.decision.reason)] : "";
    const ids = [line.id, msg && msg.id].filter(Boolean);
    const mOcr = checkMarks(checksFor("ocr", ids));
    const mParse = checkMarks(checksFor("parse", ids));
    const mAnalyze = checkMarks(checksFor("analyze", ids));
    const mPolicy = checkMarks(checksFor("policy", ids));
    const cell = (m, content) => el("td", { class: m.bad ? "mismatch" : "" }, content, m.nodes);
    const tr = el(
      "tr",
      { class: "row" + (p && !msg ? " skip" : "") + (activeLine === line.id ? " active" : ""), title: "눌러서 모듈 입력·출력 보기" },
      el("td", { class: "raw" + (mOcr.bad ? " mismatch" : "") }, line.text, " ", fbChip(ocr), mOcr.bad ? mOcr.nodes : null),
      cell(mParse, parseCell),
      cell(mAnalyze, a ? analysisCell(a) : msg ? spin("analyze", line.id) || wait() : ""),
      el("td", {}, rwCell || (msg ? spin("rewrite", line.id) : "")),
      cell(mPolicy, decision || (msg ? wait() : "")),
    );
    const detail = detailRow([p, a, rw]);
    tr.onclick = () => (detail.hidden = !detail.hidden);
    rows.push(tr, detail);
  }
  for (const c of state.run.checks.filter((x) => x.stage === "ocr" && !x.ok && x.itemId == null)) {
    rows.push(el("tr", {}, el("td", { class: "raw mismatch", colspan: "5" }, el("div", { class: "expect" }, `✗ OCR 이 읽지 못한 정답 줄: ${c.expected}`))));
  }
  if (!rows.length) rows.push(el("tr", {}, el("td", { colspan: "5", class: "muted" }, "OCR 이 읽은 줄이 없습니다. 첨부 이미지라면 왼쪽 'OCR 가정 응답'에 줄을 적어 보세요.")));
  body.replaceChildren(...rows);
}

function reportCard(draft, call) {
  const btn = el("button", { type: "button", class: "link" }, "복사");
  btn.onclick = async () => (btn.textContent = (await copyText(draft.text)) ? "복사함 ✓" : "복사 실패");
  return el(
    "article",
    { class: "report" },
    el("header", {}, el("b", {}, `${draft.kind === "report" ? "신고 문구" : "고소장 초안"} · ${draft.speaker}`), fbChip(call), draft.pdf_path ? el("span", { class: "small muted" }, draft.pdf_path) : null, btn),
    ...draftBody(draft.text),
  );
}
// report 모듈이 고소장을 서식 있는 HTML 로 돌려주면 미리보기로 그린다.
// 모듈 출력이라 sandbox(스크립트·폼·링크 이동 모두 막음) iframe 에 넣고, 원문은 접어 둔다.
function draftBody(text) {
  if (!/^\s*<(article|section|div|html|h1|p)\b/i.test(text)) return [el("pre", {}, text)];
  const frame = el("iframe", { class: "doc", sandbox: "", title: "고소장 미리보기", referrerpolicy: "no-referrer" });
  frame.srcdoc = text;
  return [frame, el("details", {}, el("summary", {}, "HTML 원문 보기"), el("pre", {}, text))];
}
function renderReports() {
  const r = state.run;
  const box = $("reports");
  if (!r.postGame) {
    if (r.stopped) box.replaceChildren(el("span", { class: "muted" }, "흐름이 중간에 멈춰 게임 종료 처리를 하지 않았습니다."));
    return;
  }
  const calls = callsOf("report");
  const callOf = (d) => calls.find((c) => c.input.kind === d.kind && c.input.speaker === d.speaker);
  const drafts = [...r.postGame.reports, ...r.postGame.complaints];
  box.replaceChildren(
    ...(drafts.length
      ? drafts.map((d) => reportCard(d, callOf(d)))
      : [el("span", { class: "muted" }, "신고·고소 대상 기록이 없어 report 모듈을 부르지 않았습니다. (정책표가 report / complaint_candidate 를 표시한 채팅이 없음)")]),
  );
  if (drafts.length && !r.postGame.complaints.length) box.append(el("p", { class: "small muted" }, "고소장 초안 없음 — L3(법적 대응 후보) 채팅이 없었습니다."));
  for (const c of r.checks.filter((x) => x.stage === "report")) {
    const label = c.field === "reports" ? "신고 문구 대상" : "고소장 대상";
    box.append(
      el("p", { class: c.ok ? "okmark" : "expect report-check" }, c.ok ? `✓ ${label} 정답: ${fmtExpected(c.field, c.actual)}` : `✗ ${label} — 기대: ${fmtExpected(c.field, c.expected)} / 결과: ${fmtExpected(c.field, c.actual)}`),
    );
  }
}

function renderAll() {
  renderStages();
  renderNow();
  renderOverlay();
  renderRows();
  renderReports();
}

// ── 실행 ───────────────────────────────────────────────
function setBadge(status) {
  $("badge").className = "badge " + ({ ok: "ok", running: "running", idle: "idle" }[status] || "error");
  $("badge").textContent = BADGE[status] || status;
}
function setRunning(on) {
  $("run").disabled = on;
  $("stop").hidden = !on;
  clearInterval(state.timer);
  if (on) {
    const t0 = performance.now();
    state.timer = setInterval(() => ($("timer").textContent = `${((performance.now() - t0) / 1000).toFixed(1)}초`), 100);
  }
}
function onFlow(ev) {
  const r = state.run;
  if (ev.checks && ev.checks.length) r.checks = [...r.checks, ...ev.checks];
  if (ev.event === "start") r.proc = ev;
  else if (ev.event === "expect") r.expect = ev;
  else if (ev.event === "call_start") r.current = ev;
  else if (ev.event === "call") [r.calls, r.current] = [[...r.calls, ev], null];
  else if (ev.event === "incident") r.incidents[ev.incident.msg.id] = ev.incident;
  else if (ev.event === "phase") r.phase = ev.phase;
  else if (ev.event === "post_game") r.postGame = ev.result;
  else if (ev.event === "done") [r.done, r.summary] = [true, ev.summary];
  else if (ev.event === "stopped") [r.stopped, r.stoppedStage, r.current] = [ev.error, ev.stage, null];
  renderAll();
  const active = document.querySelector(".lines tr.active");
  if (active) active.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function run() {
  $("input-error").textContent = "";
  $("result-error").textContent = "";
  const body = { ocrText: $("ocr-text").value, useFallback: $("use-fallback").checked, stepDelayMs: Number($("speed").value) };
  if (state.upload) body.image = { name: state.upload.name, base64: state.upload.base64 };
  else if (state.sample) body.sample = state.sample.id;
  else return ($("input-error").textContent = "예시 이미지를 고르거나 이미지를 첨부하세요");

  state.run = newRun();
  $("now").textContent = "▶ 새 프로세스를 띄우는 중…";
  $("proc").textContent = "";
  $("console").textContent = "";
  $("rows").replaceChildren(el("tr", {}, el("td", { colspan: "5", class: "muted" }, "실행 중…")));
  $("overlay").replaceChildren(el("span", { class: "muted" }, "실행 중…"));
  $("reports").replaceChildren(el("span", { class: "muted" }, "게임이 끝나면 만들어집니다…"));
  $("shot").src = state.upload ? state.upload.url : state.sample.imageUrl;
  $("shot").hidden = false;
  renderStages();
  setBadge("running");
  setRunning(true);
  const controller = new AbortController();
  state.controller = controller;
  let result = null;
  try {
    const res = await fetch("/api/flow/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: controller.signal });
    if (!res.ok || !res.body) throw new Error(`서버 응답 ${res.status}: ${await res.text()}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl);
        buf = buf.slice(nl + 1);
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.type === "log") log(ev.text, ev.stream === "stdout" ? "" : ev.stream === "stderr" ? "stderr" : "sys");
        else if (ev.type === "flow") onFlow(ev);
        else if (ev.type === "result") result = ev;
      }
    }
    if (!result) throw new Error("서버가 결과 없이 연결을 끊었습니다");
    setBadge(result.status);
    loadLogs();
    log(`■ 끝: ${BADGE[result.status] || result.status} (${result.durationMs}ms)`, "sys");
    if (result.status !== "ok") {
      $("result-error").textContent = result.error || "";
      $("console-box").open = true;
    }
  } catch (e) {
    if (controller.signal.aborted) {
      state.run.current = null;
      renderAll();
      $("now").textContent = "■ 중지했습니다";
      setBadge("stopped");
      log("■ 중지했습니다 (실행 중이던 프로세스를 끝냈습니다)", "sys");
    } else {
      setBadge("error");
      $("result-error").textContent = `시뮬레이터 서버에 연결할 수 없습니다. 터미널에서 'uv run sim flow' 가 켜져 있는지 확인하세요.\n(${e.message})`;
    }
  } finally {
    state.controller = null;
    setRunning(false);
    renderStages();
  }
}

// ── 단계별 실패 모니터링 (GET /api/flow/logs) ──────────────────
async function loadLogs() {
  try {
    renderLogs(await (await fetch("/api/flow/logs")).json());
  } catch (e) {
    $("mon-rows").replaceChildren(el("tr", {}, el("td", { colspan: "9", class: "error" }, `오류 로그를 불러오지 못했습니다: ${e.message}`)));
  }
}
function renderLogs(data) {
  $("log-path").textContent = `기록 위치: ${data.path}/<날짜>.jsonl · 실행 ${data.runs.length}번 · 실패 기록 ${data.failures.length}건`;
  $("run-dots").replaceChildren(
    ...data.runs
      .slice()
      .reverse()
      .map((r) => {
        const warn = Object.values(r.stages || {}).some((s) => s.errors);
        const d = el("span", { class: r.status !== "ok" ? "stopped" : warn ? "warn" : "" });
        d.title = `${fmtTime(r.ts)} · ${r.sample || ""} · ${r.status === "ok" ? "끝까지 실행" : `${STAGE_KO[r.stoppedAt] || r.stoppedAt} 에서 멈춤`}${warn ? " · 오류 있음(가정 응답으로 계속)" : ""} · ${r.durationMs}ms`;
        return d;
      }),
  );
  const order = [...MODULES.map(([n]) => n).slice(0, 4), "policy", "report", "game", "pipeline", "post_game"];
  const rows = order
    .map((name) => [name, data.stages[name]])
    .filter(([name, s]) => s && (MODULES.some(([n]) => n === name) || s.errors || s.warnings || s.checked))
    .map(([name, s]) => {
      const mod = MODULES.find(([n]) => n === name);
      const last = s.last;
      return el(
        "tr",
        { class: s.errors || s.mismatches ? "bad" : "" },
        el("td", {}, mod ? `${mod[1]} ${name}` : STAGE_KO[name] || name),
        el("td", { class: "num" }, String(s.failedRuns || 0)),
        el("td", { class: "num" }, String(s.calls || 0)),
        el("td", { class: "num" }, String(s.real || 0)),
        el("td", { class: "num" }, String(s.fallback || 0)),
        el("td", { class: "num" }, String(s.errors || 0)),
        el("td", { class: "num" }, String(s.warnings || 0)),
        el("td", { class: "num" + (s.mismatches ? " bad" : "") }, s.checked ? `${s.checked - (s.mismatches || 0)}/${s.checked} (${Math.round((100 * (s.checked - (s.mismatches || 0))) / s.checked)}%)` : "—"),
        el("td", {}, last ? [chip(KIND_KO[last.kind] || last.kind, last.severity === "warning" ? "warn" : "err"), el("span", { class: "small" }, ` ${fmtTime(last.ts)} — ${last.message.slice(0, 120)}`)] : el("span", { class: "muted" }, "없음")),
      );
    });
  $("mon-rows").replaceChildren(...rows);
  $("fail-list").replaceChildren(
    ...(data.failures.length
      ? data.failures.slice(0, 30).map((f) =>
          el(
            "details",
            {},
            el("summary", {}, chip(KIND_KO[f.kind] || f.kind, f.severity === "warning" ? "warn" : "err"), ` ${fmtTime(f.ts)} · ${STAGE_KO[f.stage] || f.stage}${f.itemId ? ` · ${f.itemId}` : ""} · ${f.sample || ""} — ${f.message.slice(0, 160)}`),
            el("pre", {}, f.traceback || "(traceback 없음)"),
          ),
        )
      : [el("span", { class: "muted" }, "기록된 실패가 없습니다.")]),
  );
}

// ── 시작 ───────────────────────────────────────────────
async function init() {
  $("run").onclick = run;
  $("stop").onclick = () => state.controller && state.controller.abort();
  $("upload").onchange = (e) => attachUpload(e.target.files[0]);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !state.controller) run();
  });
  state.run = newRun();
  renderStages();
  try {
    const info = await (await fetch("/api/flow/samples")).json();
    [state.samples, state.players] = [info.samples, info.players];
  } catch (e) {
    $("input-error").textContent = `예시 목록을 불러오지 못했습니다: ${e.message}`;
    return;
  }
  renderPlayers();
  $("logs-refresh").onclick = loadLogs;
  loadLogs();
  const want = new URLSearchParams(location.search).get("sample");
  if (state.samples.length) pickSample(want || state.samples[0].id);
}
init();
