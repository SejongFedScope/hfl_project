function link_rank(b, src, dst) {  // 통신 히트맵 행 순서: 엣지별 클라 → 엣지 → runner
  const ce = client_edge(b);
  const edges = Object.keys(b.assignment.assignment).sort();
  if (src in ce) return edges.indexOf(ce[src]) * 100 + Number(src.slice(1)) + (ce[src] === dst ? 0 : 50);
  if (edges.includes(src)) return 1000 + edges.indexOf(src);
  return 2000;
}

function fail_text(x) { return x.status ? String(x.status) : (x.error || "실패"); }

function node_lit(L, id) { return !L || L.clients.has(id) || L.edges.has(id); }

function link_target(src) {  // 링크를 고르면 보낸 쪽(클라·엣지)을 강조, runner 요청은 없음
  if (/^C\d+$/.test(src)) return {type: "client", id: src};
  if (/^E\d+$/.test(src)) return {type: "edge", id: src};
  return null;
}

function render_comm_heatmap(s) {  // 4.3.7 ② 링크 × 라운드, 색 = 성공 요청 평균 지연, 실패·409 = 빨강
  const b = s.bundle;
  if (!b) return;
  const chart = chart_of("p_comm_heatmap");
  const L = lit();
  const ce = client_edge(b);
  const reqs = b.comm.filter(x => x.round >= 1);
  const links = [...new Set(reqs.map(x => `${x.src}→${x.dst}`))]
    .map(k => k.split("→"))
    .sort((p, q) => link_rank(b, ...p) - link_rank(b, ...q));
  const rounds = [...Array(b.config.rounds).keys()].map(i => i + 1);
  const critical = css_var("--critical");
  const warning = css_var("--warning");
  const pick = css_var("--pick");

  const data = [], fail_data = [];
  let max_lat = 1;
  links.forEach(([src, dst], yi) => {
    rounds.forEach((r, xi) => {
      const cell = reqs.filter(x => x.src === src && x.dst === dst && x.round === r);
      if (!cell.length) return;
      const ok = cell.filter(x => x.ok);
      const bad = cell.filter(x => !x.ok);
      const mean = ok.length ? ok.reduce((a, x) => a + x.latency_ms, 0) / ok.length : 0;
      max_lat = Math.max(max_lat, mean);
      const on = node_lit(L, src) && node_lit(L, dst);
      const injected = bad.length && bad.every(x => x.kind === "injected");
      const lines = cell.map(x => `${esc(x.api)} · v${x.model_version} · ${x.ok ? Math.round(x.latency_ms) + " ms" : "<b>" + esc(fail_text(x)) + "</b>"}${x.kind === "injected" ? " (injected)" : ""}`);
      (bad.length ? fail_data : data).push({
        value: [xi, yi, bad.length ? 0 : mean],
        r, src, dst,
        tip: `${esc(src)} → ${esc(dst)} · 라운드 ${r}<br>${lines.join("<br>")}`,
        itemStyle: Object.assign(
          {opacity: on ? 1 : DIM, borderColor: r === s.round ? css_var("--text-primary") : css_var("--surface"), borderWidth: r === s.round ? 2 : 1},
          bad.length ? {color: injected ? warning : critical} : {},
        ),
        label: {
          opacity: on ? 1 : DIM,
          formatter: bad.length ? bad.map(fail_text).join(",") : `${Math.round(mean)}`,
          color: bad.length && !injected ? "#ffffff" : "#0b0b0b",
          fontWeight: bad.length ? 700 : 400,
        },
      });
    });
  });

  const text = base_text();
  const show_num = (chart.getWidth() - 90) / rounds.length >= 30;
  chart.setOption({
    animation: false,
    textStyle: text,
    tooltip: {trigger: "item", formatter: p => (p.data && p.data.tip) || ""},
    grid: {left: 84, right: 8, top: 20, bottom: 8},
    visualMap: {show: false, min: 0, max: max_lat, inRange: {color: ["#cde2fb", "#86b6ef", "#3987e5"]}, seriesIndex: 0},
    xAxis: {
      type: "category", data: rounds.map(r => `R${r}`), position: "top", triggerEvent: true,
      axisLine: {show: false}, axisTick: {show: false},
      axisLabel: {color: css_var("--text-primary"), fontWeight: 700, interval: rounds.length > 12 ? 1 : 0},
    },
    yAxis: {
      type: "category", data: links.map(([a, c]) => `${a}→${c}`), inverse: true,
      axisLine: {show: false}, axisTick: {show: false},
      axisLabel: {
        color: css_var("--text-primary"),
        formatter: v => {
          const [a, c] = v.split("→");
          return a in ce && ce[a] !== c ? `${v} 배정 밖` : v;
        },
      },
    },
    series: [
      {type: "heatmap", data, emphasis: {disabled: true}, label: {show: show_num, fontSize: 10}},
      {type: "heatmap", data: fail_data, emphasis: {disabled: true}, label: {show: true, fontSize: 10}},  // 실패 칸: 색 고정 (지연 색 안 씀)
    ],
  });
  bind_focus(chart, (p, is_click) => {
    if (p.componentType === "xAxis") {
      if (is_click) set_round(Number(String(p.value).slice(1)));
      return null;
    }
    if (!p.data || !p.data.src) return null;
    if (is_click) set_round(p.data.r);  // 칸 클릭 = 그 라운드로 이동 → 요청 목록에서 상태 코드·모델 버전 확인
    return link_target(p.data.src);
  });
}

function render_request_table(s) {  // 4.3.8 ② 선택 라운드 요청 목록
  const b = s.bundle;
  if (!b) return;
  const host = document.getElementById("p_requests");
  const L = lit();
  const reqs = b.comm.filter(x => x.round === s.round);
  const bad = reqs.filter(x => !x.ok).length;

  const table = document.createElement("table");
  table.className = "tbl";
  table.innerHTML = `<caption>라운드 ${s.round} · 요청 ${reqs.length}건 · 실패 ${bad}건</caption>
    <thead><tr><th>#</th><th>보냄 → 받음</th><th>API</th><th class="num">모델 버전</th><th class="num">지연</th><th>결과</th></tr></thead>`;
  const tbody = document.createElement("tbody");
  reqs.forEach((x, i) => {
    const tr = document.createElement("tr");
    const on = node_lit(L, x.src) && node_lit(L, x.dst);
    if (!on) tr.className = "dim";
    if (!x.ok) tr.classList.add(x.kind === "injected" ? "row_warning" : "row_critical");
    const cells = [
      String(i + 1), `${x.src} → ${x.dst}`, x.api, `v${x.model_version}`,
      x.ok ? `${Math.round(x.latency_ms)} ms` : `${(x.latency_ms / 1000).toFixed(1)} s`,
      x.ok ? "200" : `${fail_text(x)}${x.kind === "injected" ? " · injected" : ""}`,
    ];
    cells.forEach((v, ci) => {
      const td = document.createElement("td");
      td.textContent = v;  // 로그 값은 textContent 로만
      if (ci === 3 || ci === 4) td.className = "num";
      if (ci === 5 && !x.ok) td.className = "bad";
      tr.appendChild(td);
    });
    const who = link_target(x.src);
    if (who) {
      tr.onmouseenter = () => set_hover(who);
      tr.onmouseleave = () => set_hover(null);
      tr.onclick = () => set_pin(who);
    }
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  const keep = host.scrollTop;
  host.replaceChildren(table);
  host.scrollTop = keep;
}

subscribe(render_comm_heatmap);
subscribe(render_request_table);
