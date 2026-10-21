# -*- coding: utf-8 -*-
"""联赛专属 λ 偏移校正的 walk-forward 检验（2026-10-21）。

思路：现有体系对所有联赛用同一套收缩权重，只让「联赛基线均值」不同。
本检验额外给每个联赛一个**专属进球量偏移**（用该联赛过去的平均残差估），
看是否优于现状。

现状  T' = T*(1-w) + base_league*w           , w=0.25
变体  T'' = T' - alpha * mean_resid(league)   , 需 n>=MIN_N

评估：λ 偏差 / λ MAE / 比分单点 / 双档（同一批场次）。
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
BURN = 400
K_EB = 40.0
MAXG = 8
ALPHAS = (0.0, 0.3, 0.5, 0.8, 1.0)
MIN_N = (30, 60)


def pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def grid(lh, la):
    ph = [pmf(k, lh) for k in range(MAXG + 1)]
    pa = [pmf(k, la) for k in range(MAXG + 1)]
    ph[MAXG] += max(0.0, 1.0 - sum(ph))
    pa[MAXG] += max(0.0, 1.0 - sum(pa))
    m = [[ph[h] * pa[a] for a in range(MAXG + 1)] for h in range(MAXG + 1)]
    tot = sum(sum(r) for r in m)
    return [[v / tot for v in r] for r in m]


def main():
    rows = json.load(open(os.path.join(ROOT, "_bt_rows3.json"), encoding="utf-8"))
    rows.sort(key=lambda r: r["date"])

    for min_n in MIN_N:
        stats = {a: {"n": 0, "bias": 0.0, "mae": 0.0, "pk": 0, "bd": 0} for a in ALPHAS}
        gn = 0
        gsum = 0.0
        lg = {}
        resid = {}
        for i, r in enumerate(rows):
            lh0, la0 = float(r.get("lam_h") or 0), float(r.get("lam_a") or 0)
            act = r["hg"] + r["ag"]
            name = r.get("league") or ""
            d = lg.setdefault(name, [0, 0.0])
            if i >= BURN and lh0 > 0 and la0 > 0:
                g = gsum / gn if gn else 2.85
                base = ((d[0] * d[1] / d[0] + K_EB * g) / (d[0] + K_EB)) if d[0] >= 3 else g
                T = lh0 + la0
                T1 = T * (1 - 0.25) + base * 0.25
                rr = resid.get(name)
                off = (rr[1] / rr[0]) if (rr and rr[0] >= min_n) else 0.0
                for alpha in ALPHAS:
                    T2 = max(0.6, T1 - alpha * off)
                    lh, la = lh0 * T2 / T, la0 * T2 / T
                    m = grid(lh, la)
                    cells = sorted((("%d:%d" % (h, a)), m[h][a])
                                   for h in range(MAXG + 1) for a in range(MAXG + 1))
                    cells.sort(key=lambda x: -x[1])
                    hit = "%d:%d" % (r["hg"], r["ag"])
                    st = stats[alpha]
                    st["n"] += 1
                    st["bias"] += T2 - act
                    st["mae"] += abs(T2 - act)
                    st["pk"] += int(cells[0][0] == hit)
                    st["bd"] += int(hit in [c[0] for c in cells[1:3]])
            # 更新（只用过去）：残差按「现状收缩后」的口径记
            g = gsum / gn if gn else 2.85
            base = ((d[0] * d[1] / d[0] + K_EB * g) / (d[0] + K_EB)) if d[0] >= 3 else g
            if lh0 > 0:
                T = lh0 + la0
                T1 = T * (1 - 0.25) + base * 0.25
                e = resid.setdefault(name, [0, 0.0])
                e[0] += 1
                e[1] += (T1 - act)
            d[0] += 1
            d[1] += act
            gn += 1
            gsum += act

        n = stats[0.0]["n"]
        print("\nmin_n=%d（同 %d 场）" % (min_n, n))
        print("%-10s %8s %8s %8s %8s %9s" % ("alpha", "λ偏差", "λMAE", "单点%", "双档%", "MAE改善"))
        b0 = stats[0.0]["mae"] / n
        for alpha in ALPHAS:
            s = stats[alpha]
            print("%-10.1f %+8.3f %8.3f %8.2f %8.2f %+9.4f"
                  % (alpha, s["bias"] / n, s["mae"] / n, s["pk"] / n * 100,
                     s["bd"] / n * 100, s["mae"] / n - b0))

    # 分联赛残差诊断（全样本，仅用于看清分布）
    print("\n【分联赛 λ 残差（现状口径，样本≥40）】")
    lg = {}
    resid = {}
    for r in rows:
        T = (r.get("lam_h") or 0) + (r.get("lam_a") or 0)
        act = r["hg"] + r["ag"]
        if T <= 0:
            continue
        name = r.get("league") or ""
        d = lg.setdefault(name, [0, 0.0])
        d[0] += 1
        d[1] += act
        e = resid.setdefault(name, [0, 0.0])
        e[0] += 1
        e[1] += T - act
    rowsd = [(nm, v[0], v[1] / v[0]) for nm, v in resid.items() if v[0] >= 40]
    rowsd.sort(key=lambda x: x[2])
    for nm, cnt, res in rowsd[:5]:
        print("  低估最重 %-8s n=%3d  残差 %+.2f 球" % (nm, cnt, res))
    for nm, cnt, res in rowsd[-5:]:
        print("  高估最重 %-8s n=%3d  残差 %+.2f 球" % (nm, cnt, res))
    se = 1.6 / math.sqrt(40)
    print("  (n=40 时残差标准误约 ±%.2f 球，超出才算真信号)" % (se * 1.96))


if __name__ == "__main__":
    main()
