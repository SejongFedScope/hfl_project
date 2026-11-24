const state = {exp: null, compare_exp: null, compare_manual: false, round: 1, hover: null, pinned: null, bundle: null, compare_bundle: null, tab: "overview"};  // hover·pinned = {type: "edge"|"client"|"digit", id}
const listeners = [];
const charts = {};

function subscribe(fn, tab = "overview") { listeners.push([fn, tab]); }  // 패널마다 render 함수 등록 (tab = 그 패널이 있는 탭, "all" = 항상)
function notify() { listeners.forEach(([fn, tab]) => { if (tab === "all" || tab === state.tab) fn(state); }); }  // 안 보이는 탭은 그리지 않음

function set_tab(tab) {  // 개요 / 심층 분석 / 실험 실행. 선택 상태(라운드·고정)는 개요·분석이 같이 씀
  state.tab = tab;
  history.replaceState(null, "", tab === "overview" ? location.pathname : "#" + tab);  // 새로고침해도 같은 탭
  document.body.dataset.tab = tab;  // 실험 실행 탭에서는 KPI·범례 숨김 (style.css)
  document.querySelectorAll("[data-tab]").forEach(el => { el.hidden = el.dataset.tab !== tab; });
  document.querySelectorAll("[data-tab-btn]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tabBtn === tab)));
  Object.values(charts).forEach(c => c.resize());  // 숨어 있던 동안 크기가 0 이 된 차트를 다시 맞춤
  notify();
}

function css_var(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function chart_of(id) {  // 패널 div 하나 = ECharts 인스턴스 하나
  if (!charts[id]) charts[id] = echarts.init(document.getElementById(id));
  return charts[id];
}
window.addEventListener("resize", () => {
  Object.values(charts).forEach(c => c.resize());
  notify();  // 칸 크기에 따라 숫자 표시 여부가 바뀌는 패널이 있어서 다시 그림
});

function esc(s) {  // 툴팁은 HTML 이라 로그 값을 그대로 넣지 않음
  return String(s).replace(/[&<>"']/g, ch => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch]));
}

function bind_focus(chart, target_of) {  // 패널 공통: 올림 = 강조, 클릭 = 고정
  if (chart.__bound) return;
  chart.__bound = true;
  chart.on("mouseover", p => { const t = target_of(p, false); if (t) set_hover(t); });
  chart.on("mouseout", () => set_hover(null));
  chart.on("click", p => { const t = target_of(p, true); if (t) set_pin(t); });  // target_of 두 번째 인자 = 클릭인지
}

const DIM = 0.2;  // 강조 대상이 아닌 것의 불투명도

function base_text() {
  return {fontFamily: "Pretendard, system-ui, sans-serif", fontSize: 13, color: css_var("--text-secondary")};
}

function set_status(text, is_error) {
  const el = document.getElementById("status");
  el.textContent = text;
  el.title = text;  // 머리말이 좁아 … 로 잘려도 마우스 올리면 전체
  el.classList.toggle("error", Boolean(is_error));
}

async function fetch_json(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} 응답 ${res.status}`);
  return res.json();
}

function client_edge(b) {  // {C1: "E1", ...} (미배정 클라는 없음)
  const out = {};
  for (const [e, cs] of Object.entries(b.assignment.assignment)) cs.forEach(c => { out[c] = e; });
  return out;
}

function nsort(xs) { return [...xs].sort((a, b) => a.localeCompare(b, undefined, {numeric: true})); }  // C2 < C10

function edges_of(b) { return nsort(Object.keys(b.assignment.assignment)); }

function edge_color(e) {  // 엣지 순서대로 파랑·청록·보라, 4번째부터는 회색 (이름 라벨이 항상 같이 붙음)
  const i = state.bundle ? edges_of(state.bundle).indexOf(e) : -1;
  return css_var(["--e1", "--e2", "--e3"][i] || "--text-muted");
}

function draw(chart, option) {  // 매번 비우고 처음부터 그림
  chart.clear();  // ECharts 트리는 노드 수가 줄어드는 갱신에서 내부 오류(__edge)가 나서 이전 그림과 비교 자체를 안 하게 함
  chart.setOption(option);
}

function is_measured(x) { return x.kind !== "injected"; }  // 명세: 측정값과 일부러 넣은 시험 기록을 구분

function same_target(a, b) { return a && b && a.type === b.type && a.id === b.id; }

function focus_target() { return state.pinned || state.hover; }

function lit() {  // 지금 강조할 클라·엣지·숫자 묶음, 강조 대상이 없으면 null
  const t = focus_target();
  const b = state.bundle;
  if (!t || !b) return null;
  const ce = client_edge(b);
  const clients = new Set(), edges = new Set(), digits = new Set();
  if (t.type === "edge") {
    edges.add(t.id);
    Object.keys(ce).filter(c => ce[c] === t.id).forEach(c => clients.add(c));
  } else if (t.type === "client") {
    clients.add(t.id);
    edges.add(ce[t.id]);
  } else if (t.type === "digit") {
    digits.add(t.id);
    for (const [c, info] of Object.entries(b.split.clients)) {
      if (info.digit_counts[t.id] > 0) { clients.add(c); edges.add(ce[c]); }
    }
  }
  if (t.type !== "digit") {
    clients.forEach(c => b.split.clients[c].digit_counts.forEach((n, d) => { if (n > 0) digits.add(d); }));
  }
  return {clients, edges, digits};
}

function describe(t) {
  const b = state.bundle;
  if (t.type === "edge") return `${t.id} + 소속 클라 ${b.assignment.assignment[t.id].length}`;
  if (t.type === "client") return `${t.id} (${client_edge(b)[t.id]})`;
  return `숫자 ${t.id} 보유 클라`;
}

function set_hover(target) {  // 마우스 올림 = 모든 패널 임시 강조
  if (state.pinned || same_target(state.hover, target) || (!state.hover && !target)) return;
  state.hover = target;
  notify();
}

function set_pin(target) {  // 클릭 = 고정 + 상단 칩, 같은 걸 다시 클릭하면 해제
  if (same_target(state.pinned, target)) return clear_pin();
  state.pinned = target;
  state.hover = null;
  const chip = document.getElementById("pin_chip");
  chip.textContent = `고정: ${describe(target)}  ✕`;
  chip.hidden = false;
  notify();
}

function clear_pin() {  // Esc / 칩 ✕ = 해제
  if (!state.pinned) return;
  state.pinned = null;
  document.getElementById("pin_chip").hidden = true;
  notify();
}

function done_rounds(b) {  // 중앙 집계까지 끝난 라운드 수 (중간에 죽은 실험은 계획보다 적음)
  return b.train.filter(x => x.target === "global").reduce((m, x) => Math.max(m, x.round), 0);
}

function update_round_label() {
  const b = state.bundle;
  const el = document.getElementById("round_label");
  if (!b) { el.textContent = "라운드 – / –"; return; }
  const done = done_rounds(b), plan = b.config.rounds;
  el.textContent = done < plan ? `라운드 ${state.round} / ${done} (계획 ${plan}, 끝난 라운드까지만)` : `라운드 ${state.round} / ${plan}`;
}

function render_legend(b) {  // 범례의 엣지 목록은 실험 설정에서 만듦 (엣지 수가 바뀌어도 맞게)
  const group = document.getElementById("legend_edges");
  const keys = edges_of(b).map(e => {
    const span = document.createElement("span");
    span.className = "key";
    const dot = document.createElement("i");
    dot.className = "dot";
    dot.style.background = edge_color(e);
    span.append(dot, e);
    return span;
  });
  const title = document.createElement("b");
  title.textContent = "엣지";
  group.replaceChildren(title, ...keys);
}

function set_round(r) {
  if (!state.bundle) return;
  state.round = Math.max(1, Math.min(r, Math.max(1, done_rounds(state.bundle))));
  document.getElementById("round").value = state.round;
  update_round_label();
  notify();
}

async function load_bundle(exp) {  // 4.2 로그 API → state.bundle
  set_status(`${exp} 불러오는 중…`);
  try {
    state.bundle = await fetch_json(`/api/${encodeURIComponent(exp)}/bundle`);
  } catch (err) {
    set_status(`로그를 불러오지 못함: ${err.message}. 대시보드 서버가 켜져 있는지 확인하세요.`, true);
    return;
  }
  state.exp = exp;
  state.pinned = null;
  state.hover = null;
  document.getElementById("pin_chip").hidden = true;
  const done = done_rounds(state.bundle);
  document.getElementById("round").max = Math.max(1, done);
  render_legend(state.bundle);
  set_status(state.bundle.ended ? ended_text(exp, state.bundle)
    : done ? "" : `${exp}: 아직 끝난 라운드가 없음 (학습·통신 기록 없음). 배정·데이터 분포만 표시`, done === 0 && !live_on());
  set_round(unfinished(state.bundle) ? done : state.round);  // 실행 중인 실험은 마지막 라운드부터 → 새 라운드를 따라감
  update_live_status();
}

// 실행 중 화면 갱신 (명세 심화): 아직 덜 끝난 실험이면 2초마다 로그를 다시 받아 바뀐 것만 반영
const LIVE_MS = 2000;
let polling = false;

function live_on() { return document.getElementById("live").checked; }

function unfinished(b) { return b && !b.ended && done_rounds(b) < b.config.rounds; }  // 화면에서 중지·실패한 실험(ended)은 더 안 늘어남

function ended_text(exp, b) {
  const why = {stopped: "중지함", failed: "실행 실패", interrupted: "중간에 끊김"}[b.ended.reason] || "멈춤";
  return `${exp}: ${why} (계획 ${b.config.rounds}라운드 중 ${done_rounds(b)}라운드까지)`;
}

function update_live_status() {
  const b = state.bundle;
  if (!b || !live_on() || !unfinished(b)) return;
  set_status(`실행 중으로 보임 · 끝난 라운드 ${done_rounds(b)}/${b.config.rounds} · ${LIVE_MS / 1000}초마다 자동 갱신`);
}

function exp_method(e) { return String(e).split("_")[1]; }  // exp_<배정방식>_seed..

function is_variant(e) { return /_(inject|fault)/.test(e); }  // 결함 주입·지연·중단 실험

function exp_seed(e) { const m = /_seed(\d+)/.exec(e); return m ? m[1] : null; }

function default_compare(exp, exps) {  // 결함·지연 실험 → 꼬리표를 하나씩 뗀 실험(같은 실행 → 기존), 기본 실험 → 시드가 같고 배정 방식이 다른 실험
  const folder = e => (e.includes("/") ? e.split("/")[0] + "/" : "");
  const name = exp.slice(folder(exp).length);
  for (let n = name; /_(inject|fault)$/.test(n);) {  // exp_pref_seed42_inject_fault → _inject → 기본
    n = n.replace(/_(inject|fault)$/, "");
    for (const cand of [folder(exp) + n, n]) if (cand !== exp && exps.includes(cand)) return cand;
  }
  const same_seed = exps.filter(e => e !== exp && exp_seed(e) === exp_seed(exp) && exp_method(e) !== exp_method(exp));
  const plain = same_seed.filter(e => !is_variant(e));
  return plain.find(e => folder(e) === folder(exp)) ?? plain[0] ?? same_seed[0] ?? exps.find(e => e !== exp) ?? exp;  // 맞는 게 없으면 아무거나 (설정이 다르면 비교 패널이 그렇다고 알림)
}

function auto_compare() {  // 사용자가 비교 실험을 직접 고른 적이 없으면 지금 실험에 맞는 비교 실험으로
  if (state.compare_manual || !state.exp) return;
  const cmp = document.getElementById("compare_exp");
  const want = default_compare(state.exp, [...cmp.options].map(o => o.value));
  if (want !== state.compare_exp) { cmp.value = want; load_compare(want); }
}

function add_new_experiments(exps) {  // 실행 중에 새로 생긴 실험을 선택 상자에 추가
  for (const id of ["exp", "compare_exp"]) {
    const sel = document.getElementById(id);
    const have = new Set([...sel.options].map(o => o.value));
    exps.filter(e => !have.has(e)).forEach(e => sel.add(new Option(e, e)));
  }
  auto_compare();  // 처음엔 실험이 하나뿐이라 자기와 비교 중 → 맞는 실험이 생기면 바꿈
}

async function poll() {
  if (polling || !live_on()) return;
  polling = true;
  try {
    add_new_experiments(await fetch_json("/api/experiments"));
    const b = state.bundle;
    if (unfinished(b)) {
      const exp = state.exp;
      const nb = await fetch_json(`/api/${encodeURIComponent(exp)}/bundle`);
      if (state.exp !== exp) return;  // 받는 사이에 다른 실험으로 바뀌었으면 버림
      if (nb.ended || nb.train.length !== b.train.length || nb.comm.length !== b.comm.length) {
        const follow = state.round >= done_rounds(b);  // 마지막 라운드를 보고 있었으면 새 라운드를 따라감
        state.bundle = nb;
        const done = done_rounds(nb);
        document.getElementById("round").max = Math.max(1, done);
        if (follow) state.round = Math.max(1, done);
        set_round(state.round);  // 라벨·슬라이더 맞추고 다시 그림 (고정한 대상은 그대로)
        set_status(nb.ended ? ended_text(exp, nb) : unfinished(nb) ? "" : `${exp}: 실행 끝 (${done}라운드)`);
      }
      update_live_status();
    }
    if (unfinished(state.compare_bundle)) {
      const cmp = state.compare_exp;
      const cb = await fetch_json(`/api/${encodeURIComponent(cmp)}/bundle`);
      if (state.compare_exp === cmp) { state.compare_bundle = cb; notify(); }  // 받는 사이에 비교 실험이 바뀌었으면 버림
    }
  } catch (err) {
    set_status(`자동 갱신 실패: ${err.message} (서버가 꺼졌으면 다시 켜세요)`, true);
  } finally {
    polling = false;
  }
}

async function load_compare(exp) {  // ④ 배정 방식 비교용 두 번째 실험
  try {
    state.compare_bundle = await fetch_json(`/api/${encodeURIComponent(exp)}/bundle`);
    state.compare_exp = exp;
  } catch (err) {
    state.compare_bundle = null;  // 예전 비교 실험이 남아 있으면 선택 상자와 내용이 달라짐
    state.compare_exp = exp;
    set_status(`비교 실험을 불러오지 못함: ${err.message}`, true);
  }
  notify();
}

async function init() {
  await Promise.race([document.fonts.ready, new Promise(ok => setTimeout(ok, 800))]);  // 글꼴을 기다리되 최대 0.8초 (인터넷이 막혀도 화면은 뜸)
  let exps;
  try {
    exps = await fetch_json("/api/experiments");
  } catch (err) {
    set_status(`실험 목록을 불러오지 못함: ${err.message}`, true);
    return;
  }
  document.querySelectorAll("[data-tab-btn]").forEach(b => { b.onclick = () => set_tab(b.dataset.tabBtn); });  // 로그가 없어도 실험 실행 탭은 씀
  const start_tab = ["analysis", "algo", "run"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  if (!exps.length) {
    set_tab(start_tab);
    document.getElementById("kpi").innerHTML = '<p class="empty">로그가 없습니다. 실험을 먼저 돌리거나 <code>python -m dashboard.app --sample</code> 로 시험 로그를 보세요. 실험이 시작되면 자동으로 열립니다.</p>';
    setInterval(async () => {  // 실험이 처음 생기면 화면을 새로 엶
      try {
        if ((await fetch_json("/api/experiments")).length) {
          if (typeof run_ui !== "undefined" && !run_ui.switched) history.replaceState(null, "", location.pathname);  // 실행 탭에서 돌린 첫 실험 → 개요로 열림
          location.reload();
        }
      } catch (err) { /* 서버가 아직 안 떴음 */ }
    }, LIVE_MS);
    return;
  }
  const sel = document.getElementById("exp");
  const cmp = document.getElementById("compare_exp");
  for (const e of exps) {
    sel.add(new Option(e, e));
    cmp.add(new Option(e, e));
  }
  cmp.value = default_compare(exps[0], exps);
  sel.onchange = async () => { await load_bundle(sel.value); auto_compare(); };
  cmp.onchange = () => { state.compare_manual = true; load_compare(cmp.value); };  // 직접 고르면 그 뒤로 자동으로 안 바꿈
  document.getElementById("round").oninput = ev => set_round(Number(ev.target.value));
  document.getElementById("pin_chip").onclick = clear_pin;
  document.addEventListener("keydown", ev => {
    if (ev.target.tagName === "SELECT" || ev.target.tagName === "INPUT" || state.tab === "run") return;  // 선택 상자·슬라이더는 자기 키 동작 유지, 실험 실행 탭은 라운드 키 안 씀
    if (ev.key === "Escape") clear_pin();
    if (ev.key === "ArrowLeft") set_round(state.round - 1);
    if (ev.key === "ArrowRight") set_round(state.round + 1);
  });
  document.getElementById("live").onchange = () => { set_status(""); update_live_status(); };
  set_tab(start_tab);
  await load_compare(cmp.value);
  await load_bundle(sel.value);
  setInterval(poll, LIVE_MS);
}

window.addEventListener("DOMContentLoaded", init);  // 모든 패널 스크립트가 subscribe 한 뒤 시작
