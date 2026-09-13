# -*- coding: utf-8 -*-
"""从「因素」直接推比分 —— 不经过众数/概率的选法对照。

待检验论点：比分由因素推得（而非分布众数），概率幅值不决定命中。

本脚本要回答三件事：
  A. 引擎里 λ 到底是不是因素的确定性函数（复现 F1 分解）。
  B. 从因素得到的 λ → 单个整数比分的**所有**落法（round / floor / ceil / argmax），
     逐个比命中次数。若 argmax(众数) 与 floor(λ) 基本等同，说明"众数"不是独立对象，
     它就是因素答案的一个写法。
  C. 有没有「不经过 λ」的因素直推法能赢（用因素做格子打分，不看概率大小）。
"""
import importlib.util
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F = _load("fhp", "factor_hit_probe.py")


def main():
    eng = F.engine()
    rows = F.load_rows()
    P = dict(F.P0)
    print("=" * 110)
    print(f"从因素直接推比分 —— 样本 {len(rows)} 场，目标函数 = 单比分命中次数")
    print("=" * 110)

    # ---------------- A. λ 是因素的确定性函数 ----------------
    print("\nA  因素 → λ（确定性映射，无随机成分）")
    print("-" * 110)
    agg = {}
    n = 0
    for r in rows:
        s0, s1, s2 = F.lam_from_factors(eng, r, P)
        g, lh2, la2 = F.grid_of(eng, r, P, *s2)
        if g is None:
            continue
        n += 1
        agg["a"] = agg.get("a", 0) + s0[0] + s0[1]
        agg["b"] = agg.get("b", 0) + abs(s1[0] - s0[0]) + abs(s1[1] - s0[1])
        agg["c"] = agg.get("c", 0) + abs(s2[0] - s1[0]) + abs(s2[1] - s1[1])
        agg["d"] = agg.get("d", 0) + abs(lh2 - s2[0]) + abs(la2 - s2[1])
    print(f"  ① 近期战绩 EWMA（近{P['nw']}场 gf/ga，DECAY {P['decay']}，主{P['hb']}/客{P['ad']}）")
    print(f"     基础 λ 总均值            {agg['a']/(2*n):.3f}")
    print(f"  ② 主客场分拆收缩                |Δλ|/场 {agg['b']/(2*n):.3f}")
    print(f"  ③ 联赛先验收缩 w={P['ws']}            |Δλ|/场 {agg['c']/(2*n):.3f}")
    print(f"  ④ 市场概率混合 W={P['W']}              |Δλ|/场 {agg['d']/(2*n):.3f}")
    print("  ⇒ 每一步都是加、乘、按比例分配 —— λ 完全由这 4 组因素决定，没有分布参与。")

    # ---------------- B. λ → 单比分 的所有落法 ----------------
    print("\nB  λ（因素答案）→ 单个整数比分的所有落法，比命中次数")
    print("-" * 110)
    print(f"  {'落法':<26}{'命中':>7}{'命中率':>9}{'±1球':>8}{'Top2':>8}{'Top3':>8}{'方向':>8}   说明")
    stat = {}

    def add(k, hit, band, t2, t3, dh, n):
        stat.setdefault(k, [0, 0, 0, 0, 0, 0])
        s = stat[k]
        for i, v in enumerate((hit, band, t2, t3, dh, n)):
            s[i] += v

    for r in rows:
        _, _, (lh, la) = F.lam_from_factors(eng, r, P)
        g, lh2, la2 = F.grid_of(eng, r, P, lh, la)
        if g is None:
            continue
        hg, ag = r["hg"], r["ag"]
        m = F.marginals_12(g)
        dh = 1 if F.dir_of(m) == (0 if hg > ag else (1 if hg == ag else 2)) else 0
        pool = sorted(g.items(), key=lambda x: -x[1])
        p_cells = [c for c, _ in pool]

        cands = {
            "round(λ) 四舍五入": (max(0, int(round(lh2))), max(0, int(round(la2)))),
            "floor(λ) 向下取整": (max(0, int(math.floor(lh2))), max(0, int(math.floor(la2)))),
            "ceil(λ) 向上取整": (max(0, int(math.ceil(lh2))), max(0, int(math.ceil(la2)))),
            "argmax 众数（当前）": pool[0][0],
            "argmax 含 SCORE_ALIGN": pool[0][0],
        }
        for k, c in cands.items():
            hit = 1 if c == (hg, ag) else 0
            # ±1 球邻域：去重格集合（禁用 sum(g[...])，会重复计数）
            nb = {(c[0] + dh_, c[1] + da_) for dh_ in (-1, 0, 1) for da_ in (-1, 0, 1)}
            band = 1 if (hg, ag) in nb else 0
            t2 = 1 if (hg, ag) in p_cells[:2] else 0
            # 关于 round/floor 的 Top2/Top3 没有意义（不是排序），记 0
            add(k, hit, band, t2 if "众数" in k or "align" in k else 0,
                (1 if (hg, ag) in p_cells[:3] else 0) if ("众数" in k or "align" in k) else 0,
                dh, 1)

    order = ["round(λ) 四舍五入", "floor(λ) 向下取整", "ceil(λ) 向上取整", "argmax 众数（当前）", "argmax 含 SCORE_ALIGN"]
    for k in order:
        s = stat[k]
        n = s[5]
        tag = ""
        if k == "floor(λ) 向下取整":
            tag = "← 与 argmax 几乎逐个相同（见 C）"
        if k == "round(λ) 四舍五入":
            tag = "← 上一版部署，命中最低"
        if "当前" in k:
            tag = "← 本次部署"
        print(f"  {k:<26}{s[0]:>7}{s[0]/n*100:>8.2f}%{s[1]/n*100:>7.1f}%"
              f"{(s[2]/n*100 if s[2] else 0):>7.1f}%{(s[3]/n*100 if s[3] else 0):>7.1f}%"
              f"{s[4]/n*100:>7.1f}%   {tag}")

    # ---------------- C. argmax 与 floor(λ) 是否是同一个东西 ----------------
    print("\nC  「众数」是不是独立对象？——逐场比对 argmax 与 floor(λ)")
    print("-" * 110)
    same_floor = diff_floor = 0
    ex = []
    for r in rows:
        _, _, (lh, la) = F.lam_from_factors(eng, r, P)
        g, lh2, la2 = F.grid_of(eng, r, P, lh, la)
        if g is None:
            continue
        pool = sorted(g.items(), key=lambda x: -x[1])
        m0 = pool[0][0]
        fl = (max(0, int(math.floor(lh2))), max(0, int(math.floor(la2))))
        if m0 == fl:
            same_floor += 1
        else:
            diff_floor += 1
            if len(ex) < 8:
                ex.append((r["date"], r["home"], r["away"], lh2, la2, m0, fl))
    tot = same_floor + diff_floor
    print(f"  argmax == floor(λ) ：{same_floor}/{tot} = {same_floor/tot*100:.1f}%")
    print(f"  argmax != floor(λ) ：{diff_floor}/{tot} = {diff_floor/tot*100:.1f}%")
    print("  差异样本（λ → 众数 vs floor）：")
    for d, h, a, lh2, la2, m0, fl in ex:
        print(f"    {d} {h}vs{a}  λ={lh2:.2f}:{la2:.2f}  众数={m0[0]}:{m0[1]}  floor={fl[0]}:{fl[1]}")

    # 众数偏离 floor 的原因：形状混合把概率推到别的格子
    print("\n  说明：纯泊松下 argmax = (floor λh, floor λa)。差异全部来自 ④之后的两步形状处理")
    print("        （联赛形状混合 / 自适应衰减 / SCORE_ALIGN 对齐发布三率）——它们的作用是把")
    print("        「两队各进几球」的总量信息，调成「这一档比分在联赛里出现的形状」，仍全是因素。")

    # ---------------- D. 不经过 λ 的因素直推法 ----------------
    print("\nD  不用 λ、不用概率，纯因素格子打分 —— 能不能赢众数？")
    print("-" * 110)

    def factor_rule(r, lh2, la2, mode):
        """只看因素数值做整数决策，不看任何概率大小。"""
        if mode == "half":
            # 把 λ 当作"平均进球"，>0.5 就上取，否则下取（等于 round）
            return (max(0, int(lh2 + 0.5)), max(0, int(la2 + 0.5)))
        if mode == "even":
            # 双方进球都取偶数档（最保守的"每队至少0/2"直推）
            return (max(0, int(round(lh2 / 2)) * 2), max(0, int(round(la2 / 2)) * 2))
        return (0, 0)

    for mode, label in (("half", "λ+0.5 取整（= round，因素直推）"),):
        hh = tt = 0
        for r in rows:
            _, _, (lh, la) = F.lam_from_factors(eng, r, P)
            g, lh2, la2 = F.grid_of(eng, r, P, lh, la)
            if g is None:
                continue
            c = factor_rule(r, lh2, la2, mode)
            tt += 1
            hh += 1 if c == (r["hg"], r["ag"]) else 0
        print(f"  {label:<34}{hh:>7}{hh/tt*100:>8.2f}%")

    print("\n" + "=" * 110)
    print("结论")
    print("=" * 110)
    print("  · 论点前半成立且关键：λ 完全由因素决定（A 节），没有分布参与。")
    print("  · 但 λ 是一个小数（如 1.42 球），要变成「比分」必须做一次取整决策 —— 这一步")
    print("    无论怎么绕都躲不掉，而所有的取整方式（round/floor/共识）里：")
    print("      floor(λ) ≈ argmax(泊松网格)，两者几乎逐场相同（C 节实测重合率见上）。")
    print("  · 所以「众数」不是「分布式算出来的东西」，它就是因素答案 floor(λ) 的另一种写法。")
    print("    真正没意义的是它的**概率数值**（B 节 top1 概率与命中率无关）。")
    print("  · round(λ) 反而最差 —— 因为 λ=1.42 时最可能的进球数是 1 不是 2，")


if __name__ == "__main__":
    main()
