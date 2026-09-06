# -*- coding: utf-8 -*-
"""比分选法回测：在历史赛果上复刻引擎 λ 推导，对比不同 Top1 选择规则的命中率。

回答的问题：
  1) 现行 argmax（含联赛形态混合）是否已是命中率最优解？
  2) "大球概率高时改选 3+ 比分"会不会降低命中率？（用户质疑）
  3) 纯泊松 vs 形态混合的贡献分解。
"""
import json
import math
import os
import importlib.util

BASE = os.path.dirname(os.path.abspath(__file__))

spec = importlib.util.spec_from_file_location("engine", os.path.join(BASE, "_calc_engine.py"))
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.load_league_profile()  # main() 外手动触发，否则画像为空
assert engine.LEAGUE_PROFILE["leagues"], "联赛画像加载失败"

# ---------- 1. 载入赛果，按时间排序 ----------
results = json.load(open(os.path.join(BASE, "results_data.json"), encoding="utf-8"))
matches = []
for k, v in results.items():
    try:
        fs = v["fullScore"]
        h, a = (int(x) for x in fs.split(":"))
    except Exception:
        continue
    matches.append({"date": k.split("_")[0], "home": v["home"], "away": v["away"],
                    "league": v.get("league") or v.get("leagueAbbr") or "",
                    "hg": h, "ag": a})
matches.sort(key=lambda m: m["date"])
print(f"总样本: {len(matches)} 场")

# ---------- 2. 增量维护球队近期战绩，逐场推导 λ ----------
hist = {}          # team -> list[(date, gf, ga)] 按时间序
W, DECAY = 0.25, 0.85
GLOBAL_BASE = float(engine.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))

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
    lam_h = (h_gf * 0.75 + a_ga * 0.25) * engine.HOME_BOOST
    lam_a = (a_gf * 0.75 + h_ga * 0.25) * engine.AWAY_DISCOUNT
    # 联赛先验收缩（复刻 shrink_to_league）
    lg = engine.LEAGUE_PROFILE["leagues"].get(m["league"])
    base = lg["mean"] if (lg and lg.get("n", 0) >= 12) else GLOBAL_BASE
    total = (lam_h + lam_a) * (1 - W) + base * W
    old = lam_h + lam_a
    if old > 0:
        lam_h, lam_a = lam_h / old * total, lam_a / old * total
    return lam_h, lam_a

def pois_grid(lh, la, kmax=6):
    g = {}
    for h in range(kmax + 1):
        for a in range(kmax + 1):
            g[(h, a)] = math.exp(-lh) * lh ** h / math.factorial(h) * \
                        math.exp(-la) * la ** a / math.factorial(a)
    return g

def p_ge3(lh, la):
    lt = lh + la
    return 1 - sum(math.exp(-lt) * lt ** k / math.factorial(k) for k in range(3))

# ---------- 3. 逐场评估各策略 ----------
STRATS = ["S0_纯泊松argmax", "S1_混合w0.3(现行)", "S2_混合w0.5",
          "S3_大球导向58%", "S4_强选3+球", "B1_恒猜1:1"]
hit = {s: 0 for s in STRATS}
n_eval = 0
# 大球场次子集（现行分布 P(≥3)≥58%，即 017 那类）
sub_hit = {s: 0 for s in STRATS}
n_big = 0
# 预测1:1 的条件命中
p11_n = p11_hit = 0

for m in matches:
    lam = lambdas(m)
    # 更新历史（在预测之后写入，保证只用赛前信息）
    hist.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    hist.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    if lam is None:
        continue
    n_eval += 1
    lh, la = lam
    actual = (m["hg"], m["ag"])
    g0 = pois_grid(lh, la)
    g1 = engine.mix_score_matrix(dict(g0), m["league"])
    g2 = {k: v for k, v in g0.items()}
    freq = engine.league_score_freq(m["league"])
    if freq:
        g2 = {k: 0.5 * v + 0.5 * freq.get(k, 0.0) for k, v in g0.items()}
        t = sum(g2.values())
        g2 = {k: v / t for k, v in g2.items()}
    else:
        g2 = g1
    p3 = p_ge3(lh, la)
    picks = {
        "S0_纯泊松argmax": max(g0, key=g0.get),
        "S1_混合w0.3(现行)": max(g1, key=g1.get),
        "S2_混合w0.5": max(g2, key=g2.get),
        "S3_大球导向58%": (max(((k, v) for k, v in g1.items() if sum(k) >= 3),
                              key=lambda x: x[1])[0] if p3 >= 0.58 else max(g1, key=g1.get)),
        "S4_强选3+球": max(((k, v) for k, v in g1.items() if sum(k) >= 3), key=lambda x: x[1])[0],
        "B1_恒猜1:1": (1, 1),
    }
    for s, pk in picks.items():
        if pk == actual:
            hit[s] += 1
    if p3 >= 0.58:
        n_big += 1
        for s, pk in picks.items():
            if pk == actual:
                sub_hit[s] += 1
    if picks["S1_混合w0.3(现行)"] == (1, 1):
        p11_n += 1
        p11_hit += (actual == (1, 1))

print(f"\n可评估样本: {n_eval} 场（双方均有近期战绩）")
print(f"{'策略':<22}{'整体Top1命中':>14}{'大球场次命中(017类)':>20}")
for s in STRATS:
    big = f"{sub_hit[s]}/{n_big} = {sub_hit[s]/n_big*100:.1f}%" if n_big else "-"
    print(f"{s:<22}{hit[s]/n_eval*100:>10.2f}%{big:>22}")

print(f"\n预测1:1 的场次: {p11_n} 场, 实际1:1命中: {p11_hit/p11_n*100:.1f}% (全体实际1:1基准 "
      f"{sum(1 for x in matches if (x['hg'],x['ag'])==(1,1))/len(matches)*100:.1f}%)")

# 大球子集里各首选比分的实际命中率
if n_big:
    print(f"\n大球场次(现行分布P(≥3)≥58%)共 {n_big} 场，占 {n_big/n_eval*100:.0f}%")
