"""비교 표·그래프 — 담당 C(김영헌), WBS 4.6

logs/ 의 pref·random 실험 → 선호 충족도, 엣지별 숫자 분포, 정확도, 통신 기록 비교 표·그래프 → docs/report.md
docs/report.md 안의 <!-- auto:이름 --> ~ <!-- /auto:이름 --> 사이만 바꿔 씀 (그 밖의 글은 사람이 씀).
그래프는 SVG 로 docs/img/ 에 저장 (추가 패키지 없음, GitHub 에서 바로 보임).
실행: python -m scripts.make_report   (다른 로그 폴더: python -m scripts.make_report --logs dashboard/sample_logs)
"""
import argparse
import json
import re
from pathlib import Path

from hfl.common import BASE_DIR, load_config, read_json

REPORT = BASE_DIR / "docs" / "report.md"
EDGE_COLORS = ["#2a78d6", "#1baf7a", "#6250d6"]  # 대시보드와 같은 엣지 색
METHOD_STYLE = {"pref": ("#1b1f24", ""), "random": ("#6b7280", "6 4")}  # 선호 = 진한 실선, 무작위 = 회색 점선
METHOD_NAME = {"pref": "선호(matching)", "random": "무작위"}


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 빈 줄·잘린 줄
    return rows


def load_exp(d):
    return {
        "id": d.name,
        "config": read_json(d / "config.json"),
        "split": read_json(d / "split.json"),
        "assignment": read_json(d / "assignment.json"),
        "train": read_jsonl(d / "train.jsonl"),
        "comm": read_jsonl(d / "comm.jsonl"),
    }


def pick_experiments(log_root):
    """배정 방식별 결함 주입 없는 실험 1개씩 + 결함 주입 실험 (있으면)"""
    exps = [load_exp(d) for d in sorted(log_root.iterdir()) if (d / "assignment.json").exists()]
    by_method = {}
    for e in exps:
        if not e["config"].get("inject"):
            by_method.setdefault(e["config"]["assign_method"], e)
    inject = next((e for e in exps if e["config"].get("inject")), None)
    if "pref" not in by_method or "random" not in by_method:
        raise SystemExit(f"{log_root} 에 pref·random 실험이 다 있어야 함 (지금: {sorted(by_method)}). 먼저 python -m scripts.run_all")
    return by_method["pref"], by_method["random"], inject


def nkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]  # C2 < C10


def global_rows(e):
    return sorted((r for r in e["train"] if r["target"] == "global"), key=lambda r: r["round"])


def tv_distance(comp):
    """엣지 쌍마다 숫자 분포 차이(총변동거리, 0 = 같음 · 1 = 완전히 다름) 중 최댓값"""
    es = sorted(comp, key=nkey)
    dist = {e: [n / (comp[e]["n"] or 1) for n in comp[e]["digit_counts"]] for e in es}
    best = 0.0
    for i, a in enumerate(es):
        for b in es[i + 1:]:
            best = max(best, 0.5 * sum(abs(x - y) for x, y in zip(dist[a], dist[b])))
    return best


def comm_stats(e):
    reqs = [r for r in e["comm"] if r["round"] >= 1]
    measured = [r for r in reqs if r["kind"] != "injected"]
    ok = [r for r in measured if r["ok"]]
    lat = [r["latency_ms"] for r in ok]
    rounds = [r["duration_ms"] for r in e["train"] if r["target"] == "round"]
    return {
        "n": len(measured),
        "rate": len(ok) / len(measured) if measured else 0.0,
        "fail": len(measured) - len(ok),
        "injected": len(reqs) - len(measured),
        "injected_409": sum(1 for r in reqs if r["kind"] == "injected" and r["status"] == 409),
        "lat_mean": sum(lat) / len(lat) if lat else 0.0,
        "lat_max": max(lat) if lat else 0.0,
        "mb": sum(r.get("req_bytes", 0) + r.get("bytes", 0) for r in reqs) / 1e6,
        "round_ms": sum(rounds) / len(rounds) if rounds else 0.0,
    }


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def svg_lines(series, title, path):
    """라운드별 공동 정확도 꺾은선 (series = [(이름, 값 리스트, 색, 점선)])"""
    W, H, L, R, T, B = 640, 280, 56, 150, 36, 40
    vals = [v for _, vs, _, _ in series for v in vs]
    lo, hi = max(0.0, int(min(vals) * 10) / 10), 1.0
    n = max(len(vs) for _, vs, _, _ in series)
    x = lambda i: L + (W - L - R) * (i / max(n - 1, 1))
    y = lambda v: T + (H - T - B) * (1 - (v - lo) / ((hi - lo) or 1))
    pct = lambda v: f"{v * 100:.0f}%"
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Pretendard, Malgun Gothic, sans-serif">',
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
             f'<text x="{L}" y="20" font-size="14" font-weight="700" fill="#1b1f24">{title}</text>']
    step = 0.05 if hi - lo <= 0.3 else 0.1  # 눈금은 5% 또는 10% 단위
    for k in range(round((hi - lo) / step) + 1):
        v = lo + step * k
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#e9ecef"/>')
        parts.append(f'<text x="{L - 6}" y="{y(v) + 4:.1f}" font-size="11" text-anchor="end" fill="#4b5563">{pct(v)}</text>')
    for i in range(n):
        if i == 0 or (i + 1) % 5 == 0:
            parts.append(f'<text x="{x(i):.1f}" y="{H - B + 18}" font-size="11" text-anchor="middle" fill="#4b5563">R{i + 1}</text>')
    for k, (name, vs, color, dash) in enumerate(series):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vs))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"{dash_attr}/>')
        ly = T + 8 + k * 18  # 범례 = 그래프 오른쪽에 이름과 마지막 값
        parts.append(f'<line x1="{W - R + 12}" x2="{W - R + 32}" y1="{ly}" y2="{ly}" stroke="{color}" stroke-width="2"{dash_attr}/>')
        parts.append(f'<text x="{W - R + 38}" y="{ly + 4}" font-size="11" fill="#1b1f24">{name} {vs[-1] * 100:.2f}%</text>')
    if len(series) == 2 and series[0][1] == series[1][1]:  # 두 곡선이 완전히 같으면 하나로 보이므로 적어 둠
        parts.append(f'<text x="{W - R + 12}" y="{T + 52}" font-size="11" fill="#4b5563">두 곡선 완전히 겹침</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_edge_digits(exps, path):
    """배정 방식마다 엣지별 숫자 표본 수 막대 (작은 그림을 나란히)"""
    W, H, L, T, B, PW = 640, 270, 40, 52, 36, 270
    top = max(n for e in exps for c in e["assignment"]["edge_composition"].values() for n in c["digit_counts"]) or 1
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Pretendard, Malgun Gothic, sans-serif">',
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    for p, e in enumerate(exps):
        ox = L + p * (PW + 30)
        comp = e["assignment"]["edge_composition"]
        edges = sorted(comp, key=nkey)
        method = e["config"]["assign_method"]
        parts.append(f'<text x="{ox}" y="18" font-size="12" font-weight="700" fill="#1b1f24">{METHOD_NAME.get(method, method)} · 분포 차이 {tv_distance(comp):.2f}</text>')
        gw = PW / 10
        bw = (gw - 6) / len(edges)
        y0 = H - B
        parts.append(f'<line x1="{ox}" x2="{ox + PW}" y1="{y0}" y2="{y0}" stroke="#c3c2b7"/>')
        for d in range(10):
            parts.append(f'<text x="{ox + gw * d + gw / 2:.1f}" y="{y0 + 16}" font-size="11" text-anchor="middle" fill="#4b5563">{d}</text>')
            for k, ed in enumerate(edges):
                n = comp[ed]["digit_counts"][d]
                h = (H - T - B) * n / top
                if n:
                    parts.append(f'<rect x="{ox + gw * d + 3 + k * bw:.1f}" y="{y0 - h:.1f}" width="{bw - 1:.1f}" height="{h:.1f}" rx="2" fill="{EDGE_COLORS[k % len(EDGE_COLORS)]}"/>')
        for k, ed in enumerate(edges):
            parts.append(f'<rect x="{ox + k * 50}" y="{T - 12}" width="10" height="10" rx="2" fill="{EDGE_COLORS[k % len(EDGE_COLORS)]}"/>')
            parts.append(f'<text x="{ox + k * 50 + 14}" y="{T - 3}" font-size="11" fill="#1b1f24">{ed}</text>')
    parts.append(f'<text x="{L}" y="{H - 4}" font-size="11" fill="#4b5563">가로 = 숫자 0~9, 세로 = 그 엣지에 속한 표본 수 (가장 큰 막대 {top:,}장)</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def build_sections(pref, rand, inject):
    cfg = pref["config"]
    sec = {}
    keys = ("seed", "rounds", "local_epochs", "lr", "batch_size", "samples_per_client", "client_digits")
    same = all(pref["config"][k] == rand["config"][k] for k in keys)
    digits = ", ".join(f"{c}: {''.join(map(str, ds))}" for c, ds in sorted(cfg["client_digits"].items(), key=lambda kv: nkey(kv[0])))
    sec["conditions"] = table(["항목", "값"], [
        ["시드", cfg["seed"]], ["라운드", cfg["rounds"]], ["로컬 epoch", cfg["local_epochs"]], ["학습률", cfg["lr"]],
        ["배치 크기", cfg["batch_size"]], ["클라당 이미지", f"{cfg['samples_per_client']:,}장"], ["클라별 숫자", digits],
        ["엣지 정원", cfg["edge_capacity"]], ["두 실험 학습 조건 동일", "예" if same else "**아니오 — 비교 무효**"],
    ])

    rows = []
    for e in (pref, rand):
        a, ck = e["assignment"], e["assignment"]["check"]
        assign = " / ".join(f"{ed}: {', '.join(sorted(cs, key=nkey))}" for ed, cs in sorted(a["assignment"].items(), key=lambda kv: nkey(kv[0])))
        ranks = " ".join(f"{c}={r}" for c, r in sorted(ck["client_pref_rank"].items(), key=lambda kv: nkey(kv[0])) if r is not None)
        first = sum(1 for r in ck["client_pref_rank"].values() if r == 1)
        mean = "–" if ck["mean_pref_rank"] is None else f"{ck['mean_pref_rank']:.2f}"
        viol = len(ck["unassigned"]) + len(ck["duplicated"]) + len(ck["capacity_violation"])
        rows.append([METHOD_NAME.get(a["method"], a["method"]), assign, ranks, f"{first}/{len(ck['client_pref_rank'])}", mean, viol])
    sec["preference"] = table(["배정", "실제 배정", "클라별 배정 엣지의 선호 순위", "1순위 엣지 받은 클라", "평균 선호 순위", "제약 위반"], rows)

    rows = []
    for e in (pref, rand):
        comp = e["assignment"]["edge_composition"]
        for ed in sorted(comp, key=nkey):
            c = comp[ed]
            rows.append([METHOD_NAME.get(e["config"]["assign_method"]), ed, ", ".join(sorted(c["clients"], key=nkey)), f"{c['n']:,}",
                         " ".join(str(n) for n in c["digit_counts"]), f"{sum(1 for n in c['digit_counts'] if n)}/10"])
    sec["edges"] = (table(["배정", "엣지", "클라", "표본 수", "숫자 0~9 표본 수", "숫자 종류"], rows)
                    + f"\n\n엣지 간 숫자 분포 차이 (0 = 같음, 1 = 완전히 다름): 선호 **{tv_distance(pref['assignment']['edge_composition']):.2f}**, "
                      f"무작위 **{tv_distance(rand['assignment']['edge_composition']):.2f}**\n\n![엣지별 숫자 분포](img/report_edge_digits.svg)")

    gp, gr = global_rows(pref), global_rows(rand)
    diffs = [abs(a["acc"] - b["acc"]) * 100 for a, b in zip(gp, gr)]
    worst = lambda g: f"{min(g['acc_by_digit']) * 100:.1f}% (숫자 {g['acc_by_digit'].index(min(g['acc_by_digit']))})"
    rows = [[METHOD_NAME[m], f"{g['acc'] * 100:.2f}%", f"{g['loss']:.4f}", worst(g)] for m, g in (("pref", gp[-1]), ("random", gr[-1]))]
    sec["performance"] = (table([f"배정 (라운드 {gp[-1]['round']})", "공동 정확도", "손실", "가장 낮은 숫자 정확도"], rows)
                          + f"\n\n라운드별 공동 정확도 차이: 최대 **{max(diffs) if diffs else 0:.4f}%p** (라운드 {len(diffs)}개 비교)\n\n"
                          + table(["숫자"] + [str(d) for d in range(10)],
                                  [[METHOD_NAME[m]] + [f"{v * 100:.1f}" for v in g["acc_by_digit"]] for m, g in (("pref", gp[-1]), ("random", gr[-1]))])
                          + "\n\n(숫자별 정확도 %, 마지막 라운드)\n\n![공동 정확도](img/report_acc.svg)")

    rows = []
    for name, e in (("선호", pref), ("무작위", rand)) + ((("선호 + 결함 주입", inject),) if inject else ()):
        s = comm_stats(e)
        rows.append([name, s["n"], f"{s['rate'] * 100:.1f}%", s["fail"], f"{s['injected']} (409 {s['injected_409']})",
                     f"{s['lat_mean']:.1f}", f"{s['lat_max']:.1f}", f"{s['round_ms']:.0f}", f"{s['mb']:.1f}"])
    sec["comm"] = (table(["실험", "측정 요청", "성공률", "실제 실패", "일부러 넣은 시험 요청", "평균 지연(ms)", "최대 지연(ms)", "평균 라운드(ms)", "통신량(MB)"], rows)
                   + "\n\n성공률·지연은 측정 요청만 셈 (일부러 넣은 시험 요청 제외, 명세 '주입한 시험 기록 구분').")
    return sec


def fill(text, key, body):
    """<!-- auto:key --> ~ <!-- /auto:key --> 사이를 body 로 바꿈. 표시가 없으면 멈춤 (사람이 쓴 글을 덮지 않게)"""
    start, end = f"<!-- auto:{key} -->", f"<!-- /auto:{key} -->"
    if start not in text or end not in text:
        raise SystemExit(f"docs/report.md 에 {start} ... {end} 표시가 없음")
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{start}\n{body}\n{end}{tail}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", help="로그 폴더 (기본: 설정 파일 log_dir)")
    ap.add_argument("--out", help="보고서 파일 (기본: docs/report.md)")
    a = ap.parse_args(argv)
    log_root = Path(a.logs) if a.logs else BASE_DIR / load_config()["log_dir"]
    report = Path(a.out) if a.out else REPORT
    pref, rand, inject = pick_experiments(log_root)

    img_dir = report.parent / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    svg_lines([(METHOD_NAME[m], [g["acc"] for g in global_rows(e)], *METHOD_STYLE[m]) for m, e in (("pref", pref), ("random", rand))],
              "라운드별 공동 모델 정확도 (선호 vs 무작위)", img_dir / "report_acc.svg")
    svg_edge_digits([pref, rand], img_dir / "report_edge_digits.svg")

    text = report.read_text(encoding="utf-8")
    for key, body in build_sections(pref, rand, inject).items():
        text = fill(text, key, body)
    report.write_text(text, encoding="utf-8")
    print(f"{report.name} 갱신: {pref['id']} vs {rand['id']}" + (f", 결함 주입 {inject['id']}" if inject else ""))


if __name__ == "__main__":
    main()
