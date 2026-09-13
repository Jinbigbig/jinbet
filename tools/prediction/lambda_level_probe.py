#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
lambda_level_probe.py — λ 总进球水平偏差 + 头条比分选择规则 回测（2026-09-13）

背景（用户提出）：连续两日 λ 偏差 -0.63 / -0.47，且报告头条比分长期被 1:1 占据
（09-06~09-12 占比 71%~92%），单比分命中率仅 7%~27%。

本脚本在带完整「比分盘+总进球盘+1X2+赛果」的历史样本上做时间外回测，回答两问：
  Q1 λ 水平：把总进球水平整体乘 k，哪个 k 使偏差→0 且比分指标不退化？
             （现状 = k=1.0 全链严格复刻生产口径 C1 象限对齐）
  Q2 比分展示：头条比分该用什么规则？单比分命中天花板在哪？
             替代方案「方向 + 总进球区间」的合并命中率是多少？

用法：
  python lambda_level_probe.py            # 全量（首次会构建缓存）
  python lambda_level_probe.py --quick    # 最近 1200 场
"""
import argparse
import importlib.util
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "_probe_rows_lamlevel.json")

KMAX = 9
TAIL = KMAX
LIST_H = {"1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2"}
LIST_D = {"0:0", "1:1", "2:2", "3:3"}
LIST_A = {"0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4", "0:5", "1:5", "2:5"}
OSH = {"胜其他": "H", "平其他": "D", "负其他": "A"}


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
            e = _load("eng_lamlevel", p)
            e.load_league_profile()
            return e
    raise SystemExit("找不到 calc_engine.py")


CELLS = [(h, a) for h in range(KMAX + 1) for a in range(KMAX + 1)]


def _listed(c):
    return "%d:%d" % c in (LIST_H | LIST_D | LIST_A)


def bucket_of(h, a):
    s = "%d:%d" % (h, a)
    if s in LIST_H or s in LIST_D or s in LIST_A:
        return s
    if h > a:
        return "胜其他"
    if h == a:
        return "平其他"
    return "负其他"


def _pmf(k, lam):
    if k >= KMAX:
        return 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def poisson_grid(lh, la):
    th = max(0.0, 1.0 - sum(_pmf(k, lh) for k in range(KMAX)))
    ta = max(0.0, 1.0 - sum(_pmf(k, la) for k in range(KMAX)))
    ph = [_pmf(k, lh) for k in range(KMAX)] + [th]
    pa = [_pmf(k, la) for k in range(KMAX)] + [ta]
    return norm({(h, a): ph[h] * pa[a] for h in range(KMAX + 1) for a in range(KMAX + 1)})


def norm(d):
    t = sum(d.values())
    return d if t <= 0 else {k: v / t for k, v in d.items()}


def devig(od):
    inv = {k: 1.0 / float(v) for k, v in od.items() if float(v) > 1.0}
    t = sum(inv.values())
    return {k: v / t for k, v in inv.items()} if t > 0 else {}


def marginals_12(g):
    return [sum(p for (a, b), p in g.items() if a > b),
            sum(p for (a, b), p in g.items() if a == b),
            sum(p for (a, b), p in g.items() if a < b)]


def quad_align(g, target):
    cur = marginals_12(g)
    f = [target[i] / cur[i] if cur[i] > 1e-12 else 0.0 for i in range(3)]
    out = {}
    for (h, a), p in g.items():
        i = 0 if h > a else (1 if h == a else 2)
        out[(h, a)] = p * f[i]
    return norm(out)


def bucket_probs(g):
    b = {}
    for (h, a), p in g.items():
        k = bucket_of(h, a)
        b[k] = b.get(k, 0.0) + p
    return b


def topn_hit(g, hg, ag, n):
    b = bucket_probs(g)
    items = sorted(b.items(), key=lambda x: -x[1])
    return 1 if bucket_of(hg, ag) in [k for k, _ in items[:n]] else 0


def logloss(g, hg, ag):
    return -math.log(max(bucket_probs(g).get(bucket_of(hg, ag), 1e-9), 1e-9))


def brier12(g, hg, ag):
    m = marginals_12(g)
    y = [1.0 if hg > ag else 0.0, 1.0 if hg == ag else 0.0, 1.0 if hg < ag else 0.0]
    return sum((m[i] - y[i]) ** 2 for i in range(3))


# ---------- 头条比分选择规则 ----------
def dir_of(marg):
    return 0 if marg[0] >= marg[1] and marg[0] >= marg[2] else (1 if marg[1] >= marg[2] else 2)


def act_dir_of(h, a):
    return 0 if h > a else (1 if h == a else 2)


def rule_r0_quad_mode(g, marg):
    """现状：发布象限内概率最高的**列出比分**（= 报告头条「方向首选」）"""
    qi = dir_of(marg)
    flt = (lambda c: c[0] > c[1]) if qi == 0 else (
        (lambda c: c[0] == c[1]) if qi == 1 else (lambda c: c[0] < c[1]))
    pool = [(c, p) for c, p in g.items() if flt(c) and _listed(c)]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def rule_r1_grid_mode(g, marg):
    """全网格众数（未对齐象限，等价旧版）"""
    return max(g.items(), key=lambda x: x[1])[0]


def rule_r2_quad_gridmode(g, marg):
    """象限内全网格众数（不限列出比分）"""
    qi = dir_of(marg)
    flt = (lambda c: c[0] > c[1]) if qi == 0 else (
        (lambda c: c[0] == c[1]) if qi == 1 else (lambda c: c[0] < c[1]))
    pool = [(c, p) for c, p in g.items() if flt(c)]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def make_rule_round_lambda(k=1.0):
    def f(g, marg, lh=None, la=None):
        return (int(round(lh * k)), int(round(la * k)))
    return f


def rule_r4_quad_lambda(g, marg, lh=None, la=None):
    """象限内、与期望 λ 最接近的列出比分（避免 1:1 退化）"""
    qi = dir_of(marg)
    flt = (lambda c: c[0] > c[1]) if qi == 0 else (
        (lambda c: c[0] == c[1]) if qi == 1 else (lambda c: c[0] < c[1]))
    pool = [(c, p) for c, p in g.items() if flt(c) and _listed(c)]
    if not pool:
        return None
    # 目标：象限内期望比分的加权均值
    tot = sum(p for _, p in pool)
    th = sum(c[0] * p for c, p in pool) / tot
    ta = sum(c[1] * p for c, p in pool) / tot
    return min(pool, key=lambda x: (x[0][0] - th) ** 2 + (x[0][1] - ta) ** 2)[0]
    return None


def tot_bucket(n):
    if n <= 1:
        return '0-1'
    if n <= 3:
        return '2-3'
    return '4+'


def load_rows(quick=False):
    if os.path.exists(CACHE):
        rows = json.load(open(CACHE, encoding="utf-8"))
        return rows[-1200:] if quick else rows
    fit = _load("mcf_probe2", os.path.join(ROOT, "_market_calib_fit.py"))
    rows = fit.build_rows()
    slim = []
    for r in rows:
        rec = r["rec"]
        if not (rec.get("比分") and rec.get("总进球")):
            continue
        if not r["o12"][0]:
            continue
        slim.append({"date": r["date"], "hg": r["hg"], "ag": r["ag"],
                     "lam": list(r["lam"]), "o12": list(r["o12"]), "lg": r["lg"],
                     "sc": rec["比分"], "tot": rec["总进球"]})
    json.dump(slim, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return slim[-1200:] if quick else slim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--ks", default="0.90,0.95,1.00,1.05,1.10,1.15")
    args = ap.parse_args()

    eng = engine()
    eng.fit_platt_params()
    rows = load_rows(args.quick)
    ks = [float(x) for x in args.ks.split(",")]
    W = eng.MARKET_W
    print(f"样本 {len(rows)} 场 | λ口径=引擎 base_lam + 市场混合{W:.2f} + 联赛分数形态混权 + Platt + 象限对齐")
    print(f"样本期 {rows[0]['date']} ~ {rows[-1]['date']}\n")

    # Q1: λ 水平扫描
    print("=" * 100)
    print("Q1  λ 总进球水平扫描（k 乘在象限对齐前，方向由市场锚定不变）")
    print(f"{'k':>6}{'预测λ和':>10}{'实际和':>10}{'偏差':>9}{'MAE':>8}"
          f"{'比分LL':>10}{'Top1':>8}{'Top3':>8}{'Top5':>8}{'方向':>8}{'1X2Brier':>10}")
    print("-" * 100)
    for k in ks:
        st = {x: 0.0 for x in ("lam", "act", "mae", "ll", "t1", "t3", "t5", "dir", "b")}
        n = 0
        for r in rows:
            lh, la = r["lam"]
            oh, od, ol = r["o12"]
            pv = eng.devig_1x2(oh, od, ol)
            tb = (lh + la) * k
            pm = eng.pois_1x2(lh, la)
            pb = [(1 - W) * pm[i] + W * pv[i] for i in range(3)]
            s = sum(pb)
            pb = [x / s for x in pb]
            lh2, la2 = eng.prob_to_lambda(pb, tb)
            g = poisson_grid(lh2, la2)
            lo, hi = min(lh2, la2), max(lh2, la2)
            g = eng.mix_score_matrix(g, r["lg"], hi / lo if lo > 1e-9 else 99.0)
            pub = list(eng.apply_platt(*marginals_12(g)))
            g = quad_align(g, pub)
            hg, ag = r["hg"], r["ag"]
            n += 1
            st["lam"] += lh2 + la2
            st["act"] += hg + ag
            st["mae"] += abs((lh2 + la2) - (hg + ag))
            st["ll"] += logloss(g, hg, ag)
            st["t1"] += topn_hit(g, hg, ag, 1)
            st["t3"] += topn_hit(g, hg, ag, 3)
            st["t5"] += topn_hit(g, hg, ag, 5)
            st["dir"] += 1 if dir_of(marginals_12(g)) == (0 if hg > ag else (1 if hg == ag else 2)) else 0
            st["b"] += brier12(g, hg, ag)
        print(f"{k:>6.2f}{st['lam']/n:>10.2f}{st['act']/n:>10.2f}"
              f"{(st['lam']-st['act'])/n:>+9.2f}{st['mae']/n:>8.3f}"
              f"{st['ll']/n:>10.4f}{st['t1']/n*100:>7.1f}%{st['t3']/n*100:>7.1f}%"
              f"{st['t5']/n*100:>7.1f}%{st['dir']/n*100:>7.1f}%{st['b']/n:>10.4f}")

    # Q2: 头条比分规则对照（k=1.0 生产口径）
    print()
    print("=" * 100)
    print("Q2  头条比分选择规则对照（k=1.0）")
    print(f"{'规则':<26}{'单比分命中':>12}{'±1球命中':>12}{'方向命中':>10}")
    print("-" * 100)
    rules = {
        "R0 象限众数(现状头条)": rule_r0_quad_mode,
        "R1 全局网格众数": rule_r1_grid_mode,
        "R2 象限内网格众数": rule_r2_quad_gridmode,
        "R4 象限内λ最接近": rule_r4_quad_lambda,
    }
    acc = {nm: {"exact": 0, "near": 0} for nm in rules}
    dirhit = 0
    distr = {nm: {} for nm in rules}
    n = 0
    for r in rows:
        lh, la = r["lam"]
        oh, od, ol = r["o12"]
        pv = eng.devig_1x2(oh, od, ol)
        pm = eng.pois_1x2(lh, la)
        pb = [(1 - W) * pm[i] + W * pv[i] for i in range(3)]
        s = sum(pb)
        pb = [x / s for x in pb]
        lh2, la2 = eng.prob_to_lambda(pb, lh + la)
        g = poisson_grid(lh2, la2)
        lo, hi = min(lh2, la2), max(lh2, la2)
        g = eng.mix_score_matrix(g, r["lg"], hi / lo if lo > 1e-9 else 99.0)
        pub = list(eng.apply_platt(*marginals_12(g)))
        g = quad_align(g, pub)
        marg = marginals_12(g)
        hg, ag = r["hg"], r["ag"]
        n += 1
        if dir_of(marg) == (0 if hg > ag else (1 if hg == ag else 2)):
            dirhit += 1
        for nm, fn in rules.items():
            try:
                c = fn(g, marg, lh2, la2)
            except TypeError:
                c = fn(g, marg)
            if c is None:
                continue
            if c == (hg, ag):
                acc[nm]["exact"] += 1
            if abs(c[0] - hg) <= 1 and abs(c[1] - ag) <= 1:
                acc[nm]["near"] += 1
            distr[nm][c] = distr[nm].get(c, 0) + 1
    for nm in rules:
        a = acc[nm]
        print(f"{nm:<26}{a['exact']/n*100:>11.1f}%{a['near']/n*100:>11.1f}%{dirhit/n*100:>9.1f}%")
    print()
    print("各规则 Top5 取值集中度（前5个比分占总场次比例 = 退化程度）：")
    for nm in rules:
        top = sorted(distr[nm].items(), key=lambda x: -x[1])[:5]
        share = sum(v for _, v in top) / n * 100
        oneone = distr[nm].get((1, 1), 0) / n * 100
        print(f"  {nm:<26} 前5取值占 {share:5.1f}%  1:1 占 {oneone:5.1f}%  "
              f"取值数 {len(distr[nm]):>3}")

    # Q3: 方向+总进球区间 方案
    print()
    print("=" * 100)
    print("Q3  替代头条方案：方向 + 总进球区间（联合命中率）")
    comb = 0
    dirn = 0
    totn = 0
    n = 0
    for r in rows:
        lh, la = r["lam"]
        oh, od, ol = r["o12"]
        pv = eng.devig_1x2(oh, od, ol)
        pm = eng.pois_1x2(lh, la)
        pb = [(1 - W) * pm[i] + W * pv[i] for i in range(3)]
        s = sum(pb)
        pb = [x / s for x in pb]
        lh2, la2 = eng.prob_to_lambda(pb, lh + la)
        g = poisson_grid(lh2, la2)
        lo, hi = min(lh2, la2), max(lh2, la2)
        g = eng.mix_score_matrix(g, r["lg"], hi / lo if lo > 1e-9 else 99.0)
        pub = list(eng.apply_platt(*marginals_12(g)))
        g = quad_align(g, pub)
        marg = marginals_12(g)
        hg, ag = r["hg"], r["ag"]
        n += 1
        act_dir = 0 if hg > ag else (1 if hg == ag else 2)
        md = dir_of(marg)
        if md == act_dir:
            dirn += 1
        # 总进球区间：按概率最大的档
        tb = {}
        for (h, a), p in g.items():
            k = tot_bucket(h + a)
            tb[k] = tb.get(k, 0.0) + p
        pick_tb = max(tb.items(), key=lambda x: x[1])[0]
        act_tb = tot_bucket(hg + ag)
        if pick_tb == act_tb:
            totn += 1
        if md == act_dir and pick_tb == act_tb:
            comb += 1
    print(f"方向命中            {dirn/n*100:.1f}%")
    print(f"总进球区间命中      {totn/n*100:.1f}%")
    print(f"方向+区间联合命中   {comb/n*100:.1f}%   ← 对比：单比分 13~14%")

    # ---------- Q4: λ 动态校准窗口长度（是否在追高/追低） ----------
    print()
    print("=" * 100)
    print("Q4  动态校准窗口长度对照：用过去 N 天的 λ/实际 比，对今日 λ 做修正")
    print("    （现状 = N=7，EWMA a=0.25，damp=0.6，clamp 0.88~1.12；本表 λ 基线为 base_lam）")
    # 按日聚合
    byday = {}
    for r in rows:
        d = r["date"]
        b = byday.setdefault(d, {"pred": 0.0, "act": 0.0, "n": 0})
        b["pred"] += sum(r["lam"])
        b["act"] += r["hg"] + r["ag"]
        b["n"] += 1
    days = sorted(byday)
    ratios = {d: (byday[d]["pred"] / byday[d]["act"] if byday[d]["act"] else 1.0) for d in days}

    def factor_from(hist, damp=0.6, lo=0.88, hi=1.12, alpha=0.25):
        """EWMA over hist (oldest→newest) then damped to factor."""
        if not hist:
            return 1.0
        e = hist[0]
        for x in hist[1:]:
            e = alpha * x + (1 - alpha) * e
        if e <= 0:
            return 1.0
        f = 1.0 + damp * (1.0 / e - 1.0)
        return max(lo, min(hi, f))

    for N in (3, 7, 14, 21, 30, 60, 0):
        mae = mbe = 0.0
        cnt = 0
        for i, d in enumerate(days):
            if N == 0:
                f = 1.0
            else:
                hist = [ratios[dd] for dd in days[max(0, i - N):i]]
                if len(hist) < 3:
                    f = 1.0
                else:
                    f = factor_from(hist)
            for r in [x for x in rows if x["date"] == d]:
                pred = sum(r["lam"]) * f
                act = r["hg"] + r["ag"]
                mae += abs(pred - act)
                mbe += pred - act
                cnt += 1
        label = "不修正(因子=1)" if N == 0 else f"窗口 N={N}天"
        print(f"  {label:<16} MAE {mae/cnt:.4f}  平均偏差 {mbe/cnt:+.3f}  样本 {cnt}")

    # ---------- Q5: 月度偏差（判断偏差是模型问题还是赛果环境问题） ----------
    print()
    print("=" * 100)
    print("Q5  月度：模型 λ（base_lam，未加动态因子）vs 实际场均总进球")
    mon = {}
    for r in rows:
        m = r["date"][:7]
        b = mon.setdefault(m, {"n": 0, "act": 0.0, "lam": 0.0})
        b["n"] += 1
        b["act"] += r["hg"] + r["ag"]
        b["lam"] += sum(r["lam"])
    print(f"  {'月份':<10}{'场次':>6}{'实际场均':>11}{'模型λ场均':>12}{'偏差':>9}")
    for m in sorted(mon):
        b = mon[m]
        print(f"  {m:<10}{b['n']:>6}{b['act']/b['n']:>11.2f}{b['lam']/b['n']:>12.2f}"
              f"{(b['lam']-b['act'])/b['n']:>+9.2f}")

    # ---------- Q6: 串关口径对照（方向串关 vs 比分串关） ----------
    print()
    print("=" * 100)
    print("Q6  每日取「方向概率最高」的3场做3串1：方向腿 vs 比分腿（含组合赔率与 ROI）")
    byday_rows = {}
    for r in rows:
        byday_rows.setdefault(r["date"], []).append(r)
    DAYS = 0
    d3_hit = s3_hit = 0
    d3_ret = s3_ret = 0.0
    for d, rs in sorted(byday_rows.items()):
        if len(rs) < 3:
            continue
        cand = []
        for r in rs:
            lh, la = r["lam"]
            oh, od, ol = r["o12"]
            pv = eng.devig_1x2(oh, od, ol)
            pm = eng.pois_1x2(lh, la)
            pb = [(1 - W) * pm[i] + W * pv[i] for i in range(3)]
            s = sum(pb)
            pb = [x / s for x in pb]
            lh2, la2 = eng.prob_to_lambda(pb, lh + la)
            g = poisson_grid(lh2, la2)
            lo, hi = min(lh2, la2), max(lh2, la2)
            g = eng.mix_score_matrix(g, r["lg"], hi / lo if lo > 1e-9 else 99.0)
            pub = list(eng.apply_platt(*marginals_12(g)))
            g = quad_align(g, pub)
            marg = marginals_12(g)
            qi = dir_of(marg)
            pick = rule_r2_quad_gridmode(g, marg)
            d_odds = float([oh, od, ol][qi])
            sc_odds = None
            sdict = r.get("sc") or {}
            if pick is not None:
                v = sdict.get("%d:%d" % pick)
                if v:
                    try:
                        sc_odds = float(v)
                    except ValueError:
                        sc_odds = None
            cand.append({"p": max(marg), "qi": qi, "pick": pick,
                         "d_odds": d_odds, "sc_odds": sc_odds,
                         "hg": r["hg"], "ag": r["ag"]})
        cand.sort(key=lambda x: -x["p"])
        top3 = cand[:3]
        DAYS += 1
        ok_d = all(act_dir_of(c["hg"], c["ag"]) == c["qi"] for c in top3)
        ok_s = all(c["pick"] == (c["hg"], c["ag"]) for c in top3)
        if ok_d:
            d3_hit += 1
            prod = 1.0
            for c in top3:
                prod *= c["d_odds"]
            d3_ret += prod
        else:
            d3_ret += 0.0
        if ok_s and all(c["sc_odds"] for c in top3):
            s3_hit += 1
            prod = 1.0
            for c in top3:
                prod *= c["sc_odds"]
            s3_ret += prod
    print(f"  天数 {DAYS}")
    print(f"  方向串关(3腿)：全中 {d3_hit} 天 = {d3_hit/max(DAYS,1)*100:.1f}%   "
          f"每注1元总回报 {d3_ret:.1f}  ROI {(d3_ret/DAYS-1)*100:+.1f}%")
    print(f"  比分串关(3腿)：全中 {s3_hit} 天 = {s3_hit/max(DAYS,1)*100:.1f}%   "
          f"每注1元总回报 {s3_ret:.1f}  ROI {(s3_ret/DAYS-1)*100:+.1f}%")
    print("  注：单腿基准 = 方向 53.8%（3腿理论 15.6%）／比分 15.4%（3腿理论 0.37%）")


if __name__ == "__main__":
    main()
