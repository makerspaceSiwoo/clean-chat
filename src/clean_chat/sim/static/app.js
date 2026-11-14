// Clean Chat 모듈 시뮬레이터 화면 (빌드 없음, 바닐라 JS). 서버: src/clean_chat/sim/server.py
// 입력 | 디버깅 콘솔 | 반환값. 실행은 POST /api/modules/<이름>/run → NDJSON 스트림(log 여러 줄 → result 1줄).
"use strict";

const $ = (id) => document.getElementById(id);
const STATUS = {
  idle: "실행 전",
  running: "실행 중…",
  ok: "성공",
  not_implemented: "구현 안 됨",
  invalid_input: "입력 오류",
  error: "모듈 오류",
  timeout: "시간 초과",
  stopped: "중지됨",
};
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/bmp"];
const MAX_IMAGE = 10 * 1024 * 1024;

const state = { modules: [], current: null, mode: "simple", image: null, controller: null, timer: null };

// ── 콘솔 ───────────────────────────────────────────────
function log(text, cls = "") {
  const box = $("console");
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  const span = document.createElement("span");
  if (cls) span.className = cls;
  span.textContent = text + "\n";
  box.appendChild(span);
  if (atBottom) box.scrollTop = box.scrollHeight;
}
function clearConsole() {
  $("console").textContent = "";
}

// ── 반환값 ─────────────────────────────────────────────
function setBadge(status) {
  const b = $("badge");
  b.className = "badge " + status;
  b.textContent = STATUS[status] || status;
}
function showResult(ev) {
  setBadge(ev.status);
  $("duration").textContent = ev.durationMs != null ? `${ev.durationMs}ms` : "";
  $("result-error").textContent = ev.status === "ok" ? "" : ev.error || "";
  const hasOutput = ev.status === "ok";
  $("output").hidden = !hasOutput;
  $("copy").hidden = !hasOutput;
  $("output").textContent = hasOutput ? JSON.stringify(ev.output, null, 2) : "";
  $("used-input-box").hidden = ev.input == null;
  $("used-input").textContent = ev.input == null ? "" : JSON.stringify(ev.input, null, 2);
}
function resetResult() {
  showResult({ status: "idle", output: null, error: "", input: null, durationMs: null });
}

// ── 모듈 화면 ──────────────────────────────────────────
function renderTabs() {
  $("tabs").innerHTML = "";
  for (const m of state.modules) {
    const a = document.createElement("a");
    a.href = "#" + m.name;
    a.textContent = `${m.number} ${m.name}`;
    a.title = m.title;
    if (state.current && m.name === state.current.name) a.setAttribute("aria-current", "page");
    $("tabs").appendChild(a);
  }
}

function fieldEl(f) {
  const wrap = document.createElement("div");
  wrap.className = f.type === "checkbox" ? "field check" : "field";
  const id = "f-" + f.key;
  const label = document.createElement("label");
  label.htmlFor = id;
  label.textContent = f.label;
  let input;
  if (f.type === "textarea") {
    input = document.createElement("textarea");
    input.rows = 3;
  } else {
    input = document.createElement("input");
    input.type = f.type === "checkbox" ? "checkbox" : "text";
  }
  input.id = id;
  input.dataset.key = f.key;
  if (f.type === "checkbox") input.checked = Boolean(f.default);
  else input.value = f.default || "";
  if (f.type === "checkbox") wrap.append(input, label);
  else wrap.append(label, input);
  return wrap;
}

function setMode(mode) {
  const m = state.current;
  const textFields = m.form.filter((f) => f.type !== "image");
  const hasSimple = m.form.length > 0;
  state.mode = hasSimple ? mode : "json";
  $("mode-simple").disabled = !hasSimple;
  $("mode-simple").title = hasSimple ? "" : "이 모듈은 간단 입력이 없습니다. 예시를 고르세요.";
  $("mode-simple").setAttribute("aria-selected", String(state.mode === "simple"));
  $("mode-json").setAttribute("aria-selected", String(state.mode === "json"));
  $("simple-form").hidden = state.mode !== "simple" || textFields.length === 0;
  $("json-box").hidden = state.mode !== "json";
  $("input-error").textContent = "";
}

function selectModule(name) {
  if (state.controller) return; // 실행 중에는 바꾸지 않음
  const m = state.modules.find((x) => x.name === name) || state.modules[0];
  state.current = m;
  renderTabs();
  $("input-model").textContent = m.inputModel;
  $("output-model").textContent = m.outputModel;
  $("module-desc").textContent = `${m.number} ${m.title} — ${m.description}`;
  $("module-path").textContent = m.path;

  const form = $("simple-form");
  form.innerHTML = "";
  for (const f of m.form) if (f.type !== "image") form.appendChild(fieldEl(f));

  $("image-box").hidden = !m.form.some((f) => f.type === "image");
  clearImage();

  const sel = $("example");
  sel.innerHTML = "";
  m.examples.forEach((ex, i) => sel.add(new Option(ex.label, String(i))));
  sel.add(new Option("직접 입력", "custom"));
  sel.value = m.examples.length ? "0" : "custom";
  loadExample();

  setMode(m.form.length ? "simple" : "json");
  $("timer").textContent = "";
  resetResult();
  clearConsole();
  log(`▶ ${m.number} ${m.name} — 입력을 넣고 [실행] 을 누르세요.`, "sys");
}

function loadExample() {
  const ex = state.current.examples[Number($("example").value)];
  if (ex) $("json").value = JSON.stringify(ex.input, null, 2);
  $("json-error").textContent = "";
}

// ── 이미지 ─────────────────────────────────────────────
function clearImage() {
  state.image = null;
  $("image-input").value = "";
  $("image-preview").hidden = true;
  $("image-preview").removeAttribute("src");
  $("image-info").textContent = "";
}
function attachImage(file) {
  if (!file) return clearImage();
  if (!IMAGE_TYPES.includes(file.type)) return ($("input-error").textContent = `이미지 파일만 첨부할 수 있습니다: ${file.name}`);
  if (file.size > MAX_IMAGE) return ($("input-error").textContent = `10MB 이하 이미지만 첨부할 수 있습니다: ${file.name}`);
  const reader = new FileReader();
  reader.onload = () => {
    const url = String(reader.result);
    state.image = { name: file.name, base64: url.slice(url.indexOf(",") + 1) };
    $("image-preview").src = url;
    $("image-preview").alt = `첨부한 이미지: ${file.name}`;
    $("image-preview").hidden = false;
    $("image-info").textContent = `${file.name} · ${(file.size / 1024).toFixed(1)}KB — 실행하면 서버의 .clean-chat/uploads/ 에 저장하고 image_path 로 넘깁니다.`;
    $("input-error").textContent = "";
  };
  reader.onerror = () => ($("input-error").textContent = `이미지를 읽을 수 없습니다: ${file.name}`);
  reader.readAsDataURL(file);
}

// ── 실행 ───────────────────────────────────────────────
function buildBody() {
  const body = {};
  if (state.mode === "simple") {
    const simple = {};
    for (const el of $("simple-form").querySelectorAll("[data-key]")) {
      simple[el.dataset.key] = el.type === "checkbox" ? el.checked : el.value;
    }
    body.simple = simple;
  } else {
    try {
      body.input = JSON.parse($("json").value);
    } catch (e) {
      $("json-error").textContent = `JSON 형식 오류: ${e.message}`;
      return null;
    }
  }
  if (state.image) body.image = state.image;
  return body;
}

function setRunning(on) {
  $("run").disabled = on;
  $("stop").hidden = !on;
  for (const a of $("tabs").querySelectorAll("a")) a.style.pointerEvents = on ? "none" : "";
  clearInterval(state.timer);
  if (on) {
    const t0 = performance.now();
    state.timer = setInterval(() => ($("timer").textContent = `${((performance.now() - t0) / 1000).toFixed(1)}초`), 100);
  }
}

async function run() {
  $("json-error").textContent = "";
  $("input-error").textContent = "";
  const body = buildBody();
  if (!body) return;
  const m = state.current;
  clearConsole();
  resetResult();
  setBadge("running");
  setRunning(true);
  const controller = new AbortController();
  state.controller = controller;
  let gotResult = false;
  try {
    const res = await fetch(`/api/modules/${encodeURIComponent(m.name)}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
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
        else if (ev.type === "result") {
          gotResult = true;
          showResult(ev);
          if (ev.status === "invalid_input" && ev.error) log(`✖ ${ev.error}`, "stderr");
          log(`■ 끝: ${STATUS[ev.status] || ev.status} (${ev.durationMs}ms)`, "sys");
        }
      }
    }
    if (!gotResult) throw new Error("서버가 결과 없이 연결을 끊었습니다");
  } catch (e) {
    if (controller.signal.aborted) {
      setBadge("stopped");
      log("■ 중지했습니다 (실행 중이던 프로세스를 끝냈습니다)", "sys");
    } else {
      showResult({ status: "error", error: `시뮬레이터 서버에 연결할 수 없습니다. 터미널에서 'uv run sim' 이 켜져 있는지 확인하세요.\n(${e.message})`, input: null, durationMs: null });
      log(`✖ ${e.message}`, "stderr");
    }
  } finally {
    state.controller = null;
    setRunning(false);
  }
}

// ── 시작 ───────────────────────────────────────────────
async function init() {
  $("mode-simple").onclick = () => setMode("simple");
  $("mode-json").onclick = () => setMode("json");
  $("example").onchange = loadExample;
  $("image-input").onchange = (e) => attachImage(e.target.files[0]);
  $("run").onclick = run;
  $("stop").onclick = () => state.controller && state.controller.abort();
  $("clear").onclick = clearConsole;
  $("copy").onclick = () => navigator.clipboard.writeText($("output").textContent);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !state.controller) run();
  });
  window.addEventListener("hashchange", () => selectModule(location.hash.slice(1)));
  try {
    state.modules = await (await fetch("/api/modules")).json();
  } catch (e) {
    log(`✖ 모듈 목록을 불러오지 못했습니다: ${e.message}`, "stderr");
    return;
  }
  selectModule(location.hash.slice(1));
}
init();
