# -*- coding: utf-8 -*-
"""联赛适配「组合方案」A/B 探针 v2（2026-10-21）。

单方案实测：形状层 全局频率单点最高 / 画像档双档最高 / 联赛身份=现状；
            先验层 全局均值 λMAE 最低 / 联赛身份 单点最高。

v2 做三件事：
 1) 多源线性混合 f = a_l*league + a_b*bucket + a_g*global，再与泊松矩阵混合，
    象限守恒缩放 → 1X2 恒定，差异只来自形状。
 2) 验收指标：比分 log score（连续、方差远小于 0/1 命中率）+ 配对 t 检验。
    dev(前60%) 选参 / holdout(后40%) 验证，holdout 不调参。
 3) 联合叠加：形状混合 × 时间自适应残差偏移，看优点能否相加。

用法：python lg_combo_probe.py
"""
import json
import math
import os

import lg_adapt_probe as LAP

ROOT = os.path.dirname(os.path.abspath(__file__))
BURN = LAP.BURN
G = 7
CELLS = [(h, a) for h in range(G) for a in range(G)]
UNI = [1.0 / (G * G)] * (G * G)


def idx_of(h, a):
    return h * G + a


def shrink_cnt(cnt, n, prior, k):
    if n <= 0:
        return list(prior)
    out = [(cnt[j] + k * prior[j]) / (n + k) for j in range(G * G)]
    s = sum(out)
    return [v / s for v in out]


def rescale(q, base):
    out = list(q)
    for pick in ("h", "d", "a"):
        sel = [j for j, (h, a) in enumerate(CELLS)
               if ("h" if h > a else ("d" if h == a else "a")) == pick]
        cq = sum(q[j] for j in sel)
        cb = sum(base[j] for j in sel)
        if cq > 1e-12 and cb > 0:
            f = cb / cq
            for j in sel:
                out[j] = q[j] * f
    s = sum(out)
    return [v / s for v in out]


def build(rows, half=40, cap=0.15):
    """walk-forward：记录泊松基准（原/时间修正）、三源频率、真实比分。"""
    st_l, st_b = {}, {}
    st_g = [0.0] * (G * G)
    n_g = 0
    off = 0.0
    aoff = 1 - math.exp(-math.log(2) / half)
    recs = []
    for i, r in enumerate(rows):
        lg = r.get("league") or ""
        hg, ag = int(r["hg"]), int(r["ag"])
        lh = float(r.get("lam_h") or 0)
        la = float(r.get("lam_a") or 0)
        T = lh + la
        cnt_l = st_l.get(lg, [0.0] * (G * G))
        n_l = sum(cnt_l)
        bucket = None
        if n_l >= 3:
            mg = sum(cnt_l[j] * (h + a) for j, (h, a) in enumerate(CELLS)) / n_l
            bucket = "low" if mg < LAP.Q1 else ("mid" if mg < LAP.Q2 else "high")
        cnt_b = st_b.get(bucket, [0.0] * (G * G)) if bucket else [0.0] * (G * G)
        n_b = sum(cnt_b)

        ok_cell = (hg < G and ag < G)
        if i >= BURN and lh > 0 and la > 0 and ok_cell:
            bg = LAP.grid(lh, la)
            p0 = [bg[h][a] for h, a in CELLS]
            T2 = T + max(-cap, min(cap, off))
            ba = LAP.grid(lh * T2 / T, la * T2 / T)
            p0a = [ba[h][a] for h, a in CELLS]
            fg = shrink_cnt(st_g, n_g, UNI, 30.0)
            fb = shrink_cnt(cnt_b, n_b, fg, 50.0)
            recs.append({
                "lg": lg, "act": idx_of(hg, ag),
                "T": T, "p0": p0, "p0a": p0a,
                "fg": fg, "fb": fb,
                "fl": shrink_cnt(cnt_l, n_l, fg, 50.0),
                "fl2": shrink_cnt(cnt_l, n_l, fb, 50.0),
            })

        if ok_cell:
            act_i = idx_of(hg, ag)
            st_l.setdefault(lg, [0.0] * (G * G))[act_i] += 1.0
            if bucket:
                st_b.setdefault(bucket, [0.0] * (G * G))[act_i] += 1.0
            st_g[act_i] += 1.0
            n_g += 1
        if T > 0:
            off = (1 - aoff) * off + aoff * ((hg + ag) - T)
    return recs


def ev(recs, w, ab, ag, src_l="fl", adj=False):
    """返回逐场 [logscore, pk, bd]，用于配对检验。"""
    out = []
    al = 1.0 - ab - ag
    for r in recs:
        p0 = r["p0a"] if adj else r["p0"]
        if w <= 0:
            q = p0
        else:
            fl = r["fl"] if src_l == "fl" else r["fl2"]
            fm = [al * fl[j] + ab * r["fb"][j] + ag * r["fg"][j] for j in range(G * G)]
            s = sum(fm)
            q = [(1 - w) * p0[j] + w * (fm[j] / s) for j in range(G * G)]
            q = rescale(q, p0)
        order = sorted(range(G * G), key=lambda j: -q[j])
        out.append([-math.log(max(q[r["act"]], 1e-12)),
                    int(order[0] == r["act"]),
                    int(r["act"] in order[1:3])])
    return out


def summ(v):
    n = len(v)
    return {"n": n, "ls": sum(x[0] for x in v) / n,
            "pk": sum(x[1] for x in v) / n * 100,
            "bd": sum(x[2] for x in v) / n * 100}


def paired(new, base):
    """配对差（负 = 新方案更好）及其 t 值、95%CI。"""
    d = [a[0] - b[0] for a, b in zip(new, base)]
    n = len(d)
    m = sum(d) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1))
    se = sd / math.sqrt(n)
    return m, se, (m / se if se > 0 else 0.0), (m - 1.96 * se, m + 1.96 * se)


def main():
    rows = json.load(open(os.path.join(ROOT, "_bt_rows3.json"), encoding="utf-8"))
    rows.sort(key=lambda r: r["date"])
    LAP.Q1, LAP.Q2 = 0.0, 9e9
    st = LAP.State()
    for r in rows[:BURN]:
        st.add(r.get("league") or "", r["hg"] + r["ag"])
    means = sorted(v[1] / v[0] for v in st.lg.values() if v[0] >= 8)
    LAP.Q1 = means[len(means) // 3]
    LAP.Q2 = means[len(means) * 2 // 3]

    recs = build(rows)
    split = int(len(recs) * 0.6)
    dev, hold = recs[:split], recs[split:]
    print("评估 %d 场（dev %d / holdout %d）| 画像档阈值 %.3f / %.3f"
          % (len(recs), len(dev), len(hold), LAP.Q1, LAP.Q2))

    b_dev = ev(dev, 0.30, 0.0, 0.0, "fl")
    b_hold = ev(hold, 0.30, 0.0, 0.0, "fl")

    # ---------- 第一组：三源混合 ----------
    print("\n【第一组｜多源形状混合】现状 = 纯联赛源 w=0.30")
    s_base = summ(b_dev)
    print("  现状 dev ls %.5f 单点 %.2f 双档 %.2f" % (s_base["ls"], s_base["pk"], s_base["bd"]))
    cand = []
    for w in (0.15, 0.25, 0.30, 0.40, 0.50):
        for ab in (0.0, 0.25, 0.5, 0.75, 1.0):
            for ag in (0.0, 0.25, 0.5, 0.75):
                if ab + ag > 1.0:
                    continue
                for src in ("fl", "fl2"):
                    v = ev(dev, w, ab, ag, src)
                    cand.append((summ(v)["ls"], w, ab, ag, src, v))
    cand.sort(key=lambda x: x[0])
    print("\n  dev 前 6（logscore 越小越好）:")
    for ls, w, ab, ag, src, _ in cand[:6]:
        print("    %-4s w=%.2f a_bk=%.2f a_gl=%.2f  ls %.5f" % (src, w, ab, ag, ls))

    _, w0, ab0, ag0, src0, v_dev = cand[0]
    v_hold = ev(hold, w0, ab0, ag0, src0)
    m, se, t, ci = paired(v_hold, b_hold)
    sh, sb = summ(v_hold), summ(b_hold)
    print("\n  → dev 最优 w=%.2f a_bk=%.2f a_gl=%.2f 源=%s" % (w0, ab0, ag0, src0))
    dm, dse, dt, _ = paired(v_dev, b_dev)
    print("    dev  配对 %+.5f  (t=%+.2f)" % (dm, dt))
    print("    hold ls %.5f vs 现状 %.5f | 配对 %+.5f  t=%+.2f  95%%CI [%+.5f, %+.5f]"
          % (sh["ls"], sb["ls"], m, t, ci[0], ci[1]))
    print("    hold 单点 %.2f vs %.2f (%+.2fpp) | 双档 %.2f vs %.2f (%+.2fpp)"
          % (sh["pk"], sb["pk"], sh["pk"] - sb["pk"], sh["bd"], sb["bd"], sh["bd"] - sb["bd"]))

    tops = cand[:20]
    hv = [paired(ev(hold, w, ab, ag, s), b_hold)[0] for _, w, ab, ag, s, _ in tops]
    print("    dev top20 在 holdout 的配对均值 %+.5f（最差 %+.5f / 最好 %+.5f）"
          % (sum(hv) / len(hv), max(hv), min(hv)))

    # ---------- 第二组：层次收缩 ----------
    print("\n【第二组｜层次收缩】w=0.30")
    for src, lab in (("fl", "现状 联赛→全局"), ("fl2", "层次 联赛→画像档→全局")):
        d, h = summ(ev(dev, 0.30, 0.0, 0.0, src)), summ(ev(hold, 0.30, 0.0, 0.0, src))
        print("  %-24s dev ls %.5f | hold ls %.5f 单点 %.2f 双档 %.2f"
              % (lab, d["ls"], h["ls"], h["pk"], h["bd"]))

    # ---------- 第三组：λ 先验 K 敏感性 ----------
    print("\n【第三组｜λ 先验 K 敏感性】（K→∞ 等价于用全局均值）")

    def run_ls(mode, w, k):
        LAP.K_EB = float(k)
        st_ = LAP.State()
        out = []
        for i, r in enumerate(rows):
            lg = r.get("league") or ""
            lh0, la0 = float(r.get("lam_h") or 0), float(r.get("lam_a") or 0)
            act = r["hg"] + r["ag"]
            if i >= BURN and lh0 > 0 and la0 > 0:
                T = lh0 + la0
                T2 = T * (1 - w) + LAP.base_of(st_, lg, mode) * w
                bg = LAP.grid(lh0 * T2 / T, la0 * T2 / T)
                out.append((-math.log(max(bg[min(r["hg"], 8)][min(r["ag"], 8)], 1e-12)),
                            abs(T2 - act)))
            st_.add(lg, act)
        LAP.K_EB = 40.0
        return out

    for mode in ("league", "global"):
        for k in (40, 320, 100000):
            v = run_ls(mode, 0.25, k)
            d, h = v[:split], v[split:]
            print("  %-18s dev λMAE %.4f ls %.5f | hold λMAE %.4f ls %.5f"
                  % ("%s K=%s" % (mode, k),
                     sum(x[1] for x in d) / len(d), sum(x[0] for x in d) / len(d),
                     sum(x[1] for x in h) / len(h), sum(x[0] for x in h) / len(h)))

    # ---------- 第四组：时间自适应偏移 ----------
    print("\n【第四组｜时间自适应残差偏移】EWMA(残差) 加到 λ 总量，dev 选参")
    best_t = None
    for half in (10, 20, 40, 80):
        for cap in (0.10, 0.20, 0.30):
            r2 = build(rows, half, cap)
            vd = ev(r2[:split], 0.30, 0.0, 0.0, "fl", adj=True)
            vh = ev(r2[split:], 0.30, 0.0, 0.0, "fl", adj=True)
            dls = summ(vd)["ls"] - s_base["ls"]
            if best_t is None or dls < best_t[0]:
                best_t = (dls, half, cap, vh)
            print("  half=%-3d cap=%.2f  dev %+.5f" % (half, cap, dls))
    dls, half0, cap0, vh = best_t
    m, se, t, ci = paired(vh, b_hold)
    sh, sb = summ(vh), summ(b_hold)
    print("  dev 最优 half=%d cap=%.2f → holdout 配对 %+.5f  t=%+.2f  95%%CI [%+.5f, %+.5f]"
          % (half0, cap0, m, t, ci[0], ci[1]))
    print("  holdout 单点 %.2f vs %.2f (%+.2fpp) | 双档 %.2f vs %.2f (%+.2fpp)"
          % (sh["pk"], sb["pk"], sh["pk"] - sb["pk"], sh["bd"], sb["bd"], sh["bd"] - sb["bd"]))

    # ---------- 第五组：联合叠加 ----------
    print("\n【第五组｜联合叠加】形状混合 + 时间偏移")
    r2 = build(rows, half0, cap0)
    hv = r2[split:]
    combo = ev(hv, w0, ab0, ag0, src0, adj=True)
    m, se, t, ci = paired(combo, b_hold)
    sc = summ(combo)
    print("  holdout ls %.5f vs 现状 %.5f | 配对 %+.5f  t=%+.2f  95%%CI [%+.5f, %+.5f]"
          % (sc["ls"], sb["ls"], m, t, ci[0], ci[1]))
    print("  holdout 单点 %.2f vs %.2f (%+.2fpp) | 双档 %.2f vs %.2f (%+.2fpp)"
          % (sc["pk"], sb["pk"], sc["pk"] - sb["pk"], sc["bd"], sb["bd"], sc["bd"] - sb["bd"]))
    print("\n  判据：|t|>2 才算真信号；logscore 配对差 <0 为更好。")


if __name__ == "__main__":
    main()
