#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
score_rule_probe.py — 单比分预测误差拆解 + 头条比分规则对照（2026-09-13）

背景：「不只是串关，单比分预测和实际赛果出入很大」。

本脚本在 1591 场（2026-01 ~ 09，带真实赛果 + 1X2 + 比分盘）样本上，用**生产口径**
（引擎 base_lam + 市场混合0.80 + 联赛分数形态混权 + Platt + 象限对齐）重建每场的比分矩阵，
回答四组问题（全部时间外，不调参拟合）：

  S1  误差拆解：单比分错在哪一环？方向错 / 总进球错 / 分配错，各占多少？
               → 给出 方向命中、总进球众数命中、方向正确前提下单比分命中 三层的乘积关系。
  S2  分布校准：模型给的比分概率 vs 实际出现频率，哪些格子系统性高/低估？
               （尤其看模型是不是把质量堆在 1:1 / 1:0 低比分格子上）
  S3  规则对照：头条比分该选哪个格子？含现状 R0（象限列出众数）与 6 种替代规则，
               以及「完美方向+完美总进球」的天花板（oracle）。
  S4  分档诊断：按 λ 水平 / 月份拆开，看单比分命中是否集中在某类场次，
               从而决定「哪些场次的单比分值得照抄」。

用法：
  python score_rule_probe.py            # 全量
  python score_rule_probe.py --quick    # 最近 1200 场
  python score_rule_probe.py --recent 60  # 只统计最近 60 天（看近期是否退化）
"""
import argparse
import collections
import importlib.util
import json
import math
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "_probe_rows_lamlevel.json")
KMAX = 9
LIST_H = {"1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2"}
LIST_D = {"0:0", "1:1", "2:2", "3:3"}
LIST_A = {"0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4", "0:5", "1:5", "2:5"}
LISTED = LIST_H | LIST_D | LIST_A


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
            e = _load("eng_scoreprobe", p)
            e.load_league_profile()
            return e
    raise SystemExit("找不到 calc_engine.py")


def _pmf(k, lam):
    if k >= KMAX:
        return 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def norm(d):
    t = sum(d.values())
    return d if t <= 0 else {k: v / t for k, v in d.items()}


def poisson_grid(lh, la):
    th = max(0.0, 1.0 - sum(_pmf(k, lh) for k in range(KMAX)))
    ta = max(0.0, 1.0 - sum(_pmf(k, la) for k in range(KMAX)))
    ph = [_pmf(k, lh) for k in range(KMAX)] + [th]
    pa = [_pmf(k, la) for k in range(KMAX)] + [ta]
    return norm({(h, a): ph[h] * pa[a] for h in range(KMAX + 1) for a in range(KMAX + 1)})


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


def bucket_of(h, a):
    s = "%d:%d" % (h, a)
    if s in LISTED:
        return s
    return "胜其他" if h > a else ("平其他" if h == a else "负其他")


def listed(c):
    return "%d:%d" % c in LISTED


def band_cells(c):
    """参考比分 c 的 ±1 球邻域（**去重后的格集合**）。

    注意：不能用 sum(g[max(0,h+dh)]) 的写法——当 h0 或 a0 为 0/1 时
    会被 max(0,·) 折叠成同一格而重复计数（实测会把 band 虚高到 123%~386%）。
    """
    h0, a0 = c
    return {(h, a) for h in range(max(0, h0 - 1), h0 + 2)
            for a in range(max(0, a0 - 1), a0 + 2)}


def band_mass(g, c):
    return sum(g.get(x, 0.0) for x in band_cells(c))


def bucket_probs(g):
    b = {}
    for (h, a), p in g.items():
        k = bucket_of(h, a)
        b[k] = b.get(k, 0.0) + p
    return b


def logloss(g, hg, ag):
    return -math.log(max(bucket_probs(g).get(bucket_of(hg, ag), 1e-9), 1e-9))


def dir_of(marg):
    return 0 if marg[0] >= marg[1] and marg[0] >= marg[2] else (1 if marg[1] >= marg[2] else 2)


def act_dir(h, a):
    return 0 if h > a else (1 if h == a else 2)


def in_quad(c, qi):
    h, a = c
    return (h > a) if qi == 0 else ((h == a) if qi == 1 else (h < a))


def tot_pmf(g):
    d = collections.Counter()
    for (h, a), p in g.items():
        d[h + a] += p
    return d


def total_mode(g):
    d = tot_pmf(g)
    return max(d.items(), key=lambda x: x[1])[0]


# ---------------- 头条比分规则 ----------------
def r0_quad_listed_mode(g, marg, lh=None, la=None):
    """现状：象限内「列出比分」概率最高者"""
    qi = dir_of(marg)
    pool = [(c, p) for c, p in g.items() if in_quad(c, qi) and listed(c)]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def r1_global_grid_mode(g, marg, lh=None, la=None):
    return max(g.items(), key=lambda x: x[1])[0]


def r2_quad_grid_mode(g, marg, lh=None, la=None):
    qi = dir_of(marg)
    pool = [(c, p) for c, p in g.items() if in_quad(c, qi)]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def r3_joint_dir_total(g, marg, lh=None, la=None):
    """(象限, 总进球众数) 联合条件下取该格最高概率 —— 但必须是列出比分"""
    qi = dir_of(marg)
    tmode = total_mode(g)
    pool = [(c, p) for c, p in g.items() if in_quad(c, qi) and c[0] + c[1] == tmode and listed(c)]
    if not pool:
        pool = [(c, p) for c, p in g.items() if in_quad(c, qi) and listed(c)]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def r4_quad_nearest_lambda(g, marg, lh=None, la=None):
    qi = dir_of(marg)
    pool = [(c, p) for c, p in g.items() if in_quad(c, qi) and listed(c)]
    if not pool:
        return None
    tot = sum(p for _, p in pool)
    th = sum(c[0] * p for c, p in pool) / tot
    ta = sum(c[1] * p for c, p in pool) / tot
    return min(pool, key=lambda x: (x[0][0] - th) ** 2 + (x[0][1] - ta) ** 2)[0]


def r5_quad_smoothed_mode(g, marg, lh=None, la=None):
    """相邻格平滑（±1 球邻域质量）后取象限内列出比分最大者 —— 抑制尖峰格（1:1/1:0）"""
    qi = dir_of(marg)
    pool = [(c, band_mass(g, c)) for c in g if in_quad(c, qi) and listed(c)]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def r6_quad_max_near(g, marg, lh=None, la=None):
    """象限内、使 P(该格±1球) 最大的列出比分 —— 最大化「参考比分」容错"""
    qi = dir_of(marg)
    pool = [(c, band_mass(g, c)) for c in g if in_quad(c, qi) and listed(c)]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def r7_round_lambda(g, marg, lh=None, la=None):
    """直接四舍五入 λ（强制落在预测象限内）"""
    if lh is None:
        return None
    qi = dir_of(marg)
    ch = (int(round(lh)), int(round(la)))
    if in_quad(ch, qi) and listed(ch):
        return ch
    pool = [(c, p) for c, p in g.items() if in_quad(c, qi) and listed(c)]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def r8_quad_grid_mode_listed_or_nearest(g, marg, lh=None, la=None):
    """象限内**全网格**众数；若该格不在列出表，退回离它最近的列出比分"""
    qi = dir_of(marg)
    pool = [(c, p) for c, p in g.items() if in_quad(c, qi)]
    if not pool:
        return None
    mc = max(pool, key=lambda x: x[1])[0]
    if listed(mc):
        return mc
    lst = [(c, p) for c, p in pool if listed(c)]
    return min(lst, key=lambda x: abs(x[0][0] - mc[0]) + abs(x[0][1] - mc[1]))[0] if lst else None


RULES = {
    "R0 象限列出众数(现状)": r0_quad_listed_mode,
    "R1 全局网格众数": r1_global_grid_mode,
    "R2 象限全网格众数": r2_quad_grid_mode,
    "R3 象限+总进球众数": r3_joint_dir_total,
    "R4 象限内λ最接近": r4_quad_nearest_lambda,
    "R5 3x3平滑后众数": r5_quad_smoothed_mode,
    "R6 最大±1球覆盖": r6_quad_max_near,
    "R7 round(λ)": r7_round_lambda,
    "R8 网格众数→最近列出": r8_quad_grid_mode_listed_or_nearest,
}


def build_published(eng, rows, W, k=1.0):
    """按生产口径重建每场已发布比分矩阵，返回 [(row, g, marg, lh2, la2)]"""
    out = []
    for r in rows:
        lh, la = r["lam"]
        oh, od, ol = r["o12"]
        pv = eng.devig_1x2(oh, od, ol)
        if not pv:
            continue
        pm = eng.pois_1x2(lh, la)
        pb = [(1 - W) * pm[i] + W * pv[i] for i in range(3)]
        s = sum(pb)
        pb = [x / s for x in pb]
        lh2, la2 = eng.prob_to_lambda(pb, (lh + la) * k)
        g = poisson_grid(lh2, la2)
        lo, hi = min(lh2, la2), max(lh2, la2)
        g = eng.mix_score_matrix(g, r["lg"], hi / lo if lo > 1e-9 else 99.0)
        pub = list(eng.apply_platt(*marginals_12(g)))
        g = quad_align(g, pub)
        out.append((r, g, marginals_12(g), lh2, la2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--recent", type=int, default=0, help="只统计最近 N 天")
    args = ap.parse_args()

    eng = engine()
    eng.fit_platt_params()
    rows = json.load(open(CACHE, encoding="utf-8"))
    if args.recent:
        maxd = max(r["date"] for r in rows)
        import datetime
        cut = (datetime.date.fromisoformat(maxd) - datetime.timedelta(days=args.recent)).isoformat()
        rows = [r for r in rows if r["date"] >= cut]
    elif args.quick:
        rows = rows[-1200:]
    W = eng.MARKET_W

    data = build_published(eng, rows, W)
    n = len(data)
    print("=" * 104)
    print(f"score_rule_probe  |  生产口径重建 {n} 场  |  {data[0][0]['date']} ~ {data[-1][0]['date']}  |  MARKET_W={W}")
    print("=" * 104)

    # ---------------- S1 误差拆解 ----------------
    d_hit = t_hits = exact = 0
    dir_ok_exact = 0
    dsum = [0, 0]
    signed = [0, 0]
    tmode_ok = 0
    for r, g, marg, lh2, la2 in data:
        hg, ag = r["hg"], r["ag"]
        qi = dir_of(marg)
        dt = act_dir(hg, ag)
        tm = total_mode(g)
        if qi == dt:
            d_hit += 1
            if (hg, ag) == r0_quad_listed_mode(g, marg):
                dir_ok_exact += 1
        if tm == hg + ag:
            tmode_ok += 1
        pick = r0_quad_listed_mode(g, marg)
        if pick == (hg, ag):
            exact += 1
        dsum[0] += abs(hg - pick[0])
        dsum[1] += abs(ag - pick[1])
        signed[0] += pick[0] - hg
        signed[1] += pick[1] - ag

    print()
    print("S1  单比分误差拆解（现势头条 = 象限列出众数 R0）")
    print("-" * 104)
    print(f"  ① 方向命中率（胜/平/负）              {d_hit/n*100:6.1f}%   ({d_hit}/{n})")
    print(f"  ② 总进球众数命中率                    {tmode_ok/n*100:6.1f}%   ({tmode_ok}/{n})")
    print(f"  ③ 方向正确前提下，单比分命中           {dir_ok_exact/max(d_hit,1)*100:6.1f}%   ({dir_ok_exact}/{d_hit})")
    print(f"  ④ 无条件单比分命中（= ①×③）           {exact/n*100:6.1f}%   ({exact}/{n})")
    print(f"  ⑤ 平均偏差：主队进球 {signed[0]/n:+.3f} 球/场，客队进球 {signed[1]/n:+.3f} 球/场"
          f"  (正=模型偏高)")
    print(f"  ⑥ 平均绝对误差：|Δ主| {dsum[0]/n:.3f}  |Δ客| {dsum[1]/n:.3f}  "
          f"|Δ总| 约 {(dsum[0]+dsum[1])/n:.3f}")

    # ---------------- S2 分布校准 ----------------
    print()
    print("S2  比分格子校准：模型平均概率 vs 实际出现频率（列出比分，按模型概率降序前 14）")
    print("-" * 104)
    mp = collections.defaultdict(float)
    af = collections.defaultdict(float)
    for r, g, marg, lh2, la2 in data:
        for c, p in g.items():
            if listed(c):
                mp["%d:%d" % c] += p
        af["%d:%d" % (r["hg"], r["ag"])] += 1.0
    print(f"  {'比分':<8}{'模型概率':>10}{'实际频率':>10}{'差':>9}   {'柱状对比'}")
    for k_ in sorted(mp, key=lambda x: -mp[x])[:14]:
        m_, a_ = mp[k_] / n * 100, af[k_] / n * 100
        bar = "M" + "|" * int(round(m_)) + "  A" + "|" * int(round(a_))
        print(f"  {k_:<8}{m_:>9.2f}%{a_:>9.2f}%{m_-a_:>+9.2f}   {bar}")
    tpm = collections.Counter()
    taf = collections.Counter()
    for r, g, marg, lh2, la2 in data:
        for t, p in tot_pmf(g).items():
            tpm[t] += p
        taf[min(r["hg"] + r["ag"], 7)] += 1
    print()
    print(f"  {'总进球':<10}{'模型概率':>10}{'实际频率':>10}{'差':>9}")
    for t in range(8):
        lab = f"{t}" + ("+" if t == 7 else "")
        print(f"  {lab:<10}{tpm[t]/n*100:>9.2f}%{taf[t]/n*100:>9.2f}%{(tpm[t]-taf[t])/n*100:>+9.2f}")
    print(f"  {'合计≥3':<10}"
          f"{sum(tpm[t] for t in range(3,8))/n*100:>9.2f}%"
          f"{sum(taf[t] for t in range(3,8))/n*100:>9.2f}%"
          f"{(sum(tpm[t] for t in range(3,8))-sum(taf[t] for t in range(3,8)))/n*100:>+9.2f}")
    # 自评命中率：若模型分布为真，众数命中率 ≈ E[max p]；Σp² 为「模型自认的对角线概率」
    sum_p2 = 0.0
    sum_max = 0.0
    true_p = 0.0
    for r, g, marg, lh2, la2 in data:
        sum_p2 += sum(p * p for p in g.values())
        sum_max += max(g.values())
        true_p += g.get((r["hg"], r["ag"]), 0.0)
    print()
    print(f"  校准自检：模型自认众数概率均值 E[max p] = {sum_max/n*100:.2f}%  "
          f"| 实际单比分命中 = 15.4%  → 差 {15.4-sum_max/n*100:+.2f}pp")
    print(f"            「对角线概率」Σp² 均值 = {sum_p2/n*100:.2f}%   "
          f"| 模型给真实比分的平均概率 = {true_p/n*100:.2f}%")

    # ---------------- S3 规则对照 ----------------
    print()
    print("S3  头条比分规则对照（生产口径 k=1.0）")
    print("-" * 104)
    print(f"  {'规则':<26}{'单比分命中':>11}{'±1球实测':>11}{'±1球模型自评':>13}{'总进球命中':>11}{'方向命中':>10}{'比分总进球偏差':>16}")
    stats = {}
    for nm in RULES:
        stats[nm] = {"ex": 0, "near": 0, "dir": 0, "dt": 0.0, "dg": 0.0,
                     "band": 0.0, "dist": collections.Counter()}
    for r, g, marg, lh2, la2 in data:
        hg, ag = r["hg"], r["ag"]
        dt = act_dir(hg, ag)
        qi = dir_of(marg)
        for nm, fn in RULES.items():
            pick = fn(g, marg, lh2, la2)
            if pick is None:
                continue
            stats[nm]["dist"]["%d:%d" % pick] += 1
            if pick == (hg, ag):
                stats[nm]["ex"] += 1
            if abs(pick[0] - hg) <= 1 and abs(pick[1] - ag) <= 1:
                stats[nm]["near"] += 1
            if pick[0] + pick[1] == hg + ag:
                stats[nm]["dt"] += 1
            stats[nm]["dg"] += (pick[0] + pick[1]) - (hg + ag)
            stats[nm]["band"] += band_mass(g, pick)
            if qi == dt:
                stats[nm]["dir"] += 1
    for nm in RULES:
        s = stats[nm]
        print(f"  {nm:<26}{s['ex']/n*100:>10.1f}%{s['near']/n*100:>10.1f}%"
              f"{s['band']/n*100:>12.1f}%{s['dt']/n*100:>10.1f}%"
              f"{s['dir']/n*100:>9.1f}%{s['dg']/n:>+16.2f}")
    print("  注：「±1球模型自评」= 模型自己给出的 P(实际落在参考比分±1球内)；"
          "与实测列的差 = 该口径的过/欠自信度。")
    print()
    print("  各规则头条取值分布（前 5）：")
    for nm in RULES:
        top = " · ".join(f"{k} {v/n*100:.0f}%" for k, v in stats[nm]["dist"].most_common(5))
        print(f"    {nm:<26}{top}")

    # 双档（象限内 listing 概率前 2）命中
    d1 = d2 = d3 = 0
    for r, g, marg, lh2, la2 in data:
        hg, ag = r["hg"], r["ag"]
        qi = dir_of(marg)
        pool = sorted(((c, p) for c, p in g.items() if in_quad(c, qi) and listed(c)),
                      key=lambda x: -x[1])
        for i, (c, _) in enumerate(pool[:3], 1):
            if c == (hg, ag):
                if i == 1:
                    d1 += 1
                if i <= 2:
                    d2 += 1
                d3 += 1
    print()
    print(f"  象限内列出比分 Top1/双档/Top3 命中：{d1/n*100:.1f}% / {d2/n*100:.1f}% / {d3/n*100:.1f}%")

    # ---------------- S3b 目标函数扫描：精确概率 vs ±1 邻域 ----------------
    print()
    print("S3b  目标函数扫描：argmax[ P(格) + w·P(±1球邻域) ]（象限内列出比分）")
    print("-" * 104)
    print(f"  {'w':>6}{'单比分命中':>12}{'±1球命中':>11}{'比分总进球偏差':>16}{'头条取值(前4)':>40}")
    for w in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        ex = nr = 0
        dg = 0.0
        dist = collections.Counter()
        for r, g, marg, lh2, la2 in data:
            hg, ag = r["hg"], r["ag"]
            qi = dir_of(marg)
            best, bp = None, -1e18
            for c, p in g.items():
                if not (in_quad(c, qi) and listed(c)):
                    continue
                acc = p
                if w:
                    acc += w * band_mass(g, c)
                if acc > bp:
                    bp, best = acc, c
            if best is None:
                continue
            dist["%d:%d" % best] += 1
            if best == (hg, ag):
                ex += 1
            if abs(best[0] - hg) <= 1 and abs(best[1] - ag) <= 1:
                nr += 1
            dg += (best[0] + best[1]) - (hg + ag)
        top = " · ".join(f"{k} {v/n*100:.0f}%" for k, v in dist.most_common(4))
        print(f"  {w:>6.1f}{ex/n*100:>11.1f}%{nr/n*100:>10.1f}%{dg/n:>+16.2f}   {top}")

    # oracle 天花板
    o_dir = o_dir_tot = 0
    o_avg = 0.0
    for r, g, marg, lh2, la2 in data:
        hg, ag = r["hg"], r["ag"]
        dt = act_dir(hg, ag)
        pool = [(c, p) for c, p in g.items() if in_quad(c, dt) and listed(c)]
        if not pool:
            continue
        best = max(pool, key=lambda x: x[1])[0]
        o_dir += 1
        o_avg += g[(hg, ag)]
        pool2 = [(c, p) for c, p in pool if c[0] + c[1] == hg + ag]
        if pool2:
            o_dir_tot += 1
    print()
    print(f"  【天花板】已知真实方向、只在真实象限里取众数 → 单比分命中 {o_dir/n*100:.1f}%")
    print(f"  【绝对天花板】已知真实方向 + 真实总进球 → 该条件下最高概率格 = 真实比分 的比例 "
          f"{o_dir_tot/max(o_dir,1)*100:.1f}%")
    print(f"  【模型给真实比分的平均概率】{o_avg/n*100:.2f}%  ← 校准良好时 ≈ 真实命中率×100")

    # ---------------- S4 分档诊断 ----------------
    print()
    print("S4  分档诊断：单比分命中率（R0）按 λ 水平 / 月份")
    print("-" * 104)
    q = collections.defaultdict(lambda: {"n": 0, "ex": 0, "near": 0, "dir": 0, "dg": 0.0})
    for r, g, marg, lh2, la2 in data:
        hg, ag = r["hg"], r["ag"]
        lam_tot = lh2 + la2
        band = "λ≤2.3 低" if lam_tot <= 2.3 else ("2.3-3.0 中" if lam_tot <= 3.0 else ">3.0 高")
        pick = r0_quad_listed_mode(g, marg)
        for key in (band, r["date"][:7]):
            q[key]["n"] += 1
            q[key]["ex"] += 1 if pick == (hg, ag) else 0
            q[key]["near"] += 1 if abs(pick[0] - hg) <= 1 and abs(pick[1] - ag) <= 1 else 0
            q[key]["dir"] += 1 if dir_of(marg) == act_dir(hg, ag) else 0
            q[key]["dg"] += (pick[0] + pick[1]) - (hg + ag)
    print(f"  {'分组':<12}{'场次':>6}{'单比分':>9}{'±1球':>9}{'方向':>9}{'比分总进球偏差':>14}")
    for key in ("λ≤2.3 低", "2.3-3.0 中", ">3.0 高"):
        d = q[key]
        if d["n"]:
            print(f"  {key:<12}{d['n']:>6}{d['ex']/d['n']*100:>8.1f}%{d['near']/d['n']*100:>8.1f}%"
                  f"{d['dir']/d['n']*100:>8.1f}%{d['dg']/d['n']:>+14.2f}")
    print()
    for m in sorted(k for k in q if k.startswith("2026-")):
        d = q[m]
        print(f"  {m:<12}{d['n']:>6}{d['ex']/d['n']*100:>8.1f}%{d['near']/d['n']*100:>8.1f}%"
              f"{d['dir']/d['n']*100:>8.1f}%{d['dg']/d['n']:>+14.2f}")

    # ---------------- S5 联合分布离散度校准（温度 T） ----------------
    # 动机：S3 发现模型自评 ±1球覆盖 81.6% vs 实测 66.4%（过自信 15.2pp），
    # 说明 1X2/总进球边缘分布虽准，但**联合分布过于尖锐**（独立泊松低估实际方差）。
    # 用温度变换 g_T ∝ g^(1/T)（T>1 展平）检验能否在时间外改善比分 LogLoss 与覆盖校准。
    print()
    print("=" * 104)
    print("S5  联合分布离散度（温度）校准：g_T ∝ g^(1/T)，T>1 展平")
    print("-" * 104)
    cut = data[int(len(data) * 0.6)][0]["date"]
    print(f"  拟合集 = {data[0][0]['date']} ~ {cut}（前 60%）；测试集 = {cut} 之后（后 40%，时间外）")
    print(f"  {'T':>6}{'拟合LL':>10}{'拟合Top1':>10}{'拟合band自评':>14}"
          f"{'测试LL':>10}{'测试Top1':>10}{'测试±1实测':>12}{'测试band自评':>14}{'测试Δ总':>10}")
    for T in (1.0, 1.02, 1.05, 1.08, 1.12, 1.20, 1.35):
        st = {"f_ll": 0.0, "f_top": 0.0, "f_band": 0.0,
              "t_ll": 0.0, "t_top": 0.0, "t_near": 0.0, "t_band": 0.0, "t_dg": 0.0}
        for r, g, marg, lh2, la2 in data:
            gt = g if T == 1.0 else norm({c: (p ** (1.0 / T)) for c, p in g.items() if p > 0})
            hg, ag = r["hg"], r["ag"]
            qi = dir_of(marginals_12(gt))
            pool = [(c, p) for c, p in gt.items() if in_quad(c, qi) and listed(c)]
            pick = max(pool, key=lambda x: x[1])[0] if pool else None
            if pick is None:
                continue
            band = band_mass(gt, pick) * 100
            if r["date"] < cut:
                st["f_ll"] += logloss(gt, hg, ag)
                st["f_top"] += 1 if pick == (hg, ag) else 0
                st["f_band"] += band
            else:
                st["t_ll"] += logloss(gt, hg, ag)
                st["t_top"] += 1 if pick == (hg, ag) else 0
                st["t_near"] += 100 if abs(pick[0] - hg) <= 1 and abs(pick[1] - ag) <= 1 else 0
                st["t_band"] += band
                st["t_dg"] += (pick[0] + pick[1]) - (hg + ag)
        n0 = sum(1 for r in data if r[0]["date"] < cut)
        n1 = len(data) - n0
        print(f"  {T:>6.2f}{st['f_ll']/n0:>10.4f}{st['f_top']/n0*100:>9.1f}%{st['f_band']/n0:>13.1f}%"
              f"{st['t_ll']/n1:>10.4f}{st['t_top']/n1*100:>9.1f}%{st['t_near']/n1:>11.1f}%"
              f"{st['t_band']/n1:>13.1f}%{st['t_dg']/n1:>+10.2f}")
    print("  判读：若测试集 LL 随 T 单调变差，说明联合分布并不偏尖锐，保持 T=1（现状）。")


if __name__ == "__main__":
    main()
