# -*- coding: utf-8 -*-
"""诊断：今日 9/12 零封是否符合「这批对阵」的历史规律？按 λ 悬殊度分档对照。"""
import json
import math
import os
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
recs = json.load(open(os.path.join(BASE, "_grid_cache.json"), encoding="utf-8"))
today = json.load(open(os.path.join(BASE, "_calc_result.json"), encoding="utf-8"))["matches"]


def p_zero(lh, la):
    """P(至少一方 0 球) = 1 - P(双方都进球)。"""
    return 1 - (1 - math.exp(-lh)) * (1 - math.exp(-la))


def band(r):
    lo, hi = min(r, 1 / r), max(r, 1 / r)
    if hi < 1.5:
        return "A 势均(<1.5)"
    if hi < 2.5:
        return "B 略偏(1.5~2.5)"
    if hi < 5:
        return "C 明显(2.5~5)"
    if hi < 20:
        return "D 悬殊(5~20)"
    return "E 极端(>20)"


# 历史：按 λ 悬殊度分档的实际零封率 + Poisson 预测零封率
hist = defaultdict(lambda: [0, 0, 0.0])
for r in recs:
    lh, la = r["lh"], r["la"]
    if lh <= 0 or la <= 0:
        continue
    b = band(lh / la)
    hist[b][0] += 1
    hist[b][1] += int(r["hg"] == 0 or r["ag"] == 0)
    hist[b][2] += p_zero(lh, la)

print("=== 历史（4036 场）：按 λ 悬殊度分档 ===")
print(f"{'档':<16}{'n':>6}{'实际零封率':>11}{'Poisson预测零封率':>18}")
for b in sorted(hist):
    n, z, pz = hist[b]
    print(f"{b:<16}{n:>6}{z/n:>11.1%}{pz/n:>18.1%}")

print("\n=== 今日 12 场 ===")
print(f"{'编号':<8}{'对阵':<22}{'λ主/客':>13}{'悬殊':>7}{'档':>16}{'预测P(零封)':>12}{'报告首选':>10}")
cnt = defaultdict(int)
exp = 0.0
for m in sorted(today, key=lambda x: x["matchNumStr"]):
    lh, la = m["lam_home"], m["lam_away"]
    ratio = (max(lh, la) / min(lh, la)) if min(lh, la) > 1e-9 else float("inf")
    b = band(ratio if ratio else 999)
    cnt[b] += 1
    exp += p_zero(lh, la)
    print(f"{m['matchNumStr']:<8}{(m['home'] + 'vs' + m['away']):<22}"
          f"{lh:>6.2f}/{la:<6.2f}{ratio:>7.1f}{b:>16}{p_zero(lh, la):>12.1%}"
          f"{m['top_scores'][0]['score']:>10}")

print(f"\n今日分档构成: {dict(cnt)}")
print(f"按「今日各档的 λ」用 Poisson 估的期望零封场次 = {exp:.2f}/12 = {exp/12:.0%}")
# 用历史各档实际零封率加权（更贴近真实）
exp2 = tot = 0
for m in today:
    lh, la = m["lam_home"], m["lam_away"]
    ratio = max(lh, la) / min(lh, la) if min(lh, la) > 1e-9 else 999
    b = band(ratio)
    if hist[b][0]:
        exp2 += hist[b][1] / hist[b][0]
        tot += 1
print(f"按历史各档「实际」零封率加权 = {exp2:.2f}/{tot} = {exp2/tot:.0%}   （实际预测了 9/12 = 75%）")
