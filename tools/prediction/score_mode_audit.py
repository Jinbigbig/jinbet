# -*- coding: utf-8 -*-
"""
单比分「全局众数」退化审计 + 替代指标验证

问题：报告里「全局众数」几乎恒为 1:1，无信息量。
根因假设：2D 独立泊松的联合众数 = (floor λh, floor λa)；λ 落在 [1,2) 时两者 floor 均为 1
          → 众数结构性地恒等于 1:1，与模型质量无关。联赛形状混合(w=0.5)进一步强化。

本脚本 walk-forward 验证：
  A. 全局众数退化率（=1:1 的占比），并分解为「纯泊松」与「混合后」两个口径
  B. 候选替代指标的实际命中率 / 覆盖率：
       - 全局众数 Top1
       - 方向首选（倾向象限内众数）Top1
       - 比分 Top3 覆盖
       - BTTS（双方都进球）
       - 总进球区间（2-3球 / >=3）
  C. BTTS 校准曲线（预测概率分桶 vs 实际发生率）

用法: python score_mode_audit.py
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
if ENGINE_PY is None:
    raise SystemExit("找不到引擎文件")
spec = importlib.util.spec_from_file_location("engine", ENGINE_PY)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.load_league_profile()

DECAY, N_WIN = 0.96, 25
W_SHRINK = 0.25
GB = float(engine.LEAGUE_PROFILE.get("_meta", {}).get("global_mean", 2.83))
HOME_BOOST, AWAY_DISCOUNT = engine.HOME_BOOST, engine.AWAY_DISCOUNT
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
                    "hg": h, "ag": a, "oh": v.get("胜"), "oa": v.get("负")})
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


def _recent(team, store):
    return list(store.get(team, []))[-N_WIN:][::-1]


def lambdas(m):
    hr, ar = _recent(m["home"], hist), _recent(m["away"], hist)
    if not hr or not ar:
        return None
    h_gf, h_ga = wavg([x[1] for x in hr]), wavg([x[2] for x in hr])
    a_gf, a_ga = wavg([x[1] for x in ar]), wavg([x[2] for x in ar])
    lh = (h_gf * 0.75 + a_ga * 0.25) * HOME_BOOST
    la = (a_gf * 0.75 + h_ga * 0.25) * AWAY_DISCOUNT
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
    if m["oh"] and m["oa"]:
        try:
            mh, ma = 1 / float(m["oh"]) * 2.5, 1 / float(m["oa"]) * 2.5
            lh, la = 0.65 * lh + 0.35 * mh, 0.65 * la + 0.35 * ma
        except (ValueError, ZeroDivisionError):
            pass
    return lh, la


def pois_grid(lh, la):
    g = {(h, a): math.exp(-lh) * lh ** h / math.factorial(h) *
                  math.exp(-la) * la ** a / math.factorial(a)
         for h in range(KMAX + 1) for a in range(KMAX + 1)}
    t = sum(g.values())
    return {k: v / t for k, v in g.items()} if t > 0 else g


def mix_grid(g0, freq, w):
    gm = {k: (1 - w) * v + w * freq.get(k, 0.0) for k, v in g0.items()}
    t = sum(gm.values())
    return {k: v / t for k, v in gm.items()} if t > 0 else g0


def adaptive_w(lh, la):
    w0 = float(engine.LEAGUE_PROFILE.get("score_mix", {}).get("w", 0.5))
    lo, hi = min(lh, la), max(lh, la)
    ratio = (hi / lo) if lo > 1e-9 else 99.0
    if ratio > 1.0:
        w0 *= max(engine.ADAPTIVE_MIX_FLOOR, 1.0 - engine.ADAPTIVE_MIX_K * (ratio - 1.0))
    return w0


rows = []
for m in matches:
    lam = lambdas(m)
    hist.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    hist.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    histH.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    histA.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    if lam is None:
        continue
    lh, la = lam
    freq = engine.league_score_freq(m["league"])
    g_raw = pois_grid(lh, la)
    g_mix = mix_grid(g_raw, freq, adaptive_w(lh, la)) if freq else g_raw

    def top1(g):
        return max(g.items(), key=lambda x: x[1])[0]

    def p(g, pred):
        return sum(v for k, v in g.items()
                   if pred(k[0], k[1]))

    top5 = [k for k, _ in sorted(g_mix.items(), key=lambda x: -x[1])[:5]]

    def pfn(g, f):
        return sum(v for k, v in g.items() if f(*k))

    rows.append({
        "actual": (m["hg"], m["ag"]),
        "mode_raw": top1(g_raw),
        "mode_mix": top1(g_mix),
        "mode_lam": (round(lh), round(la)),
        "top5": top5,
        "p_h0": pfn(g_mix, lambda h, a: h == 0),
        "p_a0": pfn(g_mix, lambda h, a: a == 0),
        "p_00": pfn(g_mix, lambda h, a: h == 0 and a == 0),
        "p_11": pfn(g_mix, lambda h, a: h == 1 and a == 1),
        # 方向首选：1X2 最高象限内众数
        "quad_mode": max(
            [(k, v) for k, v in g_mix.items() if (k[0] > k[1])] or [((1, 0), 0.0)],
            key=lambda x: x[1])[0] if p(g_mix, lambda h, a: h > a) >= max(p(g_mix, lambda h, a: h == a), p(g_mix, lambda h, a: h < a))
        else (max([(k, v) for k, v in g_mix.items() if k[0] == k[1]], key=lambda x: x[1])[0]
              if p(g_mix, lambda h, a: h == a) >= p(g_mix, lambda h, a: h < a)
              else max([(k, v) for k, v in g_mix.items() if k[0] < k[1]], key=lambda x: x[1])[0]),
        "top3": [k for k, _ in sorted(g_mix.items(), key=lambda x: -x[1])[:3]],
        "p_btts": p(g_mix, lambda h, a: h > 0 and a > 0),
        "p_t23": p(g_mix, lambda h, a: 2 <= h + a <= 3),
        "p_ge3": p(g_mix, lambda h, a: h + a >= 3),
    })

n = len(rows)
print(f"可评估样本 {n} 场\n")

# ---------- A. 退化率 ----------
print("=== A. 全局众数退化率 ===")
for name, key in (("纯泊松（无形状混合）", "mode_raw"), ("联赛形状混合后（生产口径）", "mode_mix")):
    from collections import Counter
    c = Counter(f"{r[key][0]}:{r[key][1]}" for r in rows)
    top = c.most_common(4)
    share_11 = c.get("1:1", 0) / n
    print(f"  {name}:")
    print(f"    众数=1:1 占比 {share_11*100:.1f}%   唯一众数值个数 {len(c)}")
    print(f"    Top4 众数分布: {top}")
print()

# 唯一值个数（信息量）：全局众数 vs 方向首选
cq = Counter(f"{r['quad_mode'][0]}:{r['quad_mode'][1]}" for r in rows)
print(f"  对比·方向首选:  众数=1:1 占比 {cq.get('1:1',0)/n*100:.1f}%  唯一值个数 {len(cq)}")
print(f"    方向首选 Top5: {cq.most_common(5)}")
print()

# ---------- B. 实际命中率 ----------
print("=== B. 候选指标实际命中率（walk-forward）===")
hit_mode = sum(1 for r in rows if r["mode_mix"] == r["actual"]) / n
hit_quad = sum(1 for r in rows if r["quad_mode"] == r["actual"]) / n
hit_top3 = sum(1 for r in rows if r["actual"] in r["top3"]) / n
actual_btts = sum(1 for r in rows if r["actual"][0] > 0 and r["actual"][1] > 0) / n
hit_btts = sum(1 for r in rows
               if (r["p_btts"] >= 0.5) == (r["actual"][0] > 0 and r["actual"][1] > 0)) / n
hit_t23 = sum(1 for r in rows if 2 <= sum(r["actual"]) <= 3 and r["p_t23"] >= 0.5) / n
cov_t23 = sum(1 for r in rows if 2 <= sum(r["actual"]) <= 3) / n
hit_lam = sum(1 for r in rows if r["mode_lam"] == r["actual"]) / n
hit_top5 = sum(1 for r in rows if r["actual"] in r["top5"]) / n
print(f"  全局众数 Top1 命中        {hit_mode*100:6.2f}%   （唯一众数值 {len(Counter(f'{r['mode_mix'][0]}:{r['mode_mix'][1]}' for r in rows))} 种）")
print(f"  λ四舍五入 Top1 命中       {hit_lam*100:6.2f}%")
print(f"  方向首选 Top1 命中        {hit_quad*100:6.2f}%")
print(f"  比分 Top3 覆盖（实际命中）{hit_top3*100:6.2f}%")
print(f"  比分 Top5 覆盖（实际命中）{hit_top5*100:6.2f}%")
print(f"  BTTS 方向命中（阈值0.5）  {hit_btts*100:6.2f}%   实际 BTTS 基础率 {actual_btts*100:.2f}%")
print(f"  （参考）总进球2-3球基础率 {cov_t23*100:.2f}%，但单场 P(2-3球)≥0.5 的场次仅 {sum(1 for r in rows if r['p_t23']>=0.5)} 场")
print()

# ---------- B2. 进球边际校准 ----------
print("=== B2. 进球边际校准（预测均值 vs 实际发生率）===")
for name, pf, af in (
    ("主队零封 P(主=0)", "p_h0", lambda r: r["actual"][0] == 0),
    ("客队零封 P(客=0)", "p_a0", lambda r: r["actual"][1] == 0),
    ("0:0", "p_00", lambda r: r["actual"] == (0, 0)),
    ("1:1", "p_11", lambda r: r["actual"] == (1, 1)),
):
    ap = sum(r[pf] for r in rows) / n
    ac = sum(1 for r in rows if af(r)) / n
    print(f"  {name:<18} 预测均值 {ap*100:5.2f}%   实际 {ac*100:5.2f}%   偏差 {(ac-ap)*100:+6.2f}pp"
          f"{'  ⚠️' if abs(ac-ap) > 0.01 else ''}")
print()

# ---------- C. BTTS 校准 ----------
print("=== C. BTTS 校准曲线（预测分桶 → 实际发生率）===")
buckets = [(0, .45), (.45, .55), (.55, .65), (.65, .75), (.75, 1.01)]
print(f"  {'预测区间':<14}{'场次':>6}{'平均预测':>10}{'实际':>9}{'偏差':>9}")
for lo, hi in buckets:
    sub = [r for r in rows if lo <= r["p_btts"] < hi]
    if len(sub) < 20:
        continue
    ap = sum(r["p_btts"] for r in sub) / len(sub)
    ac = sum(1 for r in sub if r["actual"][0] > 0 and r["actual"][1] > 0) / len(sub)
    flag = "  ⚠️" if abs(ac - ap) > 0.06 else ""
    print(f"  [{lo:.2f},{hi:.2f}){'':<4}{len(sub):>6}{ap*100:>9.1f}%{ac*100:>8.1f}%{(ac-ap)*100:>+8.1f}pp{flag}")
brier_btts = sum((r["p_btts"] - (1.0 if (r["actual"][0] > 0 and r["actual"][1] > 0) else 0.0)) ** 2
                 for r in rows) / n
print(f"\n  BTTS Brier = {brier_btts:.4f}（<0.25 即优于抛硬币基线）")
