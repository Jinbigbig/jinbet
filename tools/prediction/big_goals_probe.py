# -*- coding: utf-8 -*-
"""大比分（总进球 6+ / 7+）可预测性探针（V1）。

用户 2026-09-10：「昨天几场大 6 球，今天哪几场会有可能？最近一个月几乎每天都有
6、7+ 的进球数，我觉得可以预测一下，哪一场最像。」

本脚本回答三件事：
  A. 「几乎天天有 6+」是不是异象？—— 基础率 + 每天场次数 → 至少一场 6+ 的概率。
  B. 6+ / 7+ 到底能不能预测？—— 市场总进球盘(去水) vs 市场比分盘(去水) 的校准与 Brier，
     与常数基线、模型 λ 泊松对比；并检验市场是否系统性低估/高估 6+。
  C. 今日每场的 P(≥6) / P(≥7) 排序，给出「最像」的场次。

用法：
  python big_goals_probe.py            # 全量历史校准 + 今日评分
  python big_goals_probe.py --today    # 只出今日评分
"""
import argparse
import glob
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# 总进球盘档位（固定 8 档）
TOT_KEYS = ["0", "1", "2", "3", "4", "5", "6", "7+"]
# 比分盘里明确属于 6+ 的比分
SCORE6 = ("3:3", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2", "4:3", "5:3", "5:4",
          "3:4", "3:5", "4:5")


# ---------------------------------------------------------------- 数据加载
def _load_dir(d):
    lib = {}
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        if "index" in os.path.basename(f):
            continue
        try:
            lib.update(json.load(open(f, encoding="utf-8")))
        except Exception:
            pass
    return lib


def load_lib():
    lib = _load_dir(os.path.join(ROOT, "results_history"))
    try:
        rd = json.load(open(os.path.join(ROOT, "results_data.json"), encoding="utf-8"))
    except Exception:
        rd = {}
    for k, v in rd.items():
        if k not in lib:
            lib[k] = v
        else:
            for fld in ("让球", "比分", "总进球", "半全场"):
                if not lib[k].get(fld) and v.get(fld):
                    lib[k][fld] = v[fld]
    return lib


_SC = re.compile(r"^(\d+):(\d+)$")


def final_score(v):
    s = v.get("fullScore") or v.get("score")
    if not isinstance(s, str):
        return None
    m = _SC.match(s.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def devig_totals(tot):
    """总进球盘去水 → {0..5, 6, 7+} 概率。返回 (probs, overround) 或 None。"""
    if not isinstance(tot, dict):
        return None
    raw = {}
    for k in TOT_KEYS:
        o = _f(tot.get(k))
        if o is None or o <= 1.0:
            return None
        raw[k] = 1.0 / o
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}, s


def devig_scores(sc):
    """比分盘去水 → {比分键: 概率}（含 胜其他/平其他/负其他）。"""
    if not isinstance(sc, dict) or not sc:
        return None
    raw = {}
    for k, o in sc.items():
        v = _f(o)
        if v is None or v <= 1.0:
            continue
        raw[k] = 1.0 / v
    if len(raw) < 15:
        return None
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}, s


def score_dist_ge6(probs, other_share=1.0):
    """比分盘 P(总进球≥6)。

    ⚠️ 口径要点（2026-09-10 实测 4599 场）：竞彩比分盘已列举**全部总进球 ≤5**
    的可能比分，因此「胜其他 / 平其他 / 负其他」三档 **100% 都是 6+** 
    （实测 107/107 全部 ≥6 球，Top 比分 3:4/6:0/4:3/6:1…）。
    故 other_share 默认应为 1.0，不是经验比例。
    """
    p = 0.0
    for k, v in probs.items():
        if k in SCORE6:
            p += v
        elif k.endswith("其他"):
            p += v * other_share
    return p


def poisson_ge(k, lam):
    """P(X >= k) for Poisson(lam)"""
    p = math.exp(-lam)
    c = p
    for i in range(1, k):
        p *= lam / i
        c += p
    return 1.0 - c


def poisson_total_ge(k, lh, la):
    """独立泊松和 P(H+A >= k)"""
    # 网格求和（k<=12 足够）
    p = 0.0
    for h in range(0, 16):
        ph = math.exp(-lh) * lh ** h / math.factorial(h)
        for a in range(0, 16 - h):
            if h + a >= k:
                pa = math.exp(-la) * la ** a / math.factorial(a)
                p += ph * pa
    return p


# ---------------------------------------------------------------- D ROI + 校准
def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sig(z):
    return 1.0 / (1.0 + math.exp(-z))


def ir_ols(X, y, l2=1.0, iters=25):
    """自写 IRLS 逻辑回归（无 numpy 环境）。"""
    n, k = len(X), len(X[0])
    b = [0.0] * k
    for _ in range(iters):
        A = [[0.0] * k for _ in range(k)]
        g = [0.0] * k
        for i in range(n):
            z = sum(b[j] * X[i][j] for j in range(k))
            p = _sig(z)
            w = max(p * (1 - p), 1e-9)
            for j in range(k):
                g[j] += X[i][j] * (y[i] - p)
                for l in range(k):
                    A[j][l] += X[i][j] * X[i][l] * w
        for j in range(k):
            A[j][j] += l2
        # 解线性方程 A·d = g（高斯消元）
        M = [row[:] + [g[i]] for i, row in enumerate(A)]
        for c in range(k):
            piv = max(range(c, k), key=lambda r: abs(M[r][c]))
            if abs(M[piv][c]) < 1e-12:
                continue
            M[c], M[piv] = M[piv], M[c]
            pv = M[c][c]
            M[c] = [x / pv for x in M[c]]
            for r in range(k):
                if r != c and abs(M[r][c]) > 1e-12:
                    f = M[r][c]
                    M[r] = [a - f * b2 for a, b2 in zip(M[r], M[c])]
        d = [M[i][k] for i in range(k)]
        b = [b[i] + d[i] for i in range(k)]
        if max(abs(x) for x in d) < 1e-8:
            break
    return b


def roi_part(rows, verbose=True):
    """直接按赔率回测：买「6 球」档 / 「7+」档的 ROI（不去水，最干净）。"""
    import io as _io
    # 需要用未去水的原始赔率 → 重新从库里取
    lib = load_lib()
    recs = []
    for k, v in lib.items():
        sc = final_score(v)
        tot = v.get("总进球")
        if not sc or not isinstance(tot, dict):
            continue
        o6, o7 = _f(tot.get("6")), _f(tot.get("7+"))
        if not o6 or not o7 or o6 <= 1 or o7 <= 1:
            continue
        g = sc[0] + sc[1]
        recs.append({"g": g, "o6": o6, "o7": o7, "date": k.split("_")[0]})
    n = len(recs)
    out = []
    if verbose:
        print(f"\n=== D. 直接按赔率回测（{n} 场，每场买 1 单位）===")
    for tag, hit, oddk, per in (("买「恰好 6 球」档", lambda g: g == 6, "o6", 1.0),
                                ("买「7+ 球」档", lambda g: g >= 7, "o7", 1.0),
                                ("6 档 + 7+ 档 各半注", lambda g: g >= 6, None, 0.5)):
        pnl = 0.0
        stake = 0.0
        wins = 0
        for r in recs:
            if oddk:
                pnl += (r[oddk] if hit(r["g"]) else 0.0) - 1.0
                stake += 1.0
                wins += 1 if hit(r["g"]) else 0
            else:
                pnl += per * ((r["o6"] if r["g"] == 6 else 0.0) - 1.0)
                pnl += per * ((r["o7"] if r["g"] >= 7 else 0.0) - 1.0)
                stake += 2 * per
                wins += 1 if hit(r["g"]) else 0
        if verbose:
            print(f"  {tag:<26} 命中 {wins:4d}/{n} = {wins/n*100:5.2f}%   "
                  f"投入 {stake:7.0f}  净 {pnl:+9.1f}  ROI {pnl/stake*100:+7.2f}%")
        out.append((tag, pnl / stake))
    if verbose:
        # 按赔率区间
        print(f"\n  「7+ 球」按赔率区间：")
        print(f"    {'赔率':<14}{'n':>6}{'命中率':>9}{'需命中':>9}{'ROI':>10}")
        for lo, hi in ((1, 4), (4, 6), (6, 9), (9, 14), (14, 99)):
            seg = [r for r in recs if lo <= r["o7"] < hi]
            if len(seg) < 40:
                continue
            hr = sum(1 for r in seg if r["g"] >= 7) / len(seg)
            need = 1.0 / statistics.mean(r["o7"] for r in seg)
            pnl = sum((r["o7"] if r["g"] >= 7 else 0) - 1 for r in seg)
            print(f"    {lo}–{hi:<10}{len(seg):6d}{hr*100:8.2f}%{need*100:8.2f}%"
                  f"{pnl/len(seg)*100:+9.2f}%")
        print(f"\n  「恰好 6 球」按赔率区间：")
        print(f"    {'赔率':<14}{'n':>6}{'命中率':>9}{'需命中':>9}{'ROI':>10}")
        for lo, hi in ((1, 5), (5, 7), (7, 10), (10, 15), (15, 99)):
            seg = [r for r in recs if lo <= r["o6"] < hi]
            if len(seg) < 40:
                continue
            hr = sum(1 for r in seg if r["g"] == 6) / len(seg)
            need = 1.0 / statistics.mean(r["o6"] for r in seg)
            pnl = sum((r["o6"] if r["g"] == 6 else 0) - 1 for r in seg)
            print(f"    {lo}–{hi:<10}{len(seg):6d}{hr*100:8.2f}%{need*100:8.2f}%"
                  f"{pnl/len(seg)*100:+9.2f}%")
    return recs


def calib_fit(rows, ykey="y6", key="p6_mkt", verbose=True):
    """拟合 logit 校准：真实 logit = a + b·logit(市场概率)，前 60% 拟合、后 40% 验证。"""
    seg = sorted([r for r in rows if key in r], key=lambda r: r["date"])
    if len(seg) < 400:
        return None
    cut = int(len(seg) * 0.6)
    X = [[1.0, _logit(r[key])] for r in seg]
    y = [r[ykey] for r in seg]
    b = ir_ols(X[:cut], y[:cut], l2=2.0)
    def ev(lo, hi):
        ps = [_sig(b[0] + b[1] * X[i][1]) for i in range(lo, hi)]
        ys = y[lo:hi]
        bb = statistics.mean(ys)
        return (brier(ps, ys), brier([bb] * len(ys), ys), statistics.mean(ps), bb, len(ys))
    tr = ev(0, cut)
    te = ev(cut, len(seg))
    if verbose:
        print(f"\n=== E. 市场概率校准映射（{key} → {ykey}）===")
        print(f"  logit(P_true) = {b[0]:+.4f} {b[1]:+.4f}·logit(P_市场)   "
              f"（b<1 = 市场把极端值放大）")
        for tag, r in (("拟合段", tr), ("时间外", te)):
            print(f"  {tag}: n={r[4]:5d} 校准后均值 {r[2]*100:5.2f}% 实际 {r[3]*100:5.2f}% | "
                  f"Brier {r[0]:.5f} vs 常数 {r[1]:.5f}  技巧分 {(1-r[0]/r[1])*100:+.2f}%")
        ps_raw = [r[key] for r in seg[cut:]]
        print(f"  对照 原始市场（时间外）Brier {brier(ps_raw, y[cut:]):.5f}"
              f"  技巧分 {(1-brier(ps_raw, y[cut:])/te[1])*100:+.2f}%")
    return b


def hist_part(lib, verbose=True):
    rows = []
    for k, v in lib.items():
        sc = final_score(v)
        if not sc:
            continue
        d = k.split("_")[0]
        g = sc[0] + sc[1]
        rec = {"date": d, "key": k, "g": g, "y6": 1 if g >= 6 else 0,
               "y7": 1 if g >= 7 else 0}
        dt = devig_totals(v.get("总进球"))
        if dt:
            rec["p6_mkt"] = dt[0]["6"] + dt[0]["7+"]
            rec["p7_mkt"] = dt[0]["7+"]
            rec["tot_or"] = dt[1]
            rec["lam_mkt"] = sum(int(kk.rstrip("+")) * pp for kk, pp in dt[0].items())
        ds = devig_scores(v.get("比分"))
        if ds:
            rec["p6_sc"] = score_dist_ge6(ds[0], 1.0)
            rec["p6_sc055"] = score_dist_ge6(ds[0], 0.55)
            rec["p6_sc0"] = score_dist_ge6(ds[0], 0.0)
        rows.append(rec)
    rows.sort(key=lambda r: r["key"])
    nt = sum(1 for r in rows if "p6_mkt" in r)
    ns = sum(1 for r in rows if "p6_sc" in r)
    if verbose:
        print(f"样本：有赛果 {len(rows)} 场 | 有总进球盘 {nt} 场 | 有比分盘 {ns} 场")
    return rows


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def calib_table(rows, key, ykey="y6", bins=None, bins_label=None):
    if bins is None:
        bins = [0, .03, .05, .07, .09, .11, .14, .18, 1.01]
    print(f"\n  校准（{key} → 实际 {ykey.replace('y','')}+ 发生率）")
    print(f"  {'区间':<14}{'n':>6}{'预测均值':>10}{'实际':>9}{'偏差':>9}")
    for lo, hi in zip(bins[:-1], bins[1:]):
        seg = [r for r in rows if key in r and lo <= r[key] < hi]
        if len(seg) < 25:
            continue
        ap = statistics.mean(r[key] for r in seg)
        ay = statistics.mean(r[ykey] for r in seg)
        print(f"  {lo:.2f}–{hi:<8.2f}{len(seg):6d}{ap*100:9.2f}%{ay*100:8.2f}%"
              f"{(ay-ap)*100:+8.2f}pp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true", help="只出今日评分")
    args = ap.parse_args()

    lib = load_lib()
    today = json.load(open(os.path.join(ROOT, "_calc_result.json"), encoding="utf-8"))["matches"]
    rows = hist_part(lib, verbose=not args.today)
    b6 = calib_fit(rows, "y6", "p6_mkt", verbose=not args.today) if rows else None

    if not args.today:
        n = len(rows)
        y6 = [r["y6"] for r in rows]
        y7 = [r["y7"] for r in rows]
        base6, base7 = statistics.mean(y6), statistics.mean(y7)
        print(f"\n=== A. 基础率（全量 {n} 场）===")
        print(f"  6+ : {sum(y6):4d} 场 = {base6*100:.2f}%   7+ : {sum(y7):4d} 场 = {base7*100:.2f}%")

        # 按日统计：每天至少一场 6+ 的概率 vs 理论
        byday = defaultdict(list)
        for r in rows:
            byday[r["date"]].append(r["y6"])
        days = sorted(byday)
        print(f"\n  按天（{days[0]} ~ {days[-1]}，{len(days)} 天）：")
        print(f"  {'每天场次':<12}{'天数':>6}{'有6+的天数':>12}{'实测占比':>10}{'理论(全量p)':>13}{'理论(近30天p)':>14}")
        buckets = [(1, 9), (10, 19), (20, 29), (30, 99)]
        last30 = days[-30:]
        p30 = statistics.mean(r["y6"] for r in rows if r["date"] >= last30[0])
        for lo, hi in buckets:
            ds = [d for d in days if lo <= len(byday[d]) <= hi]
            if not ds:
                continue
            hit = sum(1 for d in ds if any(byday[d]))
            nm = statistics.mean(len(byday[d]) for d in ds)
            th_all = 1 - (1 - base6) ** nm
            th_30 = 1 - (1 - p30) ** nm
            print(f"  {lo:>3}–{hi:<8}{len(ds):6d}{hit:12d}{hit/len(ds)*100:9.1f}%"
                  f"{th_all*100:12.1f}%{th_30*100:13.1f}%")

        print(f"\n=== B. 可预测性（只用有对应盘口的比赛）===")

        def evaluate(label, key, ykey, seg=None):
            seg = seg if seg is not None else [r for r in rows if key in r]
            if len(seg) < 200:
                return
            ps = [r[key] for r in seg]
            ys = [r[ykey] for r in seg]
            b = brier(ps, ys)
            baser = statistics.mean(ys)
            bb = brier([baser] * len(ys), ys)
            print(f"\n  ▸ {label}（n={len(seg)}）")
            print(f"    预测均值 {statistics.mean(ps)*100:.2f}%  实际 {baser*100:.2f}%  "
                  f"偏差 {(baser - statistics.mean(ps))*100:+.2f}pp")
            print(f"    Brier {b:.5f}   常数基线 {bb:.5f}   技巧分 {(1 - b / bb) * 100:+.2f}%")
            calib_table(seg, key, ykey)

        evaluate("① 市场总进球盘（6 档 + 7+ 档去水）", "p6_mkt", "y6")
        evaluate("② 市场总进球盘 7+ 档", "p7_mkt", "y7")
        evaluate("③ 市场比分盘（其他三档 = 6+）", "p6_sc", "y6")

        both = [r for r in rows if "p6_mkt" in r and "p6_sc" in r]
        if len(both) > 200:
            for r in both:
                r["p6_mix"] = (r["p6_mkt"] + r["p6_sc"]) / 2
            evaluate("④ 双盘平均", "p6_mix", "y6", both)
            print("\n  ▸ 双盘分歧（比分盘 − 总进球盘）分档，看谁更准：")
            print(f"    {'分歧区间':<18}{'n':>6}{'比分盘':>10}{'总进球盘':>11}{'实际':>9}{'更准':>8}")
            for lo, hi in ((-9, -0.02), (-0.02, 0.0), (0.0, 0.02), (0.02, 0.05), (0.05, 9)):
                seg = [r for r in both if lo <= r["p6_sc"] - r["p6_mkt"] < hi]
                if len(seg) < 25:
                    continue
                a_sc = statistics.mean(r["p6_sc"] for r in seg)
                a_mk = statistics.mean(r["p6_mkt"] for r in seg)
                a_y = statistics.mean(r["y6"] for r in seg)
                closer = "比分盘" if abs(a_sc - a_y) < abs(a_mk - a_y) else "总进球盘"
                print(f"    {lo:+.2f} ~ {hi:+.2f}{'':<6}{len(seg):6d}{a_sc*100:9.2f}%"
                      f"{a_mk*100:10.2f}%{a_y*100:8.2f}%{closer:>8}")
            # 若两个市场互相验证过（分歧小）时是否更准
            print("\n  ▸ 按 |分歧| 分组：")
            for lab, f in (("|分歧|≤1pp（两盘一致）", lambda x: abs(x) <= 0.01),
                           ("1~3pp", lambda x: 0.01 < abs(x) <= 0.03),
                           (">3pp（两盘打架）", lambda x: abs(x) > 0.03)):
                seg = [r for r in both if f(r["p6_sc"] - r["p6_mkt"])]
                if len(seg) < 25:
                    continue
                print(f"    {lab:<22} n={len(seg):5d}  预测均值 "
                      f"{statistics.mean(r['p6_mix'] for r in seg)*100:5.2f}%  "
                      f"实际 {statistics.mean(r['y6'] for r in seg)*100:5.2f}%  "
                      f"偏差 {(statistics.mean(r['y6'] for r in seg)-statistics.mean(r['p6_mix'] for r in seg))*100:+.2f}pp")

        # 时间趋势
        print(f"\n  逐月 6+ 发生率：")
        bym = defaultdict(list)
        for r in rows:
            bym[r["date"][:7]].append(r)
        for mth in sorted(bym):
            seg = bym[mth]
            print(f"    {mth}  {len(seg):4d} 场  6+ {statistics.mean(r['y6'] for r in seg)*100:5.2f}%"
                  f"   7+ {statistics.mean(r['y7'] for r in seg)*100:5.2f}%")

        roi_part(rows)

        print(f"\n=== F. 高进球场次：按市场隐含 λ 分档（回答「哪类场次最像出 6+」）===")
        seg = [r for r in rows if "lam_mkt" in r]
        print(f"  {'市场隐含λ总':<16}{'n':>6}{'实际均值':>9}{'实际6+':>9}{'实际7+':>9}")
        for lo, hi in ((0, 2.2), (2.2, 2.6), (2.6, 3.0), (3.0, 3.4), (3.4, 3.8), (3.8, 99)):
            s = [r for r in seg if lo <= r["lam_mkt"] < hi]
            if len(s) < 30:
                continue
            print(f"  {lo:.1f}–{hi:<11}{len(s):6d}"
                  f"{statistics.mean(r['g'] for r in s):9.2f}"
                  f"{statistics.mean(r['y6'] for r in s)*100:8.2f}%"
                  f"{statistics.mean(r['y7'] for r in s)*100:8.2f}%")
        print()
        for th in (0.20, 0.25, 0.30, 0.35):
            s = [r for r in seg if r["p6_mkt"] >= th]
            if len(s) < 5:
                print(f"  市场 P(6+)≥{th:.0%}：仅 {len(s)} 场，样本不足（历史上市场很少给到这么高）")
                continue
            print(f"  市场 P(6+)≥{th:.0%}：n={len(s):4d}  实际 6+ "
                  f"{statistics.mean(r['y6'] for r in s)*100:5.1f}%  7+ "
                  f"{statistics.mean(r['y7'] for r in s)*100:5.1f}%  "
                  f"平均总进球 {statistics.mean(r['g'] for r in s):.2f}")

    # ---------------------------------------------------------------- C 今日
    print(f"\n=== C. 今日 {len(today)} 场：大比分（6+/7+）潜力排序 ===")
    out = []
    for m in today:
        rec = {"num": m["matchNumStr"], "home": m["home"], "away": m["away"],
               "league": m["league"], "lam_tot": m.get("lam_total")}
        if m.get("lam_home") and m.get("lam_away"):
            rec["p6_model"] = poisson_total_ge(6, m["lam_home"], m["lam_away"])
            rec["p7_model"] = poisson_total_ge(7, m["lam_home"], m["lam_away"])
        sc = m.get("top_scores") or []
        rec["m_top"] = " ".join(x["score"] for x in sc[:5])
        o = m.get("odds") or {}
        tot = o.get("总进球")
        if isinstance(tot, list) and tot:
            tot = tot[0]
        dt = devig_totals(tot) if isinstance(tot, dict) else None
        if dt:
            rec["p6_mkt"] = dt[0]["6"] + dt[0]["7+"]
            rec["p7_mkt"] = dt[0]["7+"]
            rec["lam_mkt"] = sum((7 if k == "7+" else int(k)) * p for k, p in dt[0].items())
            rec["or_tot"] = dt[1]
            rec["odd6"] = tot.get("6")
            rec["odd7"] = tot.get("7+")
            rec["p6_raw"] = 1.0 / float(tot["6"]) if _f(tot.get("6")) else None
            rec["p7_raw"] = 1.0 / float(tot["7+"]) if _f(tot.get("7+")) else None
        ds = devig_scores(o.get("比分")) if isinstance(o.get("比分"), dict) else None
        if ds:
            rec["p6_sc"] = score_dist_ge6(ds[0], 1.0)
            rec["p6_sc055"] = score_dist_ge6(ds[0], 0.55)
        out.append(rec)

    out.sort(key=lambda r: -(r.get("p6_mkt", r.get("p6_model", 0))))
    b7 = calib_fit(rows, "y7", "p7_mkt", verbose=False) if rows else None
    for r in out:
        if "p6_mkt" in r and b6:
            r["p6_cal"] = _sig(b6[0] + b6[1] * _logit(r["p6_mkt"]))
        if "p7_mkt" in r and b7:
            r["p7_cal"] = _sig(b7[0] + b7[1] * _logit(r["p7_mkt"]))
        if r.get("p6_cal") is not None and r.get("p7_cal") is not None:
            r["p_eq6"] = max(r["p6_cal"] - r["p7_cal"], 1e-6)
            if r.get("odd6"):
                r["ev6"] = r["p_eq6"] * float(r["odd6"])
            if r.get("odd7"):
                r["ev7"] = r["p7_cal"] * float(r["odd7"])
    out.sort(key=lambda r: -r.get("p6_cal", 0))

    print(f"  {'编号':<8}{'对阵':<24}{'联赛':<7}{'市场P6+':>9}{'校准P6+':>9}{'校准P7+':>9}"
          f"{'6档':>7}{'7+档':>7}{'EV(6)':>8}{'EV(7+)':>8}{'模型P6+':>9}")
    print("  " + "-" * 106)
    for r in out:
        vs = f"{r['home']}vs{r['away']}"
        ev6 = f"{r['ev6']:.2f}" if r.get("ev6") else "-"
        ev7 = f"{r['ev7']:.2f}" if r.get("ev7") else "-"
        print(f"  {r['num']:<8}{vs[:22]:<24}{(r['league'] or '')[:5]:<7}"
              f"{r.get('p6_mkt',0)*100:8.2f}%{r.get('p6_cal',0)*100:8.2f}%"
              f"{r.get('p7_cal',0)*100:8.2f}%{str(r.get('odd6','-')):>7}"
              f"{str(r.get('odd7','-')):>7}{ev6:>8}{ev7:>8}"
              f"{r.get('p6_model',0)*100:8.2f}%")
    print("\n  逐场明细：")
    for r in out:
        print(f"\n  {r['num']} {r['home']} vs {r['away']}（{r['league']}）")
        if "odd6" in r:
            print(f"    市场总进球盘：6 @{r['odd6']}  7+ @{r['odd7']}  水位 {r['or_tot']:.3f}"
                  f"  → 市场隐含 P(6+)={r['p6_mkt']*100:.2f}%（校准后 {r.get('p6_cal',0)*100:.2f}%）"
                  f"  隐含期望 λ≈{r['lam_mkt']:.2f}")
        print(f"    模型：λ总 {r.get('lam_tot')} → P(6+)={r.get('p6_model',0)*100:.2f}%"
              f"  P(7+)={r.get('p7_model',0)*100:.2f}%   比分组 Top5: {r['m_top']}")
        if r.get("ev6"):
            print(f"    下注检验：买 6 球档 EV={r['ev6']:.2f}  买 7+ 档 EV={r['ev7']:.2f}"
                  f"（>1 才有价值；历史同档 ROI 见 D 段）")
    print(f"\n  ★ 最像出 6+ 的三场：" + "、".join(
        f"{r['num']} {r['home']}vs{r['away']}(校准 {r.get('p6_cal',0)*100:.1f}%)" for r in out[:3]))
    tot_exp = sum(r.get("p6_cal", 0) for r in out)
    print(f"  ★ 今日 7 场「至少一场 6+」的概率 ≈ {1 - math.prod(1 - r.get('p6_cal', 0) for r in out):.1%}"
          f"（期望场次 {tot_exp:.2f} 场）")


if __name__ == "__main__":
    main()
