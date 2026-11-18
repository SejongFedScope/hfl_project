function clients_by_edge(b) {  // 엣지 순서대로 클라 (같은 엣지끼리 붙여 둠), 미배정은 맨 뒤
  const ce = client_edge(b);
  return edges_of(b).flatMap(e => nsort(Object.keys(ce).filter(c => ce[c] === e)))
    .concat(nsort(Object.keys(b.split.clients).filter(c => !(c in ce))));
}

function client_rec(b, c, r) { return b.train.find(x => x.target === c && x.round === r); }

function pct(v) { return (v * 100).toFixed(1) + "%"; }

function render_local_vs_global(s) {  // 연합 효과: 클라 혼자 학습한 직후 모델 vs 공동 모델, 숫자별 정확도
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_local");
  if (!done_rounds(b)) return draw_empty(chart, "아직 끝난 라운드가 없음");
  const L = lit();
  const ce = client_edge(b);
  const g = b.train.find(x => x.target === "global" && x.round === s.round);
  const rows = clients_by_edge(b).map(c => ({c, rec: client_rec(b, c, s.round)})).filter(x => x.rec);
  const labels = rows.map(x => `${x.c} (${ce[x.c] || "미배정"}) ${pct(x.rec.acc)}`).concat(g ? [`공동 모델 ${pct(g.acc)}`] : []);
  const data = [];
  rows.forEach((x, yi) => x.rec.acc_by_digit.forEach((a, d) => {
    const by_digit = (focus_target() || {}).type === "digit";  // 숫자를 고르면 그 열만, 클라·엣지를 고르면 그 클라 줄 전체 (안 가진 숫자를 얼마나 잊었나)
    const on = !L || (L.clients.has(x.c) && (!by_digit || L.digits.has(d)));
    data.push({value: [d, yi, a], target: {type: "digit", id: d}, tip: `${esc(x.c)} 모델 · 숫자 ${d}: ${pct(a)}`,
      itemStyle: {opacity: on ? 1 : DIM}, label: {opacity: on ? 1 : DIM, color: a >= 0.5 ? "#ffffff" : "#0b0b0b"}});
  }));
  if (g) g.acc_by_digit.forEach((a, d) => data.push({value: [d, rows.length, a], target: {type: "digit", id: d}, tip: `공동 모델 · 숫자 ${d}: ${pct(a)}`,
    itemStyle: {opacity: !L || L.digits.has(d) ? 1 : DIM, borderColor: css_var("--text-primary"), borderWidth: 1},
    label: {color: a >= 0.5 ? "#ffffff" : "#0b0b0b", fontWeight: 700}}));
  const own = [], other = [];  // 클라가 가진 숫자 / 안 가진 숫자의 정확도
  rows.forEach(x => x.rec.acc_by_digit.forEach((a, d) => (b.split.clients[x.c].digit_counts[d] ? own : other).push(a)));
  const avg = xs => (xs.length ? xs.reduce((acc, v) => acc + v, 0) / xs.length : 0);
  const mean_local = avg(rows.map(x => x.rec.acc));
  const note = g ? `해석: 클라 모델은 가진 숫자 ${pct(avg(own))} · 안 가진 숫자 ${pct(avg(other))} (전체 평균 ${pct(mean_local)}) → 공동 모델 ${pct(g.acc)}, 연합으로 +${((g.acc - mean_local) * 100).toFixed(1)}%p` : "";
  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => (p.data && p.data.tip) || ""},
    title: {text: note, left: 0, bottom: 0, textStyle: {fontSize: 12, fontWeight: 600, color: css_var("--text-primary")}},
    grid: {left: 150, right: 12, top: 24, bottom: 30},
    visualMap: {show: false, min: 0, max: 1, inRange: {color: SEQ_BLUE}},
    xAxis: {type: "category", data: [...Array(10).keys()].map(String), position: "top", axisTick: {show: false}, axisLine: {show: false},
      axisLabel: {color: css_var("--text-primary"), fontWeight: 700}},
    yAxis: {type: "category", data: labels, inverse: true, triggerEvent: true, axisTick: {show: false}, axisLine: {show: false},
      axisLabel: {color: css_var("--text-primary"), fontWeight: 600}},
    series: [{type: "heatmap", data, emphasis: {disabled: true}, label: {show: true, fontSize: 11, formatter: p => Math.round(p.value[2] * 100)}}],
  });
  bind_focus(chart, p => {
    if (p.componentType === "yAxis") { const c = String(p.value).split(" ")[0]; return c.startsWith("C") ? {type: "client", id: c} : null; }
    return (p.data && p.data.target) || null;
  });
}

function render_traffic(s) {  // 트래픽 sankey: 클라 → 엣지 → 중앙, 선택 라운드까지 누적 바이트
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_traffic");
  const flows = {};
  b.comm.filter(x => x.round >= 1 && x.round <= s.round && /^[CE]\d+$/.test(x.src) && /^(E\d+|S)$/.test(x.dst)).forEach(x => {
    const k = `${x.src}→${x.dst}`;
    flows[k] = (flows[k] || 0) + (x.req_bytes || 0) + (x.bytes || 0);
  });
  const keys = Object.keys(flows);
  if (!keys.length) return draw_empty(chart, "아직 통신 기록이 없음");
  const L = lit();
  const ce = client_edge(b);
  const names = [...new Set(keys.flatMap(k => k.split("→")))];
  const color = n => (n === "S" ? css_var("--text-secondary") : /^E/.test(n) ? edge_color(n) : ce[n] ? edge_color(ce[n]) : css_var("--text-muted"));
  const mb = v => (v / 1e6).toFixed(1) + " MB";
  const total = Object.values(flows).reduce((a, v) => a + v, 0);
  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => (p.dataType === "edge" ? `${esc(p.data.source)} → ${esc(p.data.target)}: ${mb(p.data.value)}` : `${esc(p.name)}: ${mb(p.value)}`)},
    title: {text: `라운드 1~${s.round} 누적 ${mb(total)} · 선 굵기 = 바이트, 가는 선 = 배정 밖·시험 요청`, left: 0, bottom: 0,
      textStyle: {fontSize: 12, fontWeight: 600, color: css_var("--text-primary")}},
    series: [{
      type: "sankey", left: 8, right: 90, top: 12, bottom: 30, nodeWidth: 14, nodeGap: 10, draggable: false, layoutIterations: 0,
      emphasis: {disabled: true},
      data: nsort(names).map(n => ({name: n, itemStyle: {color: color(n), opacity: !L || n === "S" || node_lit(L, n) ? 1 : DIM},
        label: {formatter: x => `${n === "S" ? "중앙 S" : n}  ${mb(x.value)}`, color: css_var("--text-primary"), fontWeight: 600}})),
      links: keys.map(k => {
        const [src, dst] = k.split("→");
        return {source: src, target: dst, value: flows[k], lineStyle: {color: color(src), opacity: link_lit(L, src, dst) ? 0.45 : 0.06}};
      }),
    }],
  });
  bind_focus(chart, p => {
    const n = p.dataType === "edge" ? p.data.source : p.name;
    return /^C\d+$/.test(n) ? {type: "client", id: n} : /^E\d+$/.test(n) ? {type: "edge", id: n} : null;
  });
}

function render_rank(s) {  // 라운드마다 클라 정확도 순위 (1 = 가장 높음)
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_rank");
  const R = done_rounds(b);
  if (!R) return draw_empty(chart, "아직 끝난 라운드가 없음");
  const L = lit();
  const ce = client_edge(b);
  const clients = clients_by_edge(b).filter(c => client_rec(b, c, 1));
  const rank = {};
  for (let r = 1; r <= R; r++) {
    const order = clients.map(c => [c, (client_rec(b, c, r) || {acc: -1}).acc]).sort((p, q) => q[1] - p[1]);
    order.forEach(([c], i) => { (rank[c] = rank[c] || [])[r - 1] = i + 1; });
  }
  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => `${esc(p.seriesName)} · 라운드 ${p.dataIndex + 1}: ${p.value}위 (${pct(client_rec(b, p.seriesName, p.dataIndex + 1).acc)})`},
    grid: {left: 36, right: 70, top: 16, bottom: 28},
    xAxis: {type: "category", data: [...Array(R).keys()].map(i => `R${i + 1}`), boundaryGap: false, axisTick: {show: false},
      axisLine: {lineStyle: {color: css_var("--border")}}, axisLabel: {color: css_var("--text-primary"), fontWeight: 700, interval: R > 12 ? 1 : 0}},
    yAxis: {type: "value", inverse: true, min: 1, max: clients.length, interval: 1, axisLabel: {formatter: v => `${v}위`},
      splitLine: {lineStyle: {color: css_var("--hairline")}}},
    series: clients.map(c => {
      const on = !L || L.clients.has(c);
      const col = ce[c] ? edge_color(ce[c]) : css_var("--text-muted");
      return {
        type: "line", name: c, data: rank[c], symbol: "circle", symbolSize: 7, triggerLineEvent: true,
        lineStyle: {width: on && L ? 3.5 : 2, color: col, opacity: on ? 1 : DIM}, itemStyle: {color: col, opacity: on ? 1 : DIM},
        endLabel: {show: true, formatter: `${c} (${ce[c] || "미배정"})`, color: css_var("--text-primary"), fontWeight: 700, opacity: on ? 1 : DIM},
        markLine: c === clients[0] ? {symbol: "none", silent: true, label: {show: false}, lineStyle: {color: css_var("--pick"), type: "solid", width: 1.5}, data: [{xAxis: s.round - 1}]} : undefined,
        emphasis: {disabled: true},
      };
    }),
  });
  bind_focus(chart, p => (p.seriesName && /^C\d+$/.test(p.seriesName) ? {type: "client", id: p.seriesName} : null));
}

function cosine(a, b) {
  const dot = a.reduce((s, v, i) => s + v * b[i], 0);
  const na = Math.hypot(...a), nb = Math.hypot(...b);
  return na && nb ? dot / (na * nb) : 0;
}

function render_similarity(s) {  // 클라끼리 숫자별 정확도가 얼마나 비슷한가 (같은 숫자를 가진 클라끼리 묶임)
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_sim");
  if (!done_rounds(b)) return draw_empty(chart, "아직 끝난 라운드가 없음");
  const L = lit();
  const ce = client_edge(b);
  const clients = clients_by_edge(b).filter(c => client_rec(b, c, s.round));
  const vec = Object.fromEntries(clients.map(c => [c, client_rec(b, c, s.round).acc_by_digit]));
  const data = [], close = [];
  clients.forEach((a, yi) => clients.forEach((c, xi) => {
    const v = cosine(vec[a], vec[c]);
    if (yi < xi && v >= 0.95) close.push(`${a}·${c}`);  // 거의 같은 쌍
    const on = !L || L.clients.has(a) || L.clients.has(c);  // 고른 클라의 줄·열 전체 = 그 클라가 누구와 비슷한가
    data.push({value: [xi, yi, v], target: {type: "client", id: a}, tip: `${esc(a)} ↔ ${esc(c)}: ${v.toFixed(2)}`,
      itemStyle: {opacity: on ? 1 : DIM}, label: {opacity: on ? 1 : DIM, color: v >= 0.6 ? "#ffffff" : "#0b0b0b"}});
  }));
  const note = close.length ? `해석: 거의 같은 쌍(0.95 이상) ${close.join(", ")} — 같은 숫자를 가진 클라끼리 묶임` : "해석: 0.95 이상으로 비슷한 클라 쌍 없음";
  const label = c => `${c} (${ce[c] || "미배정"})`;
  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => (p.data && p.data.tip) || ""},
    title: {text: note, left: 0, bottom: 0, textStyle: {fontSize: 12, fontWeight: 600, color: css_var("--text-primary")}},
    grid: {left: 76, right: 12, top: 24, bottom: 30},
    visualMap: {show: false, min: 0, max: 1, inRange: {color: SEQ_BLUE}},
    xAxis: {type: "category", data: clients.map(label), position: "top", axisTick: {show: false}, axisLine: {show: false},
      axisLabel: {color: css_var("--text-primary"), fontWeight: 600}},
    yAxis: {type: "category", data: clients.map(label), inverse: true, triggerEvent: true, axisTick: {show: false}, axisLine: {show: false},
      axisLabel: {color: css_var("--text-primary"), fontWeight: 600}},
    series: [{type: "heatmap", data, emphasis: {disabled: true}, label: {show: true, fontSize: 11, formatter: p => p.value[2].toFixed(2)}}],
  });
  bind_focus(chart, p => {
    if (p.componentType === "yAxis") return {type: "client", id: String(p.value).split(" ")[0]};
    return (p.data && p.data.target) || null;
  });
}

subscribe(render_local_vs_global, "analysis");
subscribe(render_traffic, "analysis");
subscribe(render_rank, "analysis");
subscribe(render_similarity, "analysis");
