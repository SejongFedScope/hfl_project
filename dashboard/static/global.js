function global_series(b) {  // 라운드별 공동 모델 기록 (중앙 2차 집계 뒤 평가)
  return [...Array(b.config.rounds).keys()].map(i => b.train.find(x => x.target === "global" && x.round === i + 1) || null);
}

function draw_empty(chart, msg) {  // 그릴 기록이 없을 때 이유를 가운데에
  draw(chart, {title: {text: msg, left: "center", top: "middle", textStyle: {fontSize: 14, fontWeight: 400, color: css_var("--text-muted")}}});
}

function render_trend(s) {  // 4.3.5 ④ 공동 모델 정확도·손실 + 라운드 × 숫자 정확도
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_trend");
  if (!done_rounds(b)) return draw_empty(chart, "아직 끝난 라운드가 없음");
  const L = lit();
  const g = global_series(b);
  const rounds = g.map((_, i) => `R${i + 1}`);
  const ink = css_var("--text-primary");
  const grid_line = css_var("--hairline");
  const pick = css_var("--pick");
  const cur = s.round - 1;
  const now = g[cur];
  const worst = now ? now.acc_by_digit.indexOf(Math.min(...now.acc_by_digit)) : -1;
  const owners = worst < 0 ? [] : nsort(Object.keys(b.split.clients).filter(c => b.split.clients[c].digit_counts[worst] > 0));
  const ce = client_edge(b);
  const worst_note = worst < 0 ? "숫자별 정확도 %" :
    `숫자별 정확도 % · R${s.round} 최저 = 숫자 ${worst} (${(now.acc_by_digit[worst] * 100).toFixed(1)}%), 보유: ${owners.map(c => `${c}(${ce[c] || "미배정"})`).join(" ")}`;
  const show_num = (chart.getWidth() - 40) / rounds.length >= 26 && (chart.getHeight() * 0.5) / 10 >= 13;
  const all_acc = g.filter(Boolean).flatMap(x => x.acc_by_digit);
  const acc_floor = all_acc.length ? Math.floor(Math.min(...all_acc) * 10) / 10 : 0;

  const cells = [];
  g.forEach((x, ri) => {
    if (!x) return;
    x.acc_by_digit.forEach((a, d) => {
      const on = !L || L.digits.has(d);
      const is_worst = ri === cur && d === worst;
      cells.push({
        value: [ri, d, a],
        target: {type: "digit", id: d}, r: ri + 1,
        tip: `라운드 ${ri + 1} · 숫자 ${d} 정확도 ${(a * 100).toFixed(1)}%` + (is_worst ? "<br><b>이 라운드에서 가장 낮음</b>" : ""),
        itemStyle: {
          opacity: on ? 1 : DIM,
          borderColor: is_worst ? css_var("--critical") : ri === cur ? ink : css_var("--surface"),
          borderWidth: is_worst || ri === cur ? 2 : 1,
        },
        label: {opacity: on ? 1 : DIM, color: (a - acc_floor) / (1 - acc_floor || 1) >= 0.5 ? "#ffffff" : "#0b0b0b"},
      });
    });
  });

  const line = (name, vals, fmt) => ({
    type: "line", name, data: vals, symbol: "circle", symbolSize: 6, showSymbol: true,
    lineStyle: {width: 2, color: ink}, itemStyle: {color: ink},
    markLine: {symbol: "none", silent: true, label: {show: false}, lineStyle: {color: pick, type: "solid", width: 1.5}, data: [{xAxis: cur}]},
  });
  const axis_x = gi => ({type: "category", gridIndex: gi, data: rounds, boundaryGap: gi === 2, axisTick: {show: false},
    axisLine: {lineStyle: {color: css_var("--border")}}, axisLabel: {show: gi === 2, color: ink, fontWeight: 700, interval: rounds.length > 12 ? 1 : 0}});
  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => (p.data && p.data.tip) || `${p.seriesName} · ${p.name}: ${p.seriesName === "손실" ? Number(p.value).toFixed(3) : (p.value * 100).toFixed(1) + "%"}`},
    title: [
      {text: `공동 모델 정확도  ${now ? (now.acc * 100).toFixed(1) + "%" : "–"}`, left: 0, top: 0, textStyle: {fontSize: 13, fontWeight: 600, color: text.color}},  // 값 = 선택 라운드
      {text: `손실  ${now ? now.loss.toFixed(3) : "–"}`, left: "56%", top: 0, textStyle: {fontSize: 13, fontWeight: 600, color: text.color}},
      {text: worst_note, left: 0, top: "36%", textStyle: {fontSize: 13, fontWeight: 600, color: text.color}},
    ],
    grid: [
      {left: 40, right: "48%", top: 22, height: "22%"},  // 정확도·손실은 단위가 달라서 축을 나눠 나란히
      {left: "62%", right: 12, top: 22, height: "22%"},
      {left: 24, right: 8, top: "43%", bottom: 20},
    ],
    xAxis: [axis_x(0), axis_x(1), {...axis_x(2), position: "bottom"}],
    yAxis: [
      {type: "value", gridIndex: 0, min: v => Math.max(0, Math.floor(v.min * 10) / 10), max: 1, splitNumber: 2,
        axisLabel: {formatter: v => Math.round(v * 100) + "%"}, splitLine: {lineStyle: {color: grid_line}}},
      {type: "value", gridIndex: 1, splitNumber: 1, scale: true, axisLabel: {formatter: v => v.toFixed(1)}, splitLine: {lineStyle: {color: grid_line}}},
      {type: "category", gridIndex: 2, data: [...Array(10).keys()].map(String), inverse: true, axisTick: {show: false}, axisLine: {show: false},
        axisLabel: {color: ink, fontWeight: 700, fontSize: 12, interval: 0}},
    ],
    visualMap: {show: false, seriesIndex: 2, min: acc_floor, max: 1, inRange: {color: SEQ_BLUE}},  // 실제 값 범위에 맞춰 칸 색 차이가 보이게
    series: [
      {...line("공동 정확도", g.map(x => (x ? x.acc : null)), v => (v * 100).toFixed(1) + "%"), xAxisIndex: 0, yAxisIndex: 0},
      {...line("손실", g.map(x => (x ? x.loss : null)), v => Number(v).toFixed(3)), xAxisIndex: 1, yAxisIndex: 1},
      {type: "heatmap", xAxisIndex: 2, yAxisIndex: 2, data: cells, emphasis: {disabled: true},
        label: {show: show_num, fontSize: 11, formatter: p => Math.round(p.value[2] * 100)}},
    ],
  });
  bind_focus(chart, (p, is_click) => {
    if (p.seriesType === "line") {
      if (is_click) set_round(p.dataIndex + 1);
      return null;
    }
    if (!p.data || !p.data.target) return null;
    if (is_click) set_round(p.data.r);
    return p.data.target;
  });
}

function compare_metrics(b) {
  const comp = b.assignment.edge_composition;
  const es = nsort(Object.keys(comp));
  const dist = e => { const t = comp[e].n || 1; return comp[e].digit_counts.map(n => n / t); };
  let tv = 0;  // 엣지 쌍마다 숫자 분포 차이(총변동거리)를 재고 가장 큰 값 (엣지가 3개 이상이어도 됨)
  es.forEach((a, i) => es.slice(i + 1).forEach(c => {
    const p = dist(a), q = dist(c);
    tv = Math.max(tv, 0.5 * p.reduce((acc, v, k) => acc + Math.abs(v - q[k]), 0));
  }));
  const g = global_series(b).filter(Boolean);
  const reqs = b.comm.filter(x => x.round >= 1 && is_measured(x));  // 일부러 넣은 시험 요청은 성공률에서 뺌
  const durs = b.train.filter(x => x.target === "round").map(x => x.duration_ms);
  return [
    ["배정 방식", b.assignment.method === "pref" ? "선호(matching)" : b.assignment.method === "random" ? "무작위" : b.assignment.method],
    ["평균 선호 순위 (낮을수록 좋음)", b.assignment.check.mean_pref_rank == null ? "–" : b.assignment.check.mean_pref_rank.toFixed(2) + "위"],
    ["엣지별 숫자 종류", es.map(e => `${e} ${comp[e].digit_counts.filter(n => n > 0).length}`).join(" · ")],
    ["엣지 간 숫자 분포 차이 (0 = 같음)", es.length > 1 ? tv.toFixed(2) : "–"],
    ["마지막 라운드 공동 정확도", g.length ? (g[g.length - 1].acc * 100).toFixed(1) + "%" : "–"],
    ["요청 성공률 (시험 요청 제외)", reqs.length ? ((reqs.filter(x => x.ok).length / reqs.length) * 100).toFixed(1) + "%" : "–"],
    ["평균 라운드 시간", durs.length ? fmt_ms(durs.reduce((a, v) => a + v, 0) / durs.length) : "–"],
  ];
}

function render_assign_compare(s) {  // 4.3.9 ④ 선호 vs 무작위: 정확도 곡선 + 배정·구성 지표 표
  const b = s.bundle, c = s.compare_bundle;
  if (!b) return;
  const host = document.getElementById("p_compare");
  if (!document.getElementById("p_compare_chart")) {
    host.innerHTML = '<div id="p_compare_chart" class="sub_chart"></div><div class="sub_table"></div>';
  }
  const chart = chart_of("p_compare_chart");
  if (!c) {  // 비교 실험을 못 불러오면 빈칸 대신 이유
    host.querySelector(".sub_table").replaceChildren();
    chart.resize();
    return draw_empty(chart, "비교 실험을 불러오지 못함 · 위에서 다른 실험을 고르세요");
  }
  const ink = css_var("--text-primary");
  const muted = css_var("--text-muted");
  const ga = global_series(b), gc = global_series(c);
  const R = Math.max(ga.length, gc.length);
  const diffs = ga.map((x, i) => (x && gc[i] ? Math.abs(x.acc - gc[i].acc) * 100 : null)).filter(v => v !== null);
  const max_diff = diffs.length ? Math.max(...diffs) : null;
  const label_of = (x, exp) => `${x.assignment.method === "pref" ? "선호" : "무작위"} (${exp})`;

  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "axis", valueFormatter: v => (v === null || v === undefined ? "–" : (v * 100).toFixed(1) + "%")},
    title: {text: max_diff === null ? (done_rounds(c) ? "" : "비교 실험에 끝난 라운드가 없어 곡선 비교 불가")
      : `공동 정확도 최대 차이 ${max_diff.toFixed(1)}%p` + (max_diff < 0.05 ? " → 두 배정의 공동 모델이 같음" : ""),
      left: 0, top: 0, textStyle: {fontSize: 13, fontWeight: 600, color: ink}},
    legend: {top: 18, left: 0, itemWidth: 16, itemHeight: 2, textStyle: {fontSize: 12, color: text.color}},
    grid: {left: 40, right: 12, top: 42, bottom: 18},
    xAxis: {type: "category", data: [...Array(R).keys()].map(i => `R${i + 1}`), axisTick: {show: false},
      axisLine: {lineStyle: {color: css_var("--border")}}, axisLabel: {color: ink, fontWeight: 700, interval: R > 12 ? 1 : 0}},
    yAxis: {type: "value", min: v => Math.max(0, Math.floor(v.min * 10) / 10), max: 1, splitNumber: 2,
      axisLabel: {formatter: v => Math.round(v * 100) + "%"}, splitLine: {lineStyle: {color: css_var("--hairline")}}},
    series: [
      {type: "line", name: label_of(b, "이 실험"), data: ga.map(x => (x ? x.acc : null)), symbol: "circle", symbolSize: 6,
        lineStyle: {width: 2, color: ink}, itemStyle: {color: ink}},
      {type: "line", name: label_of(c, "비교 실험"), data: gc.map(x => (x ? x.acc : null)), symbol: "emptyCircle", symbolSize: 8,
        lineStyle: {width: 2, type: "dashed", color: muted}, itemStyle: {color: muted}},
    ],
  });

  const ma = compare_metrics(b), mc = compare_metrics(c);
  const table = document.createElement("table");
  table.className = "tbl";
  table.innerHTML = `<thead><tr><th>항목</th><th>이 실험</th><th>비교 실험</th></tr></thead>`;
  const tbody = document.createElement("tbody");
  ma.forEach(([name, va], i) => {
    const tr = document.createElement("tr");
    [name, va, mc[i][1]].forEach((v, ci) => {
      const td = document.createElement("td");
      td.textContent = v;
      if (ci > 0 && va !== mc[i][1]) td.className = "diff";  // 두 실험이 다른 값만 굵게
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  const cap = document.createElement("caption");
  cap.textContent = max_diff === null ? "" : max_diff < 0.05
    ? "해석: 모든 클라가 같은 공동 모델에서 시작해 다 참여하고, 엣지 집계 1번마다 중앙 집계 → 2단계 가중 평균 = 클라 전체 가중 평균이라 배정과 무관하게 공동 모델이 같음. 배정은 엣지 구성(분포 차이)만 바꿈"
    : "해석: 공동 정확도가 다름 → 엣지 안에서 여러 번 집계했거나 일부 클라가 빠진 라운드가 있는지 확인 (같은 조건이면 원래 같아야 함)";
  table.prepend(cap);
  host.querySelector(".sub_table").replaceChildren(table);
  chart.resize();  // 표가 들어간 뒤 줄어든 그래프 칸에 맞춤
}

subscribe(render_trend);
subscribe(render_assign_compare);
