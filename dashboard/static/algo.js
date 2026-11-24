// '알고리즘 비교' 탭: 담당 A 의 단일 중앙 집계 비교 결과(logs/algo_compare/summary.json)를 읽기만 함 (API /api/algo)
const algo_ui = {data: null, error: null, loading: false, tried: 0, epoch: 1, seed: "mean", focus: null, pinned: null};
const ALGO_COLOR = {fedavg: () => css_var("--text-primary"), "fedprox_0.01": () => "#6da7ec", "fedprox_0.1": () => "#2a78d6", "fedprox_1": () => "#0d366b",
  "qfedavg_1": () => "#9085e9", "qfedavg_5": () => "#4b3aa8"};
const EPOCH_SYMBOL = {1: "circle", 5: "rect", 10: "triangle"};

function algo_key(x) { return x.algorithm === "fedavg" ? "fedavg" : `${x.algorithm}_${x.algorithm === "fedprox" ? x.mu : x.q}`; }
function algo_label(x) { return x.algorithm === "fedavg" ? "FedAvg" : x.algorithm === "fedprox" ? `FedProx μ=${x.mu}` : `q-FedAvg q=${x.q} (참고)`; }
function is_ref(g) { return g[0].algorithm === "qfedavg"; }  // 담당 A 결론: 원본 규칙은 보폭이 작아 20라운드 안에 학습이 덜 됨 → 정확도·공정성 판단에 안 씀 (숫자만 보여 줌)
const REF_NOTE = "q-FedAvg(참고)는 원본 규칙의 보폭이 작아 20라운드 안에 학습이 덜 됨 → 학습 속도와 공정성 효과가 섞여 있어 비교·판정에서 뺌 (docs/algorithm_comparison.md 6절)";
function algo_color(k) { return (ALGO_COLOR[k] || (() => css_var("--text-muted")))(); }
function algo_order(x) { return [{fedavg: 0, fedprox: 1, qfedavg: 2}[x.algorithm], x.mu || 0, x.q || 0]; }
function mean(v) { return v.reduce((a, b) => a + b, 0) / v.length; }

function algo_groups(epoch) {  // 선택 epoch 의 알고리즘별 결과 (선택 시드 또는 시드 전부)
  const rows = algo_ui.data.results.filter(x => x.local_epochs === epoch && (algo_ui.seed === "mean" || x.seed === algo_ui.seed));
  const by = {};
  rows.forEach(x => { (by[algo_key(x)] = by[algo_key(x)] || []).push(x); });
  return Object.values(by).sort((a, b) => {
    const p = algo_order(a[0]), q = algo_order(b[0]);
    return p[0] - q[0] || p[1] - q[1] || p[2] - q[2];
  });
}

function algo_on(k) { const f = algo_ui.pinned || algo_ui.focus; return !f || f === k; }

function algo_bind(chart, key_of) {  // 알고리즘에 마우스 올림 = 탭 안 4패널 강조, 클릭 = 고정 (개요 탭의 고정과는 따로)
  chart.off("mouseover"); chart.off("mouseout"); chart.off("click");
  chart.on("mouseover", p => { const k = key_of(p); if (k && k !== algo_ui.focus) { algo_ui.focus = k; render_algo(); } });
  chart.on("mouseout", () => { if (algo_ui.focus) { algo_ui.focus = null; render_algo(); } });
  chart.on("click", p => { const k = key_of(p); algo_ui.pinned = algo_ui.pinned === k ? null : k; render_algo(); });
}

async function load_algo() {
  algo_ui.loading = true;
  algo_ui.tried = Date.now();
  algo_ui.error = null;
  try {
    const res = await fetch("/api/algo");
    const data = await res.json().catch(() => ({error: `서버 응답을 읽지 못함 (${res.status})`, hint: "대시보드 서버 출력 확인"}));
    if (!res.ok) algo_ui.error = `${data.message} — ${data.hint || ""}`;
    else if (!data.results || !data.results.length) algo_ui.error = "알고리즘 비교 결과가 비어 있음 — python -m scripts.compare_algorithms … 다시 실행";
    else algo_ui.data = data;
  } catch (err) {
    algo_ui.error = `알고리즘 비교 결과를 못 불러옴: ${err.message}`;
  }
  algo_ui.loading = false;
  build_algo_controls();
  render_algo();
}

function build_algo_controls() {
  const seg = (id, items, cur, set) => {
    const box = document.getElementById(id);
    box.replaceChildren(...items.map(([v, t]) => {
      const input = Object.assign(document.createElement("input"), {type: "radio", name: id, checked: v === cur});
      input.onchange = () => { set(v); render_algo(); };
      const span = Object.assign(document.createElement("span"), {textContent: t});
      const label = document.createElement("label");
      label.append(input, span);
      return label;
    }));
  };
  if (!algo_ui.data) return;
  const epochs = [...new Set(algo_ui.data.results.map(x => x.local_epochs))].sort((a, b) => a - b);
  if (!epochs.includes(algo_ui.epoch)) algo_ui.epoch = epochs[0];
  seg("algo_epoch", epochs.map(e => [e, String(e)]), algo_ui.epoch, v => { algo_ui.epoch = v; });
  const seeds = algo_ui.data.seeds;
  seg("algo_seed", [["mean", seeds.length > 1 ? `평균(${seeds.length})` : "전부"], ...seeds.map(s => [s, String(s)])], algo_ui.seed, v => { algo_ui.seed = v; });
}

function render_algo() {
  if (state.tab !== "algo") return;
  if (!algo_ui.data && !algo_ui.loading && (!algo_ui.error || Date.now() - algo_ui.tried > 5000)) {  // 실패했으면 5초 뒤 탭을 다시 볼 때 재시도
    load_algo();
    return;
  }
  if (!algo_ui.data && !algo_ui.error) return;
  const ids = ["p_algo_curve", "p_algo_tradeoff", "p_algo_digits"];
  if (algo_ui.error) {
    document.getElementById("algo_note").textContent = algo_ui.error;
    ids.forEach(id => draw_empty(chart_of(id), "알고리즘 비교 결과 없음 (위 명령으로 만들기)"));
    document.getElementById("p_algo_table").replaceChildren();
    return;
  }
  const cond = algo_condition(algo_ui.data);
  const code = Object.assign(document.createElement("code"), {textContent: cond.cmd});
  document.getElementById("algo_cond").replaceChildren(cond.text, code);
  const groups = algo_groups(algo_ui.epoch);
  render_algo_curve(groups);
  render_algo_table(groups);
  render_algo_tradeoff();
  render_algo_digits(groups);
  const main = groups.filter(g => !is_ref(g));  // 판정은 FedAvg·FedProx 만 (q-FedAvg 는 참고)
  const best = [...main].sort((a, b) => mean(b.map(x => x.final_acc)) - mean(a.map(x => x.final_acc)))[0];
  const fair = [...main].sort((a, b) => mean(b.map(x => x.final_own_acc_min)) - mean(a.map(x => x.final_own_acc_min)))[0];
  document.getElementById("algo_note").textContent = main.length
    ? `epoch ${algo_ui.epoch}: 정확도 최고 ${algo_label(best[0])} ${pct(mean(best.map(x => x.final_acc)))} · 공정성(클라별 최솟값) 최고 ${algo_label(fair[0])} ${pct(mean(fair.map(x => x.final_own_acc_min)))}`
    : "";
}

function algo_condition(d) {  // 이 결과를 만든 조건과 다시 만드는 명령 (담당 A scripts/compare_algorithms.py, 보고서 숫자와 같은 결과)
  const r = d.results;
  const uniq = (xs, f = x => x) => [...new Set(xs)].sort((a, b) => a - b).map(f);
  const epochs = uniq(r.map(x => x.local_epochs));
  const mu = uniq(r.filter(x => x.algorithm === "fedprox").map(x => x.mu));
  const q = uniq(r.filter(x => x.algorithm === "qfedavg").map(x => x.q));
  const q_ep = uniq(r.filter(x => x.algorithm === "qfedavg").map(x => x.local_epochs));
  const cmd = `python -m scripts.compare_algorithms --rounds ${d.rounds} --seeds ${d.seeds.join(" ")} --epochs ${epochs.join(" ")}` +
    ` --mu ${mu.length ? mu.join(" ") : 0}` + (q.length ? ` --q ${q.join(" ")} --q-epochs ${q_ep.join(" ")}` : "");  // FedProx 없으면 --mu 0 (기본값 0.01 0.1 1 이라 빼면 다른 결과)
  return {text: `조건: 시드 ${d.seeds.join("·")} · epoch ${epochs.join("·")} · ${d.rounds}라운드 · 실험 ${r.length}개 — 다시 만들기 `, cmd};
}

function avg_history(g, field) {  // 시드 여러 개면 라운드마다 평균
  const n = Math.min(...g.map(x => x.history.length));
  return [...Array(n).keys()].map(i => mean(g.map(x => x.history[i][field])));
}

function render_algo_curve(groups) {
  const chart = chart_of("p_algo_curve");
  const R = Math.min(...groups.map(g => g[0].history.length));
  const all = groups.flatMap(g => avg_history(g, "acc"));
  const lo = Math.floor(Math.min(...all) * 20) / 20;
  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "axis", valueFormatter: v => pct(v)},
    legend: {top: 0, left: 0, textStyle: {fontSize: 13, color: text.color}, itemWidth: 18, itemHeight: 3},
    grid: {left: 52, right: 170, top: 36, bottom: 28},
    xAxis: {type: "category", data: [...Array(R).keys()].map(i => `R${i + 1}`), boundaryGap: false, axisLabel: {color: css_var("--text-primary")}},
    yAxis: {type: "value", min: lo, max: v => Math.min(1, Math.ceil(v.max * 20) / 20), axisLabel: {formatter: v => `${Math.round(v * 100)}%`}, splitLine: {lineStyle: {color: css_var("--hairline")}}},
    series: groups.map(g => {
      const k = algo_key(g[0]), on = algo_on(k), col = algo_color(k);
      return {
        type: "line", name: algo_label(g[0]), data: avg_history(g, "acc"), showSymbol: false, triggerLineEvent: true,
        lineStyle: {width: on && (algo_ui.focus || algo_ui.pinned) ? 3.5 : 2, color: col, opacity: on ? 1 : DIM, type: g[0].algorithm === "qfedavg" ? "dashed" : "solid"},
        itemStyle: {color: col}, emphasis: {disabled: true},
        endLabel: {show: true, formatter: p => `${algo_label(g[0])} ${pct(p.value)}`, color: col, fontWeight: 700, opacity: on ? 1 : DIM, fontSize: 12},
        labelLayout: {moveOverlap: "shiftY"},  // 값이 거의 같은 선끼리 끝 라벨이 겹치지 않게
      };
    }),
  });
  const keys = groups.map(g => algo_key(g[0]));
  algo_bind(chart, p => (p.seriesIndex !== undefined ? keys[p.seriesIndex] : null));
}

function render_algo_table(groups) {
  const cols = [  // [제목, 필드, 형식, 클수록 좋음?(null = 좋고 나쁨 없음)]
    ["최종 정확도", "final_acc", pct, true],
    ["최저 숫자 정확도", "final_min_digit_acc", pct, true],
    ["공정성 (클라별 공동 정확도 최솟값)", "final_own_acc_min", pct, true],
    ["클라 모델 최솟값", "final_client_acc_min", pct, true],
    ["평균 변화량", "mean_update_norm", v => v.toFixed(2), null],
    ["하락 라운드 수", "acc_drop_rounds", v => v.toFixed(1), false],
  ];
  const means = cols.map(([, f]) => groups.map(g => mean(g.map(x => x[f]))));
  const best = cols.map(([, , , up], i) => {  // 열마다 가장 좋은 값 (q-FedAvg 참고 줄은 빼고 고름)
    const vals = means[i].filter((_, r) => !is_ref(groups[r]));
    return up === null || !vals.length ? null : (up ? Math.max : Math.min)(...vals);
  });
  const table = document.createElement("table");
  table.className = "tbl algo_tbl";
  const head = document.createElement("tr");
  ["알고리즘", ...cols.map(c => c[0])].forEach(t => head.append(Object.assign(document.createElement("th"), {textContent: t})));
  table.append(document.createElement("thead"), document.createElement("tbody"));
  table.tHead.append(head);
  groups.forEach((g, r) => {
    const k = algo_key(g[0]);
    const tr = document.createElement("tr");
    tr.classList.toggle("dim", !algo_on(k));
    tr.classList.toggle("ref", is_ref(g));
    const name = document.createElement("td");
    name.append(Object.assign(document.createElement("i"), {className: "dot", style: `background:${algo_color(k)}`}), " " + algo_label(g[0]));
    tr.append(name);
    cols.forEach(([, f, fmt], i) => {
      const vals = g.map(x => x[f]);
      const td = Object.assign(document.createElement("td"), {className: "num", textContent: fmt(mean(vals))});
      if (vals.length > 1) td.append(Object.assign(document.createElement("small"), {textContent: `${fmt(Math.min(...vals))}~${fmt(Math.max(...vals))}`}));  // 범위는 둘째 줄
      if (best[i] !== null && !is_ref(g) && Math.abs(means[i][r] - best[i]) < 1e-12) td.classList.add("diff");
      tr.append(td);
    });
    tr.onmouseenter = () => { if (algo_ui.focus !== k) { algo_ui.focus = k; render_algo(); } };  // 다시 그려도 같은 줄이면 반복 안 함
    tr.onmouseleave = () => { if (algo_ui.focus) { algo_ui.focus = null; render_algo(); } };
    tr.onclick = () => { algo_ui.pinned = algo_ui.pinned === k ? null : k; render_algo(); };
    table.tBodies[0].append(tr);
  });
  const fa = groups.find(g => g[0].algorithm === "fedavg");
  const cap = document.createElement("caption");
  const others = groups.filter(g => g !== fa && !is_ref(g));
  if (fa && others.length) {
    const base_acc = mean(fa.map(x => x.final_acc)), base_norm = mean(fa.map(x => x.mean_update_norm));
    cap.textContent = "FedAvg 대비: " + others.map(g => {
      const d_acc = (mean(g.map(x => x.final_acc)) - base_acc) * 100, d_norm = (mean(g.map(x => x.mean_update_norm)) / base_norm - 1) * 100;
      const sign = (v, k) => { const t = v.toFixed(k); return Number(t) === 0 ? (0).toFixed(k) : (v > 0 ? "+" : "") + t; };  // -0.0 → 0.0
      return `${algo_label(g[0])} 정확도 ${sign(d_acc, 1)}%p · 변화량 ${sign(d_norm, 0)}%`;
    }).join(" / ");
  }
  table.prepend(cap);
  const box = [table];
  if (groups.some(is_ref)) box.push(Object.assign(document.createElement("p"), {className: "algo_ref_note", textContent: REF_NOTE}));
  document.getElementById("p_algo_table").replaceChildren(...box);
}

function render_algo_tradeoff() {  // 모든 epoch: x = 평균 변화량, y = 최종 정확도 (시드 평균), 선택 epoch 만 진하게
  const chart = chart_of("p_algo_tradeoff");
  const epochs = [...new Set(algo_ui.data.results.map(x => x.local_epochs))].sort((a, b) => a - b);
  const pts = epochs.flatMap(e => algo_groups(e).map(g => ({e, g, k: algo_key(g[0])})));
  const order = algo_groups(algo_ui.epoch).map(g => algo_key(g[0]));
  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => p.data.tip},
    grid: {left: 60, right: 130, top: 36, bottom: 44},
    legend: {top: 0, right: 0, data: epochs.map(e => `epoch ${e}`), textStyle: {fontSize: 13, color: text.color}},
    xAxis: {type: "value", name: "평균 변화량 (클라 모델 − 공동 모델)", nameLocation: "middle", nameGap: 26, scale: true, splitLine: {lineStyle: {color: css_var("--hairline")}}},
    yAxis: {type: "value", scale: true, axisLabel: {formatter: v => `${Math.round(v * 100)}%`}, splitLine: {lineStyle: {color: css_var("--hairline")}}},  // 세로축 = 최종 정확도 (설명에 있음)
    labelLayout: {moveOverlap: "shiftY"},
    series: epochs.map(e => ({
      labelLayout: {moveOverlap: "shiftY"},  // 같은 자리 점(FedAvg·μ=0.01)의 이름이 겹치지 않게
      type: "scatter", name: `epoch ${e}`, symbol: EPOCH_SYMBOL[e] || "diamond", symbolSize: e === algo_ui.epoch ? 16 : 11,
      itemStyle: {color: css_var("--text-secondary")}, emphasis: {disabled: true},
      data: pts.filter(p => p.e === e).map(p => {
        const on = algo_on(p.k) && e === algo_ui.epoch;
        return {
          value: [mean(p.g.map(x => x.mean_update_norm)), mean(p.g.map(x => x.final_acc))], key: p.k,
          tip: `${esc(algo_label(p.g[0]))} · epoch ${e}<br>평균 변화량 ${mean(p.g.map(x => x.mean_update_norm)).toFixed(2)} · 최종 정확도 ${pct(mean(p.g.map(x => x.final_acc)))}`,
          itemStyle: {color: algo_color(p.k), opacity: on ? 1 : 0.25, borderColor: algo_ui.pinned === p.k && e === algo_ui.epoch ? css_var("--pick") : "transparent", borderWidth: 2},
          label: {show: e === algo_ui.epoch && algo_on(p.k), position: order.indexOf(p.k) % 2 ? "left" : "right", formatter: algo_label(p.g[0]), fontSize: 12, color: algo_color(p.k), fontWeight: 700},  // 좌우 번갈아 → 겹친 점(FedAvg·μ=0.01)도 이름이 보임
        };
      }),
    })),
  });
  algo_bind(chart, p => (p.data && p.data.key) || null);
}

function render_algo_digits(groups) {
  const chart = chart_of("p_algo_digits");
  const rows = groups.filter(g => g.every(x => x.final_by_digit));
  const no_log = groups.filter(g => !rows.includes(g)).map(g => algo_label(g[0]));  // 숫자별 기록(train.jsonl)이 없는 알고리즘
  const data = [];
  rows.forEach((g, yi) => {
    const k = algo_key(g[0]), on = algo_on(k);
    [...Array(10).keys()].forEach(d => {
      const v = mean(g.map(x => x.final_by_digit[d]));
      data.push({value: [d, yi, v], key: k, tip: `${esc(algo_label(g[0]))} · 숫자 ${d}: ${pct(v)}`,
        itemStyle: {opacity: on ? 1 : DIM}, label: {opacity: on ? 1 : DIM, color: v >= 0.75 ? "#ffffff" : "#0b0b0b"}});
    });
  });
  const judged = rows.filter(g => !is_ref(g));  // 해석은 FedAvg·FedProx 만 (q-FedAvg 참고는 학습이 덜 돼 숫자별 순서가 다름)
  const lows = judged.map(g => [...Array(10).keys()].map(d => mean(g.map(x => x.final_by_digit[d]))));
  const worst = lows.map(r => r.indexOf(Math.min(...r)));  // 알고리즘마다 가장 낮은 숫자
  const mode = worst.length ? [...new Set(worst)].sort((x, y) => worst.filter(d => d === y).length - worst.filter(d => d === x).length)[0] : null;
  const odd = judged.map((g, i) => [algo_label(g[0]), worst[i]]).filter(([, d]) => d !== mode);
  const rows_n = judged.length;
  const note = [mode === null ? "" : rows_n < 2 ? `해석: 가장 낮은 숫자 = ${mode}` : !odd.length
    ? `해석: 가장 낮은 숫자 = ${mode} (비교한 ${rows_n}개 알고리즘 공통) → 알고리즘보다 데이터 분할(그 숫자를 가진 클라 수·조합)의 영향`
    : `해석: 가장 낮은 숫자 = ${mode} (${worst.length - odd.length}/${worst.length} 알고리즘), 다른 것: ${odd.map(([n, d]) => `${n} → ${d}`).join(", ")}`,
  no_log.length ? `숫자별 기록 없음: ${no_log.join(", ")}` : "", rows.some(is_ref) ? "q-FedAvg(참고)는 학습이 덜 돼 해석에서 뺌" : ""].filter(Boolean).join(" · ");
  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => (p.data && p.data.tip) || ""},
    title: {text: note,
      left: 0, bottom: 0, textStyle: {fontSize: 13, fontWeight: 600, color: css_var("--text-primary"), width: chart.getWidth() - 8, overflow: "break"}},
    grid: {left: 140, right: 12, top: 24, bottom: 44},
    visualMap: {show: false, min: 0.5, max: 1, inRange: {color: SEQ_BLUE}},
    xAxis: {type: "category", data: [...Array(10).keys()].map(String), position: "top", axisTick: {show: false}, axisLine: {show: false},
      axisLabel: {color: css_var("--text-primary"), fontWeight: 700}},
    yAxis: {type: "category", data: rows.map(g => algo_label(g[0])), inverse: true, axisTick: {show: false}, axisLine: {show: false},
      axisLabel: {color: css_var("--text-primary"), fontWeight: 600}},
    series: [{type: "heatmap", data, emphasis: {disabled: true}, label: {show: true, fontSize: 12, formatter: p => Math.round(p.value[2] * 100)}}],
  });
  algo_bind(chart, p => (p.data && p.data.key) || null);
}

subscribe(render_algo, "algo");
