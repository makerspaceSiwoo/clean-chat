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
  return call && call.mode === "fallback" ? chip("가정", "fb") : null;
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
  return { calls: [], incidents: {}, postGame: null, phase: "idle", done: false, stopped: null, summary: null };
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
function renderStages() {
  const r = state.run;
  const items = MODULES.map(([name, num, title]) => {
    const modes = new Set(callsOf(name).map((c) => c.mode));
    let cls = "",
      status = r.done || r.stopped ? NOT_CALLED[name] : "대기";
    if (modes.size === 2) [cls, status] = ["mixed", "실제 + 가정 응답"];
    else if (modes.has("real")) [cls, status] = ["real", "실제 모듈"];
    else if (modes.has("fallback")) [cls, status] = ["fallback", "가정 응답 (구현 전·오류)"];
    if (r.stopped && r.stopped.includes(`[${name}]`)) [cls, status] = ["stopped", "여기서 멈춤"];
    const n = callsOf(name).length;
    return el("li", { class: cls, title: status }, el("b", {}, `${num} ${name}`), el("span", { class: "muted" }, title + (n ? ` · ${n}번` : "")), el("span", {}, status));
  });
  const phaseKo = { idle: "대기", in_game: "게임 중", post_game: "게임 종료" }[r.phase] || r.phase;
  items.unshift(el("li", { class: "phase" }, el("b", {}, "게임 단계"), el("span", { class: "muted" }, "core/game.py"), el("span", {}, phaseKo)));
  $("stages").replaceChildren(...items);
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
  for (const line of ocr.output.lines) {
    const p = parse[line.id];
    const msg = p && p.output.message;
    const a = msg && analyze[msg.id];
    const rw = msg && rewrite[msg.id];
    const inc = msg && state.run.incidents[msg.id];
    const parseCell = !p
      ? chip("중복 줄 · 건너뜀", "muted")
      : msg
        ? [el("div", {}, `${msg.speaker} · ${msg.channel === "all" ? "전체" : "팀"}${msg.is_me ? " · 나" : ""}`), el("div", { class: "muted" }, msg.text), fbChip(p)]
        : [chip("채팅 아님 (시스템)", "muted"), fbChip(p)];
    const rwCell = rw ? [rw.output.rewritten ? el("div", {}, rw.output.rewritten) : chip("순화 실패", "L2"), fbChip(rw)] : "";
    const decision = inc ? [el("b", {}, ACTION_KO[inc.decision.action] || inc.decision.action), el("div", { class: "muted small" }, inc.decision.reason)] : "";
    const tr = el(
      "tr",
      { class: "row" + (msg ? "" : " skip"), title: "눌러서 모듈 입력·출력 보기" },
      el("td", { class: "raw" }, line.text, " ", fbChip(ocr)),
      el("td", {}, parseCell),
      el("td", {}, analysisCell(a)),
      el("td", {}, rwCell),
      el("td", {}, decision),
    );
    const detail = detailRow([p, a, rw]);
    tr.onclick = () => (detail.hidden = !detail.hidden);
    rows.push(tr, detail);
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
    el("pre", {}, draft.text),
  );
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
}

function renderAll() {
  renderStages();
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
  if (ev.event === "call") r.calls.push(ev);
  else if (ev.event === "incident") r.incidents[ev.incident.msg.id] = ev.incident;
  else if (ev.event === "phase") r.phase = ev.phase;
  else if (ev.event === "post_game") r.postGame = ev.result;
  else if (ev.event === "done") [r.done, r.summary] = [true, ev.summary];
  else if (ev.event === "stopped") r.stopped = ev.error;
  renderAll();
}

async function run() {
  $("input-error").textContent = "";
  $("result-error").textContent = "";
  const body = { ocrText: $("ocr-text").value, useFallback: $("use-fallback").checked };
  if (state.upload) body.image = { name: state.upload.name, base64: state.upload.base64 };
  else if (state.sample) body.sample = state.sample.id;
  else return ($("input-error").textContent = "예시 이미지를 고르거나 이미지를 첨부하세요");

  state.run = newRun();
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
    log(`■ 끝: ${BADGE[result.status] || result.status} (${result.durationMs}ms)`, "sys");
    if (result.status !== "ok") {
      $("result-error").textContent = result.error || "";
      $("console-box").open = true;
    }
  } catch (e) {
    if (controller.signal.aborted) {
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
  const want = new URLSearchParams(location.search).get("sample");
  if (state.samples.length) pickSample(want || state.samples[0].id);
}
init();
