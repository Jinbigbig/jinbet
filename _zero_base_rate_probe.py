# -*- coding: utf-8 -*-
"""历史基准率：实际赛果中「至少一方 0 球（零封）」占多大比例？并按热门赔率分档对照。"""
import json
import os
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(BASE, "results_data.json"), encoding="utf-8"))

rows = []
for k, v in d.items():
    fs = str(v.get("fullScore") or v.get("score") or "")
    if ":" not in fs:
        continue
    try:
        h, a = [int(x) for x in fs.split(":")[:2]]
    except ValueError:
        continue
    try:
        oh, oa = float(v.get("胜")), float(v.get("负"))
    except (TypeError, ValueError):
        oh = oa = None
    date = k[:10]
    rows.append({"date": date, "h": h, "a": a, "oh": oh, "oa": oa,
                 "zero": (h == 0 or a == 0), "league": v.get("leagueAbbr") or v.get("league")})

n = len(rows)
z = sum(r["zero"] for r in rows)
print(f"赛果库 {n} 场 | 实际「至少一方 0 球」= {z}/{n} = {z/n:.1%}")
print(f"  其中 0-0 平局 = {sum(1 for r in rows if r['h'] == 0 and r['a'] == 0)/n:.1%}")

# 按「最热门方赔率」分档（越低=越悬殊）
bands = [(0, 1.20), (1.20, 1.35), (1.35, 1.60), (1.60, 2.00), (2.00, 99)]
print("\n按最热门方赔率分档（赔率越低越悬殊）:")
for lo, hi in bands:
    sub = [r for r in rows if r["oh"] and r["oa"]
           and lo <= min(r["oh"], r["oa"]) < hi]
    if not sub:
        continue
    zz = sum(r["zero"] for r in sub)
    print(f"  最热 {lo:.2f}~{hi:.2f}: n={len(sub):>5} 零封 {zz/len(sub):>6.1%}")

# 强热门（≤1.35）的零封率 —— 今日 12 场里 6 场属此档
strong = [r for r in rows if r["oh"] and r["oa"] and min(r["oh"], r["oa"]) <= 1.35]
print(f"\n强热门（最热赔率 ≤1.35）: n={len(strong)} 零封率 {sum(r['zero'] for r in strong)/len(strong):.1%}")

# 按日窗口：单一比赛日零封占比分布
by_date = defaultdict(list)
for r in rows:
    by_date[r["date"]].append(r["zero"])
rates = sorted(sum(v) / len(v) for v in by_date.values() if len(v) >= 6)
k = len(rates)
if k:
    print(f"\n单日零封占比（≥6 场/日，共 {k} 天）：中位 {rates[k//2]:.1%} | "
          f"P75 {rates[3*k//4]:.1%} | P90 {rates[int(k*0.9)]:.1%} | 最大 {rates[-1]:.1%}")
    print(f"  单日 ≥75% 的天数 {sum(1 for r in rates if r >= 0.75)}/{k} = "
          f"{sum(1 for r in rates if r >= 0.75)/k:.1%}")

# 12 场滑动窗口零封数分布
seq = []
for dt in sorted(by_date):
    seq.extend(by_date[dt])
w = 12
cnt = defaultdict(int)
for i in range(len(seq) - w + 1):
    cnt[sum(seq[i:i + w])] += 1
tot = sum(cnt.values())
print(f"\n12 场滚动窗口（n={tot}）零封场次数分布：")
for kk in sorted(cnt):
    if cnt[kk] / tot >= 0.01:
        print(f"  {kk:>2} 场: {cnt[kk]/tot:>6.2%}")
ge9 = sum(v for kk, v in cnt.items() if kk >= 9)
print(f"  ≥9 场: {ge9/tot:.2%}   （今日为 9/12）")
