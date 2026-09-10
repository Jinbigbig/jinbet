"""比分分布一致性探针 —— 让「预测比分」也随市场/校准一起变（2026-09-10）

问题（用户提出）：引擎第四步用 80% 市场概率混合改了 λ，第七步又混了联赛经验频率，
最后 Platt 再对 1X2 做校准——**这三步都只作用在 1X2 上**，而报告头条的
「比分概率组 Top5 / 方向首选」是从**未经这些校准的比分矩阵**里取的。
实测 09-10 七场：比分矩阵的胜/平/负边际与发布的 1X2 最多差 **9.9pp**（周四006）。
即报告一边说「客胜 58.2%」，一边给的比分组仍是按「客胜 51.5%」的分布排的。

本脚本在 3981 场（带完整比分盘+总进球盘+1X2+赛果）上做时间外比较，候选方案：
  C0 现状：比分矩阵原样（泊松 + 联赛经验频率混合）
  C1 象限对齐：把矩阵三个象限的**质量**缩放到发布的 1X2（象限内形状不变，一步精确）
  C2 = C1 + 总进球盘：再对齐总进球边际（IPF / Sinkhorn）
  C3 市场比分盘混合：把去水后的比分盘分布按权重混进矩阵（「其他」桶按模型形状摊回）
  C4 = C3 + 象限对齐
评价：比分对数损失（31 格完备划分）、Top1/3/5 覆盖、方向命中、1X2 Brier。

用法：
  python _probe_score_align.py            # 全量
  python _probe_score_align.py --quick    # 只跑最近 1200 场
"""
import argparse
import glob
import importlib.util
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "_probe_rows.json")

KMAX = 9  # 0..8 精确，9 表示 >=9
TAIL = KMAX

LIST_H = {"1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2"}
LIST_D = {"0:0", "1:1", "2:2", "3:3"}
LIST_A = {"0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4", "0:5", "1:5", "2:5"}
OTH = {"胜其他": "H", "平其他": "D", "负其他": "A"}


def _load(mod_name, path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def engine():
    for c in ("_calc_engine.py", "calc_engine.py",
              os.path.join("tools", "prediction", "calc_engine.py")):
        p = os.path.join(ROOT, c)
        if os.path.exists(p):
            e = _load("eng_probe", p)
            e.load_league_profile()
            return e
    raise SystemExit("找不到 calc_engine.py")


def cells():
    return [(h, a) for h in range(KMAX + 1) for a in range(KMAX + 1)]


CELLS = cells()


def key_of(h, a):
    return (min(h, TAIL), min(a, TAIL))


def bucket_of(h, a):
    """31 格完备划分：列出的比分各占一格，「其他」按象限归并。"""
    s = "%d:%d" % (h, a)
    if s in LIST_H or s in LIST_D or s in LIST_A:
        return s
    if h > a:
        return "胜其他"
    if h == a:
        return "平其他"
    return "负其他"


def poisson_grid(lh, la):
    g = {}
    tail_h = max(0.0, 1.0 - sum(_pmf(k, lh) for k in range(KMAX)))
    tail_a = max(0.0, 1.0 - sum(_pmf(k, la) for k in range(KMAX)))
    ph = [_pmf(k, lh) for k in range(KMAX)] + [tail_h]
    pa = [_pmf(k, la) for k in range(KMAX)] + [tail_a]
    for h in range(KMAX + 1):
        for a in range(KMAX + 1):
            g[(h, a)] = ph[h] * pa[a]
    t = sum(g.values())
    return {k: v / t for k, v in g.items()}


def _pmf(k, lam):
    if k >= KMAX:
        return 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def norm(d):
    t = sum(d.values())
    if t <= 0:
        return d
    return {k: v / t for k, v in d.items()}


def devig(od):
    inv = {k: 1.0 / float(v) for k, v in od.items() if float(v) > 1.0}
    t = sum(inv.values())
    return {k: v / t for k, v in inv.items()} if t > 0 else {}


def marginals_12(g):
    h = sum(p for (a, b), p in g.items() if a > b)
    d = sum(p for (a, b), p in g.items() if a == b)
    w = sum(p for (a, b), p in g.items() if a < b)
    return [h, d, w]


def quad_align(g, target):
    """把三个象限的质量缩放到 target（象限内形状不变）——一步精确投影。"""
    cur = marginals_12(g)
    f = [target[i] / cur[i] if cur[i] > 1e-12 else 0.0 for i in range(3)]
    out = {}
    for (a, b), p in g.items():
        i = 0 if a > b else (1 if a == b else 2)
        out[(a, b)] = p * f[i]
    return norm(out)


def expand_market_score(mkt, model_grid):
    """比分盘 → 10x10 网格；「其他」桶按模型形状摊回同象限未列出格。"""
    out = {c: 0.0 for c in CELLS}
    for k, p in mkt.items():
        if ":" in k:
            try:
                h, a = (int(x) for x in k.split(":"))
            except ValueError:
                continue
            out[key_of(h, a)] += p
        elif k in OTH:
            q = OTH[k]
            f = (lambda c: c[0] > c[1]) if q == "H" else (
                (lambda c: c[0] == c[1]) if q == "D" else (lambda c: c[0] < c[1]))
            pool = [c for c in CELLS if f(c) and not _listed(c)]
            w = sum(model_grid[c] for c in pool)
            if w <= 1e-12:
                w = float(len(pool))
                for c in pool:
                    out[c] += p * (1.0 / w) if pool else 0.0
            else:
                for c in pool:
                    out[c] += p * model_grid[c] / w
    return norm(out)


def _listed(c):
    return "%d:%d" % c in (LIST_H | LIST_D | LIST_A)


def totals_dist(g):
    d = {k: 0.0 for k in range(8)}
    for (a, b), p in g.items():
        d[min(a + b, 7)] += p
    return norm(d)


def ipf_totals(g, target_tot, iters=30):
    """IPF：保持网格形状，同时对齐总进球边际。"""
    out = dict(g)
    for _ in range(iters):
        cur = totals_dist(out)
        f = {k: (target_tot[k] / cur[k] if cur[k] > 1e-12 else 0.0) for k in range(8)}
        for c in list(out):
            out[c] *= f[min(c[0] + c[1], 7)]
        out = norm(out)
        if max(abs(totals_dist(out)[k] - target_tot[k]) for k in range(8)) < 1e-6:
            break
    return out


def bucket_probs(g):
    b = {}
    for (h, a), p in g.items():
        k = bucket_of(h, a)
        b[k] = b.get(k, 0.0) + p
    return b


def topn_hit(g, hg, ag, n, include_bucket=True):
    b = bucket_probs(g)
    items = [(k, v) for k, v in b.items() if include_bucket or k in (LIST_H | LIST_D | LIST_A)]
    items.sort(key=lambda x: -x[1])
    return 1 if bucket_of(hg, ag) in [k for k, _ in items[:n]] else 0


def logloss(g, hg, ag):
    b = bucket_probs(g)
    p = max(b.get(bucket_of(hg, ag), 1e-9), 1e-9)
    return -math.log(p)


def brier12(g, hg, ag):
    m = marginals_12(g)
    y = [1.0 if hg > ag else 0.0, 1.0 if hg == ag else 0.0, 1.0 if hg < ag else 0.0]
    return sum((m[i] - y[i]) ** 2 for i in range(3))


# ---------------------------------------------------------------- 主流程
def load_rows(quick=False):
    if os.path.exists(CACHE):
        rows = json.load(open(CACHE, encoding="utf-8"))
        return rows[-1200:] if quick else rows
    fit = _load("mcf_probe", os.path.join(ROOT, "_market_calib_fit.py"))
    rows = fit.build_rows()
    slim = []
    for r in rows:
        rec = r["rec"]
        if not (rec.get("比分") and rec.get("总进球")):
            continue
        if not r["o12"][0]:
            continue
        slim.append({"k": r["k"], "date": r["date"], "hg": r["hg"], "ag": r["ag"],
                     "lam": list(r["lam"]), "o12": list(r["o12"]), "lg": r["lg"],
                     "sc": rec["比分"], "tot": rec["总进球"]})
    json.dump(slim, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return slim[-1200:] if quick else slim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--alphas", default="0.2,0.3,0.4,0.5")
    args = ap.parse_args()

    eng = engine()
    eng.fit_platt_params()
    rows = load_rows(args.quick)
    alphas = [float(x) for x in args.alphas.split(",")]
    print(f"样本 {len(rows)} 场（带比分盘+总进球盘+1X2+赛果）| 联赛档案已加载 | "
          f"Platt 已加载={bool(eng.PLATT_PARAMS)}\n")

    W = eng.MARKET_W
    KEYS = ("ll", "b", "t1", "t3", "t5", "t5l", "qhit", "qt")
    stat = {}
    pair = {}   # nm -> [(ll, t5, t3, qhit), ...]

    names = ["C0现状", "C1象限对齐", "C2+总进球", "C1b对齐pre-Platt",
             "C5纯泊松形状+对齐", "C6半联赛混+对齐", "MKT纯比分盘", "MARKET"]
    names += [f"C3混合{a:.1f}" for a in alphas]
    names += [f"C4混合{a:.1f}+对齐" for a in alphas]
    for n_ in names:
        stat[n_] = dict({"n": 0}, **{k: 0.0 for k in KEYS})

    for r in rows:
        lh, la = r["lam"]
        oh, od, ol = r["o12"]
        pv = eng.devig_1x2(oh, od, ol)
        total_b = lh + la
        pm = eng.pois_1x2(lh, la)
        pb = [(1 - W) * pm[i] + W * pv[i] for i in range(3)]
        s = sum(pb)
        pb = [x / s for x in pb]
        lh2, la2 = eng.prob_to_lambda(pb, total_b)

        g = poisson_grid(lh2, la2)
        g0 = dict(g)                      # 未混联赛经验频率的纯泊松网格（诊断用）
        lo, hi = min(lh2, la2), max(lh2, la2)
        g = eng.mix_score_matrix(g, r["lg"], hi / lo if lo > 1e-9 else 99.0)

        raw = marginals_12(g)
        pub = list(eng.apply_platt(raw[0], raw[1], raw[2]))
        hg, ag = r["hg"], r["ag"]

        mk_sc = devig(r["sc"])
        mk_tot = devig(r["tot"])
        mk_tot = {int(k.replace("+", "")): v for k, v in mk_tot.items()}
        mk_tot = norm({k: mk_tot.get(k, 0.0) for k in range(8)})
        mk_grid = expand_market_score(mk_sc, g)

        cands = {
            "C0现状": g,
            "C1象限对齐": quad_align(g, pub),
            "C2+总进球": ipf_totals(quad_align(g, pub), mk_tot),
            "C1b对齐pre-Platt": quad_align(g, pb),
            "C5纯泊松形状+对齐": quad_align(g0, pub),
            "C6半联赛混+对齐": quad_align(norm({c: 0.5 * g[c] + 0.5 * g0[c] for c in CELLS}), pub),
            "MKT纯比分盘": mk_grid,
            "MARKET": quad_align(mk_grid, pub),
        }
        for a in alphas:
            mixg = norm({c: (1 - a) * g[c] + a * mk_grid[c] for c in CELLS})
            cands[f"C3混合{a:.1f}"] = mixg
            cands[f"C4混合{a:.1f}+对齐"] = quad_align(mixg, pub)

        for nm, gg in cands.items():
            d = stat[nm]
            d["n"] += 1
            ll_v = logloss(gg, hg, ag)
            t5_v = topn_hit(gg, hg, ag, 5)
            t3_v = topn_hit(gg, hg, ag, 3)
            mm = marginals_12(gg)
            q_v = 1 if (max(range(3), key=lambda i: mm[i]) ==
                        (0 if hg > ag else (1 if hg == ag else 2))) else 0
            # 报告「方向首选」：发布倾向象限内概率最高的**列出比分**
            qi = max(range(3), key=lambda i: mm[i])
            flt = (lambda c: c[0] > c[1]) if qi == 0 else (
                (lambda c: c[0] == c[1]) if qi == 1 else (lambda c: c[0] < c[1]))
            qpool = [(c, gg[c]) for c in gg if flt(c) and _listed(c)]
            qt_v = 1 if (max(qpool, key=lambda x: x[1])[0] == (hg, ag)) else 0
            d["qt"] += qt_v
            d["ll"] += ll_v
            d["b"] += brier12(gg, hg, ag)
            d["t1"] += topn_hit(gg, hg, ag, 1)
            d["t3"] += t3_v
            d["t5"] += t5_v
            d["t5l"] += topn_hit(gg, hg, ag, 5, include_bucket=False)
            d["qhit"] += q_v
            pair.setdefault(nm, []).append((ll_v, t5_v, t3_v, q_v))

    base = pair.get("C0现状", [])
    print(f"{'方案':<22}{'比分LogLoss':>13}{'1X2Brier':>10}{'Top1':>8}{'Top3':>8}"
          f"{'Top5':>8}{'Top5仅列出':>12}{'方向命中':>9}{'方向首选':>9}")
    print("-" * 104)
    order = sorted(stat, key=lambda k: stat[k]["ll"] / max(stat[k]["n"], 1))
    for nm in order:
        d = stat[nm]
        n = max(d["n"], 1)
        print(f"{nm:<22}{d['ll']/n:13.4f}{d['b']/n:10.4f}"
              f"{d['t1']/n*100:7.1f}%{d['t3']/n*100:7.1f}%{d['t5']/n*100:7.1f}%"
              f"{d['t5l']/n*100:11.1f}%{d['qhit']/n*100:8.1f}%{d['qt']/n*100:8.1f}%")

    # ---- 配对检验（vs C0现状）：同一批比赛上逐场比较，避免样本相关导致的假显著 ----
    print("\n配对对比（vs C0现状，同一批比赛逐场配对，n=%d）：" % len(base))
    print(f"{'方案':<22}{'ΔLogLoss':>11}{'ΔLL/t':>9}{'ΔTop5':>10}{'LL改善/恶化':>14}"
          f"{'Top5改善/恶化':>15}{'ΔTop3':>9}{'Δ方向':>9}")
    print("-" * 100)
    for nm in order:
        if nm == "C0现状" or not pair.get(nm):
            continue
        dl = [pair[nm][i][0] - base[i][0] for i in range(len(base))]
        m = sum(dl) / len(dl)
        sd = (sum((x - m) ** 2 for x in dl) / max(len(dl) - 1, 1)) ** 0.5
        t = m / (sd / len(dl) ** 0.5) if sd > 0 else 0.0
        w = sum(1 for x in dl if x < -1e-9)
        l = sum(1 for x in dl if x > 1e-9)
        d5 = [pair[nm][i][1] - base[i][1] for i in range(len(base))]
        w5 = sum(1 for x in d5 if x > 0)
        l5 = sum(1 for x in d5 if x < 0)
        d3 = [pair[nm][i][2] - base[i][2] for i in range(len(base))]
        dq = [pair[nm][i][3] - base[i][3] for i in range(len(base))]
        print(f"{nm:<22}{m:+11.4f}{t:+9.2f}{sum(d5)/len(d5)*100:+9.2f}pp"
              f"{w:>9}/{l:<5}{w5:>9}/{l5:<5}"
              f"{sum(d3)/len(d3)*100:+8.2f}pp{sum(dq)/len(dq)*100:+8.2f}pp")


if __name__ == "__main__":
    main()
