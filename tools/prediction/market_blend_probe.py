#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""市场混合方式对照实验（含 Platt 顺序）。

背景：现生产在「λ 空间」做线性混合，且市场 λ 用 1/赔率×2.5 的粗映射，
      权重仅 35%。market_lambda_probe.py 已证：粗映射系统性低估总进球约
      -0.9 球，提高权重会把进球数预测带崩。

本脚本对照三种口径（walk-forward，全部复用同一套基础λ）：
  A 现生产：λ空间线性混合，市场λ = 1/赔率×2.5，权重 0.35
  B 概率空间混合：模型1X2 与 市场去水1X2 线性混合 → 反解 λ（总量守恒）
  C B + 比分盘去水分布（覆盖不足时回退 B）

关键设计：混合发生在「λ 总量守恒」约束下，因此进球数分布不受影响。
另含 Platt 顺序检验：先校准后混合 vs 混合后再拟合 Platt。

用法：python market_blend_probe.py [K]
"""
import glob
import importlib.util
import json
import math
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _repo_root():
    for d in (_ROOT, os.path.dirname(_ROOT), os.path.dirname(os.path.dirname(_ROOT))):
        if os.path.exists(os.path.join(d, "results_data.json")):
            return d
    return _ROOT


ROOT = _repo_root()

def _engine_py():
    """兼容两种仓库布局：本地根目录 _calc_engine.py / master 下 tools/prediction/calc_engine.py"""
    for c in (os.path.join(ROOT, "_calc_engine.py"),
              os.path.join(ROOT, "calc_engine.py"),
              os.path.join(ROOT, "tools", "prediction", "calc_engine.py")):
        if os.path.exists(c):
            return c
    return os.path.join(ROOT, "_calc_engine.py")

_spec = importlib.util.spec_from_file_location("engine", _engine_py())
eng = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eng)
eng.load_league_profile()

KMAX = 6
DECAY = 0.96
NW = 25
WS = 0.25
GB = float(eng.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))
_G = [round(0.05 * i, 2) for i in range(1, 91)]
_PMF = {}
_CDF = {}
for _L in _G:
    _p = [math.exp(-_L) * _L ** k / math.factorial(k) for k in range(KMAX + 1)]
    _s = sum(_p)
    _p = [x / _s for x in _p]
    _PMF[_L] = _p
    _c = []
    _a = 0.0
    for _x in _p:
        _a += _x
        _c.append(_a)
    _CDF[_L] = _c


def snap(x):
    x = round(x / 0.05) * 0.05
    return round(min(max(x, 0.05), 4.50), 2)


def probs(lh, la):
    """独立泊松 1X2（不做零封修正，与生产第四步的模型口径一致）"""
    ph, ch = _PMF[lh], _CDF[lh]
    pa = _PMF[la]
    w = d = l = 0.0
    for a in range(KMAX + 1):
        w += pa[a] * (1.0 - ch[a])
        d += pa[a] * ph[a]
        l += pa[a] * (ch[a - 1] if a > 0 else 0.0)
    t = w + d + l
    return (w / t, d / t, l / t) if t else (0.0, 0.0, 0.0)


def solve_lambda(pb, total):
    """给定目标 1X2 概率 pb 与 λ 总量 total，反解 (λh, λa)"""
    best = None
    bl = 9.9
    for i in range(1, 90):
        lh = total * i / 90.0
        la = total - lh
        if la < 0.05:
            break
        P = probs(snap(lh), snap(la))
        e = sum((P[k] - pb[k]) ** 2 for k in range(3))
        if e < bl:
            bl = e
            best = (snap(lh), snap(la))
    return best


def wavg(v):
    s = c = 0.0
    for i, x in enumerate(v):
        w = DECAY ** i
        s += x * w
        c += w
    return s / c if c else 0.0


def effn(n):
    return sum(DECAY ** i for i in range(n))


def base_lam(h, a, lg):
    """生产同源基础λ（含主客场分拆 + 联赛先验收缩）"""
    hr = list(hist.get(h, []))[-NW:][::-1]
    ar = list(hist.get(a, []))[-NW:][::-1]
    if not hr or not ar:
        return None
    lh = (wavg([x[1] for x in hr]) * .75 + wavg([x[2] for x in ar]) * .25) * eng.HOME_BOOST
    la = (wavg([x[1] for x in ar]) * .75 + wavg([x[2] for x in hr]) * .25) * eng.AWAY_DISCOUNT
    hH = list(histH.get(h, []))[-NW:][::-1]
    aA = list(histA.get(a, []))[-NW:][::-1]
    if hH and aA:
        v = wavg([x[1] for x in hH]) * .75 + wavg([x[2] for x in aA]) * .25
        ne = min(effn(len(hH)), effn(len(aA)))
        lh = (ne * v + 4 * lh) / (ne + 4)
    if aA and hH:
        v = wavg([x[1] for x in aA]) * .75 + wavg([x[2] for x in hH]) * .25
        ne = min(effn(len(aA)), effn(len(hH)))
        la = (ne * v + 4 * la) / (ne + 4)
    L = eng.LEAGUE_PROFILE["leagues"].get(lg)
    b = L["mean"] if (L and L.get("n", 0) >= 12) else GB
    t = (lh + la) * (1 - WS) + b * WS
    o = lh + la
    return (lh / o * t, la / o * t) if o > 0 else (lh, la)


# ---------- 载入数据 ----------
odds = {}
for f in sorted(glob.glob(os.path.join(ROOT, "odds_history", "*.json"))):
    if "index" in os.path.basename(f):
        continue
    try:
        odds.update(json.load(open(f, encoding="utf-8")).get("odds") or {})
    except Exception:  # noqa: BLE001
        pass

res = json.load(open(os.path.join(ROOT, "results_data.json"), encoding="utf-8"))
recs = []
for k, v in res.items():
    try:
        hg, ag = (int(x) for x in v["fullScore"].split(":"))
    except Exception:  # noqa: BLE001
        continue
    recs.append((k, hg, ag, v.get("home"), v.get("away"),
                 v.get("league") or v.get("leagueAbbr") or ""))
recs.sort(key=lambda r: r[0].split("_")[0])

hist, histH, histA = {}, {}, {}
rows = []
for k, hg, ag, hm, aw, lg in recs:
    d = k.split("_")[0]
    lam = base_lam(hm, aw, lg)
    hist.setdefault(hm, []).append((d, hg, ag))
    hist.setdefault(aw, []).append((d, ag, hg))
    histH.setdefault(hm, []).append((d, hg, ag))
    histA.setdefault(aw, []).append((d, ag, hg))
    if lam is None:
        continue
    o = odds.get(k)
    if not o:
        continue
    try:
        oh, od, ol = float(o["胜"]), float(o["平"]), float(o["负"])
    except Exception:  # noqa: BLE001
        continue
    if min(oh, od, ol) <= 1.0:
        continue
    s = 1 / oh + 1 / od + 1 / ol
    rows.append({"act": (hg, ag), "lam": lam, "raw": (oh, od, ol),
                 "mkt": (1 / oh / s, 1 / od / s, 1 / ol / s)})

n = len(rows)
print(f"样本 {n} 场（有完整 1X2 赔率）")


def metrics(fn):
    b3 = ll = t1 = bt = 0.0
    for r in rows:
        lh, la = fn(r)
        P = probs(snap(lh), snap(la))
        hg, ag = r["act"]
        y = (1.0 if hg > ag else 0.0, 1.0 if hg == ag else 0.0, 1.0 if hg < ag else 0.0)
        b3 += sum((P[i] - y[i]) ** 2 for i in range(3))
        ll -= math.log(max(P[y.index(1.0)], 1e-9))
        t1 += 1.0 if max(range(3), key=lambda i: P[i]) == y.index(1.0) else 0.0
        hl, al = snap(lh), snap(la)
        pml, pma = _PMF[hl], _PMF[al]
        p2 = 1 - pml[0] * pma[0] - (pml[1] * pma[0] + pml[0] * pma[1]) \
            - (pml[2] * pma[0] + pml[1] * pma[1] + pml[0] * pma[2])
        bt += (p2 - (1.0 if hg + ag >= 3 else 0.0)) ** 2
    return b3 / n, ll / n, t1 / n * 100, bt / n


# ---------- A 现生产：λ空间混合 35% ----------
def A_lam(r, w):
    lh, la = r["lam"]
    oh, _od, ol = r["raw"]
    mh, ma = 1 / oh * 2.5, 1 / ol * 2.5
    return ((1 - w) * lh + w * mh, (1 - w) * la + w * ma)


# ---------- B 概率空间混合（总量守恒） ----------
def B_lam(r, w):
    lh, la = r["lam"]
    pm = probs(snap(lh), snap(la))
    pb = [(1 - w) * pm[i] + w * r["mkt"][i] for i in range(3)]
    s = sum(pb)
    pb = [x / s for x in pb]
    return solve_lambda(pb, lh + la)


print()
hdr = f"{'权重':>6}{'A λ空间 Brier':>16}{'B 概率空间 Brier':>18}{'差异':>10}"
print("=== 1X2 Brier（越低越好）===")
print(hdr)
for w in (0.0, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0):
    a = metrics(lambda r, w=w: A_lam(r, w))[0]
    b = metrics(lambda r, w=w: B_lam(r, w))[0]
    mk = "  ← 现生产" if abs(w - 0.35) < 1e-9 else ("  ← 候选" if abs(w - 0.8) < 1e-9 else "")
    print(f"{w:>6.2f}{a:>16.4f}{b:>18.4f}{b - a:>+10.4f}{mk}")

print()
print("=== 三项指标明细 ===")
print(f"{'口径':<26}{'1X2 Brier':>11}{'LogLoss':>10}{'方向Top1':>10}{'P(≥3) Brier':>13}")
for label, fn in (("A 现生产 λ空间 0.35", lambda r: A_lam(r, 0.35)),
                  ("A λ空间 0.80", lambda r: A_lam(r, 0.80)),
                  ("B 概率空间 0.35", lambda r: B_lam(r, 0.35)),
                  ("B 概率空间 0.65", lambda r: B_lam(r, 0.65)),
                  ("B 概率空间 0.80", lambda r: B_lam(r, 0.80)),
                  ("B 概率空间 0.90", lambda r: B_lam(r, 0.90)),
                  ("纯市场去水", lambda r: solve_lambda(r["mkt"], sum(r["lam"]))),
                  ("纯模型(无市场)", lambda r: r["lam"])):
    m = metrics(fn)
    print(f"{label:<26}{m[0]:>11.4f}{m[1]:>10.4f}{m[2]:>9.1f}%{m[3]:>13.4f}")

# ---------- 总进球标定 ----------
tot_act = sum(r["act"][0] + r["act"][1] for r in rows) / n
print()
print("=== 总进球标定 ===")
print(f"{'口径':<26}{'预测总量':>10}{'实际':>10}{'偏差':>10}")
print(f"{'实际':<26}{tot_act:>10.3f}{tot_act:>10.3f}{0.0:>+10.3f}")
for label, fn in (("A 现生产 λ空间 0.35", lambda r: A_lam(r, 0.35)),
                  ("A λ空间 0.80", lambda r: A_lam(r, 0.80)),
                  ("B 概率空间 0.80", lambda r: B_lam(r, 0.80))):
    m = sum(sum(fn(r)) for r in rows) / n
    print(f"{label:<26}{m:>10.3f}{tot_act:>10.3f}{m - tot_act:>+10.3f}")
