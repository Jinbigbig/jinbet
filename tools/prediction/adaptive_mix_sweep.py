# -*- coding: utf-8 -*-
"""混合权重 w 随强弱差自适应衰减 —— walk-forward 验证。

背景：第七步B 用联赛经验比分频率按 w=0.5 混合模型分布，整体提升 Top1/Brier，
      但对强弱悬殊场次会系统性稀释强队优势（周一005 利雅新月：纯泊松主胜 73.9%
      → 混合后 57.8%，市场隐含 79.2%）。

思路：w_eff = w0 * decay(λ比)，λ比 r = max(λh,λa)/min(λh,λa) ≥ 1。
      r 越大（强弱越悬殊）→ 混合权重越低 → 越信任模型自身的极端判断。

评估指标（walk-forward，前60%训练式观察/后40%验证）：
  1. 比分 Top1 命中率
  2. 比分矩阵 Brier
  3. 1X2 Brier（本次核心：关心胜平负是否被稀释）
  4. 按 λ 比分桶的「强队方向校准偏差」= 预测强队胜率均值 - 实际强队胜率
"""
import json
import math
import os
import importlib.util

BASE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "engine", os.path.join(BASE, "_calc_engine.py"))
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.load_league_profile()

W0 = 0.5
DECAY, W_SHRINK = 0.85, 0.25
GB = float(engine.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))

results = json.load(open(os.path.join(BASE, "results_data.json"), encoding="utf-8"))
matches = []
for k, v in results.items():
    try:
        h, a = (int(x) for x in v["fullScore"].split(":"))
    except Exception:
        continue
    matches.append({"date": k.split("_")[0], "home": v["home"], "away": v["away"],
                    "league": v.get("league") or v.get("leagueAbbr") or "",
                    "hg": h, "ag": a, "oh": v.get("胜"), "oa": v.get("负")})
matches.sort(key=lambda m: m["date"])

hist = {}


def wavg(vals):
    s = c = 0.0
    for i, v in enumerate(vals):
        w = DECAY ** i
        s += v * w
        c += w
    return s / c if c else 0.0


def lambdas(m):
    hr = hist.get(m["home"], [])[-10:]
    ar = hist.get(m["away"], [])[-10:]
    if not hr or not ar:
        return None
    h_gf, h_ga = wavg([x[1] for x in hr]), wavg([x[2] for x in hr])
    a_gf, a_ga = wavg([x[1] for x in ar]), wavg([x[2] for x in ar])
    lh = (h_gf * 0.75 + a_ga * 0.25) * engine.HOME_BOOST
    la = (a_gf * 0.75 + h_ga * 0.25) * engine.AWAY_DISCOUNT
    lg = engine.LEAGUE_PROFILE["leagues"].get(m["league"])
    base = lg["mean"] if (lg and lg.get("n", 0) >= 12) else GB
    tot = (lh + la) * (1 - W_SHRINK) + base * W_SHRINK
    old = lh + la
    if old > 0:
        lh, la = lh / old * tot, la / old * tot
    if m["oh"] and m["oa"]:
        try:
            mh, ma = 1 / float(m["oh"]) * 2.5, 1 / float(m["oa"]) * 2.5
            lh, la = 0.65 * lh + 0.35 * mh, 0.65 * la + 0.35 * ma
        except (ValueError, ZeroDivisionError):
            pass
    return lh, la


def pois_grid(lh, la, kmax=6):
    return {(h, a): math.exp(-lh) * lh ** h / math.factorial(h) *
            math.exp(-la) * la ** a / math.factorial(a)
            for h in range(kmax + 1) for a in range(kmax + 1)}


def mix(g0, freq, w):
    gm = {k: (1 - w) * v + w * freq.get(k, 0.0) for k, v in g0.items()}
    t = sum(gm.values())
    return {k: v / t for k, v in gm.items()} if t > 0 else g0


def quad(g0, freq, w):
    """象限守恒混合：先按 w 混合取经验『形状』，再把三个象限(主胜/平/负)的总概率
    重新标定回模型 g0 的原始值——只借形状，不借强弱方向。"""
    gm = mix(g0, freq, w)
    q0 = [sum(v for (h, a), v in g0.items() if h > a),
          sum(v for (h, a), v in g0.items() if h == a),
          sum(v for (h, a), v in g0.items() if h < a)]
    qm = [sum(v for (h, a), v in gm.items() if h > a),
          sum(v for (h, a), v in gm.items() if h == a),
          sum(v for (h, a), v in gm.items() if h < a)]
    out = {}
    for (h, a), v in gm.items():
        i = 0 if h > a else (1 if h == a else 2)
        out[(h, a)] = v * (q0[i] / qm[i]) if qm[i] > 1e-12 else v
    t = sum(out.values())
    return {k: v / t for k, v in out.items()} if t > 0 else gm


def w_eff(mode, k, r, floor=0.35):
    """r = λ比 ≥ 1；返回相对衰减系数（乘到 w0 上）。"""
    if mode == "fixed":
        return 1.0
    if mode == "linear":
        return max(floor, 1.0 - k * (r - 1.0))
    if mode == "hyper":
        return 1.0 / (1.0 + k * (r - 1.0))
    if mode == "step":          # r ≥ k 时权重直接减半
        return 0.5 if r >= k else 1.0
    return 1.0


PLANS = [("fixed", 0.0), ("linear", 0.10), ("linear", 0.15), ("linear", 0.20),
         ("linear", 0.25), ("linear", 0.30), ("quad", 0.5)]

rows = []
for m in matches:
    lam = lambdas(m)
    hist.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    hist.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    if lam is None:
        continue
    lh, la = lam
    freq = engine.league_score_freq(m["league"])
    if not freq:
        continue
    g0 = pois_grid(lh, la)
    t = sum(g0.values())
    g0 = {k: v / t for k, v in g0.items()}
    r = max(lh, la) / min(lh, la) if min(lh, la) > 1e-9 else 99.0
    act = (m["hg"], m["ag"])
    strong_home = lh >= la          # λ 较大的一方视为强队
    y_strong = 1.0 if (act[0] > act[1]) == strong_home and act[0] != act[1] else 0.0
    rec = {"date": m["date"], "r": r, "y": y_strong, "top": [], "bs": [], "b3": [], "ps": []}
    for mode, k in PLANS:
        if mode == "quad":
            gm = quad(g0, freq, k)
        else:
            gm = mix(g0, freq, W0 * w_eff(mode, k, r))
        rec["top"].append(1 if max(gm, key=gm.get) == act else 0)
        rec["bs"].append(sum((v - (1.0 if key == act else 0.0)) ** 2 for key, v in gm.items()))
        ph = sum(v for (h, a), v in gm.items() if h > a)
        pd = sum(v for (h, a), v in gm.items() if h == a)
        pa = 1.0 - ph - pd
        y = (1.0, 0.0, 0.0) if act[0] > act[1] else ((0.0, 1.0, 0.0) if act[0] == act[1] else (0.0, 0.0, 1.0))
        rec["b3"].append((ph - y[0]) ** 2 + (pd - y[1]) ** 2 + (pa - y[2]) ** 2)
        rec["ps"].append(ph if strong_home else pa)
    rows.append(rec)

n = len(rows)
cut = int(n * 0.6)
print(f"样本 {n} 场 | 前60%: {rows[0]['date']}~{rows[cut-1]['date']} | 后40%: {rows[cut]['date']}~{rows[-1]['date']}")
print()
print("【全期】方案            Top1    比分Brier   1X2Brier | 后40%Top1 后40%1X2Brier  1X2改善(配对±SE)")
base_b3 = [x["b3"][0] for x in rows]
base_top = [x["top"][0] for x in rows]
for j, (mode, k) in enumerate(PLANS):
    tag = "固定w=0.5" if mode == "fixed" else f"{mode} k={k}"
    t1 = sum(x["top"][j] for x in rows) / n
    bs = sum(x["bs"][j] for x in rows) / n
    b3 = sum(x["b3"][j] for x in rows) / n
    t1b = sum(x["top"][j] for x in rows[cut:]) / (n - cut)
    b3b = sum(x["b3"][j] for x in rows[cut:]) / (n - cut)
    d = [base_b3[i] - x["b3"][j] for i, x in enumerate(rows)]
    md = sum(d) / n
    se = (sum((x - md) ** 2 for x in d) / (n * (n - 1))) ** 0.5
    z = md / se if se > 0 else 0.0
    mark = "" if j == 0 else ("  ✅" if z > 2 else ("  ⚠️" if z < -2 else ""))
    print(f"  {tag:<16} {t1*100:>6.2f}%  {bs:>9.4f}  {b3:>9.4f} | {t1b*100:>7.2f}% {b3b:>10.4f}"
          f"   {md:+.4f}±{se:.4f} (Z={z:+.1f}){mark}")

print()
print("【5段时序一致性】每段独立统计，验证改善是否稳定而非来自单段噪声")
segs = [(int(n * i / 5), int(n * (i + 1) / 5)) for i in range(5)]
print("  方案          " + "".join(f"  段{i+1} Top1/1X2B " for i in range(5)))
for j, (mode, k) in enumerate(PLANS):
    tag = "固定w=0.5" if mode == "fixed" else f"{mode} k={k}"
    line = f"  {tag:<14}"
    for s, e in segs:
        t1 = sum(x["top"][j] for x in rows[s:e]) / (e - s)
        b3 = sum(x["b3"][j] for x in rows[s:e]) / (e - s)
        line += f"  {t1*100:>5.2f}%/{b3:.4f}"
    print(line)
print("  段区间: " + " ".join(f"{rows[s]['date'][5:]}~{rows[e-1]['date'][5:]}" for s, e in segs))

print()
print("【Top1 配对差异 vs 固定w=0.5】负值=命中率下降")
for j, (mode, k) in enumerate(PLANS):
    if j == 0:
        continue
    d = [x["top"][j] - base_top[i] for i, x in enumerate(rows)]
    md = sum(d) / n
    se = (sum((x - md) ** 2 for x in d) / (n * (n - 1))) ** 0.5
    print(f"  {mode} k={k}: {md*100:+.2f}pp ± {se*100:.2f}pp (Z={md/se if se>0 else 0:+.1f})")

print()
print("【强队方向校准偏差】= 预测强队胜率均值 - 实际强队胜率（正=高估强队，负=低估强队）")
buckets = [(1.0, 1.3), (1.3, 1.8), (1.8, 2.5), (2.5, 99)]
print("  λ比区间        场数  实际胜率 |" + "".join(
    f"{(('固定' if md=='fixed' else (md[:4]+str(k)))):>9}" for md, k in PLANS))
for lo, hi in buckets:
    sub = [x for x in rows if lo <= x["r"] < hi]
    if not sub:
        continue
    ya = sum(x["y"] for x in sub) / len(sub)
    line = f"  [{lo:.1f},{hi if hi < 90 else '∞'}): {len(sub):>7}  {ya*100:>6.1f}% |"
    for j in range(len(PLANS)):
        pp = sum(x["ps"][j] for x in sub) / len(sub)
        line += f"{(pp - ya)*100:>+8.1f} "
    print(line)
