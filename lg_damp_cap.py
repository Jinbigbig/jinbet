# -*- coding: utf-8 -*-
"""λ 校准的「绝对幅度上限」检验（2026-10-21）。

发现链：
  - offset 版（绝对球数、cap 0.10）有效：holdout logscore -0.0027，5 段中 4 段为负；
  - factor 版（比例缩放、(1/ratio)^damp）全面变差：logscore +0.013。
  - 诊断：ratio 中位 1.007、p05~p95 为 0.883~1.159，从不触 clamp。factor 的波动是
    ±8%，在 λ=4 球的比赛等于 ±0.32 球，远超小比分场的修正量 → 大球场比赛被过度修正。

假设：问题不在 damp 大小，而在「按比例修正」对大 λ 场放大过度。给 ΔT 加绝对上限
（不改 damp、不改 EWMA）应当同时保住小场修正、去掉大场过冲。

用法：python lg_damp_cap.py
"""
import json
import math
import os

import lg_adapt_probe as LAP

ROOT = os.path.dirname(os.path.abspath(__file__))
BURN = LAP.BURN


def run(rows, half, damp, cap_abs=None, lo=0.85, hi=1.18):
    alpha = 1 - math.exp(-math.log(2) / half)
    eT = eA = None
    out = []
    for i, r in enumerate(rows):
        lh = float(r.get("lam_h") or 0)
        la = float(r.get("lam_a") or 0)
        T = lh + la
        act = r["hg"] + r["ag"]
        if i >= BURN and T > 0 and eT and eA:
            factor = min(hi, max(lo, (1.0 / (eT / eA)) ** damp))
            dT = T * factor - T
            if cap_abs is not None:
                dT = max(-cap_abs, min(cap_abs, dT))
            T2 = T + dT
            bg = LAP.grid(lh * T2 / T, la * T2 / T)
            out.append((-math.log(max(bg[min(r["hg"], 8)][min(r["ag"], 8)], 1e-12)),
                        abs(T2 - act), dT))
        if T > 0:
            eT = T if eT is None else (1 - alpha) * eT + alpha * T
            eA = act if eA is None else (1 - alpha) * eA + alpha * act
    return out


def segs(vec, base, k=5):
    n = len(vec)
    return [sum(x[0] - y[0] for x, y in zip(vec[s * n // k:(s + 1) * n // k],
                                              base[s * n // k:(s + 1) * n // k])) / (n // k)
            for s in range(k)]


def main():
    rows = json.load(open(os.path.join(ROOT, "_bt_rows3.json"), encoding="utf-8"))
    rows.sort(key=lambda r: r["date"])

    base = []
    for i, r in enumerate(rows):
        lh = float(r.get("lam_h") or 0)
        la = float(r.get("lam_a") or 0)
        if i >= BURN and lh + la > 0:
            bg = LAP.grid(lh, la)
            base.append((-math.log(max(bg[min(r["hg"], 8)][min(r["ag"], 8)], 1e-12)), 0.0, 0.0))
    split = int(len(base) * 0.6)

    def stat(v):
        d = sum(x[0] for x in v[:split]) / split
        h = v[split:]
        hl = sum(x[0] for x in h) / len(h)
        hm = sum(x[1] for x in h) / len(h)
        m = sum(x[0] - y[0] for x, y in zip(v, base)) / len(v)
        mh = sum(x[0] - y[0] for x, y in zip(h, base[split:])) / len(h)
        sd = math.sqrt(sum(((x[0] - y[0]) - mh) ** 2 for x, y in zip(h, base[split:])) / (len(h) - 1))
        t = mh / (sd / math.sqrt(len(h))) if sd > 0 else 0.0
        dT = sum(abs(x[2]) for x in h) / len(h)
        return d, hl, hm, m, mh, t, dT

    sb = stat(base)
    print("现状（不校准）: dev_ls %.5f | hold_ls %.5f | hold_λMAE %.4f"
          % (sb[0], sum(x[0] for x in base[split:]) / len(base[split:]),
             sum(x[1] for x in base[split:]) / len(base[split:])))
    print("\n%-26s %8s %9s %9s %8s %9s %7s" %
          ("方案", "dev_ls", "hold_ls", "配对差", "配对t", "平均|ΔT|", "段负/5"))
    rows_out = []
    for half in (10, 30):
        for damp in (0.6, 1.0):
            for cap in (None, 0.10, 0.20):
                v = run(rows, half, damp, cap)
                d, hl, hm, m, mh, t, dT = stat(v)
                ng = sum(1 for x in segs(v, base) if x < 0)
                rows_out.append((mh, half, damp, cap, d, hl, hm, t, dT, ng))
                print("%-26s %8.5f %9.5f %+9.5f %8.2f %9.3f %7s"
                      % ("half=%d damp=%.1f cap=%s" % (half, damp, cap if cap else "无"),
                         d, hl, mh, t, dT, "%d/5" % ng))
    best = min(rows_out)
    print("\ndev 最优（按全样本配对）: half=%d damp=%.1f cap=%s → holdout 配对 %+.5f t=%+.2f"
          % (best[1], best[2], best[3] if best[3] else "无", best[0], best[7]))


if __name__ == "__main__":
    main()
