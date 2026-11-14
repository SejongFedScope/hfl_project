const state = {exp: null, compare_exp: null, round: 1, hover: null, pinned: null, bundle: null, compare_bundle: null};  // hover·pinned = {type: "edge"|"client"|"digit", id}
const listeners = [];
const charts = {};

function subscribe(fn) { listeners.push(fn); }  // 패널마다 render 함수 등록
function notify() { listeners.forEach(fn => fn(state)); }

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
  chart.on("mouseover", p => { const t = target_of(p); if (t) set_hover(t); });
  chart.on("mouseout", () => set_hover(null));
  chart.on("click", p => { const t = target_of(p); if (t) set_pin(t); });
}

const DIM = 0.2;  // 강조 대상이 아닌 것의 불투명도

function base_text() {
  return {fontFamily: "Pretendard, system-ui, sans-serif", fontSize: 11, color: css_var("--text-secondary")};
}

function set_status(text, is_error) {
  const el = document.getElementById("status");
  el.textContent = text;
  el.classList.toggle("error", Boolean(is_error));
}

async function fetch_json(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} 응답 ${res.status}`);
  return res.json();
}

function client_edge(b) {  // {C1: "E1", ...}
  const out = {};
  for (const [e, cs] of Object.entries(b.assignment.assignment)) cs.forEach(c => { out[c] = e; });
  return out;
}

function edge_color(e) { return e === "E1" ? css_var("--e1") : css_var("--e2"); }

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

function update_round_label() {
  const total = state.bundle ? state.bundle.config.rounds : "–";
  document.getElementById("round_label").textContent = `라운드 ${state.round} / ${total}`;
}

function set_round(r) {
  if (!state.bundle) return;
  state.round = Math.max(1, Math.min(r, state.bundle.config.rounds));
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
  document.getElementById("round").max = state.bundle.config.rounds;
  set_status("");
  set_round(state.round);
}

async function load_compare(exp) {  // ④ 배정 방식 비교용 두 번째 실험
  try {
    state.compare_bundle = await fetch_json(`/api/${encodeURIComponent(exp)}/bundle`);
    state.compare_exp = exp;
  } catch (err) {
    set_status(`비교 실험을 불러오지 못함: ${err.message}`, true);
    return;
  }
  notify();
}

async function init() {
  let exps;
  try {
    exps = await fetch_json("/api/experiments");
  } catch (err) {
    set_status(`실험 목록을 불러오지 못함: ${err.message}`, true);
    return;
  }
  if (!exps.length) {
    document.getElementById("kpi").innerHTML = '<p class="empty">로그가 없습니다. 실험을 먼저 돌리거나 <code>python -m dashboard.app --sample</code> 로 시험 로그를 보세요.</p>';
    return;
  }
  const sel = document.getElementById("exp");
  const cmp = document.getElementById("compare_exp");
  for (const e of exps) {
    sel.add(new Option(e, e));
    cmp.add(new Option(e, e));
  }
  cmp.value = exps.find(e => e !== exps[0]) ?? exps[0];  // 처음엔 서로 다른 두 실험
  sel.onchange = () => load_bundle(sel.value);
  cmp.onchange = () => load_compare(cmp.value);
  document.getElementById("round").oninput = ev => set_round(Number(ev.target.value));
  document.getElementById("pin_chip").onclick = clear_pin;
  document.addEventListener("keydown", ev => {
    if (ev.target.tagName === "SELECT" || ev.target.tagName === "INPUT") return;  // 선택 상자·슬라이더는 자기 키 동작 유지
    if (ev.key === "Escape") clear_pin();
    if (ev.key === "ArrowLeft") set_round(state.round - 1);
    if (ev.key === "ArrowRight") set_round(state.round + 1);
  });
  await load_compare(cmp.value);
  await load_bundle(sel.value);
}

window.addEventListener("DOMContentLoaded", init);  // 모든 패널 스크립트가 subscribe 한 뒤 시작
