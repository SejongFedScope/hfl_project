// '실험 실행' 탭: 설정을 바꿔 학습을 돌림 (API = dashboard/runs.py). 값 검사는 서버가 다시 함
const RUN_NUMBERS = [  // [설정 이름, 라벨, 설명, 증가 폭]
  ["seed", "시드", "분할·배정·학습 순서", 1],
  ["rounds", "라운드 수", "", 1],
  ["local_epochs", "학습 횟수 (epoch)", "클라가 라운드마다", 1],
  ["lr", "학습률", "", 0.01],
  ["batch_size", "배치 크기", "", 1],
  ["samples_per_client", "클라당 이미지 수", "고른 숫자 수로 나눠떨어져야 함", 1],
];
const RUN_CLIENTS = ["C1", "C2", "C3", "C4", "C5", "C6"];
const RUN_EDGES = ["E1", "E2"];
const METHOD_NAMES = {pref: "선호 배정 (matching)", random: "무작위 배정 (시드 고정)"};
const run_ui = {def: null, edge_order: {}, timer: null, watching: null, switched: true, compared: true, errors: [], running: false, seq: 0};

function h(tag, props = {}, ...kids) {  // 요소 만들기 (글자는 textContent 로만)
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids);
  return e;
}

function run_val(id) { return document.getElementById(id); }

function build_run_form(d) {
  run_ui.def = d;
  run_val("run_numbers").replaceChildren(...RUN_NUMBERS.flatMap(([k, label, hint, step]) => [
    h("label", {htmlFor: `run_${k}`}, label, hint ? h("small", {textContent: hint}) : ""),
    h("input", {id: `run_${k}`, type: "number", value: d[k], min: d.limits[k][0], max: d.limits[k][1], step}),
  ]));
  run_val("run_init").setAttribute("role", "radiogroup");
  run_val("run_init").setAttribute("aria-label", "초기 모델");
  run_val("run_init").replaceChildren(...[["zeros", "전부 0"], ["normal", "정규분포 (시드)"]].map(([v, t]) =>
    h("label", {}, h("input", {type: "radio", name: "run_init", value: v, checked: d.init_model === v}), h("span", {textContent: t}))));
  run_val("run_methods").replaceChildren(...Object.entries(METHOD_NAMES).map(([m, t]) =>
    h("label", {}, h("input", {type: "checkbox", value: m, checked: d.methods.includes(m)}), " " + t)));
  run_val("run_inject").replaceChildren(
    h("label", {}, h("input", {id: "run_inject_on", type: "checkbox", checked: d.inject}), " 거부될 시험 요청 2건 넣기"),
    h("label", {className: "inline"}, "주입할 라운드 ", h("input", {id: "run_inject_round", type: "number", value: d.inject_round, min: 1, max: d.limits.inject_round[1]})));

  const head = h("tr", {}, h("th", {textContent: ""}), ...[...Array(10).keys()].map(n => h("th", {textContent: n})), h("th", {textContent: "숫자 · 장"}));
  const rows = RUN_CLIENTS.map(c => h("tr", {id: `run_row_${c}`},
    h("th", {textContent: c, scope: "row"}),
    ...[...Array(10).keys()].map(n => {
      const box = h("input", {type: "checkbox", checked: d.client_digits[c].includes(n)});
      box.dataset.c = c;
      box.dataset.d = n;
      box.setAttribute("aria-label", `${c} 숫자 ${n}`);
      return h("td", {}, h("label", {className: "tog"}, box, h("span", {textContent: n})));
    }),
    h("td", {id: `run_sum_${c}`, className: "num"})));
  run_val("run_digits").replaceChildren(h("table", {className: "tbl run_grid"}, h("thead", {}, head), h("tbody", {}, ...rows)));

  run_val("run_client_prefs").replaceChildren(...RUN_CLIENTS.map(c => h("div", {className: "run_pref_row", id: `run_cp_row_${c}`},
    h("b", {textContent: c}),
    h("span", {className: "seg"}, ...RUN_EDGES.map(e =>
      h("label", {}, h("input", {type: "radio", name: `run_cp_${c}`, value: e, checked: d.client_prefs[c][0] === e, ariaLabel: `${c} ${e} 먼저`}), h("span", {textContent: `${e} 먼저`})))))));
  RUN_CLIENTS.forEach(c => { const row = run_val(`run_cp_row_${c}`); row.setAttribute("role", "radiogroup"); row.setAttribute("aria-label", `${c} 가 먼저 원하는 엣지`); });

  run_ui.edge_order = Object.fromEntries(RUN_EDGES.map(e => [e, [...d.edge_prefs[e]]]));
  render_edge_lists();
  on_run_change();
}

function render_edge_lists() {  // 엣지 선호: 순위 목록 + ↑↓ 로 자리 바꿈
  run_val("run_edge_prefs").replaceChildren(...RUN_EDGES.map(e => h("div", {className: "run_edge"},
    h("b", {textContent: e}),
    h("ol", {}, ...run_ui.edge_order[e].map((c, i, arr) => h("li", {},
      h("span", {className: "rank", textContent: `${i + 1}위`}),
      h("span", {className: "name", textContent: c}),
      move_btn(e, i, -1, "↑", `${e} 순위에서 ${c} 올리기`, i === 0),
      move_btn(e, i, 1, "↓", `${e} 순위에서 ${c} 내리기`, i === arr.length - 1)))))));
}

function move_btn(e, i, dir, text, label, disabled) {
  const b = h("button", {type: "button", className: "mini", textContent: text, disabled});
  b.setAttribute("aria-label", label);
  b.onclick = () => {
    const list = run_ui.edge_order[e];
    [list[i], list[i + dir]] = [list[i + dir], list[i]];
    render_edge_lists();
    const [up, down] = run_val("run_edge_prefs").querySelectorAll(".run_edge")[RUN_EDGES.indexOf(e)].querySelectorAll("li")[i + dir].querySelectorAll("button");
    const same = dir < 0 ? up : down;
    (same.disabled ? (dir < 0 ? down : up) : same).focus();  // 옮긴 클라를 따라감 (맨 위·아래면 반대쪽 버튼)
    on_run_change();
  };
  return b;
}

function collect_run() {  // 화면 값 → /api/run 본문
  const num = id => (run_val(id).value === "" ? null : Number(run_val(id).value));
  const digits = Object.fromEntries(RUN_CLIENTS.map(c => [c, [...run_val("run_digits").querySelectorAll(`input[data-c="${c}"]:checked`)].map(x => Number(x.dataset.d))]));
  return {
    ...Object.fromEntries(RUN_NUMBERS.map(([k]) => [k, num(`run_${k}`)])),
    inject_round: num("run_inject_round"),
    init_model: (document.querySelector('input[name="run_init"]:checked') || {}).value,
    methods: [...run_val("run_methods").querySelectorAll("input:checked")].map(x => x.value),
    inject: run_val("run_inject_on").checked,
    client_digits: digits,
    client_prefs: Object.fromEntries(RUN_CLIENTS.map(c => {
      const first = document.querySelector(`input[name="run_cp_${c}"]:checked`).value;
      return [c, [first, ...RUN_EDGES.filter(e => e !== first)]];
    })),
    edge_prefs: JSON.parse(JSON.stringify(run_ui.edge_order)),
  };
}

function mark_changed(body) {  // 기본값과 다른 칸에 주황 표시 + 개수 (시연 때 '무엇을 바꿨는지' 바로 보이게)
  const d = run_ui.def;
  let n = 0;
  const flag = (el, changed) => { el.classList.toggle("changed", changed); if (changed) n++; };
  RUN_NUMBERS.forEach(([k]) => flag(run_val(`run_${k}`), body[k] !== d[k]));
  flag(run_val("run_init"), body.init_model !== d.init_model);
  flag(run_val("run_methods"), body.methods.join() !== d.methods.join());
  flag(run_val("run_inject"), body.inject !== d.inject || (body.inject && body.inject_round !== d.inject_round));
  run_val("run_digits").querySelectorAll("input[data-c]").forEach(x =>
    flag(x.closest(".tog"), x.checked !== d.client_digits[x.dataset.c].includes(Number(x.dataset.d))));
  RUN_CLIENTS.forEach(c => flag(run_val(`run_cp_row_${c}`), body.client_prefs[c][0] !== d.client_prefs[c][0]));
  run_val("run_edge_prefs").querySelectorAll(".run_edge").forEach((box, i) => {
    const e = RUN_EDGES[i];
    box.querySelectorAll("li").forEach((li, r) => flag(li, run_ui.edge_order[e][r] !== d.edge_prefs[e][r]));
  });
  run_val("run_changed").textContent = n ? `기본값과 다른 칸 ${n}개 (주황)` : "기본값 그대로";
}

function on_run_change() {
  const body = collect_run();
  run_val("run_inject_round").disabled = !body.inject;  // 결함 주입을 끄면 라운드는 안 씀
  mark_changed(body);
  RUN_CLIENTS.forEach(c => {  // 클라 줄 끝: 숫자 개수 · 숫자당 장수
    const k = body.client_digits[c].length, n = body.samples_per_client;
    const cell = run_val(`run_sum_${c}`);
    const ok = k && n && n % k === 0;
    cell.textContent = !k ? "숫자 없음" : ok ? `${k}개 · ${n / k}장` : `${k}개 · 안 나눠짐`;
    cell.classList.toggle("bad", !ok);
  });
  clearTimeout(run_ui.timer);
  run_ui.timer = setTimeout(() => run_preview(body), 150);  // 칸을 연달아 눌러도 마지막 값으로 한 번만
}

function show_run_errors(errors) {  // 목록 + 해당 칸 빨간 테두리 (field = 설정 이름, client_digits.C2 = 그 줄)
  run_ui.errors = errors;
  run_val("run_errors").replaceChildren(...errors.map(e => h("li", {textContent: e.msg})));
  const fields = new Set(errors.map(e => e.field));
  RUN_NUMBERS.forEach(([k]) => run_val(`run_${k}`).setAttribute("aria-invalid", String(fields.has(k))));
  run_val("run_inject_round").setAttribute("aria-invalid", String(fields.has("inject_round")));
  RUN_CLIENTS.forEach(c => run_val(`run_row_${c}`).classList.toggle("bad_row", fields.has(`client_digits.${c}`)));
  const boxes = {client_digits: "run_digits", client_prefs: "run_client_prefs", edge_prefs: "run_edge_prefs", methods: "run_methods", init_model: "run_init"};
  Object.entries(boxes).forEach(([f, id]) => run_val(id).classList.toggle("bad_box", fields.has(f)));
  update_run_buttons();
}

async function run_preview(body) {
  const seq = ++run_ui.seq;  // 늦게 온 예전 응답이 새 값의 결과를 덮지 않게
  let res, data;
  try {
    res = await fetch("/api/run/preview", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    data = await res.json();
  } catch (err) {
    if (seq === run_ui.seq) show_run_errors([{field: "", msg: `미리보기 실패: 대시보드 서버가 켜져 있는지 확인 (${err.message})`}]);
    return;
  }
  if (seq !== run_ui.seq) return;
  const errors = data.errors || [];
  if (!run_ui.def.run_allowed) errors.push({field: "", msg: "시험 로그 모드(--sample)라 실행은 막혀 있음. 미리보기만 됨"});
  if (res.ok) render_run_preview(data.preview, body.methods);
  run_val("run_preview").classList.toggle("stale", !res.ok);  // 오류면 지난 미리보기를 흐리게 남김 (어디까지 맞았는지 보이게)
  show_run_errors(errors);
}

function render_run_preview(pv, methods) {
  const digit_list = counts => counts.map((n, d) => (n ? d : null)).filter(d => d !== null);
  const missing = counts => { const m = counts.map((n, d) => (n ? null : d)).filter(d => d !== null); return m.length ? m.join("·") : "없음"; };
  const rows = [
    ...RUN_EDGES.map(e => [`${e} 클라`, m => pv[m].assignment[e].join("·")]),
    ...RUN_EDGES.map(e => [`${e} 숫자`, m => digit_list(pv[m].edge_digits[e]).join("·")]),
    ...RUN_EDGES.map(e => [`${e} 에 없는 숫자`, m => missing(pv[m].edge_digits[e])]),
    ["평균 선호 순위 (낮을수록 좋음)", m => (pv[m].mean_pref_rank === null ? "–" : `${pv[m].mean_pref_rank.toFixed(2)}위`)],
    ["위반 (미배정·중복·정원)", m => String(pv[m].violations)],
  ];
  const ms = Object.keys(METHOD_NAMES);
  const head = h("tr", {}, h("th", {textContent: "배정 미리보기"}),
    ...ms.map(m => h("th", {textContent: methods.includes(m) ? METHOD_NAMES[m].split(" ")[0] : `${METHOD_NAMES[m].split(" ")[0]} (실행 안 함)`})));
  const body = rows.map(([label, f]) => {
    const vals = ms.map(f);
    const differ = vals[0] !== vals[1];
    return h("tr", {}, h("td", {textContent: label}), ...vals.map((v, i) => h("td", {textContent: v, className: (differ ? "diff" : "") + (methods.includes(ms[i]) ? "" : " muted")})));
  });
  run_val("run_preview").replaceChildren(h("table", {className: "tbl run_pv"}, h("thead", {}, head), h("tbody", {}, ...body)));
}

function update_run_buttons() {
  run_val("run_go").disabled = run_ui.running || run_ui.errors.length > 0;
  run_val("run_stop").hidden = !run_ui.running;
}

function render_run_status(st) {
  run_ui.running = st.running;
  const el = run_val("run_state");
  let text = "", bad = false;
  if (st.running) text = `실행 중 · ${st.tag} · ${st.exps.join(", ")}`;
  else if (st.stopped) text = `중지함 · ${st.tag} (거기까지의 로그만 남음)`;
  else if (st.tag && st.returncode === 0) text = `끝 · ${st.tag} · 실험 목록에서 ${st.exps.join(", ")}`;
  else if (st.tag) { text = `실패 (종료 코드 ${st.returncode}) · 아래 실행 기록 확인`; bad = true; }
  el.textContent = text;
  el.classList.toggle("bad", bad);
  run_val("run_log").textContent = st.log_tail.join("\n");
  document.querySelector('[data-tab-btn="run"]').classList.toggle("running", st.running);  // 다른 탭에서도 실행 중인 게 보이게
  update_run_buttons();
}

async function run_watch_step() {  // 실행 상태 갱신 + 새 실험이 생기면 개요로 넘어가 실시간으로 봄
  let st;
  try { st = await fetch_json("/api/run/status"); } catch (err) { return; }
  render_run_status(st);
  if (!run_ui.switched || !run_ui.compared) {
    const exps = await fetch_json("/api/experiments");
    if (state.bundle !== null) add_new_experiments(exps);  // 선택 상자에 먼저 넣어야 값을 고를 수 있음
    const [first, second] = st.exps;
    if (!run_ui.switched && exps.includes(first)) {
      run_ui.switched = true;
      if (state.bundle === null) { location.hash = ""; location.reload(); return; }  // 로그가 없던 화면: 새로 열어야 선택 상자가 생김
      run_val("exp").value = first;
      await load_bundle(first);
      set_tab("overview");
    }
    if (run_ui.switched && !run_ui.compared && second && exps.includes(second)) {
      run_ui.compared = true;
      run_val("compare_exp").value = second;
      await load_compare(second);
    }
  }
  const over = !st.running && (st.returncode !== null || st.stopped);
  if (over && ((run_ui.switched && run_ui.compared) || st.returncode !== 0)) { clearInterval(run_ui.watching); run_ui.watching = null; }  // 실패·중지면 새 실험을 기다리지 않음
}

function run_watch() {
  if (!run_ui.watching) run_ui.watching = setInterval(run_watch_step, 1500);
  run_watch_step();
}

async function run_start() {
  run_val("run_go").disabled = true;
  let res, data;
  try {
    res = await fetch("/api/run", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(collect_run())});
    data = await res.json();
  } catch (err) {
    show_run_errors([{field: "", msg: `실행 요청 실패: ${err.message}`}]);
    return;
  }
  if (res.status !== 202) {
    show_run_errors(data.errors || [{field: "", msg: `실행 요청 실패 (${res.status})`}]);
    return;
  }
  run_val("run_state").textContent = `실행 시작 · ${data.tag} · 첫 실험이 생기면 개요 탭에서 실시간으로 보여 줌`;
  run_ui.switched = false;
  run_ui.compared = data.exps.length < 2;
  run_ui.running = true;
  run_watch();
}

async function run_init() {
  let d;
  try { d = await fetch_json("/api/run/defaults"); } catch (err) {
    run_val("run_errors").replaceChildren(h("li", {textContent: `설정 기본값을 못 불러옴: ${err.message}. 대시보드를 http://127.0.0.1:5050 으로 열었는지 확인`}));
    run_val("run_go").disabled = true;
    run_val("run_reset").disabled = true;
    return;
  }
  build_run_form(d);
  const panel = document.querySelector(".runner");
  panel.addEventListener("input", ev => { if (!ev.target.closest(".run_edges")) on_run_change(); });
  run_val("run_reset").onclick = () => build_run_form(run_ui.def);
  run_val("run_go").onclick = run_start;
  run_val("run_stop").onclick = async () => {
    await fetch("/api/run/stop", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}).catch(() => null);
    run_watch_step();
  };
  const st = await fetch_json("/api/run/status");
  render_run_status(st);
  if (st.running) run_watch();  // 실행 도중 새로고침: 상태만 계속 보여 줌 (지금 보는 화면은 그대로)
}

window.addEventListener("DOMContentLoaded", run_init);
