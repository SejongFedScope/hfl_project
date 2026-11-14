const state = {exp: null, compare_exp: null, round: 1, hover: null, pinned: null, bundle: null, compare_bundle: null};  // hover·pinned = {type: "edge"|"client"|"round"|"digit", id}
const listeners = [];

function subscribe(fn) { listeners.push(fn); }  // 패널마다 render 함수 등록
function notify() { listeners.forEach(fn => fn(state)); }

async function fetch_json(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json();
}

function update_round_label() {
  const total = state.bundle ? state.bundle.config.rounds : "–";
  document.getElementById("round_label").textContent = `라운드 ${state.round} / ${total}`;
}

async function load_bundle(exp) {  // 4.2 로그 API → state.bundle
  state.exp = exp;
  state.bundle = await fetch_json(`/api/${encodeURIComponent(exp)}/bundle`);
  const slider = document.getElementById("round");
  slider.max = state.bundle.config.rounds;
  state.round = Math.min(state.round, state.bundle.config.rounds);
  slider.value = state.round;
  update_round_label();
  notify();
}

async function load_compare(exp) {  // ④ 배정 방식 비교용 두 번째 실험
  state.compare_exp = exp;
  state.compare_bundle = await fetch_json(`/api/${encodeURIComponent(exp)}/bundle`);
  notify();
}

function set_round(r) {  // TODO 4.4.3: 키보드 ←/→
  state.round = r;
  update_round_label();
  notify();
}

function set_hover(target) {}  // TODO 4.3.1: 마우스 올림 = 모든 패널 임시 강조
function set_pin(target) {}  // TODO 4.3.1: 클릭 = 고정 + 상단 칩
function clear_pin() {}  // TODO 4.3.1: Esc / 칩 ✕ = 해제

async function init() {
  const exps = await fetch_json("/api/experiments");
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
  await load_compare(cmp.value);
  await load_bundle(sel.value);
}

window.addEventListener("DOMContentLoaded", init);  // 모든 패널 스크립트가 subscribe 한 뒤 시작
