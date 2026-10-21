# -*- coding: utf-8 -*-
"""组合方案稳健性检验 + 引擎现有校准的 damp 网格（2026-10-21）。

背景：lg_combo_probe 显示「形状混合 + 时间偏移」在 holdout 上配对 logscore
-0.00491（t=-2.21），但单点/双档几乎没动，且 dev 上不显著。需两件事才算数：
  1) 时间分段稳健性：5 段里若只有 1-2 段为负，就是运气；
  2) 与引擎已有机制对齐：_calc_engine 的 compute_calibration 已做
     EWMA+MAD 求 ratio，再 factor=(1/ratio)**damp（damp=0.6，clamp 0.88~1.15）。
     本脚本按「场次级 EWMA + 可调 damp」重放，看 damp 该不该调。

用法：python lg_combo_robust.py
"""
import json
import math
import os

import lg_adapt_probe as LAP
import lg_combo_probe as CP

ROOT = os.path.dirname(os.path.abspath(__file__))
BURN = LAP.BURN


def load():
    rows = json.load(open(os.path.join(ROOT, "_bt_rows3.json"), encoding="utf-8"))
    rows.sort(key=lambda r: r["date"])
    LAP.Q1, LAP.Q2 = 0.0, 9e9
    st = LAP.State()
    for r in rows[:BURN]:
        st.add(r.get("league") or "", r["hg"] + r["ag"])
    means = sorted(v[1] / v[0] for v in st.lg.values() if v[0] >= 8)
    LAP.Q1 = means[len(means) // 3]
    LAP.Q2 = means[len(means) * 2 // 3]
    return rows


def seg_stats(vec, base, k=5):
    """按时间把评估集切 k 段，返回每段 (n, ls, 配对差)。"""
    n = len(vec)
    out = []
    for s in range(k):
        a, b = s * n // k, (s + 1) * n // k
        ls = sum(x[0] for x in vec[a:b]) / (b - a)
        d = sum(x[0] - y[0] for x, y in zip(vec[a:b], base[a:b])) / (b - a)
        out.append((b - a, ls, d))
    return out


def damp_run(rows, half, damp, lo=0.85, hi=1.18):
    """按引擎 compute_calibration 的映射重放：场次级 EWMA 求 ratio → factor。"""
    alpha = 1 - math.exp(-math.log(2) / half)
    eT = eA = None
    out = []
    for i, r in enumerate(rows):
        lh = float(r.get("lam_h") or 0)
        la = float(r.get("lam_a") or 0)
        T = lh + la
        act = r["hg"] + r["ag"]
        if i >= BURN and T > 0 and eT and eA:
            ratio = eT / eA
            factor = min(hi, max(lo, (1.0 / ratio) ** damp))
            T2 = T * factor
            bg = LAP.grid(lh * T2 / T, la * T2 / T)
            out.append((-math.log(max(bg[min(r["hg"], 8)][min(r["ag"], 8)], 1e-12)),
                        abs(T2 - act)))
        if T > 0:
            eT = T if eT is None else (1 - alpha) * eT + alpha * T
            eA = act if eA is None else (1 - alpha) * eA + alpha * act
    return out


def main():
    rows = load()
    recs = CP.build(rows)
    ra = CP.build(rows, half=20, cap=0.10)
    split = int(len(recs) * 0.6)

    base = CP.ev(recs, 0.30, 0.0, 0.0, "fl")
    shape = CP.ev(recs, 0.30, 0.25, 0.25, "fl2")
    time_ = CP.ev(ra, 0.30, 0.0, 0.0, "fl", adj=True)
    combo = CP.ev(ra, 0.30, 0.25, 0.25, "fl2", adj=True)

    print("评估 %d 场 | 5 段稳健性（配对差为负 = 优于现状）" % len(recs))
    print("%-6s %6s | %-18s %-18s %-18s" % ("段", "n", "形状混合", "时间偏移", "联合"))
    for i, (n1, _, d1) in enumerate(seg_stats(shape, base)):
        _, _, d2 = seg_stats(time_, base)[i]
        _, _, d3 = seg_stats(combo, base)[i]
        print("%-6s %6d | %+18.5f %+18.5f %+18.5f" % ("段%d" % (i + 1), n1, d1, d2, d3))

    def neg_count(v):
        return sum(1 for _, _, d in seg_stats(v, base) if d < 0)
    print("\n优于现状的段数：形状 %d/5 | 时间 %d/5 | 联合 %d/5"
          % (neg_count(shape), neg_count(time_), neg_count(combo)))

    print("\n全样本 vs holdout 配对（logscore）:")
    for lab, v in (("形状混合", shape), ("时间偏移", time_), ("联合", combo)):
        m_all = sum(a[0] - b[0] for a, b in zip(v, base)) / len(v)
        m_h = sum(a[0] - b[0] for a, b in zip(v[split:], base[split:])) / (len(v) - split)
        print("  %-8s 全样本 %+.5f | holdout %+.5f" % (lab, m_all, m_h))

    # ---------- 引擎现有校准的 damp 网格 ----------
    print("\n【引擎现有机制 damp 网格】场次级 EWMA → factor=(1/ratio)^damp, clamp(0.85,1.18)")
    print("  %-24s %8s %9s %9s" % ("方案", "dev_ls", "hold_ls", "hold_λMAE"))
    b_ls_d = sum(x[0] for x in base[:split]) / split
    b_ls_h = sum(x[0] for x in base[split:]) / (len(base) - split)
    print("  %-24s %8.5f %9.5f %9s" % ("现状(无校准)", b_ls_d, b_ls_h, "-"))
    best = None
    for half in (10, 30):
        for damp in (0.4, 0.6, 0.8, 1.0):
            v = damp_run(rows, half, damp)
            d = sum(x[0] for x in v[:split]) / split
            h = v[split:]
            hl = sum(x[0] for x in h) / len(h)
            hm = sum(x[1] for x in h) / len(h)
            print("  %-24s %8.5f %9.5f %9.4f"
                  % ("half=%d damp=%.1f" % (half, damp), d, hl, hm))
            if best is None or d < best[0]:
                best = (d, half, damp, hl, hm)
    d0, half0, damp0, hl0, hm0 = best
    print("  dev 最优 half=%d damp=%.1f → holdout ls %.5f vs 现状 %.5f (%+.5f) | λMAE %.4f"
          % (half0, damp0, hl0, b_ls_h, hl0 - b_ls_h, hm0))
    print("  生产现值 damp=0.6（compute_calibration），上面同 half 下 damp=0.6 那行可直接对照。")


if __name__ == "__main__":
    main()
