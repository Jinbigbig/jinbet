#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""市场偏差提示生成器 —— 「市场给基准，我们找偏差」

逻辑（用户口径）：市场先给出报价（胜平负 / 让球 / 总进球 / 比分），我们结合
自有因素（分主客场近 25 场进球、联赛进球环境、主客优势）判断这个报价偏离了
多少、偏在哪个方向 —— 是小胜、大胜，还是可能爆冷。因为我们最终买的就是市场。

输出：每场的
  · 市场基准（去水后的隐含概率）
  · 模型判断（λ / 净胜球分布 / 总进球期望）
  · 各盘口 EV 排行（EV = 模型概率 × 赔率，>1 即模型认为被低估）
  · 偏差提示（EV 达阈值才提示，阈值来自 market_edge_probe 的回测）

回测依据（4162 场，2026-01~09，market_edge_probe.py）：
  · 让球盘：纯模型 EV>1.10 时 ROI +6.9%（t=+2.45），EV>1.30 时 +18.6%（t=+4.74）
  · 总进球：纯模型 EV>1.10 时 ROI +15.6%（t=+2.65），但月度波动大
  · 比分盘：无 alpha（抽水 28.8% 太高）→ 不作提示
  · 1X2：市场极有效，不作提示

用法： python market_edge_report.py [--date 2026-09-10] [--ev 1.15]
"""
import importlib.util
import json
import math
import os
import re
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _repo_root():
    for d in (_ROOT, os.path.dirname(_ROOT), os.path.dirname(os.path.dirname(_ROOT))):
        if os.path.exists(os.path.join(d, "index.html")):
            return d
    return _ROOT


ROOT = _repo_root()
DATE = None
EV_MIN = 1.15
for _i, _a in enumerate(sys.argv):
    if _a == "--date":
        DATE = sys.argv[_i + 1]
    if _a == "--ev":
        EV_MIN = float(sys.argv[_i + 1])

KMAX = 8


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


def num(v):
    try:
        f = float(v)
        return f if f > 1.0 else None
    except Exception:  # noqa: BLE001
        return None


def pois(L, k):
    return math.exp(-L) * L ** k / math.factorial(k)


def joint(lh, la, kmax=KMAX):
    ph = [pois(lh, k) for k in range(kmax + 1)]
    pa = [pois(la, k) for k in range(kmax + 1)]
    return {(i, j): ph[i] * pa[j] for i in range(kmax + 1) for j in range(kmax + 1)}


def devig(od):
    inv = {k: 1.0 / v for k, v in od.items() if v}
    s = sum(inv.values())
    if s <= 0:
        return {}, 0.0
    return {k: v / s for k, v in inv.items()}, 1.0 / s


def outcome(hg, ag):
    return "H" if hg > ag else ("D" if hg == ag else "A")


def rq_result(hg, ag, handicap):
    try:
        h = int(str(handicap).replace("+", ""))
    except Exception:  # noqa: BLE001
        h = 0
    n = hg - ag + h
    return "win" if n > 0 else ("draw" if n == 0 else "lose")


def zjq_bucket(n):
    return str(n) if n <= 6 else "7+"


def agg(J, fn):
    d = {}
    for (i, j), p in J.items():
        d[fn(i, j)] = d.get(fn(i, j), 0.0) + p
    return d


def conf_rq(hcap):
    """让球盘提示置信度：|让球|=1 高（回测 ROI +17.4% t=+4.0）；
    =2 中（+25.2% t=+2.8 但样本仅 194）；>=3 低（模型跨联赛实力差校准缺失）"""
    try:
        h = abs(int(str(hcap).replace("+", "")))
    except Exception:  # noqa: BLE001
        h = 1
    return "高" if h <= 1 else ("中" if h == 2 else "低")


def conf_zj(diff):
    """总进球提示置信度：模型与市场的期望进球差越大，越可能是模型高估弱队进攻"""
    a = abs(diff)
    return "高" if a <= 0.60 else ("中" if a <= 1.00 else "低")


# ---------------- 读当日 index.html 的盘口 ----------------
def load_js_var(src_path, var):
    html = open(src_path, encoding="utf-8").read()
    m = re.search(r"const " + var + r" = (\{[\s\S]*?\n\});", html)
    if not m:
        return {}
    x = m.group(1)
    x = re.sub(r"'", '"', x)
    x = re.sub(r",\s*\]", "]", x)
    x = re.sub(r",\s*\}", "}", x)
    x = re.sub(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'"\1":', x)
    try:
        return json.loads(x)
    except Exception:  # noqa: BLE001
        return {}


odds_all = load_js_var(os.path.join(ROOT, "index.html"), "ODDS")
sched = load_js_var(os.path.join(ROOT, "index.html"), "SCHEDULE")

dates = sorted({k.split("_")[0] for k in odds_all})
if DATE is None:
    DATE = dates[-1]

snap_path = os.path.join(ROOT, "predictions", DATE, "pred_snapshot.json")
if not os.path.exists(snap_path):
    print(f"✗ 找不到 {snap_path}")
    sys.exit(1)
snap = json.load(open(snap_path, encoding="utf-8"))

games = sched.get(DATE, [])
print(f"日期 {DATE}   赛程 {len(games)} 场   模型 {snap.get('engine')}")

by_pair = {}
for m in snap.get("matches", []):
    by_pair[frozenset((m["home"], m["away"]))] = m

print("=" * 78)
print(f"市场偏差提示（EV > {EV_MIN} 才提示；E V = 模型概率 × 赔率）")
print("=" * 78)

tips = []
for g in games:
    hm, aw = g.get("home"), g.get("away")
    num_s = g.get("matchNumStr", "")
    key = f"{DATE}_{hm}_{aw}"
    o = odds_all.get(key)
    if not o:
        rk = f"{DATE}_{aw}_{hm}"
        o = odds_all.get(rk)
        if o:
            hm, aw = aw, hm
            key = rk
    m = by_pair.get(frozenset((hm, aw)))
    if not o or not m:
        print(f"\n【{num_s}】{hm} vs {aw}  —— 数据不全，跳过"
              f"（{'无盘口' if not o else '无模型输出'}）")
        continue
    lh, la = m["lam_home"], m["lam_away"]
    J = joint(lh, la)
    p12 = agg(J, outcome)
    print(f"\n【{num_s}】{hm} vs {aw}")
    # ---- 市场基准 ----
    o12 = [num(o.get("胜")), num(o.get("平")), num(o.get("负"))]
    if all(o12):
        mk, rr = devig({"H": o12[0], "D": o12[1], "A": o12[2]})
        top = max(mk, key=lambda s: mk[s])
        nm = {"H": "主胜", "D": "平局", "A": "客胜"}[top]
        print(f"  市场基准  主 {mk['H'] * 100:.1f}% / 平 {mk['D'] * 100:.1f}% / 客 {mk['A'] * 100:.1f}%"
              f"   → 看好 {nm}   (返还率 {rr * 100:.1f}%)")
    else:
        mk = None
        print("  市场基准  1X2 缺失（队名别名场次）")
    pj = agg(J, lambda i, j: zjq_bucket(i + j))
    mexp = sum((7.5 if k == "7+" else int(k)) * p for k, p in pj.items())
    print(f"  模型判断  λ {lh:.2f} / {la:.2f}   总进球期望 {mexp:.2f}   "
          f"主胜 {p12['H'] * 100:.1f}% / 平 {p12['D'] * 100:.1f}% / 客 {p12['A'] * 100:.1f}%")

    # ---- 让球盘 ----
    rq = o.get("让球")
    if isinstance(rq, list) and rq and isinstance(rq[0], dict):
        it = rq[0]
        hcap = it.get("handicap")
        odd = {"win": num(it.get("胜")), "draw": num(it.get("平")), "lose": num(it.get("负"))}
        if all(odd.values()):
            mrk, rrq = devig(odd)
            pmr = agg(J, lambda i, j: rq_result(i, j, hcap))
            nm = {"win": "让球主胜", "draw": "让球平", "lose": "让球客胜"}
            line = "  ".join(
                f"{nm[s]} {odd[s]:.2f}(隐{mrk[s] * 100:.0f}%/模{pmr[s] * 100:.0f}%)"
                for s in ("win", "draw", "lose"))
            print(f"  让球盘({hcap:>2})  {line}")
            evs = sorted(((pmr[s] * odd[s], s) for s in odd), reverse=True)
            ev, s = evs[0]
            if ev > EV_MIN:
                cf = conf_rq(hcap)
                mark = "⚠️" if cf != "低" else "⛔"
                tips.append((ev, cf, f"【{num_s}】{hm} vs {aw} — {nm[s]} @{odd[s]:.2f}"
                                     f"  模型 {pmr[s] * 100:.0f}% vs 市场 {mrk[s] * 100:.0f}%"))
                print(f"    {mark} 偏差提示[置信{cf}]：{nm[s]} @{odd[s]:.2f}  EV {ev:.2f}"
                      f"（模型 {pmr[s] * 100:.0f}% vs 市场隐含 {mrk[s] * 100:.0f}%）")

    # ---- 总进球盘 ----
    zj = o.get("总进球")
    if isinstance(zj, dict) and zj:
        oz = {k: num(v) for k, v in zj.items()}
        oz = {k: v for k, v in oz.items() if v}
        if len(oz) >= 5:
            mzk, rrz = devig(oz)
            line = "  ".join(f"{k}球 {oz[k]:.2f}"
                             for k in sorted(oz, key=lambda x: int(x) if x != "7+" else 7))
            print("  总进球报价 " + line)
            mk_exp = sum((7.5 if k == "7+" else int(k)) * mzk[k] for k in mzk)
            print(f"  总进球盘  市场期望 {mk_exp:.2f} 球 ｜ 模型 {mexp:.2f} 球"
                  f"  差 {mexp - mk_exp:+.2f}")
            evs = sorted(((pj.get(k, 0) * oz[k], k) for k in oz), reverse=True)
            ev, ks = evs[0]
            hit = sorted(((pj.get(k, 0), k) for k in oz), reverse=True)[0][1]
            if ev > EV_MIN:
                cf = conf_zj(mexp - mk_exp)
                mark = "⚠️" if cf != "低" else "⛔"
                tips.append((ev, cf, f"【{num_s}】{hm} vs {aw} — 总进球 {ks} @{oz[ks]:.2f}"
                                     f"  模型 {pj.get(ks, 0) * 100:.0f}% vs 市场 {mzk.get(ks, 0) * 100:.0f}%"))
                print(f"    {mark} 偏差提示[置信{cf}]：总进球 {ks} @{oz[ks]:.2f}  EV {ev:.2f}"
                      f"（模型 {pj.get(ks, 0) * 100:.0f}% vs 市场隐含 {mzk.get(ks, 0) * 100:.0f}%）")

print("\n" + "=" * 78)
print("汇总：今日偏差提示（按 EV 降序）")
print("=" * 78)
if not tips:
    print("  今日无达阈值提示 —— 说明市场报价与模型判断基本一致（这本身就是信息）")
for ev, cf, s in sorted(tips, reverse=True):
    print(f"  [置信{cf}] EV {ev:.2f}  {s}")
print("\n注：EV>1.15 仅为候选，回测口径下让球盘 EV>1.10 全期 ROI +6.9%（t=+2.45），"
      "但月间波动大，单日 7 场不构成统计意义。")
