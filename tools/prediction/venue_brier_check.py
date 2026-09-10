# -*- coding: utf-8 -*-
"""
主客场分拆基础λ —— 端到端受控 A/B（Top1 / 比分Brier / 1X2Brier）

复用 adaptive_mix_sweep.py 的评估框架，但只改一处：λ 的来源。
  baseline : λ_home = (h_gf_all*0.75 + a_ga_all*0.25)*1.15   （不分主客 + 固定系数）
  venue    : 观测改用「该队作为主队时的进球 / 作为客队时的失球」等分主客口径，
             不再乘固定系数（主客效应已含在观测里），再按有效样本量向 baseline 收缩 K。

⚠️ 修正了 adaptive_mix_sweep.py 的一处 bug：该脚本 hist 按时间正序 append，
   却直接对 [-10:] 做 wavg（权重 decay^0 给了最旧一场），衰减方向是反的。
   本脚本统一「最新在前」后再加权，与 _calc_engine.py 实跑口径一致。

用法: python venue_brier_check.py [K]
"""
import json
import math
import os
import sys
import importlib.util

BASE = os.path.dirname(os.path.abspath(__file__))
# 兼容两种位置：仓库根 或 tools/prediction/（向上查找 results_data.json）
ROOT = BASE
for _ in range(3):
    if os.path.exists(os.path.join(ROOT, "results_data.json")):
        break
    ROOT = os.path.dirname(ROOT)
# 引擎位置：仓库根为 _calc_engine.py，master 的 tools/prediction/ 为 calc_engine.py
ENGINE_PY = None
for cand in (os.path.join(ROOT, "_calc_engine.py"),
             os.path.join(ROOT, "tools", "prediction", "calc_engine.py"),
             os.path.join(BASE, "calc_engine.py"),
             os.path.join(BASE, "_calc_engine.py")):
    if os.path.exists(cand):
        ENGINE_PY = cand
        break
if ENGINE_PY is None:
    raise SystemExit("找不到引擎文件（_calc_engine.py / tools/prediction/calc_engine.py）")
spec = importlib.util.spec_from_file_location("engine", ENGINE_PY)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.load_league_profile()   # 必须显式加载，否则联赛经验分布混合静默失效

K_VENUE = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
W0 = 0.5
DECAY, N_WIN = 0.96, 25          # 与生产一致
W_SHRINK = 0.25
GB = float(engine.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))
HOME_BOOST, AWAY_DISCOUNT = engine.HOME_BOOST, engine.AWAY_DISCOUNT

results = json.load(open(os.path.join(ROOT, "results_data.json"), encoding="utf-8"))
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

hist = {}   # team -> [(date, gf, ga)] 时间正序
histH = {}  # team -> [(date, gf, ga)] 仅作为主队
histA = {}  # team -> [(date, gf, ga)] 仅作为客队


def wavg(vals):
    """vals[0] = 最新一场"""
    s = c = 0.0
    for i, v in enumerate(vals):
        w = DECAY ** i
        s += v * w
        c += w
    return s / c if c else 0.0


def eff_n(n):
    return sum(DECAY ** i for i in range(n))


def _recent(team, store):
    """取最近 N_WIN 场，返回「最新在前」"""
    return list(store.get(team, []))[-N_WIN:][::-1]


def lambdas(m, use_venue):
    hr = _recent(m["home"], hist)
    ar = _recent(m["away"], hist)
    if not hr or not ar:
        return None
    h_gf, h_ga = wavg([x[1] for x in hr]), wavg([x[2] for x in hr])
    a_gf, a_ga = wavg([x[1] for x in ar]), wavg([x[2] for x in ar])
    lh = (h_gf * 0.75 + a_ga * 0.25) * HOME_BOOST
    la = (a_gf * 0.75 + h_ga * 0.25) * AWAY_DISCOUNT

    if use_venue:
        hrH = _recent(m["home"], histH)   # 主队在主场的进球
        arA = _recent(m["away"], histA)   # 客队在客场的失球
        arA_gf = _recent(m["away"], histA)
        hrH_ga = _recent(m["home"], histH)
        if hrH and arA:
            lh_v = wavg([x[1] for x in hrH]) * 0.75 + wavg([x[2] for x in arA]) * 0.25
            ne = min(eff_n(len(hrH)), eff_n(len(arA)))
            lh = (ne * lh_v + K_VENUE * lh) / (ne + K_VENUE)
        if arA_gf and hrH_ga:
            la_v = wavg([x[1] for x in arA_gf]) * 0.75 + wavg([x[2] for x in hrH_ga]) * 0.25
            ne = min(eff_n(len(arA_gf)), eff_n(len(hrH_ga)))
            la = (ne * la_v + K_VENUE * la) / (ne + K_VENUE)

    # 联赛先验收缩（两臂一致）
    lg = engine.LEAGUE_PROFILE["leagues"].get(m["league"])
    base = lg["mean"] if (lg and lg.get("n", 0) >= 12) else GB
    tot = (lh + la) * (1 - W_SHRINK) + base * W_SHRINK
    old = lh + la
    if old > 0:
        lh, la = lh / old * tot, la / old * tot
    # 市场赔率混合（两臂一致）
    if m["oh"] and m["oa"]:
        try:
            mh, ma = 1 / float(m["oh"]) * 2.5, 1 / float(m["oa"]) * 2.5
            lh, la = 0.65 * lh + 0.35 * mh, 0.65 * la + 0.35 * ma
        except (ValueError, ZeroDivisionError):
            pass
    return lh, la


def pois_grid(lh, la, kmax=6):
    g = {(h, a): math.exp(-lh) * lh ** h / math.factorial(h) *
                  math.exp(-la) * la ** a / math.factorial(a)
         for h in range(kmax + 1) for a in range(kmax + 1)}
    t = sum(g.values())
    return {k: v / t for k, v in g.items()} if t > 0 else g


def mix(g0, freq, w):
    gm = {k: (1 - w) * v + w * freq.get(k, 0.0) for k, v in g0.items()}
    t = sum(gm.values())
    return {k: v / t for k, v in gm.items()} if t > 0 else g0


rows = []
for m in matches:
    lam_b = lambdas(m, False)
    lam_v = lambdas(m, True)
    hist.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    hist.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    histH.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    histA.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    if lam_b is None or lam_v is None:
        continue
    freq = engine.league_score_freq(m["league"])
    if not freq:
        continue
    act = (m["hg"], m["ag"])
    y = (1.0, 0.0, 0.0) if act[0] > act[1] else ((0.0, 1.0, 0.0) if act[0] == act[1] else (0.0, 0.0, 1.0))
    rec = {"date": m["date"], "top": [], "bs": [], "b3": [], "tot": []}
    for lh, la in (lam_b, lam_v):
        g0 = pois_grid(lh, la)
        gm = mix(g0, freq, W0)
        top = max(gm, key=gm.get)
        ph = sum(v for (h, a), v in gm.items() if h > a)
        pd = sum(v for (h, a), v in gm.items() if h == a)
        pa = 1.0 - ph - pd
        rec["top"].append(1 if top == act else 0)
        rec["bs"].append(sum((v - (1.0 if key == act else 0.0)) ** 2 for key, v in gm.items()))
        rec["b3"].append((ph - y[0]) ** 2 + (pd - y[1]) ** 2 + (pa - y[2]) ** 2)
        rec["tot"].append(lh + la)
    rows.append(rec)

n = len(rows)
cut = int(n * 0.6)
print(f"样本 {n} 场 | 前60% {rows[0]['date']}~{rows[cut-1]['date']} | 后40% {rows[cut]['date']}~{rows[-1]['date']}")
print(f"参数: N={N_WIN} DECAY={DECAY} 经验混合w={W0} 联赛收缩={W_SHRINK} venue收缩K={K_VENUE}")
print()
print(f"{'方案':<12}{'Top1':>9}{'比分Brier':>11}{'1X2Brier':>10}{'λ总量':>9} | {'后40%Top1':>10}{'后40%1X2B':>10}")
for j, name in enumerate(("baseline", "venue")):
    t1 = sum(x["top"][j] for x in rows) / n
    bs = sum(x["bs"][j] for x in rows) / n
    b3 = sum(x["b3"][j] for x in rows) / n
    tg = sum(x["tot"][j] for x in rows) / n
    t1b = sum(x["top"][j] for x in rows[cut:]) / (n - cut)
    b3b = sum(x["b3"][j] for x in rows[cut:]) / (n - cut)
    print(f"{name:<12}{t1*100:>8.2f}%{bs:>11.4f}{b3:>10.4f}{tg:>9.3f} | {t1b*100:>9.2f}%{b3b:>10.4f}")

print()
for key, label in (("b3", "1X2Brier"), ("bs", "比分Brier")):
    d = [x[key][0] - x[key][1] for x in rows]
    md = sum(d) / n
    se = (sum((v - md) ** 2 for v in d) / (n * (n - 1))) ** 0.5
    z = md / se if se > 0 else 0.0
    verdict = "✅ 显著改善" if z > 2 else ("⚠️ 显著恶化" if z < -2 else "○ 不显著")
    print(f"{label} 改善(baseline-venue): {md:+.5f} ± {se:.5f}  Z={z:+.2f}  {verdict}")

dt = [x["top"][1] - x["top"][0] for x in rows]
mdt = sum(dt) / n
set_ = (sum((v - mdt) ** 2 for v in dt) / (n * (n - 1))) ** 0.5
print(f"Top1 差异(venue-baseline): {mdt*100:+.2f}pp ± {set_*100:.2f}pp  "
      f"Z={mdt/set_ if set_>0 else 0:+.2f}")

print()
print("【5段时序一致性】1X2Brier（baseline → venue）")
segs = [(int(n * i / 5), int(n * (i + 1) / 5)) for i in range(5)]
line = "  "
win = 0
for s, e in segs:
    b = sum(x["b3"][0] for x in rows[s:e]) / (e - s)
    v = sum(x["b3"][1] for x in rows[s:e]) / (e - s)
    win += 1 if v < b else 0
    line += f"  {rows[s]['date'][5:]}~{rows[e-1]['date'][5:]}: {b:.4f}→{v:.4f} ({'✅' if v < b else '❌'})"
print(line)
print(f"  改善段数: {win}/5")
