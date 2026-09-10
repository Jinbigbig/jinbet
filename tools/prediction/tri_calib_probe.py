#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""三方联合校准探针：市场 × 模型 × 赛果 → 可学习的修正函数

用户逻辑（要验证的三步）
----------------------
1) 市场 vs 赛果      → 市场定价的系统性偏差（校准曲线）
2) 模型 + 市场 vs 赛果 → 三方偏差（模型相对市场有没有增量）
3) 学出修正映射 p_hat = f(p_mkt, p_model)，让预测向真实频率趋同；
   样本越多，偏差越小（= 校准参数的收缩/在线更新）
4) 冷门路线：稀有事件频率、影响因素

方法
----
方向级样本，logit 线性修正：

    logit(p_hat) = a + b1 * logit(p_mkt) + b2 * logit(p_model)

  · b1 = 市场定价的校准斜率（>1 市场过度自信，<1 市场过度保守）
  · b2 = 模型能否提供增量（显著 >0 才有 alpha；≈0 说明模型无用）
  · a  = 整体水位（去水残留）

判据：按日期前 60% 拟合 / 后 40% 样本外验证。
对比对象：纯市场 / 纯模型 / 生产@0.80 / 联合校准。

冷门（upset）定义与特征见 Part 4。

用法： python tri_calib_probe.py
"""
import glob
import importlib.util
import json
import math
import os
import sys
from collections import defaultdict

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _repo_root():
    for d in (_ROOT, os.path.dirname(_ROOT), os.path.dirname(os.path.dirname(_ROOT))):
        if os.path.exists(os.path.join(d, "results_data.json")):
            return d
    return _ROOT


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

KMAX = 8
DECAY, NW, WS, VK = 0.96, 25, 0.25, 4.0
GB = float(eng.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))
EPS = 1e-6


def num(v):
    try:
        f = float(v)
        return f if f > 1.0 else None
    except Exception:  # noqa: BLE001
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


def devig(od):
    inv = {k: 1.0 / v for k, v in od.items() if v}
    s = sum(inv.values())
    return {k: v / s for k, v in inv.items()}, s


def logit(p):
    p = min(max(p, EPS), 1 - EPS)
    return math.log(p / (1 - p))


def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def solve(A, b):
    """高斯消元（带部分选主元）"""
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


def fit_logit(X, y, l2=1.0, iters=60):
    """IRLS 拟合二项逻辑回归（含 L2，不惩罚截距）。返回 (beta, se)。"""
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
        for j in range(p):
            g[j] -= 0.0 if j == 0 else 0.0
        for j in range(p):
            A[j][j] += 0.0 if j == 0 else l2
            g[j] -= 0.0 if j == 0 else l2 * beta[j]
        step = solve(A, g)
        if step is None:
            break
        mx = max(abs(s) for s in step)
        for j in range(p):
            beta[j] += step[j]
        if mx < 1e-8:
            break
    # 协方差 = (X'WX)^-1
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
        if sol:
            se[j] = math.sqrt(sol[j]) if sol[j] > 0 else float("nan")
    return beta, se


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def logloss(ps, ys):
    return -sum(math.log(max(min(p, 1 - EPS), EPS)) if y else math.log(max(1 - min(p, 1 - EPS), EPS))
                for p, y in zip(ps, ys)) / len(ys)


# ---------------- 基础 λ（生产同源，walk-forward） ----------------
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


# ---------------- 载入 ----------------
hist_lib = {}
for f in sorted(glob.glob(os.path.join(ROOT, "results_history", "*.json"))):
    if "index" in os.path.basename(f):
        continue
    try:
        hist_lib.update(json.load(open(f, encoding="utf-8")))
    except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
        oh = od = ol = None
    rows.append({"k": k, "date": k.split("_")[0], "hg": hg, "ag": ag, "lam": lam,
                 "o12": (oh, od, ol), "rec": v, "lg": lg, "home": hm, "away": aw})

dates = sorted({r["date"] for r in rows})
MED = dates[int(len(dates) * 0.6)]
print("=" * 82)
print(f"样本 {len(rows)} 场   {dates[0]} ~ {dates[-1]}   切分点 {MED}（前 60% 拟合 / 后 40% 验证）")
print("=" * 82)

# 方向级样本：(date, dir, p_mkt, p_model, y)
samples = []
for r in rows:
    if not r["o12"][0]:
        continue
    mk, _ = devig({"H": r["o12"][0], "D": r["o12"][1], "A": r["o12"][2]})
    J = joint(*r["lam"])
    pm = agg(J, outcome)
    y = outcome(r["hg"], r["ag"])
    for d in ("H", "D", "A"):
        samples.append({"date": r["date"], "r": r, "dir": d,
                        "mkt": mk[d], "mod": pm[d], "y": 1 if y == d else 0})

print(f"\n方向级样本 {len(samples)} 条（{len(samples) // 3} 场 × 3 方向）")

# ================= Part 1. 市场 vs 赛果：校准曲线 =================
print("\n" + "=" * 82)
print("Part 1  市场 vs 赛果 —— 市场隐含概率 vs 实际频率（等频分箱）")
print("=" * 82)


def calib_table(items, key, nbin=10, label=""):
    items = sorted(items, key=lambda x: x[key])
    n = len(items)
    print(f"\n  {label}（n={n}）")
    print("    档位        样本   隐含均值   实际频率     偏差")
    for b in range(nbin):
        lo, hi = n * b // nbin, n * (b + 1) // nbin
        seg = items[lo:hi]
        pm = sum(x[key] for x in seg) / len(seg)
        fr = sum(x["y"] for x in seg) / len(seg)
        # 二项标准误
        se = math.sqrt(max(pm * (1 - pm), 1e-9) / len(seg))
        z = (fr - pm) / se
        flag = "  <<<" if abs(z) > 2 else ""
        print(f"    {lo / n * 100:3.0f}-{hi / n * 100:3.0f}%   {len(seg):6d}   {pm * 100:7.2f}%   {fr * 100:7.2f}%   {(fr - pm) * 100:+6.2f}pp (z={z:+5.2f}){flag}")


calib_table(samples, "mkt", label="全部方向")
for d, nm in (("H", "主胜"), ("D", "平局"), ("A", "客胜")):
    calib_table([s for s in samples if s["dir"] == d], "mkt", label=f"{nm}方向")

# ================= Part 2. 三方联合校准 =================
print("\n" + "=" * 82)
print("Part 2  三方联合校准 —— logit(p) = a + b1·logit(p_mkt) + b2·logit(p_model)")
print("=" * 82)

tr = [s for s in samples if s["date"] < MED]
te = [s for s in samples if s["date"] >= MED]


def build(ss):
    X = [[1.0, logit(s["mkt"]), logit(s["mod"])] for s in ss]
    y = [s["y"] for s in ss]
    return X, y


Xtr, ytr = build(tr)
Xt, yt = build(te)
beta, se = fit_logit(Xtr, ytr, l2=2.0)
names = ("截距 a", "b1·logit(市场)", "b2·logit(模型)")
print("\n  【A】全方向联合拟合（前 60%）")
for i, nm in enumerate(names):
    t = beta[i] / se[i] if se[i] == se[i] and se[i] > 0 else float("nan")
    sig = "***" if abs(t) > 3 else ("**" if abs(t) > 2 else ("*" if abs(t) > 1.6 else ""))
    print(f"    {nm:<16} 系数 {beta[i]:+8.4f}   se {se[i]:.4f}   t={t:+6.2f} {sig}")

print("\n  【B】分方向拟合（前 60%）")
by_dir = {}
for d, nm in (("H", "主胜"), ("D", "平局"), ("A", "客胜")):
    Xd, yd = build([s for s in tr if s["dir"] == d])
    bd, sd = fit_logit(Xd, yd, l2=2.0)
    by_dir[d] = bd
    print(f"    {nm}:  a={bd[0]:+7.4f}  b1(市场)={bd[1]:+7.4f} (t={bd[1] / sd[1]:+5.2f})"
          f"   b2(模型)={bd[2]:+7.4f} (t={bd[2] / sd[2]:+5.2f})")


def predict_simple(s):
    return s["mkt"], s["mod"]


def predict_prod(s):
    return 0.8 * s["mkt"] + 0.2 * s["mod"], None


print(f"\n  【C】样本外验证（后 40%，n={len(te)} 方向）")
print(f"    {'方案':<30} {'Brier':>9} {'LogLoss':>10} {'方向命中':>9}")
base_m = [s["mkt"] for s in te]
base_o = [s["mod"] for s in te]
ytl = [s["y"] for s in te]
prod = [0.8 * s["mkt"] + 0.2 * s["mod"] for s in te]
joint_ps = [sigmoid(beta[0] + beta[1] * logit(s["mkt"]) + beta[2] * logit(s["mod"])) for s in te]
Xtr_m = [[1.0, logit(s["mkt"])] for s in tr]
bm, sm = fit_logit(Xtr_m, ytr, l2=2.0)
only_mkt = [sigmoid(bm[0] + bm[1] * logit(s["mkt"])) for s in te]
Xtr_o = [[1.0, logit(s["mod"])] for s in tr]
bo, so = fit_logit(Xtr_o, ytr, l2=2.0)
only_mod = [sigmoid(bo[0] + bo[1] * logit(s["mod"])) for s in te]


def hit_rate(ps, ss):
    """按 3 方向分组，每组取最大者为预测方向，与真实比"""
    g = defaultdict(dict)
    for p, s in zip(ps, ss):
        g[(s["date"], s["r"]["k"])][s["dir"]] = p
    ok = tot = 0
    for key, dd in g.items():
        if len(dd) < 3:
            continue
        tot += 1
        pick = max(dd, key=lambda x: dd[x])
        y = next(s["y"] for s in ss if (s["date"], s["r"]["k"]) == key and s["dir"] == pick)
        ok += y
    return ok / tot * 100 if tot else float("nan")


for lab, ps in (("纯市场（去水）", base_m),
                ("纯模型", base_o),
                ("生产 @0.80 线性", prod),
                ("只校准市场", only_mkt),
                ("只校准模型", only_mod),
                ("联合校准（市场+模型）", joint_ps)):
    print(f"    {lab:<30} {brier(ps, ytl):9.5f} {logloss(ps, ytl):10.5f} {hit_rate(ps, te):8.2f}%")

print("\n  【D】b2（模型增量）在不同盘口/子集是否稳定 —— 分月滚动拟合 b2")
bym = defaultdict(list)
for s in samples:
    bym[s["date"][:7]].append(s)
print(f"    {'月份':<9} {'n':>6} {'b1 市场':>9} {'b2 模型':>9} {'t(b2)':>7}")
for mo in sorted(bym):
    ss = bym[mo]
    if len(ss) < 300:
        continue
    Xm, ym = build(ss)
    bb, sse = fit_logit(Xm, ym, l2=2.0)
    tb2 = bb[2] / sse[2] if sse[2] == sse[2] and sse[2] > 0 else float("nan")
    print(f"    {mo:<9} {len(ss):6d} {bb[1]:+9.4f} {bb[2]:+9.4f} {tb2:+7.2f}")

# ================= Part 2.5 偏差查表 + 收缩 =================
print("\n" + "=" * 82)
print("Part 2.5  偏差查表 + 样本量收缩（『数据越多偏差越小』的直接实现）")
print("=" * 82)
print("  p_adj = (n_bin·freq_bin + K·p_mkt) / (n_bin + K)   K=0 完全不信任市场")


def bin_of(p, nb):
    return min(int(p * nb), nb - 1)


best_tbl = None
for scope in ("全局", "分方向"):
    for nb in (5, 10, 20):
        tbl = defaultdict(lambda: [0, 0.0])
        for s in tr:
            key = bin_of(s["mkt"], nb) if scope == "全局" else (s["dir"], bin_of(s["mkt"], nb))
            tbl[key][0] += 1
            tbl[key][1] += s["y"]
        for K in (0.0, 20.0, 50.0, 100.0, 300.0):
            adj = []
            for s in te:
                key = bin_of(s["mkt"], nb) if scope == "全局" else (s["dir"], bin_of(s["mkt"], nb))
                n, yy = tbl[key]
                if n == 0:
                    adj.append(s["mkt"])
                    continue
                adj.append((n * (yy / n) + K * s["mkt"]) / (n + K))
            br = brier(adj, ytl)
            tag = ""
            if best_tbl is None or br < best_tbl[0]:
                best_tbl = (br, scope, nb, K)
                tag = "  <<< 当前最优"
            print(f"    {scope:<5} 分箱 {nb:2d}  K={K:5.0f}   Brier {br:.5f}"
                  f"   LogLoss {logloss(adj, ytl):.5f}   命中 {hit_rate(adj, te):6.2f}%{tag}")
print(f"  → 最优：{best_tbl[1]} 分箱{best_tbl[2]} K={best_tbl[3]:.0f}  Brier {best_tbl[0]:.5f}"
      f"（纯市场 {brier(base_m, ytl):.5f}，生产@0.80 {brier(prod, ytl):.5f}）")

# ================= Part 3. 让球盘联合校准 =================
print("\n" + "=" * 82)
print("Part 3  让球盘联合校准（模型在这里有 alpha）")
print("=" * 82)


def rq_result(hg, ag, hcap):
    try:
        h = int(str(hcap).replace("+", ""))
    except Exception:  # noqa: BLE001
        h = 0
    d = hg - ag + h
    return "W" if d > 0 else ("L" if d < 0 else "D")


rq_samples = []
for r in rows:
    rq = r["rec"].get("让球")
    if not (isinstance(rq, list) and rq and isinstance(rq[0], dict)):
        continue
    it = rq[0]
    o = {"W": num(it.get("胜")), "D": num(it.get("平")), "L": num(it.get("负"))}
    if not all(o.values()):
        continue
    mk, s = devig(o)
    J = joint(*r["lam"])
    pm = agg(J, lambda i, j: rq_result(i, j, it.get("handicap")))
    real = rq_result(r["hg"], r["ag"], it.get("handicap"))
    for d in ("W", "D", "L"):
        rq_samples.append({"date": r["date"], "dir": d, "mkt": mk[d], "mod": pm.get(d, 0.0),
                           "y": 1 if real == d else 0, "h": it.get("handicap"), "r": r})

trq = [s for s in rq_samples if s["date"] < MED]
teq = [s for s in rq_samples if s["date"] >= MED]
Xq, yq = build(trq)
bq, sq = fit_logit(Xq, yq, l2=2.0)
print(f"\n  前 60% 拟合（n={len(Xq)}）：")
for i, nm in enumerate(names):
    t = bq[i] / sq[i] if sq[i] == sq[i] and sq[i] > 0 else float("nan")
    sig = "***" if abs(t) > 3 else ("**" if abs(t) > 2 else ("*" if abs(t) > 1.6 else ""))
    print(f"    {nm:<16} 系数 {bq[i]:+8.4f}   se {sq[i]:.4f}   t={t:+6.2f} {sig}")

# 每场只取模型最看好的 1 注，比较「模型单点 vs 联合校准」
print("\n  样本外（后 40%）EV 策略对比：每场只买 EV 最高的一注")

def stat_bets(pickfn, ss):
    n = tot = wins = 0
    ret = 0.0
    for s in ss:
        odds = s["odds"]
        if odds is None:
            continue
        n += 1
        ret += (odds if s["y"] else 0.0) - 1.0
        wins += s["y"]
        tot += 1
    if not tot:
        return None
    mean = ret / tot
    var = 0.0
    for s in ss:
        if s["odds"] is None:
            continue
        v = (s["odds"] if s["y"] else 0.0) - 1.0 - mean
        var += v * v
    var /= max(tot - 1, 1)
    se = math.sqrt(var / tot) if var > 0 else 0
    return {"n": tot, "hit": wins / tot * 100, "roi": mean * 100, "t": mean / se if se > 0 else 0}


# 附加赔率到让球样本
for s in rq_samples:
    rq = s["r"]["rec"].get("让球")
    it = rq[0]
    mp = {"W": num(it.get("胜")), "D": num(it.get("平")), "L": num(it.get("负"))}
    s["odds"] = mp[s["dir"]]

# 用前段拟合的 beta 算后段 EV
for lab, use in (("纯模型概率", "mod"), ("纯市场概率", "mkt"),
                 ("联合校准概率", "joint")):
    best = defaultdict(list)
    for s in teq:
        if use == "joint":
            p = sigmoid(bq[0] + bq[1] * logit(s["mkt"]) + bq[2] * logit(s["mod"]))
        else:
            p = s[use]
        best[(s["date"], s["r"]["k"])].append((p * s["odds"], s))
    picks = []
    for key, lst in best.items():
        ev, s0 = max(lst, key=lambda x: x[0])
        if ev > 1.10:
            picks.append(s0)
    st = stat_bets(None, picks)
    if st:
        print(f"    {lab:<18} EV>1.10  注 {st['n']:5d}  命中 {st['hit']:5.2f}%  ROI {st['roi']:+7.2f}%  t={st['t']:+5.2f}")
    else:
        print(f"    {lab:<18} 无注")

# ================= Part 4. 冷门路线 =================
print("\n" + "=" * 82)
print("Part 4  冷门路线 —— 稀有事件频率与影响因素")
print("=" * 82)

ups = []
for r in rows:
    if not r["o12"][0]:
        continue
    mk, _ = devig({"H": r["o12"][0], "D": r["o12"][1], "A": r["o12"][2]})
    J = joint(*r["lam"])
    pm = agg(J, outcome)
    y = outcome(r["hg"], r["ag"])
    top = max(mk, key=lambda x: mk[x])
    us = 1 if y != top else 0
    # 冷门级别
    lvl = "平" if y == "D" else ("冷" if mk[top] >= 0.50 else "次")
    rq = r["rec"].get("让球")
    hc = None
    if isinstance(rq, list) and rq and isinstance(rq[0], dict):
        try:
            hc = abs(int(str(rq[0].get("handicap")).replace("+", "")))
        except Exception:  # noqa: BLE001
            hc = None
    ups.append({"date": r["date"], "y": us, "mk_top": mk[top], "mod_top": pm[top],
                "div": pm[top] - mk[top], "mkt": mk, "mod": pm,
                "ent": -sum(p * math.log(max(p, EPS)) for p in mk.values()),
                "lam_sum": r["lam"][0] + r["lam"][1],
                "lam_diff": r["lam"][0] - r["lam"][1],
                "hc": hc, "lg": r["lg"], "lvl": lvl, "r": r,
                "spread": max(mk.values()) - min(mk.values())})

n_up = sum(u["y"] for u in ups)
seg_hot = [u for u in ups if u["mk_top"] >= 0.50]
seg_cold = [u for u in ups if u["mk_top"] < 0.50]
n_draw = sum(1 for u in ups if u["r"]["hg"] == u["r"]["ag"])
print(f"\n  市场首选未命中（= 冷门/平局）整体频率：{n_up / len(ups) * 100:.2f}%  (n={len(ups)})")
print(f"  全部平局场次占比：{n_draw / len(ups) * 100:.2f}%")
print(f"  市场看好（首选≥0.50）子集 n={len(seg_hot)}  翻车率 {sum(u['y'] for u in seg_hot) / len(seg_hot) * 100:.2f}%")
print(f"  市场摇摆（首选<0.50）子集 n={len(seg_cold)}  翻车率 {sum(u['y'] for u in seg_cold) / len(seg_cold) * 100:.2f}%")

print("\n  【按市场首选概率分档】")
bins = [(0.28, 0.34), (0.34, 0.40), (0.40, 0.46), (0.46, 0.52), (0.52, 0.60), (0.60, 0.72), (0.72, 1.0)]
for lo, hi in bins:
    seg = [u for u in ups if lo <= u["mk_top"] < hi]
    if len(seg) < 30:
        continue
    fr = sum(u["y"] for u in seg) / len(seg)
    print(f"    首选隐含 {lo:.2f}-{hi:.2f}   n={len(seg):5d}   翻车率 {fr * 100:6.2f}%")

print("\n  【按 |让球| 分档】")
for h in (0, 1, 2, 3, 4):
    seg = [u for u in ups if u["hc"] == h]
    if len(seg) < 30:
        continue
    fr = sum(u["y"] for u in seg) / len(seg)
    print(f"    |让球|={h}   n={len(seg):5d}   翻车率 {fr * 100:6.2f}%")

print("\n  【按模型-市场分歧分档】")
for lo, hi in ((-1, -0.15), (-0.15, -0.08), (-0.08, -0.03), (-0.03, 0.03), (0.03, 0.08), (0.08, 0.15), (0.15, 1)):
    seg = [u for u in ups if lo <= u["div"] < hi]
    if len(seg) < 50:
        continue
    fr = sum(u["y"] for u in seg) / len(seg)
    print(f"    分歧 {lo:+.2f}~{hi:+.2f}   n={len(seg):5d}   翻车率 {fr * 100:6.2f}%")

print("\n  【冷门 logistic 拟合】y = 1 if 市场首选翻车")
Feat = [("截距", lambda u: 1.0),
        ("市场首选概率", lambda u: u["mk_top"]),
        ("模型-市场分歧", lambda u: u["div"]),
        ("|让球|", lambda u: (u["hc"] if u["hc"] is not None else 1.5)),
        ("λ和", lambda u: u["lam_sum"]),
        ("市场熵", lambda u: u["ent"])]
Xu = [[f(u) for _, f in Feat] for u in ups]
yu = [u["y"] for u in ups]
bu, su = fit_logit(Xu, yu, l2=2.0)
print(f"    {'特征':<14} {'系数':>10} {'z':>8}")
for i, (nm, _) in enumerate(Feat):
    z = bu[i] / su[i] if su[i] == su[i] and su[i] > 0 else float("nan")
    sig = "***" if abs(z) > 3 else ("**" if abs(z) > 2 else ("*" if abs(z) > 1.6 else ""))
    print(f"    {nm:<14} {bu[i]:+10.4f} {z:+8.2f} {sig}")

# 联赛冷门率
print("\n  【各联赛翻车率（n≥80）】")
bylg = defaultdict(lambda: [0, 0])
for u in ups:
    bylg[u["lg"]][0] += 1
    bylg[u["lg"]][1] += u["y"]
rows_lg = [(lg, v[1] / v[0], v[0]) for lg, v in bylg.items() if v[0] >= 80]
rows_lg.sort(key=lambda x: -x[1])
for lg, fr, n in rows_lg[:8]:
    print(f"    {lg:<12} n={n:5d}   翻车率 {fr * 100:6.2f}%")
print("    ...")
for lg, fr, n in rows_lg[-5:]:
    print(f"    {lg:<12} n={n:5d}   翻车率 {fr * 100:6.2f}%")

# 高概率翻车的时间外可预测性
print("\n  【冷门可预测性（时间外）】市场看好 ≥55% 的子集")
seg = [u for u in ups if u["mk_top"] >= 0.55]
tr_u = [u for u in seg if u["date"] < MED]
te_u = [u for u in seg if u["date"] >= MED]
Xu2 = [[f(u) for _, f in Feat] for u in tr_u]
yu2 = [u["y"] for u in tr_u]
bu2, su2 = fit_logit(Xu2, yu2, l2=2.0)
base_rate = sum(u["y"] for u in te_u) / len(te_u)
ps = [sigmoid(sum(bu2[i] * f(u) for i, (_, f) in enumerate(Feat))) for u in te_u]
print(f"    训练 n={len(tr_u)}   验证 n={len(te_u)}")
print(f"    验证段基础翻车率 {base_rate * 100:.2f}%")
print(f"    冷门模型 Brier {brier(ps, [u['y'] for u in te_u]):.5f}"
      f"   常数基线 {brier([base_rate] * len(te_u), [u['y'] for u in te_u]):.5f}")
# 高低分组
pairs = sorted(zip(ps, te_u), key=lambda x: x[0])
k = len(pairs) // 3
if k >= 20:
    lo_g = pairs[:k]
    hi_g = pairs[-k:]
    print(f"    预测冷门风险最低 1/3：实际翻车率 {sum(u['y'] for _, u in lo_g) / len(lo_g) * 100:.2f}%  (n={len(lo_g)})")
    print(f"    预测冷门风险最高 1/3：实际翻车率 {sum(u['y'] for _, u in hi_g) / len(hi_g) * 100:.2f}%  (n={len(hi_g)})")
