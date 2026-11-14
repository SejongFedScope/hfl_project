function fmt_pct(x) { return (x * 100).toFixed(1) + "%"; }

function fmt_bytes(b) {
  if (b >= 1e6) return (b / 1e6).toFixed(1) + " MB";
  return Math.round(b / 1e3) + " KB";
}

function fmt_ms(ms) {
  if (ms >= 1000) return (ms / 1000).toFixed(1) + " s";
  return Math.round(ms) + " ms";
}

function make_el(tag, cls, text) {
  const d = document.createElement(tag);
  d.className = cls;
  d.textContent = text;  // 로그 값은 textContent 로만 넣음 (HTML 해석 안 함)
  return d;
}

function make_tile(label, value, sub, sub_class) {
  const cell = make_el("div", "kpi_cell", "");
  const top = make_el("div", "kpi_top", "");
  top.append(make_el("span", "kpi_label", label), make_el("span", "kpi_value", value));
  const sub_el = make_el("div", ("kpi_sub " + (sub_class || "")).trim(), sub);
  sub_el.title = sub;
  cell.append(top, sub_el);
  return cell;
}

function kpi_values(b, r) {
  const global_at = t => b.train.find(x => x.target === "global" && x.round === t);
  const now = global_at(r);
  const prev = global_at(r - 1);
  const reqs = b.comm.filter(x => x.round === r);  // round 0 = 시작 설정 요청이라 빠짐
  const fails = reqs.filter(x => !x.ok);
  const ok_lat = reqs.filter(x => x.ok).map(x => x.latency_ms);
  const dur = b.train.find(x => x.target === "round" && x.round === r);
  const bytes_of = x => (x.req_bytes || 0) + (x.bytes || 0);
  return {
    now, prev, reqs, fails, ok_lat, dur,
    n409: fails.filter(x => x.status === 409).length,
    total_bytes: b.comm.filter(x => x.round <= r).reduce((a, x) => a + bytes_of(x), 0),
    round_bytes: reqs.reduce((a, x) => a + bytes_of(x), 0),
  };
}

function render_kpi(s) {
  const b = s.bundle;
  if (!b) return;
  const r = s.round;
  const v = kpi_values(b, r);
  const tiles = [];

  const ce = client_edge(b);
  const joined = new Set(b.train.filter(x => x.round === r && x.participated).map(x => x.target));
  const per_edge = Object.keys(b.assignment.assignment).sort().map(e => {
    const cs = Object.keys(ce).filter(c => ce[c] === e);
    return `${e} ${cs.filter(c => joined.has(c)).length}/${cs.length}`;
  });
  const n_clients = Object.keys(ce).length;
  tiles.push(make_tile("참여 클라", `${joined.size} / ${n_clients}`, per_edge.join(" · "), joined.size < n_clients ? "down" : ""));

  if (v.now) {
    let sub = "첫 라운드", cls = "";
    if (v.prev) {
      const d = (v.now.acc - v.prev.acc) * 100;
      sub = `${d >= 0 ? "▲" : "▼"} ${Math.abs(d).toFixed(1)}%p 직전 라운드 대비`;
      cls = d >= 0 ? "up" : "down";
    }
    tiles.push(make_tile("공동 모델 정확도", fmt_pct(v.now.acc), sub, cls));
    const abd = v.now.acc_by_digit;
    const worst = abd.indexOf(Math.min(...abd));
    tiles.push(make_tile("최저 숫자 정확도", fmt_pct(abd[worst]), `숫자 ${worst}`));
  } else {
    tiles.push(make_tile("공동 모델 정확도", "–", "이 라운드 집계 기록 없음"));
    tiles.push(make_tile("최저 숫자 정확도", "–", ""));
  }

  const rate = v.reqs.length ? (v.reqs.length - v.fails.length) / v.reqs.length : 1;
  const fail_sub = `실패 ${v.fails.length - v.n409}건 · 409 ${v.n409}건`;
  tiles.push(make_tile("요청 성공률", fmt_pct(rate), fail_sub, v.fails.length ? "down" : ""));

  const mean = v.ok_lat.length ? v.ok_lat.reduce((a, x) => a + x, 0) / v.ok_lat.length : 0;
  tiles.push(make_tile("평균 지연", fmt_ms(mean), v.ok_lat.length ? `최대 ${fmt_ms(Math.max(...v.ok_lat))} (성공 요청)` : "요청 없음"));

  tiles.push(make_tile("라운드 소요 시간", v.dur ? fmt_ms(v.dur.duration_ms) : "–", "시작 ~ 중앙 집계 확인"));
  tiles.push(make_tile("누적 통신량", fmt_bytes(v.total_bytes), `이번 라운드 ${fmt_bytes(v.round_bytes)} (요청+응답)`));

  document.getElementById("kpi").replaceChildren(...tiles);
}

subscribe(render_kpi);
