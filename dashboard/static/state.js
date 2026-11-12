const state = {exp: null, compare_exp: null, round: 1, hover: null, pinned: null, bundle: null};  // hover·pinned = {type: "edge"|"client"|"round"|"digit", id}
const listeners = [];

function subscribe(fn) { listeners.push(fn); }  // 패널마다 render 함수 등록
function notify() { listeners.forEach(fn => fn(state)); }

async function load_bundle(exp) {}  // TODO 4.2: GET /api/<exp>/bundle → state.bundle → notify()
function set_round(r) {}  // TODO 4.4.3: 라운드 바꾸면 전 패널 반영
function set_hover(target) {}  // TODO 4.3.1: 마우스 올림 = 모든 패널 임시 강조
function set_pin(target) {}  // TODO 4.3.1: 클릭 = 고정 + 상단 칩
function clear_pin() {}  // TODO 4.3.1: Esc / 칩 ✕ = 해제
