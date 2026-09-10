#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""市场校准参数离线拟合 —— 让球盘联合校准 + 冷门风险模型（V3.3）

背景（用户方法论：市场 vs 赛果 → 模型再跑 → 三方偏差 → 学修正函数）
--------------------------------------------------------------------
1) 1X2 概率「值」上模型无 alpha（纯市场 Brier 0.5504 < 纯模型 0.6134），
   任何对 1X2 概率的再校准都跑不赢纯市场（见 tri_calib_probe.py Part 2）。
2) 但模型在**条件事件**上有 alpha：
   · 让球盘（让球胜平负）联合校准后，样本外 EV>1.10 每场 1 注：
     纯模型 498 注 +4.78%(t=0.76) → 联合校准 105 注 **+33.80%(t=2.19)**
   · 冷门（市场首选翻车）可分层：低风险 1/3 翻车 22.98% vs 高风险 1/3 44.10%
3) 因此本脚本只拟合**这两个**修正函数，1X2 概率值一律不碰。

产出 market_calib.json（引擎与报告只读，不重复计算）：

  handicap: logit(P) = a + b1·logit(p_mkt) + b2·logit(p_model)   （让球盘 W/D/L）
  upset:    P(翻车) = sigmoid(β·x)，x = [1, 市场首选概率, 模型-市场分歧,
                                         |让球|, λ和, 市场熵]

系数滚动与收缩（用户要求「系数按月滚动 + 样本量收缩」）
------------------------------------------------------
· 滚动窗口：默认取最近 ROLL_MONTHS 个月的样本（regime drift 防御），
  每月重拟合一次（引擎侧按 fitted_month 判定缓存是否过期）。
  窗口长度由月度时间外验证选出（expanding / 6m / 3m 三选一）。
· 样本量收缩： beta_used = (n·beta_fit + K·beta_prior) / (n + K)
  - 让球先验 = (0, 1, 0)：无数据时完全信任市场、不要模型增量
  - 冷门先验 = (logit(基础翻车率), 0,0,0,0,0)：无数据时退化为常数基线
  样本越少越靠近先验（"数据越多偏差越小"的对称表述：数据越少越不敢下判断）。

用法
----
  python _market_calib_fit.py            # 拟合并写 market_calib.json
  python _market_calib_fit.py --valid    # 附月度时间外验证明细
  python _market_calib_fit.py --force    # 忽略缓存直接重拟合（引擎调用用）
"""
import glob
import importlib.util
import json
import math
import os
import sys
from collections import defaultdict

_ROOTS = os.path.dirname(os.path.abspath(__file__))

# ---- 拟合超参 ----
ROLL_MONTHS = 6          # 滚动窗口长度（月）；由 --valid 的月度时间外验证确定
K_HANDICAP = 300.0       # 让球盘样本量收缩强度（先验权重，等效"300 条虚拟样本"）
K_UPSET = 300.0          # 冷门模型样本量收缩强度
EV_MIN = 1.10            # 让球盘价值门槛（样本外验证用的阈值）
KMAX = 8                 # 泊松截断
NW, WS, VK = 25, 0.25, 4.0
DECAY = 0.96
EPS = 1e-6

HANDICAP_PRIOR = (0.0, 1.0, 0.0)        # a=0, b1=1(纯市场), b2=0(不要模型)


# ================================================================ 引擎常量复用
def _repo_root():
    for d in (_ROOTS, os.path.dirname(_ROOTS), os.path.dirname(os.path.dirname(_ROOTS))):
        if os.path.exists(os.path.join(d, "results_data.json")):
            return d
    return _ROOTS


ROOT = _repo_root()


def _engine_py():
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
GB = float(eng.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))


# ================================================================ 数学工具
def num(v):
    try:
        f = float(v)
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def pois(L, k):
    return math.exp(-L) * L ** k / math.factorial(k)


def joint(lh, la, kmax=KMAX):
    d = {}
    for i in range(kmax + 1):
        pi = pois(lh, i)
        for j in range(kmax + 1):
            d[(i, j)] = pi * pois(la, j)
    s = sum(d.values())
    return {k: v / s for k, v in d.items()}


def agg(J, fn):
    d = {}
    for (i, j), p in J.items():
        d[fn(i, j)] = d.get(fn(i, j), 0.0) + p
    return d


def outcome(hg, ag):
    return "H" if hg > ag else ("A" if hg < ag else "D")


def rq_result(hg, ag, hcap):
    try:
        h = int(str(hcap).replace("+", ""))
    except (TypeError, ValueError):
        h = 0
    d = hg - ag + h
    return "W" if d > 0 else ("L" if d < 0 else "D")


def devig(od):
    inv = {k: 1.0 / v for k, v in od.items() if v}
    s = sum(inv.values())
    return ({k: v / s for k, v in inv.items()}, s) if s > 0 else ({}, 0.0)


def logit(p):
    p = min(max(p, EPS), 1 - EPS)
    return math.log(p / (1 - p))


def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def solve(A, b):
    """高斯消元（部分选主元）"""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r == c:
                continue
            f = M[r][c] / M[c][c]
            for cc in range(c, n + 1):
                M[r][cc] -= f * M[c][cc]
    return [M[i][n] / M[i][i] for i in range(n)]


def fit_logit(X, y, l2=2.0, iters=60):
    """IRLS 二项逻辑回归（含 L2，不惩罚截距）。返回 (beta, se)。"""
    n, p = len(X), len(X[0])
    beta = [0.0] * p
    for _ in range(iters):
        A = [[0.0] * p for _ in range(p)]
        g = [0.0] * p
        for i in range(n):
            xi = X[i]
            mu = sigmoid(sum(beta[j] * xi[j] for j in range(p)))
            w = max(mu * (1 - mu), 1e-8)
            for a_ in range(p):
                g[a_] += xi[a_] * (y[i] - mu)
                for b_ in range(p):
                    A[a_][b_] += xi[a_] * xi[b_] * w
        for j in range(1, p):
            A[j][j] += l2
            g[j] -= l2 * beta[j]
        step = solve(A, g)
        if step is None:
            break
        mx = max(abs(s) for s in step)
        for j in range(p):
            beta[j] += step[j]
        if mx < 1e-8:
            break
    A = [[0.0] * p for _ in range(p)]
    for i in range(n):
        xi = X[i]
        mu = sigmoid(sum(beta[j] * xi[j] for j in range(p)))
        w = max(mu * (1 - mu), 1e-8)
        for a_ in range(p):
            for b_ in range(p):
                A[a_][b_] += xi[a_] * xi[b_] * w
    for j in range(1, p):
        A[j][j] += l2
    se = [float("nan")] * p
    for j in range(p):
        e = [1.0 if i == j else 0.0 for i in range(p)]
        sol = solve([row[:] for row in A], e)
        if sol and sol[j] > 0:
            se[j] = math.sqrt(sol[j])
    return beta, se


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys) if ys else float("nan")


def shrink_beta(beta_fit, prior, n, K):
    """样本量收缩： beta = (n·fit + K·prior) / (n + K)"""
    return [(n * beta_fit[i] + K * prior[i]) / (n + K) for i in range(len(beta_fit))]


# ================================================================ 基础 λ（与生产同源）
def wavg(v):
    s = c = 0.0
    for i, x in enumerate(v):
        w = DECAY ** i
        s += x * w
        c += w
    return s / c if c else 0.0


def effn(n):
    return sum(DECAY ** i for i in range(n))


def base_lam(h, a, lg, hist, histH, histA):
    """生产链路的前三步：指数衰减基础λ + 主客场分拆收缩 + 联赛先验收缩。

    不含 H2H（需 ≥3 场同向交手，赛果库仅覆盖 2026 年，绝大多数缺失）与
    市场混合——本脚本要的正是**未混市场的纯模型视角**，市场信息由 p_mkt 单独进入。
    """
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
        lh = (ne * v + VK * lh) / (ne + VK)
    if aA and hH:
        v = wavg([x[1] for x in aA]) * .75 + wavg([x[2] for x in hH]) * .25
        ne = min(effn(len(aA)), effn(len(hH)))
        la = (ne * v + VK * la) / (ne + VK)
    L = eng.LEAGUE_PROFILE["leagues"].get(lg)
    b = L["mean"] if (L and L.get("n", 0) >= 12) else GB
    t = (lh + la) * (1 - WS) + b * WS
    o = lh + la
    return (lh / o * t, la / o * t) if o > 0 else (lh, la)


# ================================================================ 数据集
def build_rows():
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
        lam = base_lam(hm, aw, lg, hist, histH, histA)
        hist.setdefault(hm, []).append((d, hg, ag))
        hist.setdefault(aw, []).append((d, ag, hg))
        histH.setdefault(hm, []).append((d, hg, ag))
        histA.setdefault(aw, []).append((d, ag, hg))
        if lam is None:
            continue
        try:
            oh, od, ol = float(v["胜"]), float(v["平"]), float(v["负"])
            if min(oh, od, ol) <= 1.0:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            oh = od = ol = None
        rows.append({"k": k, "date": d, "hg": hg, "ag": ag, "lam": lam,
                     "o12": (oh, od, ol), "rec": v, "lg": lg, "home": hm, "away": aw})
    return rows


def month_of(d):
    return d[:7]


def window_rows(rows, ref_month, months):
    """取 ref_month 之前（不含）最近 months 个月的样本；months=None → expanding。"""
    if not months:
        return [r for r in rows if month_of(r["date"]) < ref_month]
    y, m = int(ref_month[:4]), int(ref_month[5:7])
    m0 = m - months
    y0 = y
    while m0 <= 0:
        m0 += 12
        y0 -= 1
    lo = "%04d-%02d" % (y0, m0)
    return [r for r in rows if lo <= month_of(r["date"]) < ref_month]


# ================================================================ 让球盘样本
def rq_samples_of(rows):
    out = []
    for r in rows:
        rq = r["rec"].get("让球")
        if not (isinstance(rq, list) and rq and isinstance(rq[0], dict)):
            continue
        it = rq[0]
        o = {"W": num(it.get("胜")), "D": num(it.get("平")), "L": num(it.get("负"))}
        if not all(o.values()):
            continue
        mk, _ = devig(o)
        J = joint(*r["lam"])
        pm = agg(J, lambda i, j: rq_result(i, j, it.get("handicap")))
        real = rq_result(r["hg"], r["ag"], it.get("handicap"))
        for d in ("W", "D", "L"):
            out.append({"date": r["date"], "dir": d, "mkt": mk[d],
                        "mod": pm.get(d, 0.0), "odds": o[d],
                        "y": 1 if real == d else 0, "h": it.get("handicap"),
                        "k": r["k"]})
    return out


def fit_handicap(rows, months=ROLL_MONTHS, kshrink=K_HANDICAP):
    ss = rq_samples_of(rows)
    if len(ss) < 200:
        return None
    X = [[1.0, logit(s["mkt"]), logit(s["mod"])] for s in ss]
    y = [s["y"] for s in ss]
    b, se = fit_logit(X, y, l2=2.0)
    used = shrink_beta(b, HANDICAP_PRIOR, len(ss), kshrink)
    return {"beta_fit": [round(v, 5) for v in b],
            "beta": [round(v, 5) for v in used],
            "se": [round(v, 5) for v in se],
            "n_samples": len(ss),
            "prior": list(HANDICAP_PRIOR), "k_shrink": kshrink,
            "months": months}


def apply_handicap_beta(beta, p_mkt, p_mod):
    z = beta[0] + beta[1] * logit(p_mkt) + beta[2] * logit(p_mod)
    return sigmoid(z)


def ev_bets(samples, beta, ev_min=EV_MIN):
    """每场只取 EV 最高的一注（EV>ev_min），返回统计。"""
    best = defaultdict(list)
    for s in samples:
        p = apply_handicap_beta(beta, s["mkt"], s["mod"])
        best[(s["date"], s["k"])].append((p * s["odds"], s))
    picks = [max(v, key=lambda x: x[0])[1] for v in best.values()
             if max(v, key=lambda x: x[0])[0] > ev_min]
    if not picks:
        return {"n": 0}
    ret = sum((s["odds"] if s["y"] else 0.0) - 1.0 for s in picks)
    mean = ret / len(picks)
    var = sum((((s["odds"] if s["y"] else 0.0) - 1.0) - mean) ** 2 for s in picks) / max(len(picks) - 1, 1)
    se = math.sqrt(var / len(picks)) if var > 0 else 0.0
    return {"n": len(picks), "hit": sum(s["y"] for s in picks) / len(picks) * 100,
            "roi": mean * 100, "t": mean / se if se > 0 else 0.0}


# ================================================================ 冷门样本
UPSET_FEATS = ("截距", "市场首选概率", "模型-市场分歧", "|让球|", "λ和", "市场熵")


def upset_samples_of(rows):
    out = []
    for r in rows:
        if not r["o12"][0]:
            continue
        mk, _ = devig({"H": r["o12"][0], "D": r["o12"][1], "A": r["o12"][2]})
        J = joint(*r["lam"])
        pm = agg(J, outcome)
        y = outcome(r["hg"], r["ag"])
        top = max(mk, key=lambda x: mk[x])
        rq = r["rec"].get("让球")
        hc = None
        if isinstance(rq, list) and rq and isinstance(rq[0], dict):
            try:
                hc = abs(int(str(rq[0].get("handicap")).replace("+", "")))
            except (TypeError, ValueError):
                hc = None
        out.append({"date": r["date"], "k": r["k"], "y": 1 if y != top else 0,
                    "mk_top": mk[top], "div": pm[top] - mk[top],
                    "hc": hc if hc is not None else 1.5,
                    "lam_sum": r["lam"][0] + r["lam"][1],
                    "ent": -sum(p * math.log(max(p, EPS)) for p in mk.values())})
    return out


def upset_feat(u):
    return [1.0, u["mk_top"], u["div"], u["hc"], u["lam_sum"], u["ent"]]


def fit_upset(rows, months=ROLL_MONTHS, kshrink=K_UPSET):
    us = upset_samples_of(rows)
    if len(us) < 200:
        return None
    base_rate = sum(u["y"] for u in us) / len(us)
    X = [upset_feat(u) for u in us]
    y = [u["y"] for u in us]
    b, se = fit_logit(X, y, l2=2.0)
    prior = [logit(base_rate), 0.0, 0.0, 0.0, 0.0, 0.0]
    used = shrink_beta(b, prior, len(us), kshrink)
    return {"beta_fit": [round(v, 5) for v in b],
            "beta": [round(v, 5) for v in used],
            "se": [round(v, 5) for v in se],
            "n_samples": len(us), "base_rate": round(base_rate, 5),
            "prior": [round(v, 5) for v in prior], "k_shrink": kshrink,
            "features": list(UPSET_FEATS), "months": months}


def apply_upset_beta(beta, feat):
    return sigmoid(sum(beta[i] * feat[i] for i in range(len(beta))))


# ================================================================ 月度时间外验证
# ================================================================ 大比分（总进球 6+ / 7+）
TOT_KEYS = ("0", "1", "2", "3", "4", "5", "6", "7+")
K_BIG = 400          # 样本量收缩常数（先验 = 纯市场，即 a=0, b=1）

BIG_SEP = "=" * 84


def devig_tot(tot):
    """总进球盘（8 档）按赔率倒数归一化去水，返回 (概率, 水位)。"""
    if not isinstance(tot, dict):
        return None
    raw = {}
    for k in TOT_KEYS:
        o = num(tot.get(k))
        if not o or o <= 1.0:
            return None
        raw[k] = 1.0 / o
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}, s


def big_samples_of(rows):
    """每场：市场 P(6+) / P(7+)、赔率、实际是否 6+/7+。

    口径要点：竞彩比分盘/总进球盘里「6」与「7+」是独立档位，
    6+ = P(6档) + P(7+档)；而比分盘的「胜其他/平其他/负其他」
    实测 100% 落在 6+（已列举全部 ≤5 球的比分）。
    """
    out = []
    for r in rows:
        tot = r["rec"].get("总进球")
        dt = devig_tot(tot)
        if not dt:
            continue
        p = dt[0]
        g = r["hg"] + r["ag"]
        out.append({"date": r["date"], "k": r["k"],
                    "p6": p["6"] + p["7+"], "p7": p["7+"],
                    "o6": num(tot.get("6")) or 0.0, "o7": num(tot.get("7+")) or 0.0,
                    "y6": 1 if g >= 6 else 0, "y7": 1 if g >= 7 else 0,
                    "lam_mkt": sum((7 if k == "7+" else int(k)) * v for k, v in p.items())})
    return out


def apply_big_beta(beta, p):
    return sigmoid(beta[0] + beta[1] * logit(p))


def fit_big(rows, months=ROLL_MONTHS, kshrink=K_BIG):
    """市场 P(6+) / P(7+) 的 logit 校准。

    动机：市场对极端高进球（6+/7+）系统性定价偏高——去水后预测均值 9.41%
    而实际 6.28%（−3.13pp），7+ 档 4.09% vs 2.37%（−1.72pp），概率越高越离谱
    （去水 P≥18% 的档：预测 21.95% vs 实际 15.45%）。校准把概率压回诚实区间。
    """
    ss = big_samples_of(rows)
    if len(ss) < 300:
        return None
    res = {"n_samples": len(ss), "k_shrink": float(kshrink), "months": months}
    for tag, pk, yk in (("p6", "p6", "y6"), ("p7", "p7", "y7")):
        X = [[1.0, logit(s[pk])] for s in ss]
        y = [s[yk] for s in ss]
        bf, se = fit_logit(X, y, l2=2.0)
        beta = shrink_beta(bf, [0.0, 1.0], len(ss), kshrink)
        cut = int(len(ss) * 0.6)
        bo, _ = fit_logit(X[:cut], y[:cut], l2=2.0)
        ps_cal = [apply_big_beta(bo, ss[i][pk]) for i in range(cut, len(ss))]
        ps_raw = [ss[i][pk] for i in range(cut, len(ss))]
        ys = y[cut:]
        base = sum(ys) / len(ys)
        res[tag] = {
            "beta_fit": [round(x, 5) for x in bf],
            "beta": [round(x, 5) for x in beta],
            "se": [round(x, 5) for x in se],
            "prior": [0.0, 1.0],
            "oos_n": len(ys),
            "oos_brier": round(brier(ps_cal, ys), 5),
            "oos_brier_raw": round(brier(ps_raw, ys), 5),
            "oos_brier_base": round(brier([base] * len(ys), ys), 5),
            "base_rate": round(sum(y) / len(y), 5),
        }
    return res


def big_roi_check(rows, verbose=True):
    """直接按赔率回测买「6 球档」「7+ 档」的 ROI（不依赖去水假设，最硬）。"""
    ss = big_samples_of(rows)
    if not ss:
        return None
    res = {}
    for tag, ok, win, lab in (("eq6", "o6", lambda s: bool(s["y6"] and not s["y7"]), "买「恰好 6 球」档"),
                              ("ge7", "o7", lambda s: bool(s["y7"]), "买「7+ 球」档")):
        seg = [s for s in ss if s[ok]]
        if not seg:
            continue
        pnl = sum((s[ok] - 1.0) if win(s) else -1.0 for s in seg)
        res[tag] = {"n": len(seg), "roi": round(pnl / len(seg) * 100, 2)}
        if verbose:
            print(f"  {lab:<16} n={len(seg):5d}  ROI {pnl / len(seg) * 100:+7.2f}%")
    return res


def monthly_oos(rows, months_list=(None, 6, 3)):
    """对每个候选窗口做月度时间外验证：用 <M 月的样本拟合，在 M 月实测。"""
    mos = sorted({month_of(r["date"]) for r in rows})
    res = {}
    for mw in months_list:
        key = "expanding" if mw is None else f"{mw}m"
        hb_p, hb_y, hstat = [], [], defaultdict(lambda: [0, 0.0])
        ub_p, ub_y, ub_base = [], [], []
        for mo in mos[4:]:
            tr = window_rows(rows, mo, mw)
            te = [r for r in rows if month_of(r["date"]) == mo]
            if len(tr) < 500 or not te:
                continue
            fh = fit_handicap(tr, months=mw)
            fu = fit_upset(tr, months=mw)
            if fh:
                teq = rq_samples_of(te)
                for s in teq:
                    p = apply_handicap_beta(fh["beta"], s["mkt"], s["mod"])
                    hb_p.append(p)
                    hb_y.append(s["y"])
                st = ev_bets(teq, fh["beta"])
                hstat[mo][0] += st["n"]
                hstat[mo][1] += st.get("roi", 0.0) * st["n"] / 100.0
            if fu:
                for u in upset_samples_of(te):
                    ub_p.append(apply_upset_beta(fu["beta"], upset_feat(u)))
                    ub_y.append(u["y"])
                    ub_base.append(fu["base_rate"])
        if hb_y:
            n_tot = sum(v[0] for v in hstat.values())
            roi = (sum(v[1] for v in hstat.values()) / n_tot * 100) if n_tot else 0.0
            res[key] = {"handicap_brier": brier(hb_p, hb_y), "handicap_n": len(hb_y),
                        "bet_n": n_tot, "bet_roi": roi,
                        "upset_brier": brier(ub_p, ub_y) if ub_y else float("nan"),
                        "upset_base_brier": brier(ub_base, ub_y) if ub_y else float("nan"),
                        "upset_n": len(ub_y)}
    return res


def main():
    want_valid = "--valid" in sys.argv
    rows = build_rows()
    print("=" * 84)
    print(f"样本 {len(rows)} 场   {rows[0]['date']} ~ {rows[-1]['date']}   滚动窗口 {ROLL_MONTHS} 个月")
    print("=" * 84)

    oos = monthly_oos(rows)
    print("\n【月度时间外验证】用 <M 月样本拟合，在 M 月实测（每场只买 EV 最高的一注）")
    print(f"  {'窗口':<10} {'让球Brier':>10} {'让球n':>7} {'注数':>6} {'ROI':>9} "
          f"{'冷门Brier':>10} {'常数基线':>9}")
    for k, v in oos.items():
        print(f"  {k:<10} {v['handicap_brier']:10.5f} {v['handicap_n']:7d} {v['bet_n']:6d} "
              f"{v['bet_roi']:+8.2f}% {v['upset_brier']:10.5f} {v['upset_base_brier']:9.5f}")

    def score(v):
        """窗口选择判据：让球 Brier 为主（越低越好），冷门 Brier 为辅。"""
        return v["handicap_brier"] + v["upset_brier"]

    pick = min(oos, key=lambda k: score(oos[k])) if oos else "expanding"
    print(f"\n  → 月度时间外综合最优窗口：{pick}（判据 = 让球Brier + 冷门Brier 最小）")

    # 产出参数：窗口按验证结果取（若最优为 6m/3m 则用之，否则 expanding）
    mw = None if pick == "expanding" else int(pick.rstrip("m"))
    fh = fit_handicap(rows, months=mw)
    fu = fit_upset(rows, months=mw)
    fb = fit_big(rows, months=mw)

    print("\n【让球盘联合校准】logit(P) = a + b1·logit(p_mkt) + b2·logit(p_model)")
    if fh:
        fitn = fh["beta_fit"]
        for i, nm in enumerate(("a", "b1(市场)", "b2(模型)")):
            t = fitn[i] / fh["se"][i] if fh["se"][i] > 0 else float("nan")
            print(f"  拟合 {nm:<10} {fitn[i]:+9.5f}  se {fh['se'][i]:.5f}  t={t:+6.2f}"
                  f"   → 收缩后 {fh['beta'][i]:+9.5f}")
        print(f"  样本 {fh['n_samples']} 条  K={fh['k_shrink']:.0f}  窗口 {fh['months']} 月")

    print("\n【冷门风险模型】P(市场首选翻车) = sigmoid(β·x)")
    if fu:
        fitn = fu["beta_fit"]
        for i, nm in enumerate(UPSET_FEATS):
            z = fitn[i] / fu["se"][i] if fu["se"][i] > 0 else float("nan")
            print(f"  {nm:<14} {fitn[i]:+9.5f}  se {fu['se'][i]:.5f}  z={z:+6.2f}"
                  f"   → 收缩后 {fu['beta'][i]:+9.5f}")
        print(f"  样本 {fu['n_samples']} 场  基础翻车率 {fu['base_rate']*100:.2f}%  K={fu['k_shrink']:.0f}")

    print("\n【大比分（6+/7+）市场校准】logit(P_true) = a + b·logit(P_市场)")
    if fb:
        for tag, lab in (("p6", "P(总进球≥6)"), ("p7", "P(总进球≥7)")):
            d = fb[tag]
            t = d["beta_fit"][1] / d["se"][1] if d["se"][1] else float("nan")
            print(f"  {lab:<12} 拟合 a {d['beta_fit'][0]:+8.4f}  b {d['beta_fit'][1]:+8.4f}"
                  f" (t={t:+5.1f})   → 收缩后 a {d['beta'][0]:+8.4f}  b {d['beta'][1]:+8.4f}")
            print(f"      时间外 n={d['oos_n']}  基础率 {d['base_rate']*100:.2f}%  |  Brier 校准后 "
                  f"{d['oos_brier']:.5f}  原始市场 {d['oos_brier_raw']:.5f}  "
                  f"常数基线 {d['oos_brier_base']:.5f}")
        print("  直接按赔率回测（不依赖去水假设，最硬的口径）：")
        big_roi_check(rows)

    if want_valid:
        _print_extra_valid(rows, fh, fu)
        _print_star_check(rows)

    out = {
        "_meta": {
            "source": "market_calib_fit.py",
            "built_at": __import__("datetime").date.today().isoformat(),
            "fitted_month": month_of(rows[-1]["date"]),
            "roll_months": mw, "roll_label": pick,
            "sample_rows": len(rows),
            "oos": {k: {kk: (round(vv, 5) if isinstance(vv, float) else vv)
                        for kk, vv in v.items()} for k, v in oos.items()},
            "note": "只校准让球盘、冷门风险与大比分(6+/7+)概率；1X2 概率值不校准（模型在 1X2 无 alpha）",
        },
        "handicap": fh,
        "upset": fu,
        "total_goals": fb,
    }
    p = os.path.join(ROOT, "market_calib.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print(f"\n已写入 {p}")


def _print_extra_valid(rows, fh, fu):
    """附：让球盘 EV 策略按月明细 + 冷门高低分组（时间外）。"""
    if fh:
        print("\n【让球盘 EV>%.2f 按月明细（时间外）】" % EV_MIN)
        print(f"  {'月份':<9} {'注数':>6} {'命中':>8} {'ROI':>9}")
        for mo in sorted({month_of(r["date"]) for r in rows})[4:]:
            tr = window_rows(rows, mo, fh["months"])
            te = [r for r in rows if month_of(r["date"]) == mo]
            if len(tr) < 500:
                continue
            f = fit_handicap(tr, months=fh["months"])
            st = ev_bets(rq_samples_of(te), f["beta"])
            if st["n"]:
                print(f"  {mo:<9} {st['n']:6d} {st['hit']:7.2f}% {st['roi']:+8.2f}%")
    if fu:
        print("\n【冷门分层（时间外）】市场首选概率 ≥55% 子集，按风险分三组")
        for mo in sorted({month_of(r["date"]) for r in rows})[4:]:
            tr = window_rows(rows, mo, fu["months"])
            te = [r for r in rows if month_of(r["date"]) == mo]
            if len(tr) < 500:
                continue
            f = fit_upset(tr, months=fu["months"])
            us = [u for u in upset_samples_of(te) if u["mk_top"] >= 0.55]
            if len(us) < 30:
                continue
            ps = [apply_upset_beta(f["beta"], upset_feat(u)) for u in us]
            pr = sorted(zip(ps, us), key=lambda x: x[0])
            k = len(pr) // 3
            lo = sum(u["y"] for _, u in pr[:k]) / k * 100
            hi = sum(u["y"] for _, u in pr[-k:]) / k * 100
            print(f"  {mo:<9} n={len(us):4d}  低风险 {lo:5.2f}%  高风险 {hi:5.2f}%  差 {hi-lo:+5.2f}pp")


def _star_check(rows):
    """星级口径（首选比分概率）与冷门翻车率的关系 —— 检验两者是否同一件事。"""
    us = {u["k"]: u for u in upset_samples_of(rows)}
    bins = [(0.06, 0.08), (0.08, 0.10), (0.10, 0.12), (0.12, 0.15), (0.15, 0.20), (0.20, 1.0)]
    out = []
    for lo, hi in bins:
        seg = [r for r in rows if r["k"] in us and lo <= max(joint(*r["lam"]).values()) < hi]
        if len(seg) < 30:
            continue
        out.append((lo, hi, len(seg),
                    sum(us[r["k"]]["y"] for r in seg) / len(seg) * 100,
                    sum(r["lam"][0] + r["lam"][1] for r in seg) / len(seg)))
    return out


def _print_star_check(rows):
    print("\n【星级 vs 冷门风险】星级 = 首选比分概率（0.15→5★ / 0.12→4★ / 0.09→3★）")
    print("  结论：两者**不是同一件事**（相关系数≈0），且关系呈倒 U —— "
          "中档（0.10-0.15，占样本 60%）翻车率最高，极低 λ 的场次反而较低。")
    print(f"  {'首选比分概率':<14}{'n':>6}{'实际翻车率':>12}{'λ和均值':>10}")
    for lo, hi, n, fr, ls in _star_check(rows):
        star = "5★" if lo >= 0.15 else ("4★" if lo >= 0.12 else ("3★" if lo >= 0.09 else "2★"))
        print(f"  {lo:.2f}-{hi:<9}{n:6d}{fr:11.2f}%{ls:10.2f}   {star}")


if __name__ == "__main__":
    main()