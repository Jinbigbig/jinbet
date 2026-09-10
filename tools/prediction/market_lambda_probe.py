# -*- coding: utf-8 -*-
"""
市场 λ 映射修正实验：粗线性映射 vs 正确的概率反演

问题：引擎第四步用 `1/赔率 × 2.5` 把胜/负赔率换成 λ，这个映射
      (a) 系统性低估总进球（2.5 是联赛均值，但只除以单个赔率）
      (b) 完全丢弃「平」赔率
      (c) 忽略了「主队被看好时总进球更高」这类结构性关系

本脚本对比四种市场 λ 口径：
  M0 现生产：mh = 1/胜 × 2.5, ma = 1/负 × 2.5
  M1 赔率反演：去水得 (ph,pd,pa) → 解出最匹配的 (λh,λa)
  M2 M1 + 比分行盘（若有）加权
各口径在 0~100% 权重下扫描 1X2 Brier / LogLoss / 方向Top1。

用法: python market_lambda_probe.py [K_max]   (K_max 默认 6)
"""
import json
import math
import os
import glob
import sys
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
             os.path.join(BASE, "_calc_engine.py"),
             os.path.join(BASE, "calc_engine.py")):
    if os.path.exists(cand):
        ENGINE_PY = cand
        break
spec = importlib.util.spec_from_file_location("engine", ENGINE_PY)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.load_league_profile()

KMAX = int(sys.argv[1]) if len(sys.argv) > 1 else 6
DECAY, N_WIN = 0.96, 25
W_SHRINK = 0.25
GB = float(engine.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))

# ---------- Poisson 概率表（λ 网格） ----------
_G = [round(0.05 * i, 2) for i in range(1, 91)]     # 0.05 ~ 4.50
_PMF, _CDF = {}, {}
for _L in _G:
    _p = [math.exp(-_L) * _L ** k / math.factorial(k) for k in range(KMAX + 1)]
    _s = sum(_p)
    _p = [x / _s for x in _p]
    _PMF[_L] = _p
    _c, _a = [], 0.0
    for _x in _p:
        _a += _x
        _c.append(_a)
    _CDF[_L] = _c


def probs(lh, la):
    """独立泊松 1X2（用查表，快）"""
    ph, ch = _PMF[lh], _CDF[lh]
    pa = _PMF[la]
    win = 0.0
    lose = 0.0
    draw = 0.0
    for a in range(KMAX + 1):
        pa_a = pa[a]
        draw += pa_a * ph[a]
        win += pa_a * (1.0 - ch[a])
        lose += pa_a * (ch[a - 1] if a > 0 else 0.0)
    t = win + draw + lose
    return (win / t, draw / t, lose / t) if t else (0.0, 0.0, 0.0)


def snap(x):
    x = round(x / 0.05) * 0.05
    return round(min(max(x, 0.05), 4.50), 2)


def invert_lambda(ph, pd, pa):
    """给定去水后的 1X2 概率，解出最匹配的 (λh, λa)"""
    best, bl = None, 9.9
    coarse = _G[::4]                       # 0.20 步长
    for lh in coarse:
        for la in coarse:
            P = probs(lh, la)
            e = (P[0] - ph) ** 2 + (P[1] - pd) ** 2 + (P[2] - pa) ** 2
            if e < bl:
                bl, best = e, (lh, la)
    bh, ba = best
    cands = sorted({snap(bh + 0.05 * i) for i in range(-4, 5)} |
                   {snap(ba + 0.05 * i) for i in range(-4, 5)})
    for lh in cands:
        for la in cands:
            P = probs(lh, la)
            e = (P[0] - ph) ** 2 + (P[1] - pd) ** 2 + (P[2] - pa) ** 2
            if e < bl:
                bl, best = e, (lh, la)
    return best


# ---------- 载入盘口与赛果 ----------
odds_all = {}
for f in sorted(glob.glob(os.path.join(ROOT, "odds_history", "*.json"))):
    if "index" in os.path.basename(f):
        continue
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    odds_all.update(d.get("odds") or {})

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


def base_lambdas(home, away, league):
    hr, ar = list(hist.get(home, []))[-N_WIN:][::-1], list(hist.get(away, []))[-N_WIN:][::-1]
    if not hr or not ar:
        return None
    lh = (wavg([x[1] for x in hr]) * 0.75 + wavg([x[2] for x in ar]) * 0.25) * engine.HOME_BOOST
    la = (wavg([x[1] for x in ar]) * 0.75 + wavg([x[2] for x in hr]) * 0.25) * engine.AWAY_DISCOUNT
    hrH = list(histH.get(home, []))[-N_WIN:][::-1]
    arA = list(histA.get(away, []))[-N_WIN:][::-1]
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


def devig3(o):
    try:
        oh, od, ol = float(o["胜"]), float(o["平"]), float(o["负"])
    except (KeyError, TypeError, ValueError):
        return None
    if min(oh, od, ol) <= 1.0:
        return None
    s = 1 / oh + 1 / od + 1 / ol
    return (1 / oh / s, 1 / od / s, 1 / ol / s)


rows = []
for k, (hg, ag, home, away, league) in sorted(actual.items()):
    lam = base_lambdas(home, away, league)
    d = k.split("_")[0]
    hist.setdefault(home, []).append((d, hg, ag))
    hist.setdefault(away, []).append((d, ag, hg))
    histH.setdefault(home, []).append((d, hg, ag))
    histA.setdefault(away, []).append((d, ag, hg))
    if lam is None or k not in odds_all:
        continue
    od = odds_all[k]
    p3 = devig3(od)
    if p3 is None:
        continue
    lh0, la0 = lam
    mh0 = 1 / float(od["胜"]) * 2.5
    ma0 = 1 / float(od["负"]) * 2.5
    mh1, ma1 = invert_lambda(*p3)
    rows.append({"act": (hg, ag), "lam": (lh0, la0), "p3": p3,
                 "M0": (mh0, ma0), "M1": (mh1, ma1)})

n = len(rows)
print(f"可评估样本 {n} 场（有 1X2 盘口 + 历史战绩）")
if n < 50:
    raise SystemExit("样本不足")

# ---------- 总进球偏差检查 ----------
tot_m0 = sum(r["M0"][0] + r["M0"][1] for r in rows) / n
tot_m1 = sum(r["M1"][0] + r["M1"][1] for r in rows) / n
tot_mod = sum(r["lam"][0] + r["lam"][1] for r in rows) / n
tot_act = sum(r["act"][0] + r["act"][1] for r in rows) / n
print(f"\n=== 总进球期望对照（这是 M0 的致命缺陷）===")
print(f"  实际场均总进球        {tot_act:.3f}")
print(f"  M0 现生产 (1/o×2.5)   {tot_m0:.3f}   偏差 {tot_m0-tot_act:+.3f}")
print(f"  M1 概率反演           {tot_m1:.3f}   偏差 {tot_m1-tot_act:+.3f}")
print(f"  纯模型 λ              {tot_mod:.3f}   偏差 {tot_mod-tot_act:+.3f}")


def b3(lam, act):
    p = probs(snap(lam[0]), snap(lam[1]))
    y = (1.0 if act[0] > act[1] else 0.0, 1.0 if act[0] == act[1] else 0.0,
         1.0 if act[0] < act[1] else 0.0)
    return sum((p[i] - y[i]) ** 2 for i in range(3)), p, y


def ref_raw_market():
    """参照：直接用去水后的市场 1X2 概率（不经 Poisson）计算 Brier"""
    bs = ll = t1 = 0.0
    for r in rows:
        p, y = r["p3"], (1.0 if r["act"][0] > r["act"][1] else 0.0,
                         1.0 if r["act"][0] == r["act"][1] else 0.0,
                         1.0 if r["act"][0] < r["act"][1] else 0.0)
        bs += sum((p[i] - y[i]) ** 2 for i in range(3))
        ll -= math.log(max(p[y.index(1.0)], 1e-9))
        t1 += 1.0 if max(range(3), key=lambda i: p[i]) == y.index(1.0) else 0.0
    return bs / n, ll / n, t1 / n


def evaluate(blend_fn):
    """blend_fn(r, w) -> (λh, λa)"""
    out = {}
    for w in (0.0, 0.35, 0.5, 0.65, 0.8, 1.0):
        bs = ll = t1 = 0.0
        for r in rows:
            lam = blend_fn(r, w)
            b, p, y = b3(lam, r["act"])
            bs += b
            ll -= math.log(max(p[y.index(1.0)], 1e-9))
            t1 += 1.0 if max(range(3), key=lambda i: p[i]) == y.index(1.0) else 0.0
        out[w] = (bs / n, ll / n, t1 / n)
    return out


def mk(mkey):
    def fn(r, w):
        lh, la = r["lam"]
        mh, ma = r[mkey]
        return ((1 - w) * lh + w * mh, (1 - w) * la + w * ma)
    return fn


print("\n=== 参照基线 ===")
rb, rl, rt = ref_raw_market()
print(f"{'市场1X2去水（原始，不经Poisson）':<34}{rb:>12.4f}{rl:>10.4f}{rt*100:>9.1f}%")


for mkey, label in (("M0", "M0 现生产（1/赔率×2.5）"), ("M1", "M1 概率反演（去水+求解）")):
    res = evaluate(mk(mkey))
    print(f"\n=== {label} ===")
    print(f"{'市场权重':>8}{'1X2 Brier':>12}{'LogLoss':>10}{'方向Top1':>10}")
    for w, (bs, ll, t1) in res.items():
        mark = ""
        if mkey == "M0" and abs(w - 0.35) < 1e-9:
            mark = "  ← 当前生产"
        if mkey == "M1" and abs(w - 0.8) < 1e-9:
            mark = "  ← M1 最优候选"
        print(f"{w:>8.2f}{bs:>12.4f}{ll:>10.4f}{t1*100:>9.1f}%{mark}")

print("\n=== 总进球标定（80% 权重）===")
print(f"{'口径':<18}{'总进球均值':>12}{'实际均值':>10}{'偏差':>10}")
print(f"{'实际':<18}{tot_act:>12.3f}{tot_act:>10.3f}{0.0:>+10.3f}")
for mkey, label in (("M0", "M0 粗映射"), ("M1", "M1 反演")):
    f = mk(mkey)
    m = sum(sum(f(r, 0.8)) for r in rows) / n
    print(f"{label:<18}{m:>12.3f}{tot_act:>10.3f}{m - tot_act:>+10.3f}")


# ---------- M2/M3：方向与总量分离 ----------
def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _inv(x):
    return 1.0 / (1.0 + math.exp(-x))


def m_dir_total(r, w, total_from="model"):
    """方向（主队进球占比，logit 空间混合）来自市场；总量可来自模型或市场"""
    lh, la = r["lam"]
    mh, ma = r["M1"]
    tm, tk = lh + la, mh + ma
    sm = lh / tm if tm > 0 else 0.5
    sk = mh / tk if tk > 0 else 0.5
    s = _inv((1 - w) * _logit(sm) + w * _logit(sk))
    if total_from == "model":
        t = tm
    elif total_from == "mkt":
        t = tk
    else:                                   # 半模型半市场
        t = 0.5 * tm + 0.5 * tk
    return (t * s, t * (1 - s))


def m_full(r, w):
    """λ 空间直接混合（M1 口径）"""
    lh, la = r["lam"]
    mh, ma = r["M1"]
    return ((1 - w) * lh + w * mh, (1 - w) * la + w * ma)


for name, fn in (("M2 方向用市场 + 总量用模型", lambda r, w: m_dir_total(r, w, "model")),
                 ("M3 方向用市场 + 总量半混合", lambda r, w: m_dir_total(r, w, "half"))):
    res = evaluate(fn)
    print(f"\n=== {name} ===")
    print(f"{'市场权重':>8}{'1X2 Brier':>12}{'LogLoss':>10}{'方向Top1':>10}")
    for w, (bs, ll, t1) in res.items():
        print(f"{w:>8.2f}{bs:>12.4f}{ll:>10.4f}{t1*100:>9.1f}%")
    m80 = sum(sum(fn(r, 0.8)) for r in rows) / n
    print(f"  → 80% 权重总进球均值 {m80:.3f}  偏差 {m80-tot_act:+.3f}")


# ---------- 进球数盘口（O/U 3球 即 2.5 大球）Brier ----------
def p_over25(lh, la):
    """独立泊松下 P(总进球 ≥ 3)"""
    lh, la = snap(lh), snap(la)
    ph, pa = _PMF[lh], _PMF[la]
    p0 = ph[0] * pa[0]
    p1 = ph[1] * pa[0] + ph[0] * pa[1]
    p2 = ph[2] * pa[0] + ph[1] * pa[1] + ph[0] * pa[2]
    return 1.0 - p0 - p1 - p2


def devig_tot(o):
    """总进球盘去水 → P(≥3)"""
    d = o.get("总进球") or {}
    out, s = {}, 0.0
    for k, v in d.items():
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v > 1.0:
            out[str(k)] = 1.0 / v
            s += 1.0 / v
    if s <= 0:
        return None
    g = {k: v / s for k, v in out.items()}
    return sum(p for k, p in g.items() if k in ("3", "4", "5", "6", "7+"))


rows_tot = []
for k, (hg, ag, home, away, league) in sorted(actual.items()):
    if k not in odds_all:
        continue
    o = odds_all[k]
    p3 = devig3(o)
    pt = devig_tot(o)
    if p3 is None or pt is None:
        continue
    lam = base_lambdas(home, away, league)
    d = k.split("_")[0]
    hist.setdefault(home, []).append((d, hg, ag))
    hist.setdefault(away, []).append((d, ag, hg))
    histH.setdefault(home, []).append((d, hg, ag))
    histA.setdefault(away, []).append((d, ag, hg))
    if lam is None or not lam[0]:
        continue
    rows_tot.append({"act": (hg, ag), "lam": lam, "p3": p3, "pt": pt,
                     "M0": (1 / float(o["胜"]) * 2.5, 1 / float(o["负"]) * 2.5),
                     "M1": invert_lambda(*p3)})

nt = len(rows_tot)
print(f"\n=== 进球数盘口（P(≥3球) Brier，越低越好）===")
print(f"样本 {nt} 场")
bt = bm = 0.0
for r in rows_tot:
    y = 1.0 if r["act"][0] + r["act"][1] >= 3 else 0.0
    bt += (r["pt"] - y) ** 2
    bm += (p_over25(*r["lam"]) - y) ** 2
print(f"  市场总进球盘去水（天花板）        {bt/nt:.4f}")
print(f"{'口径':<26}{'权重':>6}{'P(≥3) Brier':>14}")
for lab, f in (("纯模型", lambda r, w: r["lam"]),
               ("M0 λ混合", lambda r, w: ((1 - w) * r["lam"][0] + w * r["M0"][0],
                                          (1 - w) * r["lam"][1] + w * r["M0"][1])),
               ("M1 λ混合", lambda r, w: ((1 - w) * r["lam"][0] + w * r["M1"][0],
                                          (1 - w) * r["lam"][1] + w * r["M1"][1])),
               ("M2 方向市场/总量模型", lambda r, w: (
                   (lambda lh, la, mh, ma: (
                       (lambda t, s: (t * s, t * (1 - s)))(
                           lh + la, _inv((1 - w) * _logit(lh / (lh + la)) + w * _logit(mh / (mh + ma))))))(
                       r["lam"][0], r["lam"][1], r["M1"][0], r["M1"][1])))):
    for w in (0.35, 0.8):
        if lab == "纯模型" and w == 0.8:
            continue
        b = sum((p_over25(*f(r, w)) - (1.0 if r["act"][0] + r["act"][1] >= 3 else 0.0)) ** 2
                for r in rows_tot) / nt
        mark = "  ← 现生产" if (lab == "M0 λ混合" and w == 0.35) else ""
        print(f"{lab:<26}{w:>6.2f}{b:>14.4f}{mark}")
