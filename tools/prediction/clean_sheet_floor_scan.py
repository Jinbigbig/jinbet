# -*- coding: utf-8 -*-
"""单队 λ 下界扫描（2026-09-14）：下界取多大才既压住「0封虚高」又不伤命中？

背景：09-14 头条 9/12 场含 0 球（75%）。已定位两处退化（λ 被反解推到网格边界；
零封修正放大 0 球格）。前者靠 MIN_SINGLE=0.18 止损，但 0.18 仍让「弱侧 0 球」
概率高达 83%，而历史 4036 场里 λ 比 5~20 的场次实际零封率只有 62% —— 说明
极端悬殊场次的 λ 弱侧仍偏低。本探针扫下界 0.18~0.50，看能否同时：
  (a) 把极端档的「预测 P(某方0球)」拉回实际值附近；
  (b) 单点命中 / ±1球 / Brier 不受损。

用法：python _clean_sheet_floor_scan.py
"""
import importlib.util
import math
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _find(*names):
    """同名脚本在本地带 `_` 前缀、在 master tools/prediction/ 不带 —— 两个名字都试。"""
    for nm in names:
        p = os.path.join(ROOT, nm)
        if os.path.exists(p):
            return p
    return os.path.join(ROOT, names[0])


S = _load("sfp", _find("_score_floor_probe.py", "score_floor_probe.py"))
F, eng = S.F, S.eng

FLOORS = [0.0, 0.18, 0.30, 0.40, 0.50]
EB_K = 40


def band(ratio):
    if ratio < 1.5:
        return "A 势均<1.5"
    if ratio < 2.5:
        return "B 略偏1.5~2.5"
    if ratio < 5:
        return "C 明显2.5~5"
    if ratio < 20:
        return "D 悬殊5~20"
    return "E 极端>20"


def main():
    rows = F.load_rows()
    P = dict(F.P0)
    S.apply_baseline(eng, EB_K)
    print("=" * 120)
    print(f"单队 λ 下界扫描 — 样本 {len(rows)} 场 | 零封修正已改为只削弱(ZF_CAP=1.0) "
          f"| 基线收缩 k={EB_K}")
    print("=" * 120)

    res = {}
    for ms in FLOORS:
        acc = dict(n=0, hit=0, p1=0, br=0.0, zhs=0, pz=0.0, actz=0, tot=0.0, bind=0)
        bd = defaultdict(lambda: [0, 0.0, 0])   # band -> [n, ΣP(0), 实际零封数]
        for r in rows:
            _s0, _s1, s2 = F.lam_from_factors(eng, r, P)
            g, lh2, la2 = S.chain(r, P, s2[0], s2[1], ms, 1.0, "flat")
            if g is None:
                continue
            m = F.marginals_12(g)
            pool = sorted(g.items(), key=lambda x: -x[1])
            y = 0 if r["hg"] > r["ag"] else (1 if r["hg"] == r["ag"] else 2)
            yv = [1.0 if y == k else 0.0 for k in range(3)]
            acc["n"] += 1
            acc["hit"] += int(pool[0][0] == (r["hg"], r["ag"]))
            acc["p1"] += int(abs(pool[0][0][0] - r["hg"]) <= 1 and abs(pool[0][0][1] - r["ag"]) <= 1)
            acc["br"] += sum((m[k] - yv[k]) ** 2 for k in range(3))
            acc["zhs"] += int(pool[0][0][0] == 0 or pool[0][0][1] == 0)
            pz = 1 - (1 - math.exp(-lh2)) * (1 - math.exp(-la2))
            acc["pz"] += pz
            acc["actz"] += int(r["hg"] == 0 or r["ag"] == 0)
            if ms > 0 and min(lh2, la2) <= ms + 1e-6:
                acc["bind"] += 1
            lo, hi = min(lh2, la2), max(lh2, la2)
            rt = (hi / lo) if lo > 1e-9 else 99.0
            b = band(rt)
            bd[b][0] += 1
            bd[b][1] += pz
            bd[b][2] += int(r["hg"] == 0 or r["ag"] == 0)
        res[ms] = (acc, bd)

    n = res[FLOORS[0]][0]["n"]
    print(f"\n【总体】n={n}   实际「某方 0 球」率 = {res[FLOORS[0]][0]['actz']/n*100:.1f}%")
    print(f"  {'下界':>6}{'绑定场次':>9}{'单点%':>8}{'±1球%':>8}{'Brier':>9}"
          f"{'头条0封%':>9}{'P(0封)均值':>11}")
    for ms in FLOORS:
        a = res[ms][0]
        print(f"  {ms:>6.2f}{a['bind']:>9}{a['hit']/n*100:>8.2f}{a['p1']/n*100:>8.2f}"
              f"{a['br']/n:>9.4f}{a['zhs']/n*100:>9.1f}{a['pz']/n*100:>11.1f}")

    print("\n【分档校准】预测 P(某方 0 球) vs 实际零封率（λ 比越大，模型越偏）")
    print(f"  {'档':<14}" + "".join(f"{'ms=' + str(ms):>22}" for ms in FLOORS))
    print(f"  {'':<14}" + "".join(f"{'预测/实际(n)':>22}" for _ in FLOORS))
    for b in ("A 势均<1.5", "B 略偏1.5~2.5", "C 明显2.5~5", "D 悬殊5~20", "E 极端>20"):
        cells = []
        for ms in FLOORS:
            bd = res[ms][1].get(b)
            if not bd or bd[0] == 0:
                cells.append(f"{'—':>22}")
                continue
            cells.append(f"{bd[1]/bd[0]*100:>10.1f}%/{bd[2]/bd[0]*100:>5.1f}%({bd[0]})")
        print(f"  {b:<14}" + "".join(cells))

    print("\n【判据】下界应满足：单点/±1球 不下降、Brier 不升、且 D/E 档「预测−实际」的偏差收窄。")


if __name__ == "__main__":
    main()
