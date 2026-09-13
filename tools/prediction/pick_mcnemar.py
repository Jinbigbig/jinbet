# -*- coding: utf-8 -*-
"""在 4036 场大样本上重做「择格口径」的配对显著性检验（从 _grid_cache.json 直接算）。

要回答：把头条从「联合众数」换成无脑猜 1:1 / floor(λ) / round(λ)，命中次数的差是否显著？
"""
import json
import math
import os
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(ROOT, "_grid_cache.json"), encoding="utf-8"))
n = len(D)
act = [f"{x['hg']}:{x['ag']}" for x in D]
print("=" * 100)
print(f"择格口径配对检验（McNemar）—— 样本 {n} 场")
print("=" * 100)

schemes = {
    "联合众数（部署中）": [x["top"][0][0] for x in D],
    "常数：全猜 1:1": ["1:1"] * n,
    "floor(λ) 向下取整": [f"{max(0, math.floor(x['lh']))}:{max(0, math.floor(x['la']))}" for x in D],
    "round(λ) 四舍五入": [f"{max(0, round(x['lh']))}:{max(0, round(x['la']))}" for x in D],
    "△ 左上角合并（floor 与众数取并集优先）": [x["top"][0][0] for x in D],  # 占位，下面替换
}
# 「并集优先」= 若 floor(λ) 在 top2 里就用 floor，否则用众数
schemes["△ 左上角合并（floor 与众数取并集优先）"] = [
    (f"{max(0, math.floor(x['lh']))}:{max(0, math.floor(x['la']))}"
     if f"{max(0, math.floor(x['lh']))}:{max(0, math.floor(x['la']))}" in [t[0] for t in x["top"][:2]]
     else x["top"][0][0]) for x in D
]

hits = {k: [s == a for s, a in zip(v, act)] for k, v in schemes.items()}
print(f"\n  {'口径':<34}{'命中':>7}{'命中率':>9}")
for k, h in sorted(hits.items(), key=lambda kv: -sum(kv[1])):
    print(f"  {k:<34}{sum(h):>7}{sum(h)/n*100:>8.2f}%")

base = "联合众数（部署中）"
print(f"\n  配对检验（对照 = {base}）：")
print(f"  {'对手':<34}{'我方独中':>9}{'对方独中':>9}{'χ²':>8}   显著性")
for k in schemes:
    if k == base:
        continue
    w10 = sum(1 for a, b in zip(hits[base], hits[k]) if a and not b)   # 众数独中
    w01 = sum(1 for a, b in zip(hits[base], hits[k]) if (not a) and b)  # 对手独中
    d = w10 - w01
    if w10 + w01 == 0:
        chi = 0.0
    else:
        chi = (abs(d) - 1) ** 2 / (w10 + w01)
    sig = "✅ p<0.05" if chi > 3.84 else ("~ p<0.10" if chi > 2.71 else "✗ 不显著")
    print(f"  {k:<34}{w10:>9}{w01:>9}{chi:>8.2f}   {sig}（净 {d:+d} 场）")

print("\n" + "=" * 100)
print("附带：模型首选比分的集中度")
print("=" * 100)
c = Counter(x["top"][0][0] for x in D)
for s, k in c.most_common(8):
    print(f"  {s:<7}{k:>5}  {k/n*100:>5.1f}%")
print(f"\n  1:1 退化率 = {c['1:1']/n*100:.1f}%（不是 bug：独立泊松联合众数 = (⌊λ主⌋,⌊λ客⌋)，"
      f"λ 双双落在 [1,2) 时必然 1:1）")
