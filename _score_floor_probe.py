# -*- coding: utf-8 -*-
"""零封退化与「0封偏多」的成因-修复探针（2026-09-14）

现象：09-14 报告头条比分有 9/12 场是「某方 0 球」（75%），历史中位仅 12%。
已定位三个疑似成因，本探针在 4036 场因素集上逐个量化：
  ① λ 无单队下界（反解越界 → λ客 0.0002，P(0球)≈100%）
  ② 联赛基线小样本未收缩（亚冠精英 n=24 场均 1.292 球、37.5% 是 0:0）
  ③ 第六步「零封修正」按球队近期零封率把 0 球格概率最高放大到 1.2 倍
     —— 注意：该步**不在** factor_hit_probe 的链路里（即以往往的回测从未包含它），
        本探针把它补进链路，才能测出它的真实作用。

评价：单点命中 / ±1球 / Top2 / Top3 / 方向 / Brier / λ偏差
      + 头条「某方 0 球」占比 + 预测 P(至少一方 0 球) 均值 + 实际零封率。

用法：python _score_floor_probe.py
"""
import collections
import importlib.util
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _find(*names):
    """同名脚本在本地带 `_` 前缀、在 master tools/prediction/ 不带 —— 两个名字都试。"""
    for nm in names:
        p = os.path.join(ROOT, nm)
        if os.path.exists(p):
            return p
    return os.path.join(ROOT, names[0])


F = _load("fhp", _find("factor_hit_probe.py"))
eng = F.engine()
eng.fit_platt_params()
F.sync_from_profile(eng)

KMAX = 6
MAXT = eng.MAX_TOTAL
GLOBAL_MEAN = float((eng.LEAGUE_PROFILE.get("shrink", {}) or {}).get("fallback_mean", 2.83))
_RAW_ROWS = None


# ---------------------------------------------------------------- 求解器变体
def _scan(pb, total):
    """复刻引擎 prob_to_lambda 的一维扫描 + 细化（不夹紧，返回原始解与残差）。"""
    best, bl, n = None, 9.9, 180
    for i in range(1, n):
        lh = total * i / n
        la = total - lh
        if la <= 1e-6:
            break
        P = eng.pois_1x2(lh, la)
        e = (P[0] - pb[0]) ** 2 + (P[1] - pb[1]) ** 2 + (P[2] - pb[2]) ** 2
        if e < bl:
            bl, best = e, (lh, la)
    if best is None:
        return total / 2.0, total / 2.0, 9.9
    bh, step = best[0], total / n
    for k in range(-30, 31):
        lh = bh + k * step / 30.0
        la = total - lh
        if lh <= 0 or la <= 0:
            continue
        P = eng.pois_1x2(lh, la)
        e = (P[0] - pb[0]) ** 2 + (P[1] - pb[1]) ** 2 + (P[2] - pb[2]) ** 2
        if e < bl:
            bl, best = e, (lh, la)
    return best[0], best[1], bl


def _clamp_min(lh, la, total, ms):
    lo = min(ms, total * 0.35)
    if lh < lo:
        lh = lo
        la = max(total - lh, total * 0.05)
    if la < lo:
        la = lo
        lh = max(total - la, total * 0.05)
    return lh, la


def solve(pb, total, ms=0.0, lift=0.0):
    """ms=单队 λ 下界；lift=允许的总量上抬倍数（1.0=不许抬）。"""
    lh, la, _ = _scan(pb, total)
    if ms <= 0:
        return lh, la
    if min(lh, la) >= min(ms, total * 0.35) - 1e-9:
        return lh, la
    if lift > 1.0:
        cap = min(MAXT, total * lift)
        T = total
        while T < cap - 1e-9:
            T = min(T + 0.05, cap)
            h, a, _ = _scan(pb, T)
            if min(h, a) >= min(ms, T * 0.35) - 1e-9:
                return h, a
    return _clamp_min(lh, la, total, ms)


# ---------------------------------------------------------------- 零封修正变体
def zfac(rate, mode):
    r = rate if 0.0 <= rate <= 1.0 else 0.25
    if mode == "off":            # 中性
        return 1.0
    if mode == "inv":            # 反向：近期零封率越高 → 0 球格乘得越小
        return eng.ZF_FLOOR + (eng.ZF_CEIL - eng.ZF_FLOOR) * (
            1.0 / (1.0 + math.exp(-eng.ZF_K * (eng.ZF_MID - r))))
    if mode == "flat":           # 只保留削弱侧（上限 1.0）
        return min(1.0, eng.ZF_FLOOR + (eng.ZF_CEIL - eng.ZF_FLOOR) * (
            1.0 / (1.0 + math.exp(-eng.ZF_K * (r - eng.ZF_MID)))))
    return eng.ZF_FLOOR + (eng.ZF_CEIL - eng.ZF_FLOOR) * (
        1.0 / (1.0 + math.exp(-eng.ZF_K * (r - eng.ZF_MID))))   # 生产


def zero_rate(rec):
    if not rec:
        return 0.25
    return sum(1 for x in rec if x[0] == 0) / len(rec)


def pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def chain(r, P, lh, la, ms, lift, zmode):
    """生产同源链路：市场混合 → 反解(可夹紧) → 0球格修正 → 联赛形状 → Platt → 象限对齐。"""
    pv = eng.devig_1x2(*r["o12"])
    if not pv:
        return None, None, None
    pm = eng.pois_1x2(lh, la)
    pb = [(1 - P["W"]) * pm[i] + P["W"] * pv[i] for i in range(3)]
    s = sum(pb)
    pb = [x / s for x in pb]
    lh2, la2 = solve(pb, lh + la, ms, lift)
    f_h, f_a = zfac(zero_rate(r["hr"]), zmode), zfac(zero_rate(r["ar"]), zmode)
    g = {}
    for i in range(KMAX + 1):
        for j in range(KMAX + 1):
            p = pmf(i, lh2) * pmf(j, la2)
            if i == 0:
                p *= f_h
            if j == 0:
                p *= f_a
            g[(i, j)] = p
    t = sum(g.values())
    g = {k: v / t for k, v in g.items()}
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
    pub = list(eng.apply_platt(*F.marginals_12(g)))
    g = F.quad_align(g, pub)
    return g, lh2, la2


# ---------------------------------------------------------------- 变体定义
VARIANTS = [
    ("N0 旧生产",       dict(ms=0.00, lift=1.0, zmode="on",   k=0)),
    ("N1 新生产(全上)",  dict(ms=0.18, lift=1.0, zmode="flat", k=40)),
    ("N2 仅零封修正改",   dict(ms=0.00, lift=1.0, zmode="flat", k=0)),
    ("N3 仅λ下界",      dict(ms=0.18, lift=1.0, zmode="on",   k=0)),
    ("N4 仅基线收缩",    dict(ms=0.00, lift=1.0, zmode="on",   k=40)),
]
ORDER = [t for t, _ in VARIANTS]


def _bl_raw(league):
    """旧口径联赛基线（直接用档案 mean，不收缩）。"""
    prof = eng.LEAGUE_PROFILE.get("leagues", {})
    g = prof.get(league)
    if not g:
        for kk, vv in prof.items():
            if kk and league and (kk in league or league in kk):
                g = vv
                break
    if g and g.get("n", 0) >= eng.LEAGUE_PROFILE.get("shrink", {}).get("min_n", 12):
        return float(g.get("mean") or GLOBAL_MEAN)
    return GLOBAL_MEAN


def apply_baseline(eng, k):
    """k=0 → 旧口径（不收缩）；k>0 → 经验贝叶斯收缩（新口径，与引擎一致）。"""
    if not k:
        eng.league_baseline = _bl_raw
        return
    prof = eng.LEAGUE_PROFILE.get("leagues", {})

    def bl(league):
        g = prof.get(league)
        if not g:
            for kk, vv in prof.items():
                if kk and league and (kk in league or league in vv):
                    g = vv
                    break
        if not g:
            return GLOBAL_MEAN
        n = float(g.get("n", 0) or 0)
        mean = float(g.get("mean") or GLOBAL_MEAN)
        if n <= 0:
            return GLOBAL_MEAN
        return (n * mean + k * GLOBAL_MEAN) / (n + k)

    eng.league_baseline = bl


def main():
    global _ORIG_BL
    _ORIG_BL = eng.league_baseline
    rows = F.load_rows()
    P = dict(F.P0)
    print("=" * 132)
    print("_score_floor_probe.py — 零封退化 / 0封偏多 成因与修复对照（4036 场因素集）")
    print(f"样本 {len(rows)} 场 | {rows[0]['date']} ~ {rows[-1]['date']} | 全局基线均值={GLOBAL_MEAN} "
          f"| MAX_TOTAL={MAXT} | MARKET_W={P['W']}")
    print("=" * 132)

    # ---- 数据侧：基线与小样本联赛 ----
    prof = eng.LEAGUE_PROFILE.get("leagues", {})
    small = sorted([(v.get("n", 0), kk, v.get("mean", 0)) for kk, v in prof.items()])[:8]
    print("\n【小样本联赛基线（n 最小 8 个）】收缩后的取值")
    print(f"  {'联赛':<12}{'n':>5}{'原均值':>9}{'k=40':>9}{'k=25':>9}")
    for n, kk, mn in small:
        s40 = (n * mn + 40 * GLOBAL_MEAN) / (n + 40) if n else GLOBAL_MEAN
        s25 = (n * mn + 25 * GLOBAL_MEAN) / (n + 25) if n else GLOBAL_MEAN
        print(f"  {kk:<12}{n:>5}{mn:>9.3f}{s40:>9.3f}{s25:>9.3f}")

    # ---- 主循环 ----
    acc = {t: dict(n=0, hit=0, p1=0, t2=0, t3=0, dir=0, br=0.0, mae=0.0, lb=0.0,
                   zhs=0, pz=0.0, actz=0, deg=0, tot=0.0) for t in ORDER}
    deg_raw = 0
    for r in rows:
        y = 0 if r["hg"] > r["ag"] else (1 if r["hg"] == r["ag"] else 2)
        yv = [1.0 if y == k else 0.0 for k in range(3)]
        act = (r["hg"], r["ag"])
        actz = int(r["hg"] == 0 or r["ag"] == 0)
        for tag, cfg in VARIANTS:
            apply_baseline(eng, cfg["k"])
            _s0, _s1, s2 = F.lam_from_factors(eng, r, P)
            g, lh2, la2 = chain(r, P, s2[0], s2[1], cfg["ms"], cfg["lift"], cfg["zmode"])
            if g is None:
                continue
            m = F.marginals_12(g)
            pool = sorted(g.items(), key=lambda x: -x[1])
            d = acc[tag]
            d["n"] += 1
            d["hit"] += int(pool[0][0] == act)
            d["p1"] += int(abs(pool[0][0][0] - r["hg"]) <= 1 and abs(pool[0][0][1] - r["ag"]) <= 1)
            d["t2"] += int(act in [c for c, _ in pool[:2]])
            d["t3"] += int(act in [c for c, _ in pool[:3]])
            d["dir"] += int(F.dir_of(m) == y)
            d["br"] += sum((m[k] - yv[k]) ** 2 for k in range(3))
            d["mae"] += abs(lh2 - r["hg"]) + abs(la2 - r["ag"])
            d["lb"] += (lh2 + la2) - (r["hg"] + r["ag"])
            d["tot"] += lh2 + la2
            d["zhs"] += int(pool[0][0][0] == 0 or pool[0][0][1] == 0)
            d["pz"] += 1 - (1 - math.exp(-lh2)) * (1 - math.exp(-la2))
            d["actz"] += actz
            if tag == ORDER[0] and min(lh2, la2) < 0.05:
                deg_raw += 1
    apply_baseline(eng, 0)

    print(f"\n【退化 λ】生产口径下 min(λ)<0.05 的场次 = {deg_raw}/{len(rows)} = {deg_raw/len(rows)*100:.2f}%"
          f"（这些场次 P(某方0球)≈100%，是「0封」被高估的直接来源）")

    n = acc[ORDER[0]]["n"]
    print(f"\n【逐变体对照】样本 {n} 场   实际「某方 0 球」率 = {acc[ORDER[0]]['actz']/n*100:.1f}%")
    hdr = (f"  {'方案':<30}{'单点%':>7}{'±1球%':>7}{'Top2%':>7}{'Top3%':>7}{'方向%':>7}"
           f"{'Brier':>8}{'λ偏差':>7}{'λ总量':>7}{'头条0封%':>9}{'P(0封)均值':>11}")
    print(hdr)
    print("-" * 132)
    b0 = acc[ORDER[0]]
    for tag in ORDER:
        d = acc[tag]
        print(f"  {tag:<30}{d['hit']/n*100:>7.2f}{d['p1']/n*100:>7.2f}{d['t2']/n*100:>7.2f}"
              f"{d['t3']/n*100:>7.2f}{d['dir']/n*100:>7.2f}{d['br']/n:>8.4f}"
              f"{d['lb']/n:>+7.3f}{d['tot']/n:>7.3f}{d['zhs']/n*100:>9.1f}{d['pz']/n*100:>11.1f}")

    print("\n【相对 V0 的差值】（单点/±1球 命中场次差；Brier 差；头条0封率差）")
    for tag in ORDER[1:]:
        d = acc[tag]
        print(f"  {tag:<30} 单点 {d['hit']-b0['hit']:>+4d} 场 | ±1球 {d['p1']-b0['p1']:>+4d} 场 | "
              f"Brier {(d['br']-b0['br'])/n:>+8.5f} | 头条0封 {(d['zhs']-b0['zhs'])/n*100:>+5.1f}pp | "
              f"λ总量 {(d['tot']-b0['tot'])/n:>+6.3f}")

    json.dump({t: {k: v for k, v in acc[t].items()} for t in ORDER},
              open(os.path.join(ROOT, "_score_floor_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果已存 _score_floor_result.json")


if __name__ == "__main__":
    main()
