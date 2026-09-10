#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""市场基准 × 模型分歧 → 二级盘口价值策略验证

用户逻辑
--------
市场先给基准（比如"主胜"），我们结合自有因素判断这个定价的偏差方向 ——
是小胜、大胜，还是可能爆冷。因为最终要买的就是市场挂牌的盘口。

本脚本把这句话量化成可验证的策略，并在**样本外**检查是否稳健。

方法
----
1. 市场去水：1X2 / 让球盘 / 总进球盘 / 比分盘（各盘口独立归一 → 返还率）
2. 模型分布：生产同源基础 λ（主客场分拆 + 联赛环境收缩）→ 独立泊松联合分布
   · 纯模型  = 模型分布直接算概率
   · 混合    = 方向用市场 1X2、形态用模型条件分布（市场方向 ⊕ 模型形态）
3. 价值投注：p × 赔率 > 1 + margin 才下注（margin 即"模型认为被低估的幅度"）
4. 稳健性：
   · EV 阈值扫描 —— 阈值越高 ROI 应越高（否则是噪声）
   · 时间外验证 —— 前 60% 定规则 / 后 40% 查表现

用法： python market_edge_probe.py
"""
import glob
import importlib.util
import json
import math
import os
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
MARGINS = (0.00, 0.05, 0.10, 0.15, 0.20, 0.30)


# ---------------- 基础工具 ----------------
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
    d = defaultdict(float)
    for (i, j), p in J.items():
        d[fn(i, j)] += p
    return dict(d)


def mix_joint(lh, la, mkt12):
    """P_mix(i,j) = P_mkt(结果) · P_model((i,j)|结果) —— 方向用市场、形态用模型"""
    J = joint(lh, la)
    grp = {"H": {}, "D": {}, "A": {}}
    for (i, j), p in J.items():
        grp[outcome(i, j)][(i, j)] = p
    out = {}
    for g, cells in grp.items():
        s = sum(cells.values())
        pk = mkt12.get(g, 0.0)
        if s <= 0:
            continue
        for c, p in cells.items():
            out[c] = out.get(c, 0.0) + p / s * pk
    t = sum(out.values())
    return {c: p / t for c, p in out.items()} if t else out


class Book:
    """按「模型概率 × 赔率」筛注并统计 ROI，支持 EV 阈值与时间区间筛选"""

    def __init__(self):
        self.recs = []  # (date, ev, odds, win)

    def add(self, date, ev, odds, win):
        self.recs.append((date, ev, odds, win))

    def stat(self, margin=0.0, lo=None, hi=None):
        sel = [r for r in self.recs
               if r[1] > 1.0 + margin and (lo is None or r[0] >= lo) and (hi is None or r[0] < hi)]
        n = len(sel)
        if n == 0:
            return None
        ret = sum((r[2] if r[3] else 0.0) - 1.0 for r in sel)
        wins = sum(1 for r in sel if r[3])
        m = ret / n
        var = sum((((r[2] if r[3] else 0.0) - 1.0) - m) ** 2 for r in sel) / (n - 1) if n > 1 else 0.0
        se = math.sqrt(var / n) if n > 1 else 0.0
        t = m / se if se > 0 else 0.0
        return {"n": n, "hit": wins / n * 100, "roi": m * 100, "t": t}

    def line(self, label, margin=0.0):
        s = self.stat(margin)
        if not s:
            return f"  {label:<28} n=0"
        return (f"  {label:<28} 注 {s['n']:5d}  命中 {s['hit']:5.2f}%"
                f"  ROI {s['roi']:+7.2f}%  t={s['t']:+5.2f}")


def split_two(bk, margin, med):
    def f(s):
        return "n=0" if not s else f"n={s['n']:5d} ROI {s['roi']:+7.2f}% t={s['t']:+5.2f}"
    return f(bk.stat(margin, hi=med)), f(bk.stat(margin, lo=med))


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
                 "o12": (oh, od, ol), "rec": v})

dates = sorted({r["date"] for r in rows})
MED = dates[int(len(dates) * 0.6)]
print(f"样本 {len(rows)} 场   日期 {dates[0]} ~ {dates[-1]}")
print(f"  切分点（前60%%/后40%%）：{MED}")
print(f"  有 1X2 {sum(1 for r in rows if r['o12'][0])}"
      f" ｜ 让球盘 {sum(1 for r in rows if r['rec'].get('让球'))}"
      f" ｜ 比分盘 {sum(1 for r in rows if r['rec'].get('比分'))}"
      f" ｜ 总进球盘 {sum(1 for r in rows if r['rec'].get('总进球'))}")

print("\n=== 各盘口实测返还率（抽水）===")
v12 = [1 / sum(1 / x for x in r["o12"]) for r in rows if r["o12"][0]]
print(f"  胜平负      {sum(v12) / len(v12) * 100:6.2f}%   (n={len(v12)})")
vrq = []
for r in rows:
    rq = r["rec"].get("让球")
    if isinstance(rq, list) and rq and isinstance(rq[0], dict):
        o = [num(rq[0].get(x)) for x in ("胜", "平", "负")]
        if all(o):
            vrq.append(1 / sum(1 / x for x in o))
print(f"  让球胜平负  {sum(vrq) / len(vrq) * 100:6.2f}%   (n={len(vrq)})")
for fld in ("总进球", "比分"):
    vals = []
    for r in rows:
        od = r["rec"].get(fld)
        if isinstance(od, dict) and od:
            inv = [1 / float(x) for x in od.values() if num(x)]
            if inv:
                vals.append(1 / sum(inv))
    print(f"  {fld:<8}   {sum(vals) / len(vals) * 100:6.2f}%   (n={len(vals)})")


def mkt12_of(r):
    if not r["o12"][0]:
        return None
    s = sum(1 / x for x in r["o12"])
    return {"H": (1 / r["o12"][0]) / s, "D": (1 / r["o12"][1]) / s, "A": (1 / r["o12"][2]) / s}


# ================= B. 让球盘 =================
print("\n" + "=" * 78)
print("B. 让球盘 —— 市场给方向，模型判断「怎么赢」")
print("=" * 78)
bk_mix, bk_mod = Book(), Book()
rq_disp = defaultdict(lambda: Book())
rq_agree, rq_dis = Book(), Book()
for r in rows:
    rq = r["rec"].get("让球")
    if not (isinstance(rq, list) and rq and isinstance(rq[0], dict)):
        continue
    it = rq[0]
    o = {"win": num(it.get("胜")), "draw": num(it.get("平")), "lose": num(it.get("负"))}
    if not all(o.values()):
        continue
    hcap = it.get("handicap")
    mk, _ = devig(o)
    lh, la = r["lam"]
    Jm = joint(lh, la)
    pm = agg(Jm, lambda i, j: rq_result(i, j, hcap))
    m12 = mkt12_of(r)
    Jx = mix_joint(lh, la, m12) if m12 else Jm
    px = agg(Jx, lambda i, j: rq_result(i, j, hcap))
    real = rq_result(r["hg"], r["ag"], hcap)
    d = r["date"]
    for sel in ("win", "draw", "lose"):
        bk_mix.add(d, px.get(sel, 0) * o[sel], o[sel], sel == real)
        bk_mod.add(d, pm.get(sel, 0) * o[sel], o[sel], sel == real)
    top = max(o, key=lambda s: mk.get(s, 0))
    k = round((px.get(top, 0) - mk.get(top, 0)) * 20) / 20.0
    rq_disp[k].add(d, 1.0, o[top], top == real)
    mtop = max(o, key=lambda s: px.get(s, 0))
    if mtop == top:
        rq_agree.add(d, px[mtop] * o[mtop], o[mtop], mtop == real)
    else:
        rq_dis.add(d, px[mtop] * o[mtop], o[mtop], mtop == real)

print(f"  场上 {len(vrq)} 场")
print("\n  EV 阈值扫描（模型认为被低估越多，ROI 应越高）：")
for lab, bk in (("纯模型", bk_mod), ("混合（市场方向+模型形态）", bk_mix)):
    print(f"   [{lab}]")
    for m in MARGINS:
        print("  " + bk.line(f"EV > {1 + m:.2f}", m))
    a, b = split_two(bk, 0.10, MED)
    print(f"     EV>1.10 时间外：前段 {a} ｜ 后段 {b}")

print("\n  分歧分档（模型比市场更看好【市场首选方向】的程度 → 买该方向）：")
for k in sorted(rq_disp):
    s = rq_disp[k].stat()
    if s:
        print(f"     分歧 {k * 100:+5.1f}pp   注 {s['n']:5d}  命中 {s['hit']:5.2f}%"
              f"  ROI {s['roi']:+7.2f}%  t={s['t']:+5.2f}")

print("\n  模型首选 vs 市场首选（让球盘）：")
print("  " + rq_agree.line("方向一致（买该方向）"))
print("  " + rq_dis.line("方向分歧（买模型首选）"))
a, b = split_two(rq_dis, 0.0, MED)
print(f"     分歧子集 前段 {a} ｜ 后段 {b}")

# ================= C. 总进球盘 =================
print("\n" + "=" * 78)
print("C. 总进球盘 —— 模型 λ 和 vs 市场期望进球")
print("=" * 78)
bkz_mix, bkz_mod = Book(), Book()
for r in rows:
    od = r["rec"].get("总进球")
    if not (isinstance(od, dict) and od):
        continue
    o = {k: num(v) for k, v in od.items()}
    o = {k: v for k, v in o.items() if v}
    if len(o) < 5:
        continue
    lh, la = r["lam"]
    Jm = joint(lh, la)
    pm = agg(Jm, lambda i, j: zjq_bucket(i + j))
    m12 = mkt12_of(r)
    Jx = mix_joint(lh, la, m12) if m12 else Jm
    px = agg(Jx, lambda i, j: zjq_bucket(i + j))
    real = zjq_bucket(r["hg"] + r["ag"])
    for sel, ov in o.items():
        bkz_mix.add(r["date"], px.get(sel, 0) * ov, ov, sel == real)
        bkz_mod.add(r["date"], pm.get(sel, 0) * ov, ov, sel == real)
print("  EV 阈值扫描：")
for lab, bk in (("纯模型", bkz_mod), ("混合", bkz_mix)):
    print(f"   [{lab}]")
    for m in MARGINS:
        print("  " + bk.line(f"EV > {1 + m:.2f}", m))
    a, b = split_two(bk, 0.10, MED)
    print(f"     EV>1.10 时间外：前段 {a} ｜ 后段 {b}")

# ================= D. 比分盘 =================
print("\n" + "=" * 78)
print("D. 比分盘 —— 模型比分分布 vs 市场比分分布")
print("=" * 78)
bkbf = Book()
cov_m = cov_x = nb = 0
for r in rows:
    od = r["rec"].get("比分")
    if not (isinstance(od, dict) and od):
        continue
    full = {k: num(v) for k, v in od.items() if num(v)}
    o = {k: v for k, v in full.items() if ":" in k}
    if len(o) < 10:
        continue
    mk, _ = devig(full)
    lh, la = r["lam"]
    Jm = joint(lh, la)
    m12 = mkt12_of(r)
    Jx = mix_joint(lh, la, m12) if m12 else Jm
    real = f"{r['hg']}:{r['ag']}"
    tm = [k for k, _ in sorted(mk.items(), key=lambda x: -x[1]) if ":" in k][:5]
    tx = [f"{c[0]}:{c[1]}" for c, _ in sorted(Jx.items(), key=lambda x: -x[1])][:5]
    cov_m += 1 if real in tm else 0
    cov_x += 1 if real in tx else 0
    for sel, ov in o.items():
        i, j = (int(x) for x in sel.split(":"))
        bkbf.add(r["date"], Jx.get((i, j), 0) * ov, ov, sel == real)
    nb += 1
print(f"  场上 {nb} 场")
print(f"  Top5 覆盖：市场 {cov_m / nb * 100:.2f}%   混合 {cov_x / nb * 100:.2f}%")
print("  EV 阈值扫描（只投具体比分）：")
for m in MARGINS:
    print("  " + bkbf.line(f"EV > {1 + m:.2f}", m))
a, b = split_two(bkbf, 0.10, MED)
print(f"     EV>1.10 时间外：前段 {a} ｜ 后段 {b}")


# ================= E. 可执行版：每场每盘口只买 EV 最高的一注 =================
print("\n" + "=" * 78)
print("E. 可执行版 —— 每场只买 EV 最高的一注（同场多注会虚高显著性）")
print("=" * 78)

top_rq, top_zj = Book(), Book()
for r in rows:
    lh, la = r["lam"]
    Jm = joint(lh, la)
    d = r["date"]
    rq = r["rec"].get("让球")
    if isinstance(rq, list) and rq and isinstance(rq[0], dict):
        it = rq[0]
        o = {"win": num(it.get("胜")), "draw": num(it.get("平")), "lose": num(it.get("负"))}
        if all(o.values()):
            pm = agg(Jm, lambda i, j: rq_result(i, j, it.get("handicap")))
            real = rq_result(r["hg"], r["ag"], it.get("handicap"))
            best = max(o, key=lambda s: pm.get(s, 0) * o[s])
            top_rq.add(d, pm[best] * o[best], o[best], best == real)
    od = r["rec"].get("总进球")
    if isinstance(od, dict) and od:
        o2 = {k: num(v) for k, v in od.items()}
        o2 = {k: v for k, v in o2.items() if v}
        if len(o2) >= 5:
            pm2 = agg(Jm, lambda i, j: zjq_bucket(i + j))
            real2 = zjq_bucket(r["hg"] + r["ag"])
            best2 = max(o2, key=lambda s: pm2.get(s, 0) * o2[s])
            top_zj.add(d, pm2[best2] * o2[best2], o2[best2], best2 == real2)

for lab, bk in (("让球盘", top_rq), ("总进球盘", top_zj)):
    print(f"\n   [{lab}] 每场 1 注")
    for m in MARGINS:
        print("  " + bk.line(f"EV > {1 + m:.2f}", m))
    a, b = split_two(bk, 0.10, MED)
    print(f"     EV>1.10 时间外：前段 {a} ｜ 后段 {b}")
    # 月度稳定性
    bym = defaultdict(list)
    for rec in bk.recs:
        bym[rec[0][:7]].append(rec)
    print("     月度（EV>1.10）：")
    for mo in sorted(bym):
        sub = [rec for rec in bym[mo] if rec[1] > 1.10]
        if not sub:
            continue
        ret = sum((rec[2] if rec[3] else 0.0) - 1.0 for rec in sub)
        n = len(sub)
        mm = ret / n
        var = sum((((rec[2] if rec[3] else 0.0) - 1.0) - mm) ** 2 for rec in sub) / (n - 1) if n > 1 else 0
        se = math.sqrt(var / n) if n > 1 else 0
        t = mm / se if se > 0 else 0
        print(f"       {mo}  注 {n:4d}  ROI {mm * 100:+7.2f}%  t={t:+5.2f}")

# ================= F. 偏差预测力：模型与市场的分歧是否预示真实形态 =================
print("\n" + "=" * 78)
print("F. 分歧的预测力 —— 模型偏离市场越多，实际形态是否跟着偏")
print("=" * 78)

gz = defaultdict(list)
gn = defaultdict(list)
for r in rows:
    lh, la = r["lam"]
    od = r["rec"].get("总进球")
    if isinstance(od, dict) and od:
        o = {k: num(v) for k, v in od.items()}
        o = {k: v for k, v in o.items() if v}
        if len(o) >= 5:
            mk, _ = devig(o)
            mexp = sum((7.5 if k == "7+" else int(k)) * p for k, p in mk.items())
            gz[round(((lh + la) - mexp) * 2) / 2].append(r["hg"] + r["ag"])
    rq = r["rec"].get("让球")
    if isinstance(rq, list) and rq and isinstance(rq[0], dict):
        it = rq[0]
        o = [num(it.get(x)) for x in ("胜", "平", "负")]
        if all(o):
            mk, _ = devig({"w": o[0], "d": o[1], "l": o[2]})
            try:
                h = int(str(it.get("handicap")).replace("+", ""))
            except Exception:  # noqa: BLE001
                h = 0
            # 市场让球盘隐含净胜球（粗算：win→+h 以上, draw→h, lose→h 以下）
            mexp_n = (-h) + 1.05 * mk["w"] + 0.0 * mk["d"] - 1.05 * mk["l"]
            gn[round(((lh - la) - mexp_n) * 1.0) / 1.0].append(r["hg"] - r["ag"])

print("  总进球：模型 λ和 − 市场期望 → 实际场均总进球")
for k in sorted(gz):
    v = gz[k]
    if len(v) >= 20:
        print(f"     偏差 {k:+.2f} 球   n={len(v):5d}   实际场均 {sum(v) / len(v):.3f}")
print("  净胜球：模型 λ差 − 市场让球盘隐含 → 实际场均净胜球")
for k in sorted(gn):
    v = gn[k]
    if len(v) >= 30:
        print(f"     偏差 {k:+.1f} 球   n={len(v):5d}   实际场均 {sum(v) / len(v):+.3f}")


# ================= G. 分歧校准：模型说市场错了，到底谁对 =================
print("\n" + "=" * 78)
print("G. 1X2 分歧校准 —— 模型概率 − 市场概率 分档 → 实际发生频率")
print("=" * 78)

g = defaultdict(lambda: [0, 0.0, 0.0, 0])  # 分档 -> n, 模型p和, 市场p和, 实际次数
cold = defaultdict(lambda: [0, 0, 0.0])    # 市场首选概率>=0.5 的场次分档：n, 首选命中, 模型首选偏差和
for r in rows:
    if not r["o12"][0]:
        continue
    mk = mkt12_of(r)
    lh, la = r["lam"]
    Jm = joint(lh, la)
    pm = agg(Jm, outcome)
    y = outcome(r["hg"], r["ag"])
    for k_ in ("H", "D", "A"):
        d = pm[k_] - mk[k_]
        key = round(d * 20) / 20.0
        c = g[key]
        c[0] += 1
        c[1] += pm[k_]
        c[2] += mk[k_]
        c[3] += 1 if y == k_ else 0
    # 市场首选方向
    top = max(mk, key=lambda s: mk[s])
    if mk[top] >= 0.50:
        d = pm[top] - mk[top]
        ck = round(d * 20) / 20.0
        c = cold[ck]
        c[0] += 1
        c[1] += 1 if y == top else 0
        c[2] += d

print("  每个方向（主/平/客）单独看：分歧越大，实际频率是否跟着模型走")
print("  分歧档        n     模型均值   市场均值   实际频率   实际−市场")
for k_ in sorted(g):
    v = g[k_]
    if v[0] < 40:
        continue
    mp, kp = v[1] / v[0], v[2] / v[0]
    fr = v[3] / v[0]
    print(f"   {k_ * 100:+6.1f}pp  {v[0]:6d}   {mp * 100:6.2f}%   {kp * 100:6.2f}%   {fr * 100:6.2f}%   {(fr - kp) * 100:+6.2f}pp")

print("\n  只取「市场明确看好某方（≥50%）」的场次：模型分歧 vs 首选实际命中率")
print("  分歧档        n     实际命中   保本线(隐含)   差")
for k_ in sorted(cold):
    v = cold[k_]
    if v[0] < 30:
        continue
    hit = v[1] / v[0]
    print(f"   {k_ * 100:+6.1f}pp  {v[0]:6d}   {hit * 100:6.2f}%      (模型平均分歧 {v[2] / v[0] * 100:+.1f}pp)")

print("\n  冷门检验：市场看好方被模型大幅看衰（分歧 ≤ -10pp）时，实际翻车率")
tot = hit = 0
for k_, v in cold.items():
    if k_ <= -0.10:
        tot += v[0]
        hit += v[0] - v[1]
print(f"   分歧≤-10pp: n={tot}  实际未命中(冷门/平) {hit / max(tot, 1) * 100:.2f}%")
tot2 = hit2 = 0
for k_, v in cold.items():
    if -0.05 <= k_ <= 0.05:
        tot2 += v[0]
        hit2 += v[0] - v[1]
print(f"   分歧≈0    : n={tot2}  实际未命中 {hit2 / max(tot2, 1) * 100:.2f}%")
