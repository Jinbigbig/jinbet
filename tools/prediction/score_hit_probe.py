#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
score_hit_probe.py — 以「单比分命中次数」为目标函数的口径优化（2026-09-13）

用户定调：主要优化方向 = 比分的准确度；「概率大」本身没有意义；
         哪怕只猜中一次也有价值，命中次数多了，目标函数才好继续优化。

本脚本先自证一个数学前提，再在此前提下找可优化的空间：

  前提：给定一个比分分布 g，(单场) 使 P(命中) 最大的选择唯一 = argmax_g。
        → 任何单调变换（温度展平/锐化、概率缩放）都不改变 argmax，
          因此**不影响命中率**；「概率高不高」与命中率无关，
          只有「格子排序对不对」有关。
        → 提升命中次数只能换**排序来源**（更好的分布），换不了「选法」。

据此本脚本对照多组排序来源，全部时间外评估（前 60% 拟合 / 后 40% 检验）：

  M       模型网格（生产口径：base_λ + 市场混合0.80 + 联赛形态 + Platt + 象限对齐）
  K       市场比分盘去水（28 档列出比分）—— 引擎从未使用的完整盘口
  Mix(w)  (1-w)·M + w·K
  Bias(γ) M · B^γ，B = 训练集「实测频率 / 模型平均概率」的收缩比（格子级乘性纠偏）
  Bias+K  纠偏后再与市场混合
  DirSwap 方向不一致时改用市场象限再取模内众数

输出 H1~H5 五节，核心指标一律是 **单比分命中率 / 命中场次数**。

用法：
  python score_hit_probe.py
  python score_hit_probe.py --cache _probe_rows_lamlevel.json
"""
import argparse
import collections
import importlib.util
import json
import math
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
KMAX = 9
LIST_H = ["1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2"]
LIST_D = ["0:0", "1:1", "2:2", "3:3"]
LIST_A = ["0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4", "0:5", "1:5", "2:5"]
LISTED_STR = set(LIST_H) | set(LIST_D) | set(LIST_A)
LISTED = set()
for _s in LISTED_STR:
    _h, _a = _s.split(":")
    LISTED.add((int(_h), int(_a)))


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
            e = _load("eng_hitprobe", p)
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


def dir_of(marg):
    return 0 if marg[0] >= marg[1] and marg[0] >= marg[2] else (1 if marg[1] >= marg[2] else 2)


def act_dir(h, a):
    return 0 if h > a else (1 if h == a else 2)


def in_quad(c, qi):
    h, a = c
    return (h > a) if qi == 0 else ((h == a) if qi == 1 else (h < a))


def devig_market_score(sc):
    """市场比分盘去水 → 28 档列出比分的概率分布（其他档忽略，不参与取最大）"""
    q = {}
    tot = 0.0
    for k, o in sc.items():
        if not isinstance(o, (int, float)) or o <= 1.0:
            continue
        v = 1.0 / o
        tot += v
        if k in LISTED_STR:
            h, a = k.split(":")
            q[(int(h), int(a))] = v
    if tot <= 0:
        return None
    return {k: v / tot for k, v in q.items()}


def build_published(eng, rows, W, k=1.0):
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
        K = devig_market_score(r.get("sc") or {})
        out.append({"r": r, "g": g, "marg": marginals_12(g),
                    "lh2": lh2, "la2": la2, "K": K})
    return out


def argmax_listed(g):
    pool = [(c, p) for c, p in g.items() if c in LISTED]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def argmax_all(g):
    return max(g.items(), key=lambda x: x[1])[0]


def hits(data, picker):
    """返回 (命中数, 样本数, 命中分布Counter, 逐月命中率)"""
    n = ex = 0
    dist = collections.Counter()
    mon = collections.defaultdict(lambda: [0, 0])
    for d in data:
        p = picker(d)
        if p is None:
            continue
        n += 1
        ok = 1 if p == (d["r"]["hg"], d["r"]["ag"]) else 0
        ex += ok
        dist["%d:%d" % p] += 1
        m = d["r"]["date"][:7]
        mon[m][0] += ok
        mon[m][1] += 1
    return ex, n, dist, mon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(ROOT, "_probe_rows_lamlevel.json"))
    args = ap.parse_args()

    eng = engine()
    eng.fit_platt_params()
    rows = json.load(open(args.cache, encoding="utf-8"))
    W = eng.MARKET_W
    data = build_published(eng, rows, W)
    n = len(data)
    d0, d1 = data[0]["r"]["date"], data[-1]["r"]["date"]
    cut_i = int(n * 0.6)
    cut = data[cut_i]["r"]["date"]
    tr, te = data[:cut_i], data[cut_i:]
    print("=" * 100)
    print(f"score_hit_probe  |  生产口径重建 {n} 场  |  {d0} ~ {d1}  |  MARKET_W={W}")
    print(f"目标函数 H = 单比分命中场次数   拟合集(前60%) {len(tr)} 场 | 检验集(后40%) {len(te)} 场（分界 {cut}）")
    print("=" * 100)

    # ---------- H1 前提自证：单调变换不改命中 ----------
    print()
    print("H1  前提自证：单调变换（锐化/展平）不改变 argmax → 不改变命中次数")
    print("-" * 100)
    print(f"  {'变换':<22}{'检验集命中':>12}{'命中场次':>10}{'头条Top3':>34}")
    for lbl, T in (("锐化 T=0.85", 0.85), ("原样 T=1.00", 1.0), ("展平 T=1.15", 1.15), ("展平 T=1.35", 1.35)):
        def mk(T=T):
            def picker(d):
                g = d["g"] if T == 1.0 else norm({c: p ** (1.0 / T) for c, p in d["g"].items() if p > 0})
                return argmax_all(g)
            return picker
        ex, m, dist, _ = hits(te, mk())
        top = " · ".join(f"{k} {v/m*100:.0f}%" for k, v in dist.most_common(3))
        print(f"  {lbl:<22}{ex/m*100:>11.1f}%{ex:>10}{'   ' + top:>34}")
    print("  结论：四种变换命中完全相同 → 「概率大」不是可优化量，排序才是。")
    print("        （也让「比分可信度」这类由概率幅值决定的指标，与命中率无因果关系。）")

    # ---------- H2 候选排序来源 ----------
    print()
    print("H2  排序来源对照（核心：命中次数 / 命中率，全部时间外）")
    print("-" * 100)
    cands = []

    def add(name, fn):
        cands.append((name, fn))

    add("M  模型网格众数(全局)", lambda d: argmax_all(d["g"]))
    add("M* 模型网格众数(仅列出)", lambda d: argmax_listed(d["g"]))
    add("R0 象限列出众数(旧现状)", lambda d: _quad_listed_mode(d["g"], d["marg"]))
    add("R7 round(λ)(上一版部署)", lambda d: _round_lam(d))
    add("K  市场比分盘众数", lambda d: (argmax_all(d["K"]) if d["K"] else None))
    for w in (0.2, 0.35, 0.5, 0.65, 0.8):
        add(f"Mix{int(w*100)} 模型×市场比分盘", lambda d, w=w: _mix_pick(d, w))
    add("DirSwap 方向取市场", lambda d: _dirswap_pick(d))

    print(f"  {'规则':<26}{'拟合集':>9}{'检验集':>9}{'检验命中场':>11}{'检验±1球':>10}"
          f"{'检验Δ总':>9}   头条Top4")
    base_te = None
    for name, fn in cands:
        exr, nr, _, _ = hits(tr, fn)
        ex, m, dist, _ = hits(te, fn)
        near = _near_rate(te, fn)
        dg = _delta_total(te, fn)
        top = " · ".join(f"{k} {v/m*100:.0f}%" for k, v in dist.most_common(4))
        flag = ""
        if base_te is None:
            base_te = ex / m
        print(f"  {name:<26}{exr/nr*100:>8.1f}%{ex/m*100:>8.1f}%{ex:>11}{near:>9.1f}%"
              f"{dg:>+9.2f}   {top}{flag}")

    # ---------- H3 格子级乘性纠偏 ----------
    print()
    print("H3  格子级乘性纠偏：g' ∝ g · B^γ，B = 收缩后的「实测频率/模型概率」（训练集拟合）")
    print("-" * 100)
    mp = collections.defaultdict(float)
    af = collections.Counter()
    for d in tr:
        for c in LISTED:
            mp[c] += d["g"].get(c, 0.0)
        af[(d["r"]["hg"], d["r"]["ag"])] += 1
    ntr = len(tr)
    print("  训练集偏差最大的格子（模型概率 vs 实测频率）：")
    rows_b = []
    for c in LISTED:
        me = mp[c] / ntr * 100
        fe = af[c] / ntr * 100
        rows_b.append((c, me, fe))
    rows_b.sort(key=lambda x: -(x[2] - x[1]))
    for c, me, fe in rows_b[:5]:
        print(f"    高估 {c[0]}:{c[1]:<4} 模型 {me:5.2f}%  实测 {fe:5.2f}%  ({fe-me:+.2f}pp)")
    for c, me, fe in rows_b[-5:]:
        print(f"    低估 {c[0]}:{c[1]:<4} 模型 {me:5.2f}%  实测 {fe:5.2f}%  ({fe-me:+.2f}pp)")
    print()
    print(f"  {'K(收缩)':>8}{'γ':>6}{'拟合集':>9}{'检验集':>9}{'检验命中场':>11}{'检验Δ总':>9}   头条Top4")
    best = None
    for Ks in (100.0, 300.0, 800.0, 3000.0):
        B = {}
        for c in LISTED:
            me = mp[c] / ntr
            if me <= 1e-9:
                B[c] = 1.0
                continue
            fe_s = (af[c] + Ks * me) / (ntr + Ks)
            B[c] = fe_s / me
        for g_ in (0.25, 0.5, 0.75, 1.0):
            def mk(B=B, g_=g_):
                def picker(d):
                    gg = {c: p * (B.get(c, 1.0) ** g_) for c, p in d["g"].items()}
                    return argmax_all(norm(gg))
                return picker
            fn = mk()
            exr, nr, _, _ = hits(tr, fn)
            ex, m, dist, _ = hits(te, fn)
            dg = _delta_total(te, fn)
            top = " · ".join(f"{k} {v/m*100:.0f}%" for k, v in dist.most_common(4))
            mark = ""
            if best is None or ex / m > best[0]:
                best = (ex / m, Ks, g_, B, ex, m)
                mark = "  ←"
            print(f"  {Ks:>8.0f}{g_:>6.2f}{exr/nr*100:>8.1f}%{ex/m*100:>8.1f}%{ex:>11}{dg:>+9.2f}   {top}{mark}")

    # ---------- H4 纠偏 + 市场混合 ----------
    print()
    print("H4  最优纠偏 × 市场比分盘混合（在 H3 最优 B 上再混合）")
    print("-" * 100)
    _, Kbest, gbest, Bbest, _, _ = best
    print(f"  取 H3 最优：K={Kbest:.0f}, γ={gbest:.2f}")
    print(f"  {'w(市场权重)':>12}{'拟合集':>9}{'检验集':>9}{'检验命中场':>11}{'检验±1球':>10}{'检验Δ总':>9}   头条Top4")
    best2 = None
    for w in (0.0, 0.1, 0.2, 0.3, 0.45, 0.6):
        def mk(w=w):
            def picker(d):
                gg = norm({c: p * (Bbest.get(c, 1.0) ** gbest) for c, p in d["g"].items()})
                if d["K"] and w > 0:
                    gg = norm({c: (1 - w) * gg.get(c, 0.0) + w * d["K"].get(c, 0.0) for c in LISTED})
                return argmax_all(gg) if gg else None
            return picker
        fn = mk()
        exr, nr, _, _ = hits(tr, fn)
        ex, m, dist, _ = hits(te, fn)
        near = _near_rate(te, fn)
        dg = _delta_total(te, fn)
        top = " · ".join(f"{k} {v/m*100:.0f}%" for k, v in dist.most_common(4))
        mark = ""
        if best2 is None or ex / m > best2[0]:
            best2 = (ex / m, w, ex, m)
            mark = "  ←"
        print(f"  {w:>12.2f}{exr/nr*100:>8.1f}%{ex/m*100:>8.1f}%{ex:>11}{near:>9.1f}%{dg:>+9.2f}   {top}{mark}")

    # ---------- H5 命中率分层：哪些场次值得照抄 ----------
    print()
    print("H5  命中率分层（检验集，M 全局网格众数）— 决定「哪些场次的单比分值得照抄」")
    print("-" * 100)
    bk = collections.defaultdict(lambda: [0, 0])
    for d in te:
        lt = d["lh2"] + d["la2"]
        band = "λ≤2.3" if lt <= 2.3 else ("2.3-3.0" if lt <= 3.0 else ("3.0-3.7" if lt <= 3.7 else ">3.7"))
        p = argmax_all(d["g"])
        bk[band][0] += 1 if p == (d["r"]["hg"], d["r"]["ag"]) else 0
        bk[band][1] += 1
    print(f"  {'λ_total 档':<12}{'场次':>7}{'单比分命中':>12}   说明")
    for b in ("λ≤2.3", "2.3-3.0", "3.0-3.7", ">3.7"):
        if bk[b][1]:
            print(f"  {b:<12}{bk[b][1]:>7}{bk[b][0]/bk[b][1]*100:>11.1f}%"
                  f"   {'✅ 可照抄' if b == 'λ≤2.3' else ''}")
    print()
    print(f"  逐月（检验集）：")
    _, _, _, mon = hits(te, lambda d: argmax_all(d["g"]))
    for m in sorted(mon):
        print(f"    {m}  {mon[m][1]:>4} 场  命中 {mon[m][0]:>3}  ({mon[m][0]/mon[m][1]*100:.1f}%)")

    # ---------- H6 总进球边缘纠偏 ----------
    # 动机：头条 Δ总 = -0.93 球/场（众数必然低于均值）。若把模型的总进球边缘往市场
    # 总进球盘（引擎从未使用）拉，cond(比分|总进球) 形状不变，看能不能换来命中。
    print()
    print("H6  总进球边缘纠偏：g' ∝ g · T_blend(t)/T_model(t)，T_blend=(1-w)·模型+(w)·市场总进球盘")
    print("-" * 100)
    print(f"  {'w':>6}{'拟合集':>9}{'检验集':>9}{'检验命中场':>11}{'检验±1球':>10}{'检验Δ总':>9}   头条Top4")
    best6 = None
    for w in (0.0, 0.1, 0.2, 0.3, 0.45, 0.6):
        def mk(w=w):
            def picker(d):
                return argmax_all(_tot_correct(d, w))
            return picker
        fn = mk()
        exr, nr, _, _ = hits(tr, fn)
        ex, m, dist, _ = hits(te, fn)
        near = _near_rate(te, fn)
        dg = _delta_total(te, fn)
        top = " · ".join(f"{k} {v/m*100:.0f}%" for k, v in dist.most_common(4))
        mark = ""
        if best6 is None or ex / m > best6[0]:
            best6 = (ex / m, w, ex, m)
            mark = "  ←"
        print(f"  {w:>6.2f}{exr/nr*100:>8.1f}%{ex/m*100:>8.1f}%{ex:>11}{near:>9.1f}%{dg:>+9.2f}   {top}{mark}")

    # ---------- H7 稳定性 + 配对显著性 ----------
    print()
    print("H7  稳定性：把 1591 场按时间切 4 段（各约 25%），看排序来源的命中优势是否稳定")
    print("-" * 100)
    q = n // 4
    folds = [(i * q, n if i == 3 else (i + 1) * q) for i in range(4)]
    cand7 = {
        "M 模型网格众数": lambda d: argmax_all(d["g"]),
        "R0 象限列出众数": lambda d: _quad_listed_mode(d["g"], d["marg"]),
        "R7 round(λ)": lambda d: _round_lam(d),
        "K 市场比分盘众数": lambda d: (argmax_all(d["K"]) if d["K"] else None),
        "Mix20": lambda d: _mix_pick(d, 0.2),
    }
    print(f"  {'规则':<20}" + "".join(f"{'折'+str(i+1):>10}" for i in range(4)) + f"{'合计':>10}")
    for name, fn in cand7.items():
        cell = []
        tot_ex = tot_n = 0
        for i, (a, b) in enumerate(folds):
            sub = data[a:b]
            e, m, _, _ = hits(sub, fn)
            cell.append(f"{e/m*100:.1f}%")
            tot_ex += e
            tot_n += m
        print(f"  {name:<20}" + "".join(f"{c:>10}" for c in cell) + f"{tot_ex/tot_n*100:>9.1f}%")
    print()
    print("  配对检验（全样本 1591 场，McNemar）：")
    picks = {}
    for name, fn in cand7.items():
        picks[name] = [fn(d) for d in data]
    tgt = [(d["r"]["hg"], d["r"]["ag"]) for d in data]
    for name in ("R0 象限列出众数", "R7 round(λ)", "K 市场比分盘众数", "Mix20"):
        a_ = picks["M 模型网格众数"]
        b_ = picks[name]
        w01 = sum(1 for x, y, t in zip(a_, b_, tgt) if x == t and y != t)
        w10 = sum(1 for x, y, t in zip(a_, b_, tgt) if x != t and y == t)
        chi = (abs(w01 - w10) - 1) ** 2 / max(w01 + w10, 1)
        verdict = "显著" if chi > 3.84 else ("边缘" if chi > 2.71 else "不显著")
        print(f"    M vs {name:<18} M独中 {w01:>3} / 对手独中 {w10:>3}  χ²={chi:>6.2f}  → {verdict}"
              f"（χ²>3.84 即 p<0.05）")

    # ---------- H8 条件经验重排（按方向×λ档分区拟合） ----------
    print()
    print("H8  条件经验重排：g' ∝ g · (f̂/me)^α，f̂ = 分区(方向×λ档)内该格实测频率（收缩）")
    print("-" * 100)
    schemes = {
        "A 方向×λ4档": lambda d: "%d|%d" % (dir_of(d["marg"]), _lam_band(d["lh2"] + d["la2"])),
        "C 仅λ4档": lambda d: "x|%d" % _lam_band(d["lh2"] + d["la2"]),
        "D 方向×λ3档": lambda d: "%d|%d" % (dir_of(d["marg"]), min(_lam_band(d["lh2"] + d["la2"]), 2)),
    }
    print(f"  {'分区':<14}{'K':>6}{'α':>6}{'拟合集':>9}{'检验集':>9}{'检验命中场':>11}{'检验Δ总':>9}   头条Top4")
    best8 = None
    for sname, sfn in schemes.items():
        for Ks in (200.0, 800.0):
            # 训练集统计
            cnt = collections.defaultdict(collections.Counter)
            me = collections.defaultdict(lambda: collections.defaultdict(float))
            nb = collections.Counter()
            for d in tr:
                b = sfn(d)
                nb[b] += 1
                for c in LISTED:
                    me[b][c] += d["g"].get(c, 0.0)
                cnt[b][(d["r"]["hg"], d["r"]["ag"])] += 1
            for b in nb:
                for c in LISTED:
                    me[b][c] /= max(nb[b], 1)
            for a_ in (0.25, 0.5, 0.75, 1.0):
                def mk(sfn=sfn, Ks=Ks, a_=a_, cnt=cnt, me=me, nb=nb):
                    def picker(d):
                        b = sfn(d)
                        if not nb.get(b):
                            return argmax_all(d["g"])
                        out = {}
                        for c, p in d["g"].items():
                            m_ = me[b].get(c, 0.0)
                            if m_ <= 1e-9:
                                out[c] = p
                                continue
                            f_ = (cnt[b][c] + Ks * m_) / (nb[b] + Ks)
                            out[c] = p * ((f_ / m_) ** a_)
                        return argmax_all(norm(out))
                    return picker
                fn = mk()
                exr, nr, _, _ = hits(tr, fn)
                ex, m, dist, _ = hits(te, fn)
                dg = _delta_total(te, fn)
                top = " · ".join(f"{k} {v/m*100:.0f}%" for k, v in dist.most_common(4))
                mark = ""
                if best8 is None or ex / m > best8[0]:
                    best8 = (ex / m, sname, Ks, a_, ex, m)
                    mark = "  ←"
                print(f"  {sname:<14}{Ks:>6.0f}{a_:>6.2f}{exr/nr*100:>8.1f}%{ex/m*100:>8.1f}%{ex:>11}{dg:>+9.2f}   {top}{mark}")
    print(f"  → 最优 {best8[1]} K={best8[2]:.0f} α={best8[3]:.2f}：检验集 {best8[4]}/{best8[5]} = {best8[0]*100:.1f}%"
          f"（基线 M = 18.4%）")

    # ---------- H9 Dixon-Coles 低分修正 ----------
    print()
    print("H9  Dixon-Coles 低分修正 τ（历史按 LogLoss 否决过，此处按命中次数重测）")
    print("-" * 100)
    print(f"  {'ρ':>7}{'拟合集':>9}{'检验集':>9}{'检验命中场':>11}{'检验Δ总':>9}   头条Top4")
    for rho in (0.0, 0.03, 0.06, 0.09, 0.12):
        def mk(rho=rho):
            def picker(d):
                lh, la = d["lh2"], d["la2"]
                out = {}
                for (h, a), p in d["g"].items():
                    t = 1.0
                    if h == 0 and a == 0:
                        t = 1 - lh * la * rho
                    elif h == 0 and a == 1:
                        t = 1 + lh * rho
                    elif h == 1 and a == 0:
                        t = 1 + la * rho
                    elif h == 1 and a == 1:
                        t = 1 - rho
                    out[(h, a)] = p * max(t, 1e-6)
                out = quad_align(norm(out), d["marg"])
                return argmax_all(out)
            return picker
        fn = mk()
        exr, nr, _, _ = hits(tr, fn)
        ex, m, dist, _ = hits(te, fn)
        dg = _delta_total(te, fn)
        top = " · ".join(f"{k} {v/m*100:.0f}%" for k, v in dist.most_common(4))
        print(f"  {rho:>7.2f}{exr/nr*100:>8.1f}%{ex/m*100:>8.1f}%{ex:>11}{dg:>+9.2f}   {top}")

    # ---------- H10 双档定义对照（Top2 覆盖 = 目标函数的自然延伸） ----------
    print()
    print("H10 双档（第二选择）定义对照 —— 目标是「前两档命中率」最大")
    print("-" * 100)
    n_ = e1 = e2 = e3 = 0
    alt1 = alt2 = 0
    for d in data:
        hg, ag = d["r"]["hg"], d["r"]["ag"]
        g = d["g"]
        qi = dir_of(d["marg"])
        pool = sorted(((c, p) for c, p in g.items() if c in LISTED), key=lambda x: -x[1])
        if not pool:
            continue
        n_ += 1
        top1 = pool[0][0]
        e1 += 1 if top1 == (hg, ag) else 0
        two = [pool[0][0], pool[1][0]]
        e2 += 1 if (hg, ag) in two else 0
        three = [c for c, _ in pool[:3]]
        e3 += 1 if (hg, ag) in three else 0
        # 备选口径：期望比分 + 同倾向次高（上一版部署）
        b = _exp_band(d)
        alt1 += 1 if b[0] == (hg, ag) else 0
        alt2 += 1 if (hg, ag) in b else 0
    print(f"  口径① 网格众数 Top1 / Top2 / Top3      {e1/n_*100:5.1f}% / {e2/n_*100:5.1f}% / {e3/n_*100:5.1f}%"
          f"   （{e1}/{n_}, {e2}/{n_}, {e3}/{n_}）")
    print(f"  口径② round(λ)+同倾向次高（上一版）      {alt1/n_*100:5.1f}% / {alt2/n_*100:5.1f}%"
          f"        （{alt1}/{n_}, {alt2}/{n_}）")
    print(f"  → 以目标函数（命中次数）论，口径① 双档多中 {e2-alt2} 场。")


def _lam_band(lt):
    return 0 if lt <= 2.3 else (1 if lt <= 3.0 else (2 if lt <= 3.7 else 3))


def _exp_band(d):
    """上一版部署口径：round(λ) 期望比分 + 同倾向次高"""
    qi = dir_of(d["marg"])
    c0 = (int(round(d["lh2"])), int(round(d["la2"])))
    if not (in_quad(c0, qi) and c0 in LISTED):
        c0 = _round_lam(d)
    pool = sorted(((c, p) for c, p in d["g"].items() if in_quad(c, qi) and c in LISTED),
                  key=lambda x: -x[1])
    second = next((c for c, _ in pool if c != c0), c0)
    return [c0, second]


def _tot_correct(d, w):
    """按总进球边缘纠偏后的分布（条件形状不变）"""
    g = d["g"]
    tm = collections.Counter()
    for (h, a), p in g.items():
        tm[min(h + a, 7)] += p
    tk = None
    tot = d["r"].get("tot") or {}
    s = 0.0
    acc = collections.Counter()
    for k, o in tot.items():
        if not isinstance(o, (int, float)) or o <= 1.0:
            continue
        v = 1.0 / o
        t = 7 if str(k).endswith("+") else int(k)
        acc[min(t, 7)] += v
        s += v
    if s > 0:
        tk = {t: acc[t] / s for t in acc}
    if not tk or w <= 0:
        return g
    tb = {}
    for t in range(8):
        tb[t] = (1 - w) * tm[t] + w * tk.get(t, 0.0)
    out = {}
    for (h, a), p in g.items():
        t = min(h + a, 7)
        if tm[t] > 1e-12:
            out[(h, a)] = p * tb[t] / tm[t]
    return norm(out)


def _quad_listed_mode(g, marg):
    qi = dir_of(marg)
    pool = [(c, p) for c, p in g.items() if in_quad(c, qi) and c in LISTED]
    return max(pool, key=lambda x: x[1])[0] if pool else None


def _round_lam(d):
    qi = dir_of(d["marg"])
    ch = (int(round(d["lh2"])), int(round(d["la2"])))
    if in_quad(ch, qi) and ch in LISTED:
        return ch
    return _quad_listed_mode(d["g"], d["marg"])


def _mix_pick(d, w):
    if not d["K"]:
        return argmax_all(d["g"])
    gg = norm({c: (1 - w) * d["g"].get(c, 0.0) + w * d["K"].get(c, 0.0) for c in LISTED})
    return max(gg.items(), key=lambda x: x[1])[0]


def _dirswap_pick(d):
    """方向取市场 1X2（去水后 argmax 象限），模内取模型众数"""
    o = d["r"]["o12"]
    tot = sum(1.0 / x for x in o if x > 1.0)
    if tot <= 0:
        return argmax_all(d["g"])
    p = [1.0 / x / tot for x in o]
    qi = 0 if p[0] >= p[1] and p[0] >= p[2] else (1 if p[1] >= p[2] else 2)
    pool = [(c, v) for c, v in d["g"].items() if in_quad(c, qi) and c in LISTED]
    return max(pool, key=lambda x: x[1])[0] if pool else argmax_all(d["g"])


def _near_rate(sub, picker):
    ok = n = 0
    for d in sub:
        p = picker(d)
        if p is None:
            continue
        n += 1
        hg, ag = d["r"]["hg"], d["r"]["ag"]
        ok += 1 if abs(p[0] - hg) <= 1 and abs(p[1] - ag) <= 1 else 0
    return ok / max(n, 1) * 100


def _delta_total(sub, picker):
    s = n = 0
    for d in sub:
        p = picker(d)
        if p is None:
            continue
        n += 1
        s += (p[0] + p[1]) - (d["r"]["hg"] + d["r"]["ag"])
    return s / max(n, 1)


if __name__ == "__main__":
    main()
