const SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];  // 순차 색: 파랑 한 가지, 연함 → 진함

function render_data_heatmap(s) {  // 4.3.4 ③ 클라 × 숫자 표본 수, 엣지별 합
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_data");
  const L = lit();
  const comp = b.assignment.edge_composition;
  const pick = css_var("--pick");

  const r = s.round;
  const ran = b.train.some(x => x.round === r);  // 아직 안 돈 라운드면 배정대로 보여 줌
  const joined = new Set(b.train.filter(x => x.round === r && x.participated).map(x => x.target));
  const out = c => ran && !joined.has(c);  // 이 라운드 집계에서 빠진 클라 (지연·중단 실험)
  const rows = [], lost = [];  // 위에서부터: E1 클라들, E1 합, E2 클라들, E2 합
  for (const e of nsort(Object.keys(comp))) {
    const cs = nsort(comp[e].clients);
    cs.forEach(c => rows.push({key: c, label: out(c) ? `${c} · R${r} 빠짐` : c, edge: e, counts: b.split.clients[c].digit_counts, target: {type: "client", id: c}, out: out(c)}));
    const kept = cs.filter(c => !out(c));
    const counts = kept.length === cs.length ? comp[e].digit_counts
      : [...Array(10).keys()].map(d => kept.reduce((a, c) => a + b.split.clients[c].digit_counts[d], 0));
    const n = counts.reduce((a, v) => a + v, 0);
    const covered = counts.filter(v => v > 0).length;
    const gone = comp[e].digit_counts.map((v, d) => (v > 0 && counts[d] === 0 ? d : null)).filter(d => d !== null);
    if (gone.length) lost.push(`${e} 숫자 ${gone.join("·")}`);
    rows.push({key: e, label: `${e} 합 · ${n.toLocaleString()}장\n` + (kept.length === cs.length ? `클라 ${cs.length}` : `R${r} ${kept.length}/${cs.length}명`) +
      ` · 숫자 ${covered}/10`, edge: e, counts, target: {type: "edge", id: e}, total: true});  // 명세 '엣지별 구성': 담당 클라 수 · 전체 표본 수(= 중앙 집계 가중치) · 숫자 종류
  }
  const max = Math.max(...rows.flatMap(r => r.counts));
  const show_num = (chart.getWidth() - 120) / 10 >= 26;  // 칸이 좁으면 숫자 숨김 (툴팁엔 그대로)

  const data = [];
  rows.forEach((row, yi) => {
    const row_on = !L || (row.total ? L.edges.has(row.edge) : L.clients.has(row.key));
    row.counts.forEach((n, d) => {
      const on = row_on && (!L || L.digits.has(d)) && !row.out;  // 빠진 클라 줄은 흐리게
      data.push({
        value: [d, yi, n > 0 ? n : "-"],  // 0 은 칸을 비워 둠
        target: {type: "digit", id: d},
        tip: `${esc(row.label.split(" ·")[0])} · 숫자 ${d} · ${n.toLocaleString()}장`,
        itemStyle: {opacity: on ? 1 : DIM, borderColor: L && on && n > 0 ? pick : css_var("--surface"), borderWidth: 2},
        label: {opacity: on ? 1 : DIM, color: n / max >= 0.5 ? "#ffffff" : "#0b0b0b"},  // 진한 칸만 흰 글씨
      });
    });
  });

  const text = base_text();
  const missing = nsort(Object.keys(comp)).map(e => [e, comp[e].digit_counts.map((n, d) => (n ? null : d)).filter(d => d !== null)]);
  const gaps = missing.filter(([, ds]) => ds.length);
  const note = (gaps.length ? "해석: " + gaps.map(([e, ds]) => `${e}에 숫자 ${ds.join("·")} 없음`).join(", ") + " → 엣지 모델이 그 숫자를 못 배움"
    : "해석: 모든 엣지가 숫자 0~9 를 다 가짐 → 엣지끼리 데이터 구성이 비슷") +
    (lost.length ? ` · R${r} 에는 빠진 클라 때문에 ${lost.join(", ")} 도 집계에 없음` : "");
  draw(chart, {
    animation: false,  // 글자·칸이 바로 보이게 애니메이션 끔
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => (p.data && p.data.tip) || ""},
    title: {text: note, left: 0, bottom: 0, textStyle: {fontSize: 13, fontWeight: 600, color: text.color, width: chart.getWidth() - 8, overflow: "break"}},  // 좁으면 두 줄로
    grid: {left: 168, right: 8, top: 20, bottom: 42},  // 엣지 합 줄 이름(클라 수·표본 수)이 다 보이게
    visualMap: {show: false, min: 1, max, inRange: {color: SEQ_BLUE}},
    xAxis: {
      type: "category", data: [...Array(10).keys()].map(String), position: "top",
      axisLine: {show: false}, axisTick: {show: false}, axisLabel: {fontWeight: 700, color: css_var("--text-primary")},
    },
    yAxis: {
      type: "category", data: rows.map(r => r.label), inverse: true, triggerEvent: true,
      axisLine: {show: false}, axisTick: {show: false},
      axisLabel: {
        formatter: (v, i) => (rows[i].total ? `{total|${v}}` : `{c|${v}}  {e${edges_of(b).indexOf(rows[i].edge)}|●}`),
        rich: Object.assign(
          {c: {fontWeight: 700, color: css_var("--text-primary")}, total: {fontWeight: 700, color: css_var("--text-secondary")}},
          ...edges_of(b).map((e, i) => ({[`e${i}`]: {color: edge_color(e)}})),  // 엣지 수만큼 점 색
        ),
      },
    },
    series: [{
      type: "heatmap", data, emphasis: {disabled: true},
      label: {show: show_num, fontSize: 12, fontWeight: 600, formatter: p => p.value[2].toLocaleString()},
    }],
  });
  bind_focus(chart, p => {
    if (p.componentType === "yAxis") return rows.find(r => r.label === p.value).target;
    return (p.data && p.data.target) || null;
  });
}

function sparkline(values, cur, fmt) {  // 작은 추이선 + 선택 라운드 점·값 (숫자만 넣어서 만든 SVG)
  const w = 44, h = 16, pts = values.map((v, i) => [i, v]).filter(([, v]) => v !== null);
  const span = document.createElement("span");
  span.className = "spark";
  if (!pts.length) { span.textContent = "–"; return span; }
  const vs = pts.map(([, v]) => v);
  const lo = Math.min(...vs), hi = Math.max(...vs), n = Math.max(values.length - 1, 1);
  const xy = (i, v) => [2 + (i / n) * (w - 4), hi === lo ? h / 2 : h - 2 - ((v - lo) / (hi - lo)) * (h - 4)];
  const line = pts.map(([i, v]) => xy(i, v).map(c => c.toFixed(1)).join(",")).join(" ");
  const now = values[cur - 1];
  const dot = now === null || now === undefined ? "" : (() => { const [x, y] = xy(cur - 1, now); return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" fill="var(--pick)"/>`; })();
  span.innerHTML = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${line}" fill="none" stroke="var(--text-muted)" stroke-width="1.5"/>${dot}</svg>`;
  const val = document.createElement("b");
  val.textContent = now === null || now === undefined ? "–" : fmt(now);
  span.appendChild(val);
  return span;
}

function render_client_table(s) {  // 4.3.6 ③ 클라별 담당 엣지, 정확도·학습 손실·지연 추이, 실패 수
  const b = s.bundle;
  if (!b) return;
  const host = document.getElementById("p_clients");
  const L = lit();
  const R = b.config.rounds;
  const comp = b.assignment.edge_composition;
  const clients = nsort(Object.keys(comp)).flatMap(e => nsort(comp[e].clients).map(c => [c, e]));

  const table = document.createElement("table");
  table.className = "tbl";
  table.innerHTML = `<caption>주황 점 = 라운드 ${s.round} · 정확도는 클라 학습 직후 공통 시험 데이터 기준 · 실패는 R${s.round}까지 누적</caption>
    <thead><tr><th>클라</th><th title="클라가 학습한 직후 모델을 공통 시험 데이터로 잰 값 (공동 모델 정확도와 다름)">클라 모델 정확도</th><th>학습 손실</th><th>평균 지연</th><th class="num">실패</th></tr></thead>`;
  const tbody = document.createElement("tbody");
  for (const [c, e] of clients) {
    const rec = r => b.train.find(x => x.target === c && x.round === r);
    const per_round = f => [...Array(R).keys()].map(i => { const x = rec(i + 1); return x ? f(x) : null; });
    const lat = [...Array(R).keys()].map(i => {
      const ok = b.comm.filter(x => x.src === c && x.round === i + 1 && x.ok);
      return ok.length ? ok.reduce((a, x) => a + x.latency_ms, 0) / ok.length : null;
    });
    const fails = b.comm.filter(x => x.src === c && x.round <= s.round && !x.ok && is_measured(x)).length;
    const tests = b.comm.filter(x => x.src === c && x.round <= s.round && !x.ok && !is_measured(x)).length;

    const tr = document.createElement("tr");
    if (L && !L.clients.has(c)) tr.className = "dim";
    const name = document.createElement("td");
    const dot = document.createElement("i");
    dot.className = "dot";
    dot.style.background = edge_color(e);
    name.append(dot, ` ${c} (${e})`);
    const cells = [
      sparkline(per_round(x => x.acc), s.round, v => (v * 100).toFixed(1) + "%"),
      sparkline(per_round(x => x.train_loss), s.round, v => v.toFixed(3)),
      sparkline(lat, s.round, v => Math.round(v) + " ms"),
    ].map(sp => { const td = document.createElement("td"); td.appendChild(sp); return td; });
    const fail_td = document.createElement("td");
    fail_td.className = "num" + (fails ? " bad" : "");
    fail_td.textContent = tests ? `${fails}+시험${tests}` : String(fails);  // 일부러 넣은 시험 요청은 따로
    fail_td.title = "실제 실패 수 (괄호 = 일부러 넣은 시험 요청 수)";
    tr.append(name, ...cells, fail_td);
    const who = {type: "client", id: c};
    tr.onmouseenter = () => set_hover(who);
    tr.onmouseleave = () => set_hover(null);
    tr.onclick = () => set_pin(who);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  host.replaceChildren(table);
}

subscribe(render_data_heatmap);
subscribe(render_client_table);
