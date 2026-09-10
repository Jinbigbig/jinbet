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
engine.fit_platt_params()      # V3.3 对齐需要 Platt 参数（价格：读缓存）

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
                    "hg": h, "ag": a, "oh": v.get("胜"), "od": v.get("平"), "oa": v.get("负")})
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


def lambdas(m, mode="v3"):
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
    if mode == "v3":
        # V3.2+ 生产口径：模型 1X2 与市场去水 1X2 在**概率空间**按 MARKET_W 加权后反解 λ（总量守恒）
        if m["oh"] and m["od"] and m["oa"]:
            try:
                pv = engine.devig_1x2(float(m["oh"]), float(m["od"]), float(m["oa"]))
                pm = engine.pois_1x2(lh, la)
                W = engine.MARKET_W
                pb = [(1 - W) * pm[i] + W * pv[i] for i in range(3)]
                s = sum(pb)
                pb = [x / s for x in pb]
                lh, la = engine.prob_to_lambda(pb, lh + la)
            except (ValueError, ZeroDivisionError):
                pass
    else:
        # V2 旧口径（已弃用，保留作对照）：1/赔率×2.5 的粗映射，权重 0.35
        if m["oh"] and m["oa"]:
            try:
                mh, ma = 1 / float(m["oh"]) * 2.5, 1 / float(m["oa"]) * 2.5
                lh, la = 0.65 * lh + 0.35 * mh, 0.65 * la + 0.35 * ma
            except (ValueError, ZeroDivisionError):
                pass
    return lh, la


def align_grid(g):
    """V3.3：把比分矩阵三象限的质量缩放到**已发布**的（Platt 后）1X2，象限内形状不变。"""
    cur = [sum(v for k, v in g.items() if k[0] > k[1]),
           sum(v for k, v in g.items() if k[0] == k[1]),
           sum(v for k, v in g.items() if k[0] < k[1])]
    tgt = list(engine.apply_platt(cur[0], cur[1], cur[2]))
    f = [tgt[i] / cur[i] if cur[i] > 1e-12 else 1.0 for i in range(3)]
    out = {k: v * f[0 if k[0] > k[1] else (1 if k[0] == k[1] else 2)] for k, v in g.items()}
    t = sum(out.values())
    return {k: v / t for k, v in out.items()} if t > 0 else out


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


def build_row(m, lh, la, g_mix, g_raw=None):
    """把网格压成一行指标（V2/V3 共用口径，保证两套对比是同定义）。"""
    def top1(g):
        return max(g.items(), key=lambda x: x[1])[0]

    def pfn(g, f):
        return sum(v for k, v in g.items() if f(*k))

    ph, pd, pa = (pfn(g_mix, lambda h, a: h > a), pfn(g_mix, lambda h, a: h == a),
                  pfn(g_mix, lambda h, a: h < a))
    quad = "H" if ph >= max(pd, pa) else ("D" if pd >= pa else "A")
    qf = {"H": lambda h, a: h > a, "D": lambda h, a: h == a, "A": lambda h, a: h < a}[quad]
    pool = [(k, v) for k, v in g_mix.items() if qf(*k)] or [((1, 0), 0.0)]
    r5 = [k for k, _ in sorted(g_mix.items(), key=lambda x: -x[1])]
    return {
        "actual": (m["hg"], m["ag"]),
        "mode_raw": top1(g_raw) if g_raw else None,
        "mode_mix": top1(g_mix),
        "mode_lam": (round(lh), round(la)),
        "top1": r5[:1], "top3": r5[:3], "top5": r5[:5],
        "quad_mode": max(pool, key=lambda x: x[1])[0],
        "quad": quad,
        "p_h0": pfn(g_mix, lambda h, a: h == 0),
        "p_a0": pfn(g_mix, lambda h, a: a == 0),
        "p_00": pfn(g_mix, lambda h, a: h == 0 and a == 0),
        "p_11": pfn(g_mix, lambda h, a: h == 1 and a == 1),
        "p_btts": pfn(g_mix, lambda h, a: h > 0 and a > 0),
        "p_t23": pfn(g_mix, lambda h, a: 2 <= h + a <= 3),
        "p_ge3": pfn(g_mix, lambda h, a: h + a >= 3),
    }


rows, rows3, rows3noalign = [], [], []   # V2旧口径 / V3.3生产 / V3.3但矩阵不对齐
for m in matches:
    lam_v2 = lambdas(m, "v2")
    lam_v3 = lambdas(m, "v3")
    # 历史库每场只推进一次（两套口径共用同一 walk-forward 序列）
    hist.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    hist.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    histH.setdefault(m["home"], []).append((m["date"], m["hg"], m["ag"]))
    histA.setdefault(m["away"], []).append((m["date"], m["ag"], m["hg"]))
    if lam_v3 is None:
        continue
    freq = engine.league_score_freq(m["league"])

    def mk(lh, la):
        g = pois_grid(lh, la)
        return (mix_grid(g, freq, adaptive_w(lh, la)) if freq else g), g

    g2, g2raw = mk(*lam_v2)
    rows.append(build_row(m, lam_v2[0], lam_v2[1], g2, g2raw))
    g3, _ = mk(*lam_v3)
    rows3noalign.append(g3)
    rows3.append(build_row(m, lam_v3[0], lam_v3[1], align_grid(g3), None))

n = len(rows)
print(f"可评估样本 {n} 场（V2/V3 同一批，walk-forward）\n")

# ---------- A. 退化率（V2 旧口径，仅作对照）----------
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
print("=== B. 候选指标实际命中率（V2 旧口径，walk-forward，仅作对照）===")
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
print("=== B2. 进球边际校准（V2 旧口径）===")
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
print("=== C. BTTS 校准曲线（V2 旧口径）===")
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

# ================================================================ D. V3.3 生产口径（当前口径）
# 用户 2026-09-10：「引擎把 λ 混了市场、1X2 做了校准，那预测的比分也应该跟着变」。
# 本段用**当前生产管道**重跑同一批比赛：λ 走概率空间市场混合(80%, 总量守恒) → 联赛经验频率混合
# → 比分矩阵三象限质量对齐到 Platt 后的发布 1X2（V3.3 SCORE_ALIGN）。
# 报告 4.1/4.2 里引用的「单比分上限 / Top3 / Top5 覆盖 / 方向首选」应改用本段数字。
print()
print("=== D. V3.3 生产口径（当前口径：市场混合80% + Platt + 比分矩阵对齐）===")


def metrics(rs, tag):
    n_ = len(rs)
    hit_mode = sum(1 for r in rs if r["mode_mix"] == r["actual"]) / n_
    hit_quad = sum(1 for r in rs if r["quad_mode"] == r["actual"]) / n_
    hit_t3 = sum(1 for r in rs if r["actual"] in r["top3"]) / n_
    hit_t5 = sum(1 for r in rs if r["actual"] in r["top5"]) / n_
    hit_t1 = sum(1 for r in rs if r["actual"] in r["top1"]) / n_
    uniq_q = len(Counter(f"{r['quad_mode'][0]}:{r['quad_mode'][1]}" for r in rs))
    return {"n": n_, "t1": hit_t1, "t3": hit_t3, "t5": hit_t5,
            "quad": hit_quad, "mode": hit_mode, "uniq_q": uniq_q}


mv2, mv3 = metrics(rows, "v2"), metrics(rows3, "v3")
# V3.3 去对齐（只换 λ 口径、不做矩阵对齐）→ 用于把「市场混合」与「矩阵对齐」两件事分开归因
mv3na = []
for i, r in enumerate(rows3):
    mm = dict(r)
    g = rows3noalign[i]
    r5 = [k for k, _ in sorted(g.items(), key=lambda x: -x[1])]
    mm["top1"], mm["top3"], mm["top5"] = r5[:1], r5[:3], r5[:5]
    mm["mode_mix"] = r5[0]
    mv3na.append(mm)
mvna = metrics(mv3na, "v3na")
print(f"  {'指标':<26}{'V2 旧口径':>11}{'V3.3无对齐':>12}{'V3.3生产':>11}{'对齐影响':>11}")
print("  " + "-" * 74)
for label, k in (("单比分 Top1 命中（全局众数）", "mode"),
                 ("方向首选 Top1 命中（象限内众数）", "quad"),
                 ("比分 Top1 覆盖", "t1"),
                 ("比分 Top3 覆盖", "t3"),
                 ("比分 Top5 覆盖", "t5")):
    print(f"  {label:<26}{mv2[k]*100:10.2f}%{mvna[k]*100:11.2f}%{mv3[k]*100:10.2f}%"
          f"{(mv3[k]-mvna[k])*100:+10.2f}pp")
print(f"  {'方向首选唯一值个数':<26}{mv2['uniq_q']:>11}{mvna['uniq_q']:>12}{mv3['uniq_q']:>11}")
print(f"  对比 V2 → V3.3 生产总变化：Top3 {(mv3['t3']-mv2['t3'])*100:+.2f}pp、"
      f"Top5 {(mv3['t5']-mv2['t5'])*100:+.2f}pp、方向首选 {(mv3['quad']-mv2['quad'])*100:+.2f}pp")
print()
print("  ※ 报告 4.1/4.2 的说明文字请以 V3.3 生产列为准；V2 列仅用于说明历史数字（13.15%/9.90%/")
print("     31.78%/47.69%）出自已弃用的 λ 空间粗混合口径，不再代表当前模型。")

# 进球边际校准（V3.3）
for name, pf, af in (("主队零封 P(主=0)", "p_h0", lambda r: r["actual"][0] == 0),
                     ("客队零封 P(客=0)", "p_a0", lambda r: r["actual"][1] == 0),
                     ("0:0", "p_00", lambda r: r["actual"] == (0, 0)),
                     ("1:1", "p_11", lambda r: r["actual"] == (1, 1))):
    ap = sum(r[pf] for r in rows3) / len(rows3)
    ac = sum(1 for r in rows3 if af(r)) / len(rows3)
    print(f"  {name:<18} 预测均值 {ap*100:5.2f}%   实际 {ac*100:5.2f}%   偏差 {(ac-ap)*100:+6.2f}pp")
