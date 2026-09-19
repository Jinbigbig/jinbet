# -*- coding: utf-8 -*-
"""
被浪费的市场信息：比分盘 / 总进球盘 / 让球盘 的可用性验证

发现：index.html 与 odds_history/*.json 里 92% 的场次都带
      「比分」「总进球」「让球」「半全场」四个盘口，
      但引擎第四步只用了 胜/负 两个赔率（还丢弃了 平），
      且用 `1/赔率 × 2.5` 这种极粗的线性映射换算 λ。

本脚本验证：直接把这些盘口拿来做预测，比现模型好多少？
  口径 A: 现模型（近25场状态 + 主客场分拆 + 联赛收缩 + 35%市场混合）
  口径 B: 市场总进球盘去水 → 总进球分布（用于校准 λ_total）
  口径 C: 市场比分盘去水 → 完整比分分布
  口径 D: A 与 C 的加权混合

用法: python market_score_probe.py
"""
import json
import math
import os
import glob
import importlib.util

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = BASE
for _ in range(3):
    if os.path.exists(os.path.join(ROOT, "results_data.json")):
        break
    ROOT = os.path.dirname(ROOT)

ENGINE_PY = None
for cand in (os.path.join(ROOT, "_calc_engine.py"),
             os.path.join(ROOT, "tools", "prediction", "calc_engine.py"),
             os.path.join(BASE, "calc_engine.py"),
             os.path.join(BASE, "_calc_engine.py")):
    if os.path.exists(cand):
        ENGINE_PY = cand
        break
spec = importlib.util.spec_from_file_location("engine", ENGINE_PY)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.load_league_profile()

DECAY, N_WIN = 0.96, 25
W_SHRINK = 0.25
GB = float(engine.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))
KMAX = 6

# ---------- 载入历史盘口 ----------
odds_all = {}
for f in sorted(glob.glob(os.path.join(ROOT, "odds_history", "*.json"))):
    if "index" in os.path.basename(f):
        continue
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    odds_all.update(d.get("odds") or {})
print(f"odds_history 载入 {len(odds_all)} 场盘口")

results = json.load(open(os.path.join(ROOT, "results_data.json"), encoding="utf-8"))
actual = {}
for k, v in results.items():
    try:
        h, a = (int(x) for x in v["fullScore"].split(":"))
    except Exception:
        continue
    actual[k] = (h, a, v.get("home"), v.get("away"),
                 v.get("league") or v.get("leagueAbbr") or "")

hist, histH, histA = {}, {}, {}


def wavg(vals):
    s = c = 0.0
    for i, v in enumerate(vals):
        w = DECAY ** i
        s += v * w
        c += w
    return s / c if c else 0.0


def eff_n(n):
    return sum(DECAY ** i for i in range(n))


def _recent(t, store):
    return list(store.get(t, []))[-N_WIN:][::-1]


def base_lambdas(home, away, league):
    hr, ar = _recent(home, hist), _recent(away, hist)
    if not hr or not ar:
        return None
    lh = (wavg([x[1] for x in hr]) * 0.75 + wavg([x[2] for x in ar]) * 0.25) * engine.HOME_BOOST
    la = (wavg([x[1] for x in ar]) * 0.75 + wavg([x[2] for x in hr]) * 0.25) * engine.AWAY_DISCOUNT
    hrH, arA = _recent(home, histH), _recent(away, histA)
    if hrH and arA:
        lh_v = wavg([x[1] for x in hrH]) * 0.75 + wavg([x[2] for x in arA]) * 0.25
        ne = min(eff_n(len(hrH)), eff_n(len(arA)))
        lh = (ne * lh_v + 4.0 * lh) / (ne + 4.0)
    if arA and hrH:
        la_v = wavg([x[1] for x in arA]) * 0.75 + wavg([x[2] for x in hrH]) * 0.25
        ne = min(eff_n(len(arA)), eff_n(len(hrH)))
        la = (ne * la_v + 4.0 * la) / (ne + 4.0)
    lg = engine.LEAGUE_PROFILE["leagues"].get(league)
    base = lg["mean"] if (lg and lg.get("n", 0) >= 12) else GB
    tot = (lh + la) * (1 - W_SHRINK) + base * W_SHRINK
    old = lh + la
    if old > 0:
        lh, la = lh / old * tot, la / old * tot
    return lh, la


def devig(d):
    """比例去水：p_i = (1/o_i) / Σ(1/o_j)"""
    out, s = {}, 0.0
    for k, v in d.items():
        try:
            o = float(v)
        except (TypeError, ValueError):
            continue
        if o <= 1.0:
            continue
        out[k] = 1.0 / o
        s += 1.0 / o
    return {k: v / s for k, v in out.items()} if s > 0 else {}


def parse_score_odds(d):
    """比分盘 → {(h,a): p}；跳过「x其他」残差桶"""
    out = {}
    for k, v in d.items():
        if "其他" in k:
            continue
        try:
            h, a = (int(x) for x in k.split(":"))
        except (ValueError, AttributeError):
            continue
        try:
            o = float(v)
        except (TypeError, ValueError):
            continue
        if o > 1.0:
            out[(h, a)] = 1.0 / o
    s = sum(out.values())
    return {k: v / s for k, v in out.items()} if s > 0 else {}


def model_grid(lh, la, league, mh=None, ma=None):
    g = {}
    for i in range(KMAX + 1):
        for j in range(KMAX + 1):
            g[(i, j)] = (math.exp(-lh) * lh ** i / math.factorial(i)) * \
                        (math.exp(-la) * la ** j / math.factorial(j))
    if mh is not None:
        lh2, la2 = 0.65 * lh + 0.35 * mh, 0.65 * la + 0.35 * ma
        g = {}
        for i in range(KMAX + 1):
            for j in range(KMAX + 1):
                g[(i, j)] = (math.exp(-lh2) * lh2 ** i / math.factorial(i)) * \
                            (math.exp(-la2) * la2 ** j / math.factorial(j))
    t = sum(g.values())
    g = {k: v / t for k, v in g.items()}
    freq = engine.league_score_freq(league)
    if freq:
        w0 = float(engine.LEAGUE_PROFILE.get("score_mix", {}).get("w", 0.5))
        lo, hi = min(lh, la), max(lh, la)
        r = (hi / lo) if lo > 1e-9 else 99.0
        if r > 1.0:
            w0 *= max(engine.ADAPTIVE_MIX_FLOOR, 1.0 - engine.ADAPTIVE_MIX_K * (r - 1.0))
        gm = {k: (1 - w0) * v + w0 * freq.get(k, 0.0) for k, v in g.items()}
        t = sum(gm.values())
        if t > 0:
            g = {k: v / t for k, v in gm.items()}
    return g


rows = []
for k, (hg, ag, home, away, league) in sorted(actual.items()):
    lam = base_lambdas(home, away, league)
    hist.setdefault(home, []).append((k.split("_")[0], hg, ag))
    hist.setdefault(away, []).append((k.split("_")[0], ag, hg))
    histH.setdefault(home, []).append((k.split("_")[0], hg, ag))
    histA.setdefault(away, []).append((k.split("_")[0], ag, hg))
    if lam is None or k not in odds_all:
        continue
    od = odds_all[k]
    grid_score = parse_score_odds(od.get("比分") or {})
    if not grid_score:
        continue
    tot_mkt = devig(od.get("总进球") or {})
    lh, la = lam
    mh = ma = None
    try:
        oh, oa = float(od.get("胜")), float(od.get("负"))
        mh, ma = 1 / oh * 2.5, 1 / oa * 2.5
    except (TypeError, ValueError):
        pass
    rows.append({"act": (hg, ag), "model": model_grid(lh, la, league, mh, ma),
                 "score": grid_score, "tot": tot_mkt,
                 "mkt1x2": devig({kk: od.get(kk) for kk in ("胜", "平", "负")
                                  if od.get(kk)})})

n = len(rows)
print(f"可评估样本 {n} 场（有完整比分盘 + 历史战绩）\n")
if n < 50:
    raise SystemExit("样本不足，跳过")


def top1(g):
    return max(g.items(), key=lambda x: x[1])[0]


def brier_score(g, act):
    return sum((v - (1.0 if kk == act else 0.0)) ** 2 for kk, v in g.items())


def p1x2(g):
    h = sum(v for k, v in g.items() if k[0] > k[1])
    d = sum(v for k, v in g.items() if k[0] == k[1])
    a = sum(v for k, v in g.items() if k[0] < k[1])
    t = h + d + a
    return (h / t, d / t, a / t) if t else (0, 0, 0)


def b3(p, act):
    y = (1.0 if act[0] > act[1] else 0.0, 1.0 if act[0] == act[1] else 0.0,
         1.0 if act[0] < act[1] else 0.0)
    return sum((p[i] - y[i]) ** 2 for i in range(3))


print(f"{'口径':<34}{'比分Top1':>10}{'比分Brier':>11}{'1X2Brier':>10}")
res = {}
res["A 现模型"] = {
    "top1": sum(1 for r in rows if top1(r["model"]) == r["act"]) / n,
    "bs": sum(brier_score(r["model"], r["act"]) for r in rows) / n,
    "b3": sum(b3(p1x2(r["model"]), r["act"]) for r in rows) / n}
res["C 市场比分盘（去水）"] = {
    "top1": sum(1 for r in rows if top1(r["score"]) == r["act"]) / n,
    "bs": sum(brier_score(r["score"], r["act"]) for r in rows) / n,
    "b3": sum(b3(p1x2(r["score"]), r["act"]) for r in rows) / n}
for w in (0.3, 0.5, 0.7):
    def mixg(r, w=w):
        a, b = r["model"], r["score"]
        keys = set(a) | set(b)
        g = {k: (1 - w) * a.get(k, 0.0) + w * b.get(k, 0.0) for k in keys}
        t = sum(g.values())
        return {k: v / t for k, v in g.items()} if t else a
    res[f"D 模型×{int((1-w)*100)}% + 比分盘×{int(w*100)}%"] = {
        "top1": sum(1 for r in rows if top1(mixg(r)) == r["act"]) / n,
        "bs": sum(brier_score(mixg(r), r["act"]) for r in rows) / n,
        "b3": sum(b3(p1x2(mixg(r)), r["act"]) for r in rows) / n}
res["（参考）市场1X2去水"] = {
    "top1": float("nan"), "bs": float("nan"),
    "b3": sum(b3((r["mkt1x2"].get("胜", 0), r["mkt1x2"].get("平", 0),
                  r["mkt1x2"].get("负", 0)), r["act"]) for r in rows) / n}

for name, v in res.items():
    t1 = f"{v['top1']*100:>9.1f}%" if v['top1'] == v['top1'] else "        -"
    bs = f"{v['bs']:>11.4f}" if v['bs'] == v['bs'] else "          -"
    print(f"{name:<34}{t1}{bs}{v['b3']:>10.4f}")

# 总进球盘的可用性
tot_eval = [r for r in rows if r["tot"] and r["act"][0] + r["act"][1] <= 6]
hit_tot = (sum(1 for r in tot_eval
               if max(r["tot"], key=r["tot"].get) == str(r["act"][0] + r["act"][1]))
           / max(len(tot_eval), 1))
print(f"\n（参考）市场总进球盘众数命中率：{hit_tot*100:.1f}%  "
      f"（{len(tot_eval)} 场，剔除 7+）")