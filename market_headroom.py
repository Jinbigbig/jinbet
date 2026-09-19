# -*- coding: utf-8 -*-
"""
模型 vs 市场：同口径对照，量化「补新因素还有多少空间」

关键问题：模型已经把 35% 权重给了市场赔率，那么剩下 65% 的自有特征（状态/主客/联赛/H2H）
到底有没有带来增量？如果模型打不过纯市场，那么补新因素应优先补「市场不知道的」，
而不是重复市场的已知信息。

三个口径，同一批样本、同一指标：
  1. market   : 去水后赔率隐含 1X2
  2. model    : 完整引擎链路（含 35% 市场混合）
  3. nomarket : 引擎链路去掉市场混合（纯自有特征）

用法: python market_headroom.py
"""
import json
import math
import os
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

results = json.load(open(os.path.join(ROOT, "results_data.json"), encoding="utf-8"))
matches = []
for k, v in results.items():
    try:
        h, a = (int(x) for x in v["fullScore"].split(":"))
    except Exception:
        continue
    matches.append({"date": k.split("_")[0], "home": v["home"], "away": v["away"],
                    "league": v.get("league") or v.get("leagueAbbr") or "",
                    "hg": h, "ag": a, "oh": v.get("胜"), "oa": v.get("负"),
                    "od": v.get("平")})
matches.sort(key=lambda m: m["date"])

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


def base_lambdas(m):
    hr, ar = _recent(m["home"], hist), _recent(m["away"], hist)
    if not hr or not ar:
        return None
    lh = (wavg([x[1] for x in hr]) * 0.75 + wavg([x[2] for x in ar]) * 0.25) * engine.HOME_BOOST
    la = (wavg([x[1] for x in ar]) * 0.75 + wavg([x[2] for x in hr]) * 0.25) * engine.AWAY_DISCOUNT
    hrH, arA = _recent(m["home"], histH), _recent(m["away"], histA)
    if hrH and arA:
        lh_v = wavg([x[1] for x in hrH]) * 0.75 + wavg([x[2] for x in arA]) * 0.25
        ne = min(eff_n(len(hrH)), eff_n(len(arA)))
        lh = (ne * lh_v + 4.0 * lh) / (ne + 4.0)
    if arA and hrH:
        la_v = wavg([x[1] for x in arA]) * 0.75 + wavg([x[2] for x in hrH]) * 0.25
        ne = min(eff_n(len(arA)), eff_n(len(hrH)))
        la = (ne * la_v + 4.0 * la) / (ne + 4.0)
    lg = engine.LEAGUE_PROFILE["leagues"].get(m["league"])
    base = lg["mean"] if (lg and lg.get("n", 0) >= 12) else GB
    tot = (lh + la) * (1 - W_SHRINK) + base * W_SHRINK
    old = lh + la
    if old > 0:
        lh, la = lh / old * tot, la / old * tot
    return lh, la


def pois1x2(lh, la):
    g = {}
    for i in range(KMAX + 1):
        for j in range(KMAX + 1):
            g[(i, j)] = (math.exp(-lh) * lh ** i / math.factorial(i)) * \
                        (math.exp(-la) * la ** j / math.factorial(j))
    t = sum(g.values())
    h = sum(v for k, v in g.items() if k[0] > k[1]) / t
    d = sum(v for k, v in g.items() if k[0] == k[1]) / t
    a = sum(v for k, v in g.items() if k[0] < k[1]) / t
    return h, d, a


# 加载 Platt 校准参数（否则模型侧未校准，与市场的对比不公平：
# 市场赔率本身已高度校准，而裸泊松 1X2 有已知的系统性偏差）
try:
    engine.PLATT_PARAMS = json.load(open(os.path.join(ROOT, "platt_params.json"),
                                         encoding="utf-8"))
    print(f"已加载 Platt 参数（拟合于 {engine.PLATT_PARAMS.get('fitted_at')}，"
          f"{engine.PLATT_PARAMS.get('n_samples')} 样本）\n")
except Exception as e:
    print(f"⚠️ 未加载 Platt 参数（{e}），模型侧为未校准口径\n")

WMKT = [0.0, 0.25, 0.35, 0.5, 0.65, 0.8, 1.0]
rows = []
for m in matches:
    lam = base_lambdas(m)
    hist.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    hist.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    histH.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    histA.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    if lam is None:
        continue
    lh, la = lam
    try:
        oh, od, oa = float(m["oh"]), float(m["od"]), float(m["oa"])
    except (TypeError, ValueError):
        continue
    if min(oh, od, oa) <= 1.01:
        continue
    s = 1 / oh + 1 / od + 1 / oa
    p_mkt = (1 / oh / s, 1 / od / s, 1 / oa / s)
    # 引擎的市场混合（复刻 _calc_engine 第四步）
    mh, ma = 1 / oh * 2.5, 1 / oa * 2.5
    lhM, laM = 0.65 * lh + 0.35 * mh, 0.65 * la + 0.35 * ma
    p_model = engine.apply_platt(*pois1x2(lhM, laM))
    p_nomkt = engine.apply_platt(*pois1x2(lh, la))
    Y = (1.0 if m["hg"] > m["ag"] else 0.0,
         1.0 if m["hg"] == m["ag"] else 0.0,
         1.0 if m["hg"] < m["ag"] else 0.0)
    p_sw = {_w: pois1x2((1 - _w) * lh + _w * mh, (1 - _w) * la + _w * ma) for _w in WMKT}
    rows.append({"mkt": p_mkt, "model": p_model, "nomkt": p_nomkt, "Y": Y, "sw": p_sw})

n = len(rows)
print(f"同口径样本 {n} 场（有完整 1X2 赔率 + 历史战绩）\n")


def brier(key):
    return sum(sum((r[key][i] - r["Y"][i]) ** 2 for i in range(3)) for r in rows) / n


def logloss(key):
    t = 0.0
    for r in rows:
        i = r["Y"].index(1.0)
        t -= math.log(max(r[key][i], 1e-9))
    return t / n


def top1(key):
    return sum(1 for r in rows if max(range(3), key=lambda i: r[key][i]) == r["Y"].index(1.0)) / n


print(f"{'口径':<28}{'Brier(3项和)':>14}{'LogLoss':>10}{'方向Top1':>10}")
for name, key in (("① 纯市场（去水赔率）", "mkt"),
                  ("② 模型（含35%市场）", "model"),
                  ("③ 模型去掉市场（纯自有）", "nomkt")):
    print(f"{name:<28}{brier(key):>14.4f}{logloss(key):>10.4f}{top1(key)*100:>9.1f}%")

b_mkt, b_mod, b_nom = brier("mkt"), brier("model"), brier("nomkt")
print()
print(f"模型 − 市场 = {(b_mod-b_mkt):+.4f}  → {'模型更优' if b_mod < b_mkt else '⚠️ 模型劣于纯市场'}")
print(f"自有 − 市场 = {(b_nom-b_mkt):+.4f}  → {'自有特征带来增量' if b_nom < b_mkt else '⚠️ 自有特征不如直接用市场'}")

# 配对显著性：model vs market
d = [sum((r["model"][i]-r["Y"][i])**2 for i in range(3)) -
     sum((r["mkt"][i]-r["Y"][i])**2 for i in range(3)) for r in rows]
mu = sum(d)/n
sd = math.sqrt(sum((x-mu)**2 for x in d)/(n-1))
z = -mu/(sd/math.sqrt(n))
print(f"\n配对检验（model vs market）：ΔBrier 均值 {mu:+.5f}  标准差 {sd:.4f}  Z = {z:+.2f}"
      f"  → {'显著' if abs(z) > 1.96 else '不显著'}")


print("\n=== 市场权重扫描（自有特征 vs 市场 的线性混合）===")
print(f"{'市场权重':>8}{'Brier':>10}{'LogLoss':>10}{'方向Top1':>10}")
for _w in WMKT:
    b = sum(sum((r["sw"][_w][i] - r["Y"][i]) ** 2 for i in range(3)) for r in rows) / n
    ll = -sum(math.log(max(r["sw"][_w][r["Y"].index(1.0)], 1e-9)) for r in rows) / n
    t1 = sum(1 for r in rows if max(range(3), key=lambda i: r["sw"][_w][i]) == r["Y"].index(1.0)) / n
    mark = "  ← 当前生产值" if abs(_w - 0.35) < 1e-9 else ""
    print(f"{_w:>8.2f}{b:>10.4f}{ll:>10.4f}{t1*100:>9.1f}%{mark}")
