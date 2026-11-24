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
  const gc_vals = s.compare_bundle && s.compare_exp !== s.exp  // 비교 실험 공동 정확도 (같은 라운드 수까지)
    ? global_series(s.compare_bundle).slice(0, g.length).map(x => (x ? x.acc : null)) : [];
  const gc_line = gc_vals.some(v => v !== null) ? gc_vals : [];  // 비교 실험에 끝난 라운드가 없으면 점선·안내 없음
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
  const sorted_acc = [...all_acc].sort((p, q) => p - q);
  const acc_floor = sorted_acc.length ? Math.floor(sorted_acc[Math.floor(sorted_acc.length * 0.05)] * 20) / 20 : 0;  // 하위 5% 값부터 색을 나눔 → 첫 라운드 몇 칸 때문에 나머지가 다 진해지지 않게

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
      {text: `공동 모델 정확도  ${now ? (now.acc * 100).toFixed(1) + "%" : "–"}` + (gc_line.length ? "  (점선: 비교)" : ""), left: 0, top: 0,
        textStyle: {fontSize: 13, fontWeight: 600, color: text.color, width: chart.getWidth() * 0.54 - 8, overflow: "truncate"}},  // 값 = 선택 라운드, 손실 제목과 안 겹치게
      {text: `손실  ${now ? now.loss.toFixed(3) : "–"}`, left: "56%", top: 0, textStyle: {fontSize: 13, fontWeight: 600, color: text.color}},
      {text: worst_note, left: 0, top: "36%", textStyle: {fontSize: 13, fontWeight: 600, color: text.color}},
    ],
    grid: [
      {left: 40, right: "48%", top: 22, height: "22%"},  // 정확도·손실은 단위가 달라서 축을 나눠 나란히
      {left: "62%", right: 12, top: 22, height: "22%"},
      {left: 24, right: 52, top: "43%", bottom: 20},
    ],
    xAxis: [axis_x(0), axis_x(1), {...axis_x(2), position: "bottom"}],
    yAxis: [
      {type: "value", gridIndex: 0, min: v => Math.max(0, Math.floor(v.min * 10) / 10), max: 1, splitNumber: 2,
        axisLabel: {formatter: v => Math.round(v * 100) + "%"}, splitLine: {lineStyle: {color: grid_line}}},
      {type: "value", gridIndex: 1, splitNumber: 1, scale: true, axisLabel: {formatter: v => v.toFixed(1)}, splitLine: {lineStyle: {color: grid_line}}},
      {type: "category", gridIndex: 2, data: [...Array(10).keys()].map(String), inverse: true, axisTick: {show: false}, axisLine: {show: false},
        axisLabel: {color: ink, fontWeight: 700, fontSize: 12, interval: 0}},
    ],
    visualMap: {show: true, seriesIndex: 2, min: acc_floor, max: 1, inRange: {color: SEQ_BLUE}, orient: "vertical", right: 0, bottom: 24,
      itemWidth: 10, itemHeight: Math.max(40, Math.min(90, chart.getHeight() * 0.5 - 60)), calculable: false, text: ["100%", `${Math.round(acc_floor * 100)}% 이하`],  // 좁은 화면에선 짧게 (손실 그래프와 안 겹치게)
      textStyle: {fontSize: 11, color: css_var("--text-secondary")}},  // 대부분 값이 몰린 범위에 색 차이 → 낮은 칸이 눈에 띔
    series: [
      {...line("공동 정확도", g.map(x => (x ? x.acc : null)), v => (v * 100).toFixed(1) + "%"), xAxisIndex: 0, yAxisIndex: 0},
      {...line("손실", g.map(x => (x ? x.loss : null)), v => Number(v).toFixed(3)), xAxisIndex: 1, yAxisIndex: 1},
      {type: "heatmap", xAxisIndex: 2, yAxisIndex: 2, data: cells, emphasis: {disabled: true},
        label: {show: show_num, fontSize: 11, formatter: p => Math.round(p.value[2] * 100)}},
      ...(gc_line.length ? [{type: "line", name: "비교 실험 공동 정확도", data: gc_line, xAxisIndex: 0, yAxisIndex: 0, symbol: "none", silent: true,
        lineStyle: {width: 1.5, type: "dashed", color: css_var("--text-muted")}}] : []),  // 실험 비교용 점선 (맨 뒤: 히트맵 색 범례가 seriesIndex 2), 지연·중단의 하락 라운드가 보임
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

function config_diff(a, b) {  // 정확도에 영향을 주는 학습 설정 중 다른 것 (배정·결함·지연·라운드 수는 비교하려는 조건이라 뺌)
  const keys = {seed: "시드", lr: "학습률", local_epochs: "epoch", batch_size: "배치", samples_per_client: "클라당 장수",
    client_digits: "데이터 분할", init_model: "초기 모델"};
  return Object.entries(keys).filter(([k]) => JSON.stringify(a[k] ?? "zeros") !== JSON.stringify(b[k] ?? "zeros")).map(([, v]) => v);
}

function missing_rounds(b) {  // [[라운드, [빠진 클라...]], ...] — 배정된 클라 중 그 라운드에 집계에 안 들어간 클라 (지연·중단 실험)
  const all = Object.keys(client_edge(b));
  const out = [];
  for (let r = 1; r <= done_rounds(b); r++) {
    const joined = new Set(b.train.filter(x => x.round === r && x.participated).map(x => x.target));
    const gone = nsort(all.filter(c => !joined.has(c)));
    if (gone.length) out.push([r, gone]);
  }
  return out;
}

function edge_tv(b) {  // 엣지 쌍마다 숫자 분포 차이(총변동거리)를 재고 가장 큰 값 (엣지가 3개 이상이어도 됨)
  const comp = b.assignment.edge_composition;
  const es = nsort(Object.keys(comp));
  const dist = e => { const t = comp[e].n || 1; return comp[e].digit_counts.map(n => n / t); };
  let tv = 0;
  es.forEach((a, i) => es.slice(i + 1).forEach(c => {
    const p = dist(a), q = dist(c);
    tv = Math.max(tv, 0.5 * p.reduce((acc, v, k) => acc + Math.abs(v - q[k]), 0));
  }));
  return tv;
}

function compare_metrics(b) {
  const comp = b.assignment.edge_composition;
  const es = nsort(Object.keys(comp));
  const tv = edge_tv(b);
  const g = global_series(b).filter(Boolean);
  const reqs = b.comm.filter(x => x.round >= 1 && is_measured(x));  // 일부러 넣은 시험 요청은 성공률에서 뺌
  const durs = b.train.filter(x => x.target === "round").map(x => x.duration_ms);
  return [
    ["평균 선호 순위 (낮을수록 좋음)", b.assignment.check.mean_pref_rank == null ? "–" : b.assignment.check.mean_pref_rank.toFixed(2) + "위"],
    ["엣지 간 숫자 분포 차이 (0 = 같음)", es.length > 1 ? tv.toFixed(2) : "–"],
    ["마지막 라운드 공동 정확도", g.length ? (g[g.length - 1].acc * 100).toFixed(1) + "%" : "–"],
    ["요청 성공률 (시험 요청 제외)", reqs.length ? ((reqs.filter(x => x.ok).length / reqs.length) * 100).toFixed(1) + "%" : "–"],
    ["평균 라운드 시간", durs.length ? fmt_ms(durs.reduce((a, v) => a + v, 0) / durs.length) : "–"],
    ["집계에서 빠진 클라", missing_rounds(b).map(([r, cs]) => `R${r} ${cs.join("·")}`).join(", ") || "없음"],
  ];
}

function render_assign_compare(s) {  // 4.3.9 ④ 실험 비교: 두 실험의 엣지별 숫자 분포 + 지표 표 + 해석
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
  const label_of = (x, exp) => `${x.assignment.method === "pref" ? "선호" : "무작위"}${x.config.inject ? "·결함 주입" : ""}${x.config.fault_on ? "·지연·중단" : ""} (${exp})`;
  const diff_at = ga.map((x, i) => (x && gc[i] ? Math.abs(x.acc - gc[i].acc) * 100 : -1));
  const worst_r = diff_at.indexOf(Math.max(...diff_at)) + 1;
  const n = Math.min(ga.length, gc.length);
  const last_diff = n && ga[n - 1] && gc[n - 1] ? Math.abs(ga[n - 1].acc - gc[n - 1].acc) * 100 : null;

  // 두 실험의 엣지 × 숫자 표본 수를 나란히 (명세: 배정 방식 비교 = 선호 충족도 · 엣지별 숫자 분포 · 학습 성능 · 실행 기록)
  // 두 실험의 정확도 곡선은 학습 추세 패널에 점선으로 같이 그림 (여기서는 차이 숫자만)
  const sides = [[b, "이 실험"], [c, "비교 실험"]];
  const edges_b = nsort(Object.keys(b.assignment.edge_composition)), edges_c = nsort(Object.keys(c.assignment.edge_composition));
  const max_n = Math.max(1, ...[b, c].flatMap(x => Object.values(x.assignment.edge_composition).flatMap(v => v.digit_counts)));
  const cells = (x, gi) => nsort(Object.keys(x.assignment.edge_composition)).flatMap((e, yi) =>
    x.assignment.edge_composition[e].digit_counts.map((v, d) => ({
      value: [d, yi, v || "-"], tip: `${gi ? "비교" : "이"} 실험 · ${esc(e)} · 숫자 ${d}: ${v.toLocaleString()}장`,
      label: {color: v / max_n >= 0.5 ? "#ffffff" : "#0b0b0b"},
    })));
  const text = base_text();
  draw(chart, {
    animation: false,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => (p.data && p.data.tip) || ""},
    title: [
      {text: max_diff === null ? (done_rounds(c) ? "" : "비교 실험에 끝난 라운드가 없음")
        : `공동 정확도 최대 차이 ${max_diff.toFixed(1)}%p` + (max_diff < 0.05 ? " → 라운드마다 같음 (곡선은 학습 추세의 점선)"
          : ` (R${worst_r})` + (last_diff === null ? "" : ` · R${n} 차이 ${last_diff.toFixed(1)}%p` + (ga.length !== gc.length ? " (공통 마지막 라운드)" : ""))),
        left: 0, top: 0, textStyle: {fontSize: 13, fontWeight: 600, color: ink}},
      ...sides.map(([x, who], i) => ({text: `${who}: ${label_of(x, who).replace(/ \(.*\)$/, "")}`, left: i ? "52%" : 0, top: 20,
        textStyle: {fontSize: 12, fontWeight: 600, color: i ? muted : ink, width: chart.getWidth() * 0.46, overflow: "truncate"}})),  // 칸 = 엣지별 숫자 표본 (패널 설명에)
    ],
    grid: [{left: 28, right: "52%", top: 52, bottom: 18}, {left: "56%", right: 4, top: 52, bottom: 18}],
    xAxis: [0, 1].map(gi => ({type: "category", gridIndex: gi, data: [...Array(10).keys()].map(String), position: "bottom", axisTick: {show: false},
      axisLine: {show: false}, axisLabel: {color: ink, fontWeight: 700, fontSize: 11}})),
    yAxis: [edges_b, edges_c].map((es, gi) => ({type: "category", gridIndex: gi, data: es, inverse: true, axisTick: {show: false}, axisLine: {show: false},
      axisLabel: {color: ink, fontWeight: 700}})),
    visualMap: {show: false, min: 1, max: max_n, inRange: {color: SEQ_BLUE}, seriesIndex: [0, 1]},
    series: sides.map(([x], gi) => ({type: "heatmap", xAxisIndex: gi, yAxisIndex: gi, data: cells(x, gi), emphasis: {disabled: true},
      itemStyle: {borderColor: css_var("--surface"), borderWidth: 2}, label: {show: false}})),  // 칸 색 = 표본 수, 빈 칸 = 그 숫자 없음 (값은 툴팁)
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
  const miss = [[b, "이 실험"], [c, "비교 실험"]].flatMap(([x, who]) => missing_rounds(x).map(([r, cs]) => ({who, r, cs, x})));
  const diff_keys = config_diff(b.config, c.config);
  const at_worst = miss.filter(m => m.r === worst_r);  // 가장 크게 벌어진 라운드에 빠진 클라가 있을 때만 그 탓으로 봄
  const last_miss = Math.max(0, ...miss.map(m => m.r));
  cap.textContent = max_diff === null ? "" : diff_keys.length
    ? `해석: 두 실험의 학습 설정이 다름 (${diff_keys.join(", ")}) → 정확도 차이를 배정·결함·지연 탓으로 볼 수 없음. 같은 설정의 실험과 비교하세요`
    : max_diff < 0.05
      ? (b.assignment.method !== c.assignment.method
        ? "해석: 공동 정확도가 같음 — 모든 클라가 같은 공동 모델에서 시작해 다 참여하고, 엣지 집계 1번마다 중앙 집계 → 2단계 가중 평균 = 클라 전체 가중 평균이라 배정과 무관. 배정은 엣지 구성(분포 차이)·선호 충족도만 바꿈"
        : b.config.inject || c.config.inject
          ? "해석: 공동 정확도가 같음 — 일부러 넣은 시험 요청(지난 버전·배정 밖 엣지 제출)은 409 로 거부돼 집계에 안 들어감 → 버전 검사·배정 검사가 잘못된 제출을 막음"
          : "해석: 공동 정확도가 같음 — 같은 배정·같은 설정, 집계에서 빠진 클라도 없음")
      : at_worst.length
        ? `해석: ${at_worst.map(m => `${m.who}은 R${m.r} 에 ${m.cs.map(k => `${k}(숫자 ${digits_of(m.x, k).join("·")})`).join("·")} 가 빠짐`).join(", ")}` +
          ` → 그 라운드 집계에 그 숫자가 덜 들어가 공동 정확도가 ${max_diff.toFixed(1)}%p 벌어짐` +
          (last_miss < n && last_diff !== null && last_diff < 0.5 ? `. R${last_miss + 1} 부터 모두 참여해 회복 (R${n} 차이 ${last_diff.toFixed(1)}%p)` : "")
        : miss.length
          ? `해석: 가장 크게 벌어진 R${worst_r} 에는 빠진 클라가 없음 (빠진 라운드: ${miss.map(m => `R${m.r}`).join("·")}) → 다른 원인도 확인`
          : "해석: 공동 정확도가 다름 → 엣지 안에서 여러 번 집계했거나 일부 클라가 빠진 라운드가 있는지 확인 (같은 조건이면 원래 같아야 함)";
  table.prepend(cap);
  host.querySelector(".sub_table").replaceChildren(table);
  chart.resize();  // 표가 들어간 뒤 줄어든 그래프 칸에 맞춤
}

function headline_pin(s, t) {  // 고정한 대상 요약 한 줄 (명세 사용성: 지정한 클라·배정·통신 기록을 빨리 찾게) → [[글, 굵게?], ...]
  const b = s.bundle, r = s.round, ce = client_edge(b);
  const reqs = b.comm.filter(x => x.round === r);
  const req_text = xs => {
    const m = xs.filter(is_measured), f = m.filter(x => !x.ok).length, inj = xs.length - m.length;
    return [`R${r} 요청 ${m.length} · 실패 ${f}` + (inj ? ` · 시험 ${inj}` : ""), f > 0];
  };
  if (t.type === "client") {
    const c = t.id, e = ce[c], rank = b.assignment.check.client_pref_rank[c];
    const rec = b.train.find(x => x.target === c && x.round === r);
    return [[`${c} → ${e || "미배정"}`, true], [`숫자 ${digits_of(b, c).join("·")}`], [e && rank ? `${e} = ${c}의 ${rank}순위` : "배정 순위 없음"],
      [rec ? (rec.participated ? `R${r} 클라 모델 ${pct(rec.acc)}` : `R${r} 집계에서 빠짐`) : `R${r} 기록 없음`, !!rec && !rec.participated],
      req_text(reqs.filter(x => x.src === c))];
  }
  if (t.type === "edge") {
    const e = t.id, comp = b.assignment.edge_composition[e], cs = nsort(b.assignment.assignment[e] || []);
    const miss = comp.digit_counts.map((n, d) => (n ? null : d)).filter(d => d !== null);
    const row = b.train.find(x => x.target === e && x.round === r);
    const agg = row && row.clients ? row.clients.length : null;
    return [[`${e} · 클라 ${cs.join("·")}`, true], [`${comp.n.toLocaleString()}장`],
      [`숫자 ${10 - miss.length}/10` + (miss.length ? ` (${miss.join("·")} 없음)` : "")],
      ...(agg !== null && agg < cs.length ? [[`R${r} 집계 ${agg}명 (${row.clients.join("·")})`, true]] : []),
      req_text(reqs.filter(x => x.src === e || x.dst === e))];
  }
  const d = t.id, owners = nsort(Object.keys(b.split.clients).filter(c => b.split.clients[c].digit_counts[d] > 0));
  const g = b.train.find(x => x.target === "global" && x.round === r);
  const low = g ? g.acc_by_digit.indexOf(Math.min(...g.acc_by_digit)) === d : false;
  return [[`숫자 ${d}`, true], [`가진 클라 ${owners.map(c => `${c}(${ce[c] || "미배정"})`).join("·") || "없음"}`],
    [g ? `R${r} 공동 정확도 ${pct(g.acc_by_digit[d])}` + (low ? " · 이 라운드에서 가장 낮음" : "") : `R${r} 기록 없음`, low]];
}

function headline_result(s) {  // 지금 실험 쌍의 핵심 결과 한 줄 (5초 안에 결론) → [[글, 굵게?], ...]
  const b = s.bundle, c = s.compare_bundle;
  const ga = global_series(b), gc = c ? global_series(c) : [];
  const n = Math.min(done_rounds(b), c ? done_rounds(c) : 0);
  const name = x => `${x.assignment.method === "pref" ? "선호" : "무작위"}${x.config.inject ? "·결함 주입" : ""}${x.config.fault_on ? "·지연·중단" : ""}`;
  if (!c || !n || s.compare_exp === s.exp) {  // 비교 실험이 없거나, 자기 자신이거나, 비교 실험에 끝난 라운드가 없음
    const last = ga.filter(Boolean).pop();
    const why = !c ? "비교 실험을 고르면 차이를 요약" : s.compare_exp === s.exp ? "다른 비교 실험을 고르면 차이를 요약" : "비교 실험은 아직 끝난 라운드가 없음";
    return [[`${name(b)}`, true], [last ? `R${last.round} 공동 정확도 ${pct(last.acc)}` : "끝난 라운드 없음"], [why]];
  }
  const keys = config_diff(b.config, c.config);
  if (keys.length) return [[`${name(b)} vs ${name(c)}`, true], [`학습 설정이 다름 (${keys.join(", ")})`, true], ["정확도 차이를 비교 조건 탓으로 볼 수 없음"]];
  const acc = (g, r) => (g[r - 1] ? g[r - 1].acc : null);
  const diffs = [...Array(n).keys()].map(i => Math.abs(acc(ga, i + 1) - acc(gc, i + 1)) * 100);
  const max_d = Math.max(...diffs), worst = diffs.indexOf(max_d) + 1, last_d = diffs[n - 1];
  const same = max_d < 0.05;
  const fx = b.config.fault_on ? b : c.config.fault_on ? c : null;
  if (fx) {
    const all = missing_rounds(fx), other = fx === b ? c : b;
    const miss = all.filter(([r]) => r <= n), later = all.filter(([r]) => r > n);  // 두 실험이 다 끝낸 R1~Rn 안에서만 판단
    const said = all.length ? all.map(([r, cs]) => `R${r}에 ${cs.join("·")} 빠짐`).join(", ") : "빠진 클라 없음";
    if (!miss.length) return [[`지연·중단`, true], [said], [later.length ? `비교는 R${n}까지라 빠진 라운드는 비교 못 함` : `R1~R${n} 최대 차이 ${max_d.toFixed(1)}%p`]];
    const at = miss.find(([r]) => r === worst);
    const drop = (acc(global_series(fx), worst) - acc(global_series(other), worst)) * 100;
    const last_miss = Math.max(...miss.map(([r]) => r));
    const after = !at ? `R${n} 차이 ${last_d.toFixed(1)}%p`
      : last_miss < n && last_d < 0.5 ? `R${last_miss + 1}부터 회복 (R${n} 차이 ${last_d.toFixed(1)}%p)`  // 실제로 차이가 줄었을 때만 '회복'
      : `R${n} 차이 ${last_d.toFixed(1)}%p`;
    return [[`지연·중단`, true], [said],
      [at ? `R${worst} 공동 정확도 ${drop >= 0 ? "+" : ""}${drop.toFixed(1)}%p` : `가장 큰 차이 R${worst} ${max_d.toFixed(1)}%p (빠진 라운드 아님)`, true], [after]];
  }
  const ix = b.config.inject ? b : c.config.inject ? c : null;
  if (ix && b.assignment.method === c.assignment.method) {
    const inj = ix.comm.filter(x => !is_measured(x)), rej = inj.filter(x => !x.ok).length;
    return [[`결함 주입`, true], [`시험 요청 ${inj.length}건 중 ${rej}건 거부`, rej === inj.length], [rej === inj.length ? "집계에 안 들어감" : "일부가 받아들여짐"],
      [same ? `공동 정확도 같음 (${pct(acc(ga, n))})` : `공동 정확도 최대 차이 ${max_d.toFixed(1)}%p`, true]];
  }
  if (b.assignment.method !== c.assignment.method) {
    const rk = x => x.assignment.check.mean_pref_rank;
    return [[`${name(b)} vs ${name(c)}`, true], [`선호 충족도 ${rk(b) == null ? "–" : rk(b).toFixed(2)}위 vs ${rk(c) == null ? "–" : rk(c).toFixed(2)}위`, true],
      [`엣지 간 숫자 분포 차이 ${edge_tv(b).toFixed(2)} vs ${edge_tv(c).toFixed(2)}`, true],
      [same ? `공동 정확도 같음 (${pct(acc(ga, n))}) → 배정은 엣지 구성만 바꿈` : `공동 정확도 최대 차이 ${max_d.toFixed(1)}%p (R${worst})`]];
  }
  return [[`${name(b)} vs ${name(c)}`, true], [same ? `공동 정확도 같음 (${pct(acc(ga, n))})` : `공동 정확도 최대 차이 ${max_d.toFixed(1)}%p (R${worst})`]];
}

function render_headline(s) {
  const host = document.getElementById("headline");
  if (!s.bundle || !done_rounds(s.bundle)) { host.replaceChildren(); return; }
  const t = state.pinned;  // 고정한 대상이 있으면 그 요약, 없으면 실험 쌍의 핵심 결과
  const parts = t ? headline_pin(s, t) : headline_result(s);
  const text = make_el("span", "headline_text", "");
  parts.forEach(([p, bold], i) => {
    if (i) text.append(make_el("span", "sep", "·"));
    text.append(make_el(bold ? "b" : "span", "", p));
  });
  host.replaceChildren(make_el("span", t ? "headline_tag pin" : "headline_tag", t ? "고정한 대상" : "핵심 결과"), text);
  host.title = parts.map(([p]) => p).join(" · ");
}

subscribe(render_trend);
subscribe(render_headline);
subscribe(render_headline, "analysis");
subscribe(render_assign_compare);
