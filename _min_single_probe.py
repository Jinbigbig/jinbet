# -*- coding: utf-8 -*-
"""单队 λ 下界（MIN_SINGLE）回测：4036 场缓存 λ 上加重建比分网格，比较命中率/覆盖/Brier。"""
import json
import math
import os

BASE = os.path.dirname(os.path.abspath(__file__))
recs = json.load(open(os.path.join(BASE, "_grid_cache.json"), encoding="utf-8"))
print(f"样本 {len(recs)} 场（缓存 λ + 实际比分）")

KMAX = 12


def grid(lh, la):
    ph = [math.exp(-lh) * lh ** k / math.factorial(k) for k in range(KMAX + 1)]
    pa = [math.exp(-la) * la ** k / math.factorial(k) for k in range(KMAX + 1)]
    return ph, pa


def metrics(lh, la, hg, ag, floor=0.0, conserve=False):
    h2, a2 = lh, la
    if floor > 0:
        h2, a2 = max(lh, floor), max(la, floor)
        if conserve:
            t0, t1 = lh + la, h2 + a2
            if t1 > 0:
                s = t0 / t1
                h2, a2 = h2 * s, a2 * s
    ph, pa = grid(h2, a2)
    best, bp = None, -1.0
    for i in range(KMAX + 1):
        for j in range(KMAX + 1):
            p = ph[i] * pa[j]
            if p > bp:
                bp, best = p, (i, j)
    hit = int(best == (hg, ag))
    nb = int(abs(best[0] - hg) <= 1 and abs(best[1] - ag) <= 1)
    wh = sum(ph[i] * sum(pa[j] for j in range(i)) for i in range(KMAX + 1))
    dr = sum(ph[i] * pa[i] for i in range(KMAX + 1))
    wn = sum(ph[i] * sum(pa[j] for j in range(i + 1, KMAX + 1)) for i in range(KMAX + 1))
    tot = wh + dr + wn
    wh, dr, wn = wh / tot, dr / tot, wn / tot
    act = 0 if hg > ag else (1 if hg == ag else 2)
    pr = (wh, dr, wn)
    brier = sum((pr[k] - (1.0 if k == act else 0.0)) ** 2 for k in range(3))
    return hit, nb, brier, best, (h2, a2)


print(f"\n{'下界':>6} {'绑定场次':>8} {'Top1命中':>9} {'±1球':>8} {'Brier':>8} {'零封占比':>8}")
base_hits = base_nb = 0
base_brier = 0.0
for floor in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40):
    hits = nb = 0
    brier = 0.0
    bound = 0
    zc = 0
    for r in recs:
        lh, la, hg, ag = r["lh"], r["la"], r["hg"], r["ag"]
        h, n, b, bp, (h2, a2) = metrics(lh, la, hg, ag, floor)
        if floor > 0 and (h2 != lh or a2 != la):
            bound += 1
        hits += h
        nb += n
        brier += b
        if bp[0] == 0 or bp[1] == 0:
            zc += 1
    n = len(recs)
    if floor == 0.0:
        base_hits, base_nb, base_brier = hits, nb, brier
    mark = "" if floor == 0.0 else f"  (Δ命中 {hits-base_hits:+d})"
    print(f"{floor:>6.2f} {bound:>8} {hits/n:>8.2%} {nb/n:>7.1%} {brier/n:>8.4f} {zc/n:>7.1%}{mark}")

print(f"\n基准（现状）: Top1 {base_hits/len(recs):.2%}  ±1球 {base_nb/len(recs):.1%}  Brier {base_brier/len(recs):.4f}")

# 只看「λ 极悬殊」子集（min(λ) < 0.3）——即下界真正会绑定的场次
print("\n=== 子集：min(λ) < 0.30（下界实际绑定的场次）===")
sub = [r for r in recs if min(r["lh"], r["la"]) < 0.30]
print(f"子集 {len(sub)} 场（占 {len(sub)/len(recs):.1%}）")
for floor in (0.0, 0.10, 0.15, 0.20, 0.25, 0.30):
    hits = nb = 0
    for r in sub:
        h, n, b, bp, _ = metrics(r["lh"], r["la"], r["hg"], r["ag"], floor)
        hits += h
        nb += n
    print(f"  下界 {floor:.2f}: Top1 {hits/len(sub):.2%}  ±1球 {nb/len(sub):.1%}")

# 这些场次预测零封 vs 实际零封
print("\n子集里：预测零封率 vs 实际零封率")
for floor in (0.0, 0.15, 0.25):
    pz = az = 0
    for r in sub:
        h, n, b, bp, _ = metrics(r["lh"], r["la"], r["hg"], r["ag"], floor)
        pz += (bp[0] == 0 or bp[1] == 0)
        az += (r["hg"] == 0 or r["ag"] == 0)
    print(f"  下界 {floor:.2f}: 预测 {pz/len(sub):.1%} vs 实际 {az/len(sub):.1%}")
