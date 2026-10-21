# -*- coding: utf-8 -*-
"""联赛先验分层 A/B 探针（2026-10-21）。

目的：把「联赛身份 → 联赛基线」换成「联赛画像档 → 联赛基线」，用严格
walk-forward 判断是否优于现状（不是理论推演，是真算）。

现状（baseline/现状方案 A）：
    base = EB(n_lg, mean_lg → 全局, K=40)
    T'   = T*(1-w) + base*w ,  w=0.25

变体：
    B 画像档：base = EB(n_bucket, mean_bucket → 全局, K=40)，桶按该联赛截至
              当日的场均总进球分 3 档（低/中/高，阈值取 burn-in 期联赛均值分位）
    C 不收缩：w=0
    D 全局  ：base = 全局均值

评估口径（全部同一套泊松矩阵，差异只归因于联赛先验）：
    λ 偏差 / λ MAE / 比分单点 / 比分双档 / 1X2 方向 / 1X2 Brier

用法：python lg_adapt_probe.py
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
BURN = 400          # 前 400 场只建统计不评估
K_EB = 40.0
W_GRID = (0.0, 0.15, 0.25, 0.35, 0.50)
MAXG = 8
Q1 = 0.0
Q2 = 9e9


def pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def grid(lh, la):
    """独立泊松矩阵（截断到 MAXG，尾部并入最后一格）。"""
    ph = [pmf(k, lh) for k in range(MAXG + 1)]
    pa = [pmf(k, la) for k in range(MAXG + 1)]
    ph[MAXG] += max(0.0, 1.0 - sum(ph))
    pa[MAXG] += max(0.0, 1.0 - sum(pa))
    m = [[ph[h] * pa[a] for a in range(MAXG + 1)] for h in range(MAXG + 1)]
    tot = sum(sum(r) for r in m)
    return [[v / tot for v in r] for r in m]


def metrics(m):
    n = len(m)
    win = sum(m[h][a] for h in range(n) for a in range(n) if h > a)
    drw = sum(m[h][a] for h in range(n) for a in range(n) if h == a)
    los = max(0.0, 1.0 - win - drw)
    cells = sorted(((m[h][a], "%d:%d" % (h, a)) for h in range(n) for a in range(n)),
                   key=lambda x: -x[0])
    return (win, drw, los), [c[1] for c in cells[:3]]


def eb(n, mean, prior):
    return (n * mean + K_EB * prior) / (n + K_EB)


class State:
    """截至当前时点的累计统计（严格只用过去场次）。"""

    def __init__(self):
        self.gn = 0
        self.gsum = 0.0
        self.lg = {}        # league -> [n, sum_goals]
        self.bk = {}        # bucket -> [n, sum_goals]

    def add(self, league, total):
        self.gn += 1
        self.gsum += total
        d = self.lg.setdefault(league, [0, 0.0])
        d[0] += 1
        d[1] += total
        b = self.bucket(league)
        if b is not None:
            e = self.bk.setdefault(b, [0, 0.0])
            e[0] += 1
            e[1] += total

    def gmean(self):
        return self.gsum / self.gn if self.gn else 2.85

    def lg_mean(self, league):
        d = self.lg.get(league)
        return (d[1] / d[0]) if d and d[0] else None

    def bucket(self, league):
        m = self.lg_mean(league)
        if m is None:
            return None
        if m < Q1:
            return "low"
        if m < Q2:
            return "mid"
        return "high"


def base_of(st, league, mode):
    g = st.gmean()
    if mode == "none":
        return g
    if mode == "global":
        return g
    if mode == "league":
        d = st.lg.get(league)
        if not d or d[0] < 3:
            return g
        return eb(d[0], d[1] / d[0], g)
    if mode == "bucket":
        b = st.bucket(league)
        d = st.bk.get(b) if b else None
        if not d or d[0] < 3:
            return g
        return eb(d[0], d[1] / d[0], g)
    raise ValueError(mode)


def run(rows, mode, w):
    st = State()
    ev = {"n": 0, "lb": 0.0, "lae": 0.0, "hit": 0, "pk": 0, "bd": 0,
          "dir": 0, "brier": 0.0, "tot": 0.0, "act": 0.0}
    for i, r in enumerate(rows):
        lh0, la0 = float(r.get("lam_h") or 0), float(r.get("lam_a") or 0)
        act = r["hg"] + r["ag"]
        if i >= BURN and lh0 > 0 and la0 > 0:
            T = lh0 + la0
            base = base_of(st, r.get("league") or "", mode)
            T2 = T * (1 - w) + base * w
            lh, la = lh0 * T2 / T, la0 * T2 / T
            (p1, p2, p3), top3 = metrics(grid(lh, la))
            p = (p1, p2, p3)
            res = 0 if r["hg"] > r["ag"] else (1 if r["hg"] == r["ag"] else 2)
            ev["n"] += 1
            ev["lb"] += T2 - act
            ev["lae"] += abs(T2 - act)
            ev["tot"] += T2
            ev["act"] += act
            ev["pk"] += int(top3[0] == "%d:%d" % (r["hg"], r["ag"]))
            ev["bd"] += int(("%d:%d" % (r["hg"], r["ag"])) in top3[1:])
            ev["dir"] += int(max(range(3), key=lambda k: p[k]) == res)
            ev["brier"] += sum((p[k] - (1.0 if k == res else 0.0)) ** 2 for k in range(3)) / 3.0
        st.add(r.get("league") or "", act)
    n = ev["n"]
    return {
        "n": n,
        "bias": ev["lb"] / n,
        "mae": ev["lae"] / n,
        "pk": ev["pk"] / n * 100,
        "bd": ev["bd"] / n * 100,
        "dir": ev["dir"] / n * 100,
        "brier": ev["brier"] / n,
        "mkt_total": ev["act"] / n,
        "mdl_total": ev["tot"] / n,
    }


def exp2_shape(rows):
    """第二组：比分「形状混合」来源 A/B（同一批可评估场次 + 1X2 守恒）。

    现状 = 联赛自身经验比分频率；变体 = 画像档合并频率 / 全局合并频率 / 不混合。
    关键：像引擎 SCORE_ALIGN 那样把象限合计缩放回基准 1X2，令方向与 Brier
    在各变体间恒等 → 差异只来自「形状」，看的指标是单点 / 双档。
    """
    G = 7
    uni = {"%d:%d" % (h, a): 1.0 / (G * G) for h in range(G) for a in range(G)}

    def norm(d):
        s = sum(d.values())
        return {k: v / s for k, v in d.items()} if s > 0 else dict(uni)

    def shrink_pool(raw, n, prior, k=50.0):
        s = sum(raw.values())
        out = {}
        for key in uni:
            e = (raw.get(key, 0.0) / s) if s > 0 else 0.0
            out[key] = (n * e + k * prior.get(key, uni[key])) / (n + k)
        return norm(out)

    def rescale(q, base):
        """象限守恒：把 q 的 主/平/客 合计缩放回 base，只留形状差异。"""
        out = dict(q)
        for pick in ("h", "d", "a"):
            ck = [k for k in uni if ("h" if int(k.split(":")[0]) > int(k.split(":")[1])
                                     else ("d" if k.split(":")[0] == k.split(":")[1] else "a")) == pick]
            cq = sum(q[k] for k in ck)
            cb = sum(base[k] for k in ck)
            if cq > 1e-12 and cb > 0:
                f = cb / cq
                for k in ck:
                    out[k] = q[k] * f
        return norm(out)

    st_lg, st_bk, st_gl = {}, {}, {}
    res = {}
    for mode in ("none", "global", "league", "bucket"):
        res[mode] = {"n": 0, "pk": 0, "bd": 0, "dir": 0, "brier": 0.0, "gm": 0.0, "cnt": 0}

    for i, r in enumerate(rows):
        lh, la = float(r.get("lam_h") or 0), float(r.get("lam_a") or 0)
        lg = r.get("league") or ""
        hg, ag = r["hg"], r["ag"]
        act_sc = "%d:%d" % (hg, ag)
        res_v = 0 if hg > ag else (1 if hg == ag else 2)

        raw_l = st_lg.get(lg, {})
        n_l = sum(raw_l.values())
        bucket = None
        if n_l >= 3:
            mg = sum((int(s.split(":")[0]) + int(s.split(":")[1])) * v for s, v in raw_l.items()) / n_l
            bucket = "low" if mg < Q1 else ("mid" if mg < Q2 else "high")
        raw_b = st_bk.get(bucket, {}) if bucket else {}
        n_b = sum(raw_b.values())

        if i >= BURN and lh > 0 and la > 0 and n_l >= 20 and n_b >= 20:
            bg = grid(lh, la)
            p0 = norm({"%d:%d" % (h, a): bg[h][a] for h in range(G) for a in range(G)})
            gl = shrink_pool(st_gl.get("__g", {}), sum(st_gl.get("__g", {}).values()), uni, k=30.0)
            fl = shrink_pool(raw_l, n_l, gl)
            fb = shrink_pool(raw_b, n_b, gl)
            for mode, f in (("none", None), ("global", gl), ("league", fl), ("bucket", fb)):
                w = 0.0 if f is None else 0.30
                q = norm({k: (1 - w) * p0[k] + w * f.get(k, 0.0) for k in p0}) if f else dict(p0)
                q = rescale(q, p0)
                cells = sorted(q.items(), key=lambda x: -x[1])
                d = res[mode]
                d["n"] += 1
                d["pk"] += int(cells[0][0] == act_sc)
                d["bd"] += int(act_sc in [c[0] for c in cells[1:3]])
                p3 = (sum(v for k, v in q.items() if int(k.split(":")[0]) > int(k.split(":")[1])),
                      sum(v for k, v in q.items() if k.split(":")[0] == k.split(":")[1]),
                      sum(v for k, v in q.items() if int(k.split(":")[0]) < int(k.split(":")[1])))
                d["dir"] += int(max(range(3), key=lambda k: p3[k]) == res_v)
                d["brier"] += sum((p3[k] - (1.0 if k == res_v else 0.0)) ** 2 for k in range(3)) / 3.0
                if hg < G and ag < G:
                    d["gm"] += cells[0][0] == act_sc
                    d["cnt"] += 1

        if hg < G and ag < G:
            st_lg.setdefault(lg, {})
            st_lg[lg][act_sc] = st_lg[lg].get(act_sc, 0.0) + 1.0
            if bucket:
                st_bk.setdefault(bucket, {})
                st_bk[bucket][act_sc] = st_bk[bucket].get(act_sc, 0.0) + 1.0
            st_gl.setdefault("__g", {})
            st_gl["__g"][act_sc] = st_gl["__g"].get(act_sc, 0.0) + 1.0

    print("\n【第二组｜比分形状混合来源】w=0.30，同批场次 + 象限守恒（方向/Brier 恒定）")
    print("%-24s %6s %8s %8s" % ("形状来源", "n", "单点%", "双档%"))
    lab = {"none": "无形状混合(纯泊松)", "global": "全局合并频率",
           "league": "联赛自身频率(现状)", "bucket": "画像档合并频率(新)"}
    for mode in ("none", "global", "league", "bucket"):
        d = res[mode]
        n = d["n"]
        print("%-24s %6d %8.2f %8.2f" % (lab[mode], n, d["pk"] / n * 100, d["bd"] / n * 100))
    a, b, g = res["league"], res["bucket"], res["global"]
    n = a["n"]
    s1 = 100 * math.sqrt(0.13 * 0.87 / n)
    print("\n配对（同 %d 场）：" % n)
    print("  B 画像档 vs A 现状  → 单点 %+.2fpp | 双档 %+.2fpp   (1σ≈%.2fpp)"
          % ((b["pk"] - a["pk"]) / n * 100, (b["bd"] - a["bd"]) / n * 100, s1))
    print("  G 全局   vs A 现状  → 单点 %+.2fpp | 双档 %+.2fpp"
          % ((g["pk"] - a["pk"]) / n * 100, (g["bd"] - a["bd"]) / n * 100))

def main():
    global Q1, Q2
    rows = json.load(open(os.path.join(ROOT, "_bt_rows3.json"), encoding="utf-8"))
    rows.sort(key=lambda r: r["date"])

    # 阈值：burn-in 期联赛场均进球的分位（只用过去数据）
    st = State()
    for r in rows[:BURN]:
        st.add(r.get("league") or "", r["hg"] + r["ag"])
    means = sorted(v[1] / v[0] for v in st.lg.values() if v[0] >= 8)
    Q1 = means[len(means) // 3]
    Q2 = means[len(means) * 2 // 3]
    print("burn-in %d 场 | 联赛画像档阈值 低<%.3f  中<%.3f  高" % (BURN, Q1, Q2))

    names = {"none": "C 不收缩", "global": "D 全局均值",
             "league": "A 联赛身份(现状)", "bucket": "B 画像档(新)"}
    print("\n%-16s %5s %8s %7s %7s %7s %8s %8s" %
          ("方案 w", "n", "λ偏差", "λMAE", "单点%", "双档%", "方向%", "Brier"))
    best = {}
    for w in W_GRID:
        for mode in ("none", "global", "league", "bucket"):
            if mode == "none" and w != 0.0:
                continue
            if mode == "none":
                ww = 0.0
            else:
                ww = w
            m = run(rows, mode, ww)
            key = names[mode]
            print("%-16s %5d %+8.3f %7.3f %7.2f %7.2f %8.2f %8.4f" %
                  ("%s w=%.2f" % (key, ww), m["n"], m["bias"], m["mae"],
                   m["pk"], m["bd"], m["dir"], m["brier"]))
            best[(key, ww)] = m
        print("-" * 70)

    a = best[("A 联赛身份(现状)", 0.25)]
    print("\n实际赛场均总进球 %.3f | 现状模型 %.3f（偏差 %+.3f）" %
          (a["mkt_total"], a["mdl_total"], a["bias"]))
    for w in W_GRID[1:]:
        b = best[("B 画像档(新)", w)]
        print("B w=%.2f vs A w=0.25 → λMAE %+.4f | 单点 %+.2fpp | 双档 %+.2fpp | 方向 %+.2fpp | Brier %+.5f"
              % (w, b["mae"] - a["mae"], b["pk"] - a["pk"], b["bd"] - a["bd"],
                 b["dir"] - a["dir"], b["brier"] - a["brier"]))

    exp2_shape(rows)


if __name__ == "__main__":
    main()
