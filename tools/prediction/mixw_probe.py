# -*- coding: utf-8 -*-
"""形状混合权重 w 的真实影响 —— 生产档案是 0.3，但代码注释/探针都按 0.5 假设。

背景：build_league_profile.py 写入 score_mix.w = 0.3（w=0.3 时代的遗留），
      _calc_engine.mix_score_matrix 读取该档案值 → **线上实跑 w_eff ≤ 0.3**。
      而引擎注释、factor_hit_probe 的"生产口径"、项目记忆都按 0.5 处理。
本脚本测：0.3（真实线上） vs 0.5（文档声称） 的命中次数差，并做时间外验证。
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    F = _load("fhp", "factor_hit_probe.py")
    eng = F.engine()
    rows = F.load_rows()
    prof_w = eng.LEAGUE_PROFILE.get("score_mix", {}).get("w")
    print("=" * 108)
    print(f"形状混合权重 w：档案实际值 = {prof_w}   （代码注释/探针假设 = 0.5）")
    print("=" * 108)

    GRID = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70]
    res = {}
    for w in GRID:
        r = F.ev(eng, rows, mixw=w)[0]
        res[w] = r
    print(f"\n  全样本 {len(rows)} 场（时间上不分段，仅看口径差）")
    print(f"  {'w':<8}{'命中':>7}{'命中率':>9}{'Top2':>8}{'Top3':>8}{'方向':>8}   说明")
    for w in GRID:
        r = res[w]
        tag = ""
        if abs(w - 0.3) < 1e-9:
            tag = "← 线上真实口径"
        if abs(w - 0.5) < 1e-9:
            tag = "← 文档/探针假设"
        print(f"  {w:<8}{r['hit']:>7}{r['hit%']:>8.2f}%{r['top2%']:>7.2f}%{r['top3%']:>7.2f}%"
              f"{r['dir%']:>7.2f}%   {tag}")
    d = res[0.5]["hit"] - res[0.3]["hit"]
    print(f"\n  ⇒ w 0.3 → 0.5：命中 {res[0.3]['hit']} → {res[0.5]['hit']}"
          f"（{d:+d} 场 / {res[0.3]['hit%']:.2f}% → {res[0.5]['hit%']:.2f}%，"
          f"{res[0.5]['hit%']-res[0.3]['hit%']:+.2f}pp）")

    # ---- 时间外：前 60% 选 w，后 40% 检验 ----
    n = len(rows)
    cut = int(n * 0.6)
    tr, te = rows[:cut], rows[cut:]
    print(f"\n  时间外验证：训练 {len(tr)} 场（前60%） → 检验 {len(te)} 场（后40%）")
    print(f"  {'w':<8}{'训练命中率':>12}{'检验命中率':>12}{'检验命中':>10}")
    best_w, best = None, -1
    for w in GRID:
        a = F.ev(eng, tr, cache={}, mixw=w)[0]
        b = F.ev(eng, te, cache={}, mixw=w)[0]
        print(f"  {w:<8}{a['hit%']:>11.2f}%{b['hit%']:>11.2f}%{b['hit']:>10}")
        if a["hit"] > best:
            best, best_w = a["hit"], w
    bt = F.ev(eng, te, cache={}, mixw=best_w)[0]
    print(f"\n  训练集最优 w = {best_w} → 检验命中 {bt['hit']}（{bt['hit%']:.2f}%）")
    print(f"  线上原值 w=0.3 → 检验命中 {F.ev(eng, te, cache={}, mixw=0.3)[0]['hit']}"
          f"（{F.ev(eng, te, cache={}, mixw=0.3)[0]['hit%']:.2f}%）")

    # ---- λ 比分层：混合对强弱悬殊场次的影响（诊断用）----
    print("\n  分层诊断（全样本，λ比 = max/min）：")
    print(f"  {'λ比档':<14}{'场次':>7}{'w=0.3命中率':>13}{'w=0.5命中率':>13}{'差':>9}")
    for lo, hi, lbl in ((1.0, 1.5, "1.0~1.5"), (1.5, 2.0, "1.5~2.0"),
                        (2.0, 3.0, "2.0~3.0"), (3.0, 99, ">3.0")):
        sub = []
        for r in rows:
            _, _, (lh, la) = F.lam_from_factors(eng, r, F.P0)
            _, lh2, la2 = F.grid_of(eng, r, F.P0, lh, la)
            if lh2 is None:
                continue
            ratio = max(lh2, la2) / max(1e-9, min(lh2, la2))
            if lo <= ratio < hi:
                sub.append(r)
        if not sub:
            continue
        a = F.ev(eng, sub, cache={}, mixw=0.3)[0]
        b = F.ev(eng, sub, cache={}, mixw=0.5)[0]
        print(f"  {lbl:<14}{a['n']:>7}{a['hit%']:>12.2f}%{b['hit%']:>12.2f}%"
              f"{b['hit%']-a['hit%']:>+8.2f}pp")


if __name__ == "__main__":
    main()
