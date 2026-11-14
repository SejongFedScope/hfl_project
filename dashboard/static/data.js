const SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];  // 순차 색: 파랑 한 가지, 연함 → 진함

function render_data_heatmap(s) {  // 4.3.4 ③ 클라 × 숫자 표본 수, 엣지별 합
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_data");
  const L = lit();
  const comp = b.assignment.edge_composition;
  const pick = css_var("--pick");

  const rows = [];  // 위에서부터: E1 클라들, E1 합, E2 클라들, E2 합
  for (const e of Object.keys(comp).sort()) {
    [...comp[e].clients].sort().forEach(c => rows.push({key: c, label: c, edge: e, counts: b.split.clients[c].digit_counts, target: {type: "client", id: c}}));
    const covered = comp[e].digit_counts.filter(n => n > 0).length;
    rows.push({key: e, label: `${e} 합 · 숫자 ${covered}/10`, edge: e, counts: comp[e].digit_counts, target: {type: "edge", id: e}, total: true});
  }
  const max = Math.max(...rows.flatMap(r => r.counts));
  const show_num = (chart.getWidth() - 120) / 10 >= 32;  // 칸이 좁으면 숫자 숨김 (툴팁엔 그대로)

  const data = [];
  rows.forEach((row, yi) => {
    const row_on = !L || (row.total ? L.edges.has(row.edge) : L.clients.has(row.key));
    row.counts.forEach((n, d) => {
      const on = row_on && (!L || L.digits.has(d));
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
  chart.setOption({
    animationDurationUpdate: 150,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => (p.data && p.data.tip) || ""},
    grid: {left: 112, right: 8, top: 20, bottom: 8},
    visualMap: {show: false, min: 1, max, inRange: {color: SEQ_BLUE}},
    xAxis: {
      type: "category", data: [...Array(10).keys()].map(String), position: "top",
      axisLine: {show: false}, axisTick: {show: false}, axisLabel: {fontWeight: 700, color: css_var("--text-primary")},
    },
    yAxis: {
      type: "category", data: rows.map(r => r.label), inverse: true, triggerEvent: true,
      axisLine: {show: false}, axisTick: {show: false},
      axisLabel: {
        formatter: (v, i) => (rows[i].total ? `{total|${v}}` : `{c|${v}}  {e${rows[i].edge}|●}`),
        rich: {
          c: {fontWeight: 700, color: css_var("--text-primary")},
          total: {fontWeight: 700, color: css_var("--text-secondary")},
          eE1: {color: css_var("--e1")},
          eE2: {color: css_var("--e2")},
        },
      },
    },
    series: [{
      type: "heatmap", data, emphasis: {disabled: true},
      label: {show: show_num, fontSize: 10, fontWeight: 600, formatter: p => p.value[2].toLocaleString()},
    }],
  });
  bind_focus(chart, p => {
    if (p.componentType === "yAxis") return rows.find(r => r.label === p.value).target;
    return (p.data && p.data.target) || null;
  });
}

function render_client_table(state) {}  // TODO 4.3.6 ③ 클라별 담당 엣지, 손실·정확도·지연 작은 추이선, 실패 수

subscribe(render_data_heatmap);
