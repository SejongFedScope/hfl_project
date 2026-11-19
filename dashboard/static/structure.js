function round_failures(b, r) {  // {보낸 쪽: 실패 수}, 실제 실패와 일부러 넣은 시험 요청(injected)을 따로 셈
  const real = {}, test = {};
  b.comm.filter(x => x.round === r && !x.ok).forEach(x => {
    const box = is_measured(x) ? real : test;
    box[x.src] = (box[x.src] || 0) + 1;
  });
  return {real, test};
}

function digits_of(b, c) {
  return b.split.clients[c].digit_counts.map((n, d) => (n > 0 ? d : null)).filter(d => d !== null);
}

function render_tree(s) {  // 4.3.2 ① 계층 트리
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_tree");
  const L = lit();
  const {real: fails, test: tests} = round_failures(b, s.round);
  const joined = new Set(b.train.filter(x => x.round === s.round && x.participated).map(x => x.target));
  const round_ran = b.train.some(x => x.round === s.round);  // 아직 안 돌린 라운드면 '미참여' 표시 안 함
  const pick = css_var("--pick");
  const muted = css_var("--text-muted");
  const critical = css_var("--critical");

  const node_style = (color, on) => ({
    color, opacity: on ? 1 : DIM,
    borderColor: L && on ? pick : color, borderWidth: L && on ? 2 : 1,
  });

  const edges = edges_of(b).map(e => {
    const on_e = !L || L.edges.has(e);
    const clients = nsort(b.assignment.assignment[e]).map(c => {
      const on_c = !L || L.clients.has(c);
      const f = fails[c] || 0, t = tests[c] || 0;
      const absent = round_ran && !joined.has(c);
      return {
        name: c,
        target: {type: "client", id: c},
        itemStyle: node_style(absent ? muted : edge_color(e), on_c),
        lineStyle: {color: edge_color(e), opacity: on_c ? 0.8 : DIM},
        label: {
          opacity: on_c ? 1 : DIM,
          formatter: `{id|${c}}  {d|${digits_of(b, c).join(" ")}}` + (f ? `  {bad|실패 ${f}}` : "") + (t ? `  {test|시험 ${t}}` : "") + (absent ? "  {bad|미참여}" : ""),
        },
        tip: `${esc(c)} · ${esc(e)}<br>숫자 ${digits_of(b, c).join(", ")} · ${b.split.clients[c].n.toLocaleString()}장` +
          (f ? `<br>이번 라운드 실패 요청 ${f}건` : "") + (t ? `<br>일부러 넣은 시험 요청 ${t}건 (거부됨)` : "") + (absent ? "<br>이번 라운드 미참여" : ""),
      };
    });
    const f = fails[e] || 0;
    return {
      name: e,
      target: {type: "edge", id: e},
      itemStyle: node_style(edge_color(e), on_e),
      lineStyle: {color: edge_color(e), opacity: on_e ? 0.8 : DIM},
      label: {position: "top", align: "center", distance: 8, opacity: on_e ? 1 : DIM, formatter: `{id|${e}}` + (f ? `  {bad|실패 ${f}}` : "")},  // 선과 안 겹치게 노드 위
      tip: `${esc(e)} · 클라 ${clients.length}명 · 표본 ${b.assignment.edge_composition[e].n.toLocaleString()}장` + (f ? `<br>이번 라운드 실패 요청 ${f}건` : ""),
      children: clients,
    };
  });

  const unassigned = nsort(b.assignment.check.unassigned || []);
  if (unassigned.length) {  // 배정 실패한 클라도 트리에 보여 줌 (회색 점선)
    edges.push({
      name: "미배정", itemStyle: {color: muted, opacity: L ? DIM : 1}, lineStyle: {color: muted, type: "dashed"},
      label: {position: "top", align: "center", distance: 8, formatter: "{bad|미배정}"},
      tip: `배정 안 된 클라 ${unassigned.length}명`,
      children: unassigned.map(c => ({
        name: c, target: {type: "client", id: c}, itemStyle: {color: muted, opacity: !L || L.clients.has(c) ? 1 : DIM},
        lineStyle: {color: muted, type: "dashed"}, label: {formatter: `{id|${c}}  {bad|미배정}`}, tip: `${esc(c)} · 배정 안 됨`,
      })),
    });
  }

  const root = {
    name: "S",
    itemStyle: {color: css_var("--text-secondary"), opacity: L ? DIM : 1},
    label: {formatter: "{id|중앙 S}", opacity: L ? DIM : 1},
    tip: "중앙 서버 S · 2차 집계",
    children: edges,
  };

  const text = base_text();
  draw(chart, {
    animation: false,  // 글자·칸이 바로 보이게 애니메이션 끔
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => p.data.tip || esc(p.name)},
    series: [{
      type: "tree", data: [root], orient: "LR", layout: "orthogonal",
      left: 56, right: 120, top: 12, bottom: 12,
      symbol: "circle", symbolSize: 11, expandAndCollapse: false, roam: false,
      lineStyle: {width: 1.5, curveness: 0.5},
      label: {
        position: "left", verticalAlign: "middle", align: "right", fontSize: 13,
        rich: {
          id: {fontWeight: 700, color: css_var("--text-primary"), fontSize: 14},
          d: {color: text.color, fontSize: 13},
          bad: {color: critical, fontWeight: 700, fontSize: 13},
          test: {color: css_var("--text-secondary"), fontSize: 13, backgroundColor: css_var("--warning"), padding: [1, 3], borderRadius: 2},
        },
      },
      leaves: {label: {position: "right", align: "left"}},
      emphasis: {disabled: true},
    }],
  });
  bind_focus(chart, p => (p.data && p.data.target) || null);
}

function render_assign_matrix(s) {  // 4.3.3 ① 선호·배정 행렬
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_assign");
  const a = b.assignment;
  const L = lit();
  const edges = nsort(Object.keys(a.edge_prefs));
  const clients = nsort(Object.keys(a.client_prefs));
  const ce = client_edge(b);
  const pick = css_var("--pick");

  const data = [];
  clients.forEach((c, yi) => {
    edges.forEach((e, xi) => {
      const assigned = ce[c] === e;
      const c_rank = a.client_prefs[c].indexOf(e) + 1;
      const e_rank = a.edge_prefs[e].indexOf(c) + 1;
      const on = !L || (L.clients.has(c) && (L.edges.has(e) || !assigned));
      data.push({
        value: [xi, yi, assigned ? 1 : 0],
        target: {type: "client", id: c},
        tip: `${esc(c)} → ${esc(e)}: 클라가 매긴 순위 ${c_rank}위 · 엣지가 매긴 순위 ${e_rank}위` + (assigned ? "<br><b>실제 배정</b>" : ""),
        itemStyle: {
          color: assigned ? edge_color(e) : css_var("--sunken"),
          opacity: on ? 1 : DIM,
          borderColor: L && on && assigned ? pick : css_var("--surface"),
          borderWidth: L && on && assigned ? 2 : 2,
        },
        label: {
          show: true, opacity: on ? 1 : DIM,
          color: assigned ? "#ffffff" : css_var("--text-secondary"),
          fontWeight: assigned ? 700 : 400,
          formatter: `클라 ${c_rank}위 · 엣지 ${e_rank}위`,
        },
      });
    });
  });

  const ck = a.check;
  const summary = `평균 선호 순위 ${ck.mean_pref_rank == null ? "–" : ck.mean_pref_rank.toFixed(2) + "위"} · 미배정 ${ck.unassigned.length} · 중복 ${ck.duplicated.length} · 정원 위반 ${ck.capacity_violation.length}`;
  const text = base_text();
  draw(chart, {
    animation: false,  // 글자·칸이 바로 보이게 애니메이션 끔
    textStyle: text,
    title: {text: `${a.method === "pref" ? "선호 배정" : "무작위 배정"} · ${summary}`, bottom: 0, left: 0, textStyle: {fontSize: 13, fontWeight: 400, color: text.color}},
    tooltip: {trigger: "item", formatter: p => (p.data && p.data.tip) || ""},
    grid: {left: clients.some(c => !(c in ce)) ? 72 : 32, right: 4, top: 22, bottom: 28},  // 미배정 클라가 있으면 이름 칸을 넓힘
    xAxis: {
      type: "category", data: edges, position: "top", triggerEvent: true,
      axisLine: {show: false}, axisTick: {show: false},
      axisLabel: {fontWeight: 700, color: css_var("--text-primary"), formatter: e => `${e} (정원 ${a.capacity})`},
    },
    yAxis: {
      type: "category", data: clients, inverse: true, triggerEvent: true,
      axisLine: {show: false}, axisTick: {show: false},
      axisLabel: {
        fontWeight: 700, color: css_var("--text-primary"),
        formatter: c => (c in ce ? c : `{bad|${c} 미배정}`),  // 배정 안 된 클라는 빨간 글씨
        rich: {bad: {color: css_var("--critical"), fontWeight: 700}},
      },
    },
    series: [{type: "heatmap", data, emphasis: {disabled: true}}],
  });
  bind_focus(chart, p => {
    if (p.componentType === "xAxis") return {type: "edge", id: p.value};
    if (p.componentType === "yAxis") return {type: "client", id: p.value};
    return (p.data && p.data.target) || null;
  });
}

subscribe(render_tree);
subscribe(render_assign_matrix);
