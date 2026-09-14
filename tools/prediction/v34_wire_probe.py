#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v34_wire_probe.py — V3.4 两模块接线前的**证伪性**回测（2026-09-14）

背景：KALMAN_STRENGTH / HEDGE_ENSEMBLE 此前只有实现、没有接线（路线图却打印 ON）。
接线前必须先回答一个可证伪的问题：把它们作用于生产链路，**样本外会不会变差**。

样本与口径：复用 factor_hit_probe 的 4036 场因素集（含近期战绩 / 分主客战绩 / 联赛 /
1X2 赔率 / 赛果），λ 走与生产同源的链路：
  近期EWMA → 主客场分拆收缩 → 联赛先验收缩 → [Kalman 修正] → 市场概率混合(W)
  → 联赛经验形状混合 → Platt → 象限对齐

待测方案：
  C0 生产现状（W=0.80 固定，无 Kalman）
  C1 Kalman 修正在**市场混合之前**（模型侧，即生产接线的位置）
  C2 Kalman 修正在**市场混合之后**（对照组：验证位置选择）
  C3 HEDGE 动态市场权重（替代固定 0.80，η 扫描）
  C4 C1 + C3

评价：1X2 Brier（主判据）＋ 方向命中 / 比分单点命中 / Top3 / λMAE / λ偏差；
另附**分月稳定性**（Brier 逐月差值）—— 单月噪声大，需多数月份同向才算真信号。

判据（与项目既有纪律一致）：
  · 样本外 Brier 改善 ≥ 0.5% 且分月同向 ≥ 2/3 → 可接线生效（apply=True）
  · 否则接线但 apply=False（只记录不改预测）

用法：python v34_wire_probe.py [--quick]
"""
import argparse
import collections
import importlib.util
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F = _load("fhp", os.path.join(ROOT, "factor_hit_probe.py"))
eng = F.engine()
eng.fit_platt_params()
F.sync_from_profile(eng)

ETA_GRID = [6.0, 20.0, 40.0]
ETA_MAIN = 20.0
BAND = (0.70, 0.90)
WIN = 400
WARM = 100          # HEDGE 需要的最少历史损失样本

TAGS_STATIC = ["C0 生产(W=0.80)", "C1 Kalman(混前)", "C2 Kalman(混后)"]
TAGS_HEDGE = [f"C3 HEDGE动态(η={e:g})" for e in ETA_GRID] + [f"C4 C1+HEDGE(η={ETA_MAIN:g})"]


def grid_from_lambda(r, P, lh, la, W, post=None):
    """与 factor_hit_probe.grid_of 同源，但 W 显式传入；post=(mh,ma) 时在混后乘修正。"""
    pv = eng.devig_1x2(*r["o12"])
    if not pv:
        return None, None, None
    pm = eng.pois_1x2(lh, la)
    pb = [(1 - W) * pm[i] + W * pv[i] for i in range(3)]
    s = sum(pb)
    pb = [x / s for x in pb]
    lh2, la2 = eng.prob_to_lambda(pb, (lh + la))
    if post:
        lh2, la2 = lh2 * post[0], la2 * post[1]
    g = F.poisson_grid(lh2, la2)
    lo, hi = min(lh2, la2), max(lh2, la2)
    _old = (eng.ADAPTIVE_MIX_K, eng.ADAPTIVE_MIX_FLOOR)
    eng.ADAPTIVE_MIX_K, eng.ADAPTIVE_MIX_FLOOR = P["amk"], P["amf"]
    _sw = eng.LEAGUE_PROFILE.setdefault("score_mix", {}).get("w", 0.5)
    eng.LEAGUE_PROFILE["score_mix"]["w"] = P["mixw"]
    try:
        g = eng.mix_score_matrix(g, r["lg"], hi / lo if lo > 1e-9 else 99.0)
    finally:
        eng.ADAPTIVE_MIX_K, eng.ADAPTIVE_MIX_FLOOR = _old
        eng.LEAGUE_PROFILE["score_mix"]["w"] = _sw
    pub = list(eng.apply_platt(*F.marginals_12(g)))
    g = F.quad_align(g, pub)
    return g, lh2, la2


def new_acc():
    return {"n": 0, "brier": 0.0, "dir": 0, "hit": 0, "top3": 0, "mae": 0.0, "lb": 0.0,
            "months": collections.defaultdict(lambda: [0.0, 0])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()

    rows = F.load_rows(a.quick)
    P = dict(F.P0)
    print("=" * 118)
    print("v34_wire_probe.py — V3.4 接线前证伪回测（KALMAN_STRENGTH / HEDGE_ENSEMBLE）")
    print(f"样本 {len(rows)} 场 | {rows[0]['date']} ~ {rows[-1]['date']} | 口径=生产链路（含档案旋钮）")
    print("=" * 118)

    # ---------- Kalman 强度库：walk-forward 逐场取「赛前」修正 ----------
    matches = [{"date": r["date"], "league": r["lg"], "home": r["home"], "away": r["away"],
                "hg": r["hg"], "ag": r["ag"]} for r in rows]
    _db, snaps = eng.replay_strength(matches, collect=True)
    mods = [s["mods"] for s in snaps]
    cov = sum(1 for m in mods if m != (1.0, 1.0))
    dev = [abs(m[0] - 1.0) for m in mods] + [abs(m[1] - 1.0) for m in mods]
    print(f"\nKalman 强度库：覆盖球队 {len(_db['teams'])} | 非中性修正 {cov}/{len(mods)}"
          f"（{cov/len(mods)*100:.1f}%）| |修正−1| 均值 {sum(dev)/len(dev):.4f} 最大 {max(dev):.4f}")
    print(f"  状态分布示例（主队进攻/防守偏置）: " + ", ".join(
        f"{t}:{round(v['ha'],3)}/{round(v['hd'],3)}"
        for t, v in list(_db["teams"].items())[:6]))

    # ---------- 主循环 ----------
    full = {t: new_acc() for t in TAGS_STATIC + TAGS_HEDGE}
    oos = {t: new_acc() for t in TAGS_STATIC + TAGS_HEDGE}
    cut = int(len(rows) * 0.6)
    hist_lm = collections.deque(maxlen=WIN)
    hist_lv = collections.deque(maxlen=WIN)

    for i, r in enumerate(rows):
        _s0, _s1, s2 = F.lam_from_factors(eng, r, P)
        lh_m, la_m = s2
        mh, ma = mods[i]

        pv = eng.devig_1x2(*r["o12"])
        pm = eng.pois_1x2(lh_m, la_m)
        y = 0 if r["hg"] > r["ag"] else (1 if r["hg"] == r["ag"] else 2)
        if pv:
            hist_lm.append(-math.log(max(pm[y], 1e-9)))
            hist_lv.append(-math.log(max(pv[y], 1e-9)))

        w_hedge = {}
        for eta in ETA_GRID:
            if len(hist_lm) >= WARM:
                w = eng.hedge_weights({"model": sum(hist_lm) / len(hist_lm),
                                       "market": sum(hist_lv) / len(hist_lv)}, eta=eta)
                w_hedge[eta] = min(max(w["market"], BAND[0]), BAND[1])
            else:
                w_hedge[eta] = P["W"]

        variants = [("C0 生产(W=0.80)", lh_m, la_m, P["W"], None),
                    ("C1 Kalman(混前)", lh_m * mh, la_m * ma, P["W"], None),
                    ("C2 Kalman(混后)", lh_m, la_m, P["W"], (mh, ma))]
        if len(hist_lm) >= WARM:
            for eta in ETA_GRID:
                variants.append((f"C3 HEDGE动态(η={eta:g})", lh_m, la_m, w_hedge[eta], None))
            variants.append((f"C4 C1+HEDGE(η={ETA_MAIN:g})", lh_m * mh, la_m * ma,
                             w_hedge[ETA_MAIN], None))

        yv = [1.0 if y == k else 0.0 for k in range(3)]
        act = (r["hg"], r["ag"])
        for tag, lh, la, W, post in variants:
            g, lh2, la2 = grid_from_lambda(r, P, lh, la, W, post)
            if g is None:
                continue
            m = F.marginals_12(g)
            br = sum((m[k] - yv[k]) ** 2 for k in range(3))
            pool = sorted(g.items(), key=lambda x: -x[1])
            o = (i >= cut)
            for acc in (full[tag], oos[tag]) if o else (full[tag],):
                acc["n"] += 1
                acc["brier"] += br
                acc["dir"] += int(F.dir_of(m) == y)
                acc["hit"] += int(pool[0][0] == act)
                acc["top3"] += int(act in [c for c, _ in pool[:3]])
                acc["mae"] += abs(lh2 - r["hg"]) + abs(la2 - r["ag"])
                acc["lb"] += (lh2 + la2) - (r["hg"] + r["ag"])
                acc["months"][r["date"][:7]][0] += br
                acc["months"][r["date"][:7]][1] += 1

    # ---------- 输出 ----------
    order = TAGS_STATIC + TAGS_HEDGE
    header = (f"{'方案':<24}{'n':>5}{'Brier':>9}{'方向%':>8}{'单点%':>8}{'Top3%':>8}"
              f"{'λMAE':>8}{'λ偏差':>8}{'OOS n':>7}{'OOS Brier':>11}{'OOS Δ':>9}")

    def show(accs):
        b0 = accs["C0 生产(W=0.80)"]
        b0br = b0["brier"] / b0["n"] if b0["n"] else 0
        for tag in order:
            d = accs[tag]
            n = d["n"]
            if not n:
                print(f"{tag:<24}{'—':>5}（样本不足，HEDGE 需 ≥{WARM} 场预热）")
                continue
            br = d["brier"] / n
            print(f"{tag:<24}{n:>5}{br:>9.4f}{d['dir']/n*100:>8.2f}{d['hit']/n*100:>8.2f}"
                  f"{d['top3']/n*100:>8.2f}{d['mae']/n:>8.4f}{d['lb']/n:>+8.3f}")

    print("\n【全样本】")
    print(header)
    print("-" * 118)
    show(full)
    print("\n【样本外（后 40%）】")
    print(header)
    print("-" * 118)
    show(oos)

    # ---------- 分月稳定性（全样本 Brier 逐月差值） ----------
    b0m = full["C0 生产(W=0.80)"]["months"]
    print("\n分月 Brier 差值（vs C0；负 = 该月改善）")
    print(f"  {'月份':<9}{'C0 Brier':>10}{'C1 Kalman':>12}{'C2 混后':>11}"
          f"{'C3(η=20)':>11}{'C4':>11}")
    for mo in sorted(b0m):
        if b0m[mo][1] < 10:
            continue
        c0 = b0m[mo][0] / b0m[mo][1]
        cells = []
        for tag in ("C1 Kalman(混前)", "C2 Kalman(混后)",
                    f"C3 HEDGE动态(η={ETA_MAIN:g})", f"C4 C1+HEDGE(η={ETA_MAIN:g})"):
            mm = full[tag]["months"].get(mo)
            cells.append(f"{mm[0]/mm[1]-c0:>+11.4f}" if mm else f"{'—':>11}")
        print(f"  {mo:<9}{c0:>10.4f}" + "".join(cells))

    # ---------- 判据 ----------
    print("\n【判据】样本外 Brier 改善 ≥0.5% 且分月同向 ≥2/3 → 接线生效（apply=True）")
    o0 = oos["C0 生产(W=0.80)"]
    o0br = o0["brier"] / o0["n"] if o0["n"] else 0
    for tag in order[1:]:
        d = oos[tag]
        if not d["n"]:
            continue
        br = d["brier"] / d["n"]
        delta = (br - o0br) / o0br * 100
        mon = full[tag]["months"]
        base_mon = full["C0 生产(W=0.80)"]["months"]
        better = worse = 0
        for mo in base_mon:
            if base_mon[mo][1] < 10 or mo not in mon:
                continue
            if mon[mo][0] / mon[mo][1] < base_mon[mo][0] / base_mon[mo][1]:
                better += 1
            else:
                worse += 1
        print(f"  {tag:<24} OOS Δ {delta:+.2f}% | 分月 改善{better}/恶化{worse}"
              f" → {'✅ 可生效' if (delta <= -0.5 and better >= 2 * max(1, better + worse) / 3) else '❌ 只记录(apply=False)'}")


if __name__ == "__main__":
    main()
