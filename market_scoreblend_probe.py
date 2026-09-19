#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""比分盘（正确比分市场）接入验证。

背景：数据里早已有完整比分盘（28~31 档），但引擎从未使用。1X2 去水只能
修正「方向」，比分盘还能修正「比分形态」（哪些比分概率被市场高估/低估）。

本脚本在「已启用概率空间混合 0.8」的基础上，再叠加比分盘去水分布：
  grid_final = (1-w) * grid_model + w * grid_market_score
对照指标：1X2 Brier、比分 Top3/Top5 覆盖命中率。

用法：python market_scoreblend_probe.py
"""
import glob
import importlib.util
import json
import math
import os

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
MK = eng.MARKET_W

hist, histH, histA = {}, {}, {}
rows = []
res = json.load(open(os.path.join(ROOT, "results_data.json"), encoding="utf-8"))
odds = {}
for f in sorted(glob.glob(os.path.join(ROOT, "odds_history", "*.json"))):
    if "index" in os.path.basename(f):
        continue
    try:
        odds.update(json.load(open(f, encoding="utf-8")).get("odds") or {})
    except Exception:  # noqa: BLE001
        pass

recs = []
for k, v in res.items():
    try:
        hg, ag = (int(x) for x in v["fullScore"].split(":"))
    except Exception:  # noqa: BLE001
        continue
    recs.append((k, hg, ag, v.get("home"), v.get("away"),
                 v.get("league") or v.get("leagueAbbr") or ""))
recs.sort(key=lambda r: r[0].split("_")[0])


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


def parse_score_market(d):
    """比分盘赔率 → 归一化比分分布（去水）。返回 {(h,a): p} 或 None"""
    out = {}
    extra = {0: 0.0, 1: 0.0, 2: 0.0}   # 胜其他/平其他/负其他 的 1/赔率 之和
    for k, v in (d or {}).items():
        try:
            iv = 1.0 / float(v)
        except Exception:  # noqa: BLE001
            continue
        if ":" in k:
            try:
                h, a = (int(x) for x in k.split(":"))
            except ValueError:
                continue
            out[(h, a)] = iv
        elif "其他" in k:
            q = 0 if "胜" in k else (1 if "平" in k else 2)
            extra[q] += iv
    if not out:
        return None
    s = sum(out.values()) + sum(extra.values())
    dist = {k: v / s for k, v in out.items()}
    return dist, {k: v / s for k, v in extra.items()}


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
    sm = parse_score_market(o.get("比分"))
    rows.append({"act": (hg, ag), "lg": lg, "lam": lam, "raw": (oh, od, ol), "sm": sm})

n = len(rows)
n_sm = sum(1 for r in rows if r["sm"])
print(f"样本 {n} 场（有 1X2 赔率），其中带比分盘 {n_sm} 场（{n_sm/n*100:.1f}%）")


def final_lambda(r):
    """概率空间混合 0.8 → 与生产第四步同源"""
    lh, la = r["lam"]
    pv = eng.devig_1x2(*r["raw"])
    pm = eng.pois_1x2(lh, la)
    pb = [(1 - MK) * pm[i] + MK * pv[i] for i in range(3)]
    st = sum(pb)
    pb = [x / st for x in pb]
    return eng.prob_to_lambda(pb, lh + la)


def model_grid(lh, la, lg):
    g = {}
    for i in range(KMAX + 1):
        for j in range(KMAX + 1):
            g[(i, j)] = eng.pmf(i, lh) * eng.pmf(j, la)
    t = sum(g.values())
    g = {k: v / t for k, v in g.items()}
    lo, hi = min(lh, la), max(lh, la)
    ratio = (hi / lo) if lo > 1e-9 else 99.0
    return eng.mix_score_matrix(g, lg, ratio)


def blend_grid(g, sm, w):
    """把比分盘去水分布并入模型网格（只在比分盘覆盖的档位上做）"""
    dist, extra = sm
    if w <= 0:
        return g, w
    cov = sum(dist.values())
    out = {}
    for k, v in g.items():
        mv = dist.get(k, 0.0)
        out[k] = (1 - w * cov) * v + w * mv
    # 「其他」桶：按模型在同象限高分位的相对比例分摊
    for q, ev in extra.items():
        if ev <= 0:
            continue
        cand = {k: v for k, v in g.items()
                if (k[0] > k[1] if q == 0 else (k[0] == k[1] if q == 1 else k[0] < k[1]))
                and (k[0] + k[1]) >= 4}
        sc = sum(cand.values())
        if sc <= 0:
            continue
        for k, v in cand.items():
            out[k] = out.get(k, 0.0) + w * ev * v / sc
    t = sum(out.values())
    return {k: v / t for k, v in out.items()}, w


def evaluate(fn):
    b3 = t3 = t5 = cov3 = cov5 = 0.0
    m = 0
    for r in rows:
        g = fn(r)
        if g is None:
            continue
        m += 1
        P = (sum(v for k, v in g.items() if k[0] > k[1]),
             sum(v for k, v in g.items() if k[0] == k[1]),
             sum(v for k, v in g.items() if k[0] < k[1]))
        hg, ag = r["act"]
        y = (1.0 if hg > ag else 0.0, 1.0 if hg == ag else 0.0, 1.0 if hg < ag else 0.0)
        b3 += sum((P[i] - y[i]) ** 2 for i in range(3))
        top = [k for k, _ in sorted(g.items(), key=lambda x: -x[1])[:5]]
        if (hg, ag) in top[:3]:
            t3 += 1
        if (hg, ag) in top:
            t5 += 1
    return b3 / m, t3 / m * 100, t5 / m * 100, m


print()
print(f"{'口径':<38}{'1X2 Brier':>11}{'Top3命中':>10}{'Top5命中':>10}{'样本':>7}")


def mk(w):
    def fn(r):
        lh, la = final_lambda(r)
        g = model_grid(lh, la, r["lg"])
        if r["sm"] and w > 0:
            g, _ = blend_grid(g, r["sm"], w)
        return g
    return fn


for w in (0.0, 0.15, 0.3, 0.5):
    m = evaluate(mk(w))
    print(f"{'比分盘混合 w=' + format(w, '.2f'):<38}{m[0]:>11.4f}{m[1]:>9.1f}%{m[2]:>9.1f}%{m[3]:>7}")

# 仅比分盘覆盖的子集上对比（更公平）
sub = [r for r in rows if r["sm"]]
print(f"\n--- 仅带比分盘的 {len(sub)} 场子集 ---")
print(f"{'口径':<38}{'1X2 Brier':>11}{'Top3命中':>10}{'Top5命中':>10}")
for w in (0.0, 0.15, 0.3, 0.5):
    b3 = t3 = t5 = 0.0
    for r in sub:
        lh, la = final_lambda(r)
        g = model_grid(lh, la, r["lg"])
        if w > 0:
            g, _ = blend_grid(g, r["sm"], w)
        P = (sum(v for k, v in g.items() if k[0] > k[1]),
             sum(v for k, v in g.items() if k[0] == k[1]),
             sum(v for k, v in g.items() if k[0] < k[1]))
        hg, ag = r["act"]
        y = (1.0 if hg > ag else 0.0, 1.0 if hg == ag else 0.0, 1.0 if hg < ag else 0.0)
        b3 += sum((P[i] - y[i]) ** 2 for i in range(3))
        top = [k for k, _ in sorted(g.items(), key=lambda x: -x[1])[:5]]
        t3 += 1.0 if (hg, ag) in top[:3] else 0.0
        t5 += 1.0 if (hg, ag) in top else 0.0
    m = len(sub)
    print(f"{'比分盘混合 w=' + format(w, '.2f'):<38}{b3/m:>11.4f}{t3/m*100:>9.1f}%{t5/m*100:>9.1f}%")
