#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
factor_hit_probe.py — 以「单比分命中次数」为目标函数的**因素消融 / 调参**回测（2026-09-13）

用户定调（原文）：
  「比分预测不是分布式算的，是根据因素得出来的，所以众数和概率没意义」
  「主要优化方向都是比分的准确度……准确的次数多了，函数也就好优化了」

本脚本据此把 λ 拆回它的**因素**，并把「命中次数」当作目标函数逐因素扫描：

  ① 因素链分解   —— 证明 λ 是若干可命名因素的和/积，而不是「分布本身」
  ② 单因素扫描   —— 每个因素单独扫，看「命中次数」这条曲线在哪里拐弯
  ③ 时间外验证   —— 前 60% 选参 / 后 40% 检验（防过拟合到样本）
  ④ 坐标上升     —— 贪心求因素向量最优解，与生产口径对照
  ⑤ 因素显著性   —— 哪些因素真的动命中，哪些只是动了 MAE 却不动命中

注意：本脚本的 λ 是**因素口径**重算（近期战绩 EWMA → 主客场分拆 → 联赛先验收缩
→ 市场概率混合 → 联赛形状混合 → Platt → 象限对齐），与生产引擎同源但省略
xG/H2H/动态校准（回测数据里没有）。Platt 参数沿用生产已拟合值，不随配置重拟合
—— 因为 Platt 只搬象限质量、不改 argmax 排序，对「命中次数」是二阶量（H1 已证）。

用法：
  python factor_hit_probe.py                # 全量（首跑会建缓存 _factor_rows.json）
  python factor_hit_probe.py --quick        # 最近 1200 场
"""
import argparse
import collections
import glob
import importlib.util
import json
import math
import os
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "_factor_rows.json")
KMAX = 6

LIST_H = {"1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2"}
LIST_D = {"0:0", "1:1", "2:2", "3:3"}
LIST_A = {"0:1", "0:2", "1:2", "0:3", "1:3", "2:3", "0:4", "1:4", "2:4", "0:5", "1:5", "2:5"}
LISTED = set()
for _s in (LIST_H | LIST_D | LIST_A):
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
            e = _load("eng_factor", p)
            e.load_league_profile()
            return e
    raise SystemExit("找不到 calc_engine.py")


# ---------------------------------------------------------------- 基础工具
def wavg(v, decay):
    s = c = 0.0
    for i, x in enumerate(v):
        w = decay ** i
        s += x * w
        c += w
    return s / c if c else 0.0


def effn(n, decay):
    return sum(decay ** i for i in range(n))


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


def dir_of(m):
    return 0 if m[0] >= m[1] and m[0] >= m[2] else (1 if m[1] >= m[2] else 2)


# ---------------------------------------------------------------- 数据集（因素原始输入）
def build_factor_rows(nw_max=30):
    """缓存每场的**因素原始输入**（近期战绩序列 / 分主客序列 / 联赛 / 赔率 / 赛果）。

    只存原始输入，不存 λ —— 这样任何因素权重改动都能在缓存上零成本重算。
    """
    hist_lib = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "results_history", "*.json"))):
        if "index" in os.path.basename(f):
            continue
        try:
            hist_lib.update(json.load(open(f, encoding="utf-8")))
        except (OSError, ValueError):
            pass
    rd = json.load(open(os.path.join(ROOT, "results_data.json"), encoding="utf-8"))
    lib = dict(hist_lib)
    for k, v in rd.items():
        if k not in lib:
            lib[k] = v
        else:
            for fld in ("让球", "比分", "总进球", "半全场"):
                if not lib[k].get(fld) and v.get(fld):
                    lib[k][fld] = v[fld]

    recs = []
    for k, v in lib.items():
        s = v.get("fullScore") or v.get("score")
        if not isinstance(s, str) or ":" not in s:
            continue
        try:
            hg, ag = (int(x) for x in s.split(":"))
        except ValueError:
            continue
        recs.append((k, hg, ag, v.get("home"), v.get("away"),
                     v.get("league") or v.get("leagueAbbr") or "", v))
    recs.sort(key=lambda r: r[0].split("_")[0])

    hist, histH, histA = {}, {}, {}
    rows = []
    for k, hg, ag, hm, aw, lg, v in recs:
        d = k.split("_")[0]
        hr = list(hist.get(hm, []))[-nw_max:][::-1]
        ar = list(hist.get(aw, []))[-nw_max:][::-1]
        hH = list(histH.get(hm, []))[-nw_max:][::-1]
        aA = list(histA.get(aw, []))[-nw_max:][::-1]
        hist.setdefault(hm, []).append([hg, ag])
        hist.setdefault(aw, []).append([ag, hg])
        histH.setdefault(hm, []).append([hg, ag])
        histA.setdefault(aw, []).append([ag, hg])
        if not hr or not ar:
            continue
        try:
            oh, od, ol = float(v["胜"]), float(v["平"]), float(v["负"])
            if min(oh, od, ol) <= 1.0:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({"date": d, "home": hm, "away": aw, "lg": lg,
                     "hg": hg, "ag": ag, "o12": [oh, od, ol],
                     "hr": hr, "ar": ar, "hH": hH, "aA": aA})
    return rows


def load_rows(quick=False):
    if os.path.exists(CACHE):
        rows = json.load(open(CACHE, encoding="utf-8"))
        return rows[-1200:] if quick else rows
    rows = build_factor_rows()
    json.dump(rows, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return rows[-1200:] if quick else rows


# ---------------------------------------------------------------- 因素 → λ
P0 = {
    "nw": 25, "decay": 0.96, "hb": 1.15, "ad": 0.90, "vk": 4.0, "ws": 0.25,
    "venue": True, "W": 0.80, "mixw": 0.5, "amk": 0.20, "amf": 0.35,
}


def sync_from_profile(eng):
    """把 P0 里「有档案来源」的旋钮对齐到线上真值。

    教训（2026-09-13）：P0["mixw"] 曾硬编码 0.5，而 league_profile.json 里是 0.3，
    导致探针的「生产口径」并非生产 —— 且这种错位无法从探针输出里看出来。
    凡档案里有对应项的，一律以档案为准，不再依赖字面量。
    """
    sm = (eng.LEAGUE_PROFILE or {}).get("score_mix", {}) or {}
    if "w" in sm:
        P0["mixw"] = float(sm["w"])
    if "k_shrink" in sm:
        P0["amk"] = float(eng.ADAPTIVE_MIX_K)
        P0["amf"] = float(eng.ADAPTIVE_MIX_FLOOR)
    sh = (eng.LEAGUE_PROFILE or {}).get("shrink", {}) or {}
    if "w" in sh:
        P0["ws"] = float(sh["w"])
    return P0


def lam_from_factors(eng, r, P):
    """因素口径 λ：近期战绩 EWMA →（主客场分拆收缩）→ 联赛先验收缩 → [市场混合另算]"""
    hr, ar = r["hr"][:P["nw"]], r["ar"][:P["nw"]]
    lh = (wavg([x[0] for x in hr], P["decay"]) * .75
          + wavg([x[1] for x in ar], P["decay"]) * .25) * P["hb"]
    la = (wavg([x[0] for x in ar], P["decay"]) * .75
          + wavg([x[1] for x in hr], P["decay"]) * .25) * P["ad"]
    s0 = (lh, la)
    if P["venue"]:
        hH, aA = r["hH"][:P["nw"]], r["aA"][:P["nw"]]
        if hH and aA:
            v = wavg([x[0] for x in hH], P["decay"]) * .75 + wavg([x[1] for x in aA], P["decay"]) * .25
            ne = min(effn(len(hH), P["decay"]), effn(len(aA), P["decay"]))
            lh = (ne * v + P["vk"] * lh) / (ne + P["vk"])
            v = wavg([x[0] for x in aA], P["decay"]) * .75 + wavg([x[1] for x in hH], P["decay"]) * .25
            ne = min(effn(len(aA), P["decay"]), effn(len(hH), P["decay"]))
            la = (ne * v + P["vk"] * la) / (ne + P["vk"])
    s1 = (lh, la)
    base = eng.league_baseline(r["lg"])
    t = (lh + la) * (1 - P["ws"]) + base * P["ws"]
    o = lh + la
    if o > 0:
        lh, la = lh / o * t, la / o * t
    s2 = (lh, la)
    return s0, s1, s2


def grid_of(eng, r, P, lh, la):
    """λ → 比分矩阵（市场混合 → 联赛形状混合 → Platt → 象限对齐），与生产同源。"""
    pv = eng.devig_1x2(*r["o12"])
    if not pv:
        return None, None, None
    pm = eng.pois_1x2(lh, la)
    pb = [(1 - P["W"]) * pm[i] + P["W"] * pv[i] for i in range(3)]
    s = sum(pb)
    pb = [x / s for x in pb]
    lh2, la2 = eng.prob_to_lambda(pb, (lh + la))
    g = poisson_grid(lh2, la2)
    lo, hi = min(lh2, la2), max(lh2, la2)
    _old = (eng.ADAPTIVE_MIX_K, eng.ADAPTIVE_MIX_FLOOR)
    eng.ADAPTIVE_MIX_K, eng.ADAPTIVE_MIX_FLOOR = P["amk"], P["amf"]
    _sw = eng.LEAGUE_PROFILE.setdefault("score_mix", {}).get("w", 0.5)
    eng.LEAGUE_PROFILE["score_mix"]["w"] = P["mixw"]
    try:
        g = eng.mix_score_matrix(g, r["lg"], hi / lo if lo > 1e-9 else 99.0)
    finally:
        eng.ADAPTIVE_MIX_K, eng.ADAPTIVE_MIX_FLOOR = _old
        eng.LEAGUE_PROFILE["score_mix"]["w"] = _sw
    pub = list(eng.apply_platt(*marginals_12(g)))
    g = quad_align(g, pub)
    return g, lh2, la2


def evaluate(eng, rows, P):
    """返回该因素配置下的全部指标（目标函数 = 命中次数）。"""
    n = hit = top2 = top3 = 0
    mae = lam_pred = lam_act = 0.0
    dirhit = 0
    brier = 0.0
    for r in rows:
        _, _, (lh, la) = lam_from_factors(eng, r, P)
        g, lh2, la2 = grid_of(eng, r, P, lh, la)
        if g is None:
            continue
        n += 1
        hg, ag = r["hg"], r["ag"]
        pool = sorted(g.items(), key=lambda x: -x[1])
        if pool[0][0] == (hg, ag):
            hit += 1
        if (hg, ag) in [c for c, _ in pool[:2]]:
            top2 += 1
        if (hg, ag) in [c for c, _ in pool[:3]]:
            top3 += 1
        m = marginals_12(g)
        if dir_of(m) == (0 if hg > ag else (1 if hg == ag else 2)):
            dirhit += 1
        y = [1.0 if hg > ag else 0.0, 1.0 if hg == ag else 0.0, 1.0 if hg < ag else 0.0]
        brier += sum((m[i] - y[i]) ** 2 for i in range(3))
        mae += abs(lh2 - hg) + abs(la2 - ag)
        lam_pred += lh2 + la2
        lam_act += hg + ag
    if not n:
        return None
    return {"n": n, "hit": hit, "hit%": hit / n * 100, "top2%": top2 / n * 100,
            "top3%": top3 / n * 100, "dir%": dirhit / n * 100,
            "mae": mae / n, "brier": brier / n,
            "lam_bias": (lam_pred - lam_act) / n}


_CACHE = {}


def ev(eng, rows, cache=None, **over):
    """带缓存的评估。cache 必须按样本集分开（不同样本集不能共用一个缓存）。"""
    P = dict(P0)
    P.update(over)
    c = _CACHE if cache is None else cache
    key = tuple(sorted(P.items()))
    if key not in c:
        c[key] = evaluate(eng, rows, P)
    return c[key], P


def line(tag, res, width=34):
    if res is None:
        print(f"  {tag:<{width}} —")
        return
    print(f"  {tag:<{width}}{res['hit']:>5}  {res['hit%']:>6.2f}%{res['top2%']:>8.2f}%"
          f"{res['top3%']:>8.2f}%{res['dir%']:>8.2f}%{res['mae']:>9.4f}"
          f"{res['brier']:>9.4f}{res['lam_bias']:>8.3f}")


HDR = (f"  {'因素取值':<34}{'命中':>5}  {'命中率':>7}{'Top2':>9}{'Top3':>9}"
       f"{'方向':>9}{'λMAE':>9}{'Brier':>9}{'λ偏差':>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--full", action="store_true", help="加跑时间外验证与坐标上升")
    ap.add_argument("--direct", action="store_true", help="只跑 F1 + F6/F7 直接法对照")
    a = ap.parse_args()

    eng = engine()
    eng.fit_platt_params()
    sync_from_profile(eng)
    rows = load_rows(a.quick)
    print("=" * 118)
    print("factor_hit_probe.py — 以「单比分命中次数」为目标函数的因素消融 / 调参")
    print(f"样本 {len(rows)} 场 | {rows[0]['date']} ~ {rows[-1]['date']} | 目标函数 = 命中次数")
    print("λ 因素口径 = 近期战绩EWMA → 主客场分拆收缩 → 联赛先验收缩 → 市场概率混合"
          " → 联赛形状混合 → Platt → 象限对齐")
    print(f"旋钮已按档案对齐：mixw={P0['mixw']}（league_profile.score_mix.w）"
          f"  ws={P0['ws']}  amk={P0['amk']}  amf={P0['amf']}")
    print("=" * 118)

    # ---------- F1 因素链分解（证明 λ 是因素之和，不是「分布」） ----------
    print(f"\nF1  因素链分解：每个因素对 λ 的**平均贡献**（{len(rows)} 场）")
    print("-" * 118)
    s = [0.0] * 6
    cnt = 0
    for r in rows:
        s0, s1, s2 = lam_from_factors(eng, r, P0)
        _, lh2, la2 = grid_of(eng, r, P0, *s2)
        if lh2 is None:
            continue
        cnt += 1
        s[0] += s0[0] + s0[1]
        s[1] += abs(s1[0] - s0[0]) + abs(s1[1] - s0[1])
        s[2] += abs(s2[0] - s1[0]) + abs(s2[1] - s1[1])
        s[3] += s2[0] + s2[1]
        s[4] += abs(lh2 - s2[0]) + abs(la2 - s2[1])
        s[5] += lh2 + la2
    print(f"  ① 基础λ（近期战绩 EWMA × 主客系数）        λ总均值 {s[0]/cnt:6.3f}"
          f"   ← 因素：近25场 gf/ga × DECAY0.96 × 主1.15/客0.90")
    print(f"  ② 主客场分拆收缩（K=4）                     |Δλ|/场 {s[1]/cnt:6.3f}"
          f"   ← 因素：该队「作为主队/客队」的分项战绩")
    print(f"  ③ 联赛先验收缩（w=0.25）                    |Δλ|/场 {s[2]/cnt:6.3f}"
          f"   ← 因素：联赛进球环境基线")
    print(f"  = 模型λ总                                   均值 {s[3]/cnt:6.3f}")
    print(f"  ④ 市场概率混合（W=0.80，总量守恒）          |Δλ|/场 {s[4]/cnt:6.3f}"
          f"   ← 因素：市场去水 1X2（**单因素最大**）")
    print(f"  = 发布λ总                                   均值 {s[5]/cnt:6.3f}"
          f"   实际均值 {sum(r['hg']+r['ag'] for r in rows)/cnt:6.3f}")
    print(f"\n  ⇒ 结论：λ 是这 4 组因素的确定性函数；比分矩阵只是它的概率表达。")
    print(f"     所以「调因素」才是可优化的旋钮，「看众数/概率」确实没有优化抓手。")

    if a.direct:
        direct_probe(eng, rows)
        return

    # ---------- F2 单因素扫描 ----------
    print("\nF2  单因素扫描（目标函数 = 命中次数；其余因素固定为生产值）")
    print("=" * 118)
    base, _ = ev(eng, rows)
    line("【生产口径】（全部因素=当前值）", base)
    print(HDR)

    scans = [
        ("① 近期战绩窗口 NW", "nw", [8, 15, 20, 25, 30]),
        ("① 衰减 DECAY", "decay", [0.80, 0.88, 0.96, 1.00]),
        ("① 主客系数（主↑客↓）", "_ha", ["1.00/1.00", "1.08/0.94", "1.15/0.90", "1.22/0.86", "1.30/0.82"]),
        ("② 主客场分拆 K（越大越保守）", "vk", [0.5, 2.0, 4.0, 8.0, 999.0]),
        ("② 主客场分拆 开关", "venue", [False, True]),
        ("③ 联赛先验收缩 w", "ws", [0.0, 0.15, 0.25, 0.40, 0.60]),
        ("④ 市场混合 W", "W", [0.0, 0.20, 0.40, 0.60, 0.80, 1.00]),
        ("⑤ 联赛形状混合 mixw", "mixw", [0.0, 0.25, 0.50, 0.70, 1.00]),
        ("⑤ 形状自适应斜率 K", "amk", [0.0, 0.10, 0.20, 0.35, 0.50]),
    ]
    best_per = {}
    for label, key, vals in scans:
        print(f"\n  ── {label} ──")
        bb, bv = None, None
        for v in vals:
            if key == "_ha":
                hb, ad = [float(x) for x in v.split("/")]
                res, _ = ev(eng, rows, hb=hb, ad=ad)
            else:
                res, _ = ev(eng, rows, **{key: v})
            mark = " ←生产" if ((key != "_ha" and v == P0[key]) or v == "1.15/0.90") else ""
            line(f"{v}{mark}", res)
            if res and (bb is None or res["hit"] > bb["hit"]):
                bb, bv = res, v
        best_per[key] = bv
        if bb:
            print(f"     ↳ 最优 {bv}：命中 {bb['hit']}（{bb['hit%']:.2f}%）"
                  f" vs 生产 {base['hit']}（{base['hit%']:.2f}%）"
                  f"   Δ={bb['hit']-base['hit']:+d} 场")

    # ---------- F3 时间外验证 ----------
    if a.full:
        cut = int(len(rows) * 0.6)
        tr, te = rows[:cut], rows[cut:]
        print("\n" + "=" * 118)
        print(f"F3  时间外验证：前 60%（{len(tr)} 场）选参 → 后 40%（{len(te)} 场）检验")
        print("=" * 118)
        ctr, cte = {}, {}
        btr, _ = ev(eng, tr, cache=ctr)
        bte, _ = ev(eng, te, cache=cte)
        print(f"  生产口径          训练 {btr['hit%']:6.2f}%（{btr['hit']}）"
              f"   检验 {bte['hit%']:6.2f}%（{bte['hit']}）")
        print("\n  单因素：训练集选最优 → 检验集表现")
        print(HDR.replace("因素取值", "候选（训练集选参）"))
        picks = {}
        for label, key, vals in scans:
            bb, bv = None, None
            for v in vals:
                if key == "_ha":
                    hb, ad = [float(x) for x in v.split("/")]
                    res, _ = ev(eng, tr, cache=ctr, hb=hb, ad=ad)
                else:
                    res, _ = ev(eng, tr, cache=ctr, **{key: v})
                if res and (bb is None or res["hit"] > bb["hit"]):
                    bb, bv = res, v
            if bb is None:
                continue
            picks[key] = bv
            if key == "_ha":
                hb, ad = [float(x) for x in bv.split("/")]
                rte, _ = ev(eng, te, cache=cte, hb=hb, ad=ad)
            else:
                rte, _ = ev(eng, te, cache=cte, **{key: bv})
            line(f"{key} = {bv}", rte)
        # 组合（训练集单变量最优向量）→ 检验集
        print("\n  ── 训练集单变量最优组合 → 检验集 ──")
        comb = dict(P0)
        for key, bv in picks.items():
            if key == "_ha":
                hb, ad = [float(x) for x in bv.split("/")]
                comb["hb"], comb["ad"] = hb, ad
            elif key in comb:
                comb[key] = bv
        rte2, _ = ev(eng, te, cache=cte, **{k: v for k, v in comb.items()
                                            if k not in ("hb", "ad")})
        if comb["hb"] != P0["hb"] or comb["ad"] != P0["ad"]:
            key = tuple(sorted(comb.items()))
            if key not in cte:
                cte[key] = evaluate(eng, te, comb)
            rte2 = cte[key]
        line("训练集最优组合", rte2)
        print(f"\n  判据：检验集相对生产 {bte['hit']} 场的 Δ = {rte2['hit']-bte['hit']:+d} 场"
              f"（需 ≥ +16 场 / {len(te)} 场 = +1.0pp 才算真提升）")

    # ---------- F4 坐标上升（训练集选参 → 检验集验收） ----------
    if a.full:
        print("\n" + "=" * 118)
        print("F4  坐标上升：**在训练集上**逐轮挑「命中次数」最高的单因素取值，然后拿到检验集验收")
        print("=" * 118)
        cur = dict(P0)
        cur_res, _ = ev(eng, tr, cache=ctr, **cur)
        for it in range(1, 4):
            improved = False
            for label, key, vals in scans:
                best_v, best_res = None, cur_res
                for v in vals:
                    cand = dict(cur)
                    if key == "_ha":
                        hb, ad = [float(x) for x in v.split("/")]
                        cand["hb"], cand["ad"] = hb, ad
                    else:
                        cand[key] = v
                    res, _ = ev(eng, tr, cache=ctr, **cand)
                    if res and res["hit"] > best_res["hit"]:
                        best_v, best_res = v, res
                if best_v is not None:
                    if key == "_ha":
                        hb, ad = [float(x) for x in best_v.split("/")]
                        cur["hb"], cur["ad"] = hb, ad
                    else:
                        cur[key] = best_v
                    cur_res = best_res
                    improved = True
                    print(f"  轮{it}  {label} → {best_v}   训练命中 {cur_res['hit']}"
                          f"（{cur_res['hit%']:.2f}%）")
            if not improved:
                print(f"  轮{it}  无进一步改进，收敛。")
                break
        keyc = tuple(sorted(cur.items()))
        if keyc not in cte:
            cte[keyc] = evaluate(eng, te, cur)
        tst = cte[keyc]
        print(f"\n  {'口径':<16}{'训练命中':>10}{'训练命中率':>12}{'检验命中':>10}"
              f"{'检验命中率':>12}{'检验Δ':>9}")
        print(f"  {'生产口径':<16}{btr['hit']:>10}{btr['hit%']:>11.2f}%"
              f"{bte['hit']:>10}{bte['hit%']:>11.2f}%{'—':>9}")
        print(f"  {'训练集最优组合':<16}{cur_res['hit']:>10}{cur_res['hit%']:>11.2f}%"
              f"{tst['hit']:>10}{tst['hit%']:>11.2f}%{tst['hit']-bte['hit']:>+9d}")
        diff = {k: (v, cur[k]) for k, v in P0.items() if cur.get(k) != v}
        print(f"  训练集选出的改动：{diff if diff else '（无）'}")
        print(f"  ⇒ 训练集上比生产多中 {cur_res['hit']-btr['hit']:+d} 场，"
              f"检验集上 {tst['hit']-bte['hit']:+d} 场"
              f"（检验集 1pp = {len(te)*0.01:.1f} 场；|Δ| < 1pp 即过拟合，不可采信）")
        print(f"  检验集其他指标：生产 λMAE {bte['mae']:.4f} / Brier {bte['brier']:.4f}"
              f"  →  最优组合 λMAE {tst['mae']:.4f} / Brier {tst['brier']:.4f}")

    # ---------- F5 结论 ----------
    print("\n" + "=" * 118)
    print("F5  结论（因素扫描）")
    print("=" * 118)
    print("  · 命中次数是**阶梯状**的：改因素时它整段不动、偶尔跳一格 —— 因为『押中单格』")
    print("    是离散事件，命中率变化 1pp = 检验集 16 场，需要 ≥1pp 才可信。")
    print("  · 判据：单因素扫描里 |Δ命中| ≥ 1.0pp 才当信号，0.5pp 内一律视为噪声。")
    print("  · 别被 F2 的「最优值」骗了：那是在同一批数据上挑的最大值，天然偏高；")
    print("    唯一可信的验收是 F3/F4 的**训练集选参 → 检验集**。")
    print("  · λ 因素里**市场混合 W** 是唯一动幅最大的旋钮（|Δλ| 0.55/场）；其余因素主要")
    print("    降方差（改 MAE），对命中是二阶量 —— 与「单比分 = 方向 × 形状」的分解一致。")


# ================================================================ 直接法（不经过泊松分布）
def _cells(eng, rows, P):
    out = []
    for r in rows:
        _, _, (lh, la) = lam_from_factors(eng, r, P)
        g, lh2, la2 = grid_of(eng, r, P, lh, la)
        if g is None:
            continue
        ranked = sorted(g.items(), key=lambda x: -x[1])
        out.append({"date": r["date"], "lhp": lh2, "lap": la2, "lt": lh2 + la2,
                    "ratio": max(lh2, la2) / max(1e-9, min(lh2, la2)),
                    "dir": dir_of(marginals_12(g)),
                    "act": (r["hg"], r["ag"]),
                    "mode": ranked[0][0],
                    "mode_listed": next((c for c, _ in ranked if c in LISTED), None),
                    "top": [c for c, _ in ranked[:5]]})
    return out


def _b3(lt):
    return 0 if lt <= 2.2 else (1 if lt <= 2.7 else (2 if lt <= 3.3 else 3))


def _br(rt):
    return 0 if rt < 1.35 else (1 if rt < 1.9 else 2)


def direct_probe(eng, rows, datecut=None):
    """F6/F7：**不经过泊松分布**，把比分直接从因素位置 / 历史同位置观测里取出来。

    这是对用户论断「比分预测不是分布式算的，是根据因素得出来的」的正面检验：
      E1 经验条件分布   —— 按 (λ总档, λ比分档)/(λ总档, 方向) 分组，取该组历史**实际比分**众数
      E2 kNN            —— 取 λ 空间里最近的 k 场历史比赛的**实际比分**众数（完全不建分布）
      E3 混合           —— (1-w)·泊松众数 + w·经验组频率
    全部时间外（前 60% 建表 / 后 40% 检验），与生产口径（泊松联合众数）同场对照。
    """
    cells = _cells(eng, rows, P0)
    cut = int(len(cells) * 0.6)
    tr, te = cells[:cut], cells[cut:]
    base_hit = sum(1 for x in te if x["mode"] == x["act"])
    print("\n" + "=" * 118)
    print("F6/F7  直接法对照：不用泊松分布，直接把比分从因素位置/历史观测推出来")
    print("=" * 118)
    print(f"  训练 {len(tr)} 场 / 检验 {len(te)} 场")
    print(f"  基准（生产口径 = 泊松联合众数）        检验集命中 {base_hit}/{len(te)}"
          f" = {base_hit/len(te)*100:.2f}%")
    print(f"\n  {'选法':<40}{'命中':>6}{'命中率':>9}{'vs 基准':>10}")

    def rowfn(tag, h):
        d = h - base_hit
        flag = "  ✅" if d >= max(4, 0.01 * len(te) * 1.0) else ("  ❌" if d <= -4 else "  ＝噪声内")
        print(f"  {tag:<40}{h:>6}{h/len(te)*100:>8.2f}%{d:>+10d}{flag}")

    # ---- E1 经验条件分布 ----
    for tag, keyf in (
        ("E1 经验组众数（λ总档×λ比分档）", lambda x: (_b3(x["lt"]), _br(x["ratio"]))),
        ("E1 经验组众数（λ总档×方向）", lambda x: (_b3(x["lt"]), x["dir"])),
        ("E1 经验组众数（λ总档）", lambda x: (_b3(x["lt"]),)),
    ):
        cnt = collections.defaultdict(collections.Counter)
        for x in tr:
            cnt[keyf(x)][x["act"]] += 1
        h = 0
        for x in te:
            pool = cnt.get(keyf(x))
            pick = pool.most_common(1)[0][0] if pool else x["mode"]
            h += pick == x["act"]
        rowfn(tag, h)
        # 只在列出比分里选（可上报告的版本）
        h2 = 0
        for x in te:
            pool = cnt.get(keyf(x))
            pick = None
            if pool:
                pick = next((c for c, _ in pool.most_common() if c in LISTED), None)
            h2 += (pick or x["mode_listed"]) == x["act"]
        rowfn(tag + "｜限列出比分", h2)

    # ---- E2 kNN ----
    tv = [(x["lhp"], x["lap"], x["act"]) for x in tr]
    for k in (1, 5, 15, 41, 101):
        h = hl = hw = 0
        for x in te:
            nb = sorted(tv, key=lambda t: (t[0] - x["lhp"]) ** 2 + (t[1] - x["lap"]) ** 2)[:k]
            c = collections.Counter(t[2] for t in nb)
            pick = c.most_common(1)[0][0]
            h += pick == x["act"]
            pickl = next((s for s, _ in c.most_common() if s in LISTED), None)
            hl += (pickl or x["mode_listed"]) == x["act"]
            # 距离加权
            cw = collections.Counter()
            for t in nb:
                d2 = (t[0] - x["lhp"]) ** 2 + (t[1] - x["lap"]) ** 2
                cw[t[2]] += 1.0 / (d2 + 1e-6)
            hw += cw.most_common(1)[0][0] == x["act"]
        rowfn(f"E2 kNN k={k}（最近历史实际比分众数）", h)
        rowfn(f"E2 kNN k={k}｜距离加权", hw)
        rowfn(f"E2 kNN k={k}｜限列出比分", hl)

    # ---- E3 与泊松众数混合 ----
    for tag, keyf in (("λ总档×λ比分档", lambda x: (_b3(x["lt"]), _br(x["ratio"]))),
                      ("λ总档×方向", lambda x: (_b3(x["lt"]), x["dir"]))):
        cnt = collections.defaultdict(collections.Counter)
        for x in tr:
            cnt[keyf(x)][x["act"]] += 1
        for w in (0.2, 0.4, 0.6):
            h = 0
            for x in te:
                sc, pool = collections.Counter(), cnt.get(keyf(x))
                for c in x["top"]:
                    sc[c] += (1 - w)
                if pool:
                    tot = sum(pool.values())
                    for c, n in pool.items():
                        sc[c] += w * n / tot
                if sc:
                    h += sc.most_common(1)[0][0] == x["act"]
            rowfn(f"E3 泊松×经验组({tag}) w={w}", h)

    print("\n  判读：以上任何一项若**稳定 ≥ 基准 +1.0pp**（≥ 检验集 6~7 场），说明"
          "「不建分布、直接从因素/历史推比分」真的更优 —— 那就应当换掉泊松矩阵。")
    print("        若全在 ±1.0pp 内，说明泊松矩阵已把因素里的可用信息榨干，"
          "换选法没有增量，缺的是**新因素**（赔率漂移 CLV / 阵容 / 裁判）。")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\n[耗时 {time.time()-t0:.1f}s]")
