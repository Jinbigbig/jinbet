# -*- coding: utf-8 -*-
"""形态混合权重 w 的 walk-forward 扫描（命中率 + Brier 双指标，前60%/后40%时序分段）。"""
import json
import math
import os
import importlib.util

spec = importlib.util.spec_from_file_location("engine", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_calc_engine.py"))
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.load_league_profile()

results = json.load(open("results_data.json", encoding="utf-8"))
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
DECAY, W_SHRINK = 0.85, 0.25
GB = float(engine.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))

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

Ws = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
rows = []
for m in matches:
    lam = lambdas(m)
    hist.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    hist.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    if lam is None:
        continue
    lh, la = lam
    g0 = pois_grid(lh, la)
    t = sum(g0.values())
    g0 = {k: v / t for k, v in g0.items()}
    freq = engine.league_score_freq(m["league"])
    if not freq:
        continue
    act = (m["hg"], m["ag"])
    hs, brs = [], []
    for w in Ws:
        gm = {k: (1 - w) * v + w * freq.get(k, 0.0) for k, v in g0.items()}
        tt = sum(gm.values())
        gm = {k: v / tt for k, v in gm.items()}
        hs.append(1 if max(gm, key=gm.get) == act else 0)
        brs.append(sum((gm.get(k, 0.0) - (1.0 if k == act else 0.0)) ** 2 for k in gm))
    rows.append((m["date"], hs, brs, act))

n = len(rows)
cut = int(n * 0.6)
print(f"样本 {n} 场 | 前60%: {rows[0][0]}~{rows[cut-1][0]} | 后40%: {rows[cut][0]}~{rows[-1][0]}")
print(f"{'w':>4} | {'全期命中':>8} {'全期Brier':>9} | {'前60%命中':>9} {'后40%命中':>9} {'后40%Brier':>10}")
for i, w in enumerate(Ws):
    h = sum(r[1][i] for r in rows) / n
    b = sum(r[2][i] for r in rows) / n
    h1 = sum(r[1][i] for r in rows[:cut]) / cut
    h2 = sum(r[1][i] for r in rows[cut:]) / (n - cut)
    b2 = sum(r[2][i] for r in rows[cut:]) / (n - cut)
    print(f"{w:>4} | {h*100:>7.2f}% {b:>9.4f} | {h1*100:>8.2f}% {h2*100:>8.2f}% {b2:>10.4f}")
b11 = sum(1 for r in rows if r[3] == (1, 1)) / n
print(f"\n恒猜1:1基线: {b11*100:.2f}%")
