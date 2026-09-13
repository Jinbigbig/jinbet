# -*- coding: utf-8 -*-
"""每日精选：模型在哪些场次对「单比分」真的有把握？

背景（_baseline_probe.py 已证）：
  · 模型 argmax 15.61% vs 无脑猜 1:1 的 12.93%，净多中 108 场（χ²=32.16 显著）——有内容；
  · 但 65.4% 的场次都选 1:1，且因素调参无法再提升（factor_hit_probe F3/F4）。
⇒ 择格规则已到顶。剩下的增量不在「预测所有场次」，而在「挑出模型真有把握的场次」。

本脚本量化：按模型自评概率排序，每天取前 k 场，单比分命中率是多少？
对照：λ 总量最低的前 k 场、方向最确定的前 k 场。
"""
import importlib.util
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
CACHE = os.path.join(ROOT, "_grid_cache.json")


def main():
    D = json.load(open(CACHE, encoding="utf-8"))
    by_day = defaultdict(list)
    for x in D:
        by_day[x["d"]].append(x)
    nd = len(by_day)
    n = len(D)
    print("=" * 106)
    print(f"每日精选检验 —— {n} 场 / {nd} 个比赛日")
    print("=" * 106)

    def hit(x):
        return x["top"][0][0] == f"{x['hg']}:{x['ag']}"

    def band(x):
        c = tuple(int(v) for v in x["top"][0][0].split(":"))
        nb = {(c[0] + i, c[1] + j) for i in (-1, 0, 1) for j in (-1, 0, 1)}
        return (x["hg"], x["ag"]) in nb

    def top2(x):
        return f"{x['hg']}:{x['ag']}" in [t[0] for t in x["top"][:2]]

    print(f"\n  全体基线：单比分 {sum(hit(x) for x in D)/n*100:.2f}%   双档 "
          f"{sum(top2(x) for x in D)/n*100:.2f}%   ±1球 {sum(band(x) for x in D)/n*100:.2f}%")

    def daily_top(k, keyfn, reverse):
        """每天按 keyfn 排序取前 k 场，统计单比分命中率与「当天至少中 1 场」的比例。"""
        hh = tt = dhit = 0
        for d, ms in by_day.items():
            sel = sorted(ms, key=keyfn, reverse=reverse)[:k]
            tt += len(sel)
            h = sum(hit(x) for x in sel)
            hh += h
            dhit += 1 if h else 0
        return hh, tt, dhit, len(by_day)

    rankers = [
        ("模型自评 Top1 概率（= 众数概率）", lambda x: x["top"][0][1], True),
        ("λ 总量最低（低进球场次）", lambda x: x["lh"] + x["la"], False),
        ("模型自评 P(1:1) 最高", lambda x: x["p11"], True),
        ("首选概率 ÷ λ总量（确定性/进球量）", lambda x: x["top"][0][1] / max(0.5, x["lh"] + x["la"]), True),
    ]

    for name, fn, rev in rankers:
        print(f"\n  【{name}】")
        print(f"  {'每日取前 k':<12}{'场次':>7}{'单比分命中':>12}{'当天至少中1场':>14}")
        for k in (1, 2, 3, 5, 8, 999):
            hh, tt, dhit, _ = daily_top(k, fn, rev)
            lab = f"k={k}" if k != 999 else "全部"
            print(f"  {lab:<12}{tt:>7}{hh:>8} ({hh/tt*100:>5.2f}%){(dhit/len(by_day)*100):>13.1f}%")

    # ---- 交叉：低 λ 总量 × 高概率 的交集 ----
    print("\n  交叉筛选：λ 总量 ≤ 阈值 且 首选概率 ≥ 阈值 的子集")
    print(f"  {'λ总≤':<8}{'概率≥':<8}{'场次':>7}{'单比分命中':>12}{'双档':>9}{'±1球':>9}")
    for lt in (2.2, 2.5, 2.8):
        for pt in (0.10, 0.11):
            sub = [x for x in D if (x["lh"] + x["la"]) <= lt and x["top"][0][1] >= pt]
            if len(sub) < 30:
                continue
            h = sum(hit(x) for x in sub)
            b2 = sum(1 for x in sub if f"{x['hg']}:{x['ag']}" in [t[0] for t in x["top"][:2]])
            bb = sum(band(x) for x in sub)
            print(f"  {lt:<8}{pt:<8}{len(sub):>7}{h:>7} ({h/len(sub)*100:>5.2f}%)"
                  f"{b2/len(sub)*100:>8.2f}%{bb/len(sub)*100:>8.2f}%")

    # ---- 每日精选的实证：命中率提升倍数 ----
    print("\n" + "=" * 106)
    print("结论")
    print("=" * 106)
    h3, t3, d3, _ = daily_top(3, lambda x: x["top"][0][1], True)
    hall = sum(hit(x) for x in D)
    print(f"  · 全场次平均 单比分 {hall/n*100:.2f}%；每天只取模型自评最高的 3 场 → {h3/t3*100:.2f}%"
          f"（{h3/t3/(hall/n):.2f}× 提升），且 {d3/nd*100:.0f}% 的日子至少中 1 场。")
    h1, t1, d1, _ = daily_top(1, lambda x: x["top"][0][1], True)
    print(f"  · 每天只取 1 场（自评最高）→ {h1/t1*100:.2f}%（{h1} 次命中 / {t1} 天）。")
    print("  · 这就是「择格已到顶」之后的可用增量：不是预测更多场，而是**挑出该押的场**。")


if __name__ == "__main__":
    main()
