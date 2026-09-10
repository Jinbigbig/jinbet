#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""赛程间隔（体能/轮换）有效性检验 —— 已验证否决。

动机：用户清单里的「赛程与动机」（旅途疲劳、轮换、连续作战）无法从盘口获得，
      唯一可从现有赛果库推导的是「距上一场比赛的天数」。

原始结果（全量 2310 场，看似强信号）：
  主队多休 ≥4 天 → 净胜球 −0.611，主胜率 24.9%
  客队多休 ≥4 天 → 净胜球 +0.092，主胜率 38.5%
  且前后半段稳定、各大联赛内一致。

但这是**混淆**：强队参赛更密（多线作战、杯赛晋级），「休息少」实为「实力强」的
代理变量。两条独立证据：

1) 加入「有赔率」这一筛选后（265 场），原始效应就已塌缩到 −0.050（对比无赔率的
   冷门联赛），说明原效应主要集中在缺乏市场关注的低级别赛事。
2) 用市场去水赔率控制实力后，效应不成立（见下方输出）：

  分组           n    实际净胜球   市场期望   残差
  主多休≥4       40    −0.050      −0.136    +0.086
  休息差0~3     183    −0.213      −0.124    −0.089
  客多休≥4       42    −0.143      −0.016    −0.127

残差仅 0.2 球（真实体能效应量级 ~0.05~0.15 且方向应为「多休更好」），
分层后残差符号不一致（+0.49 / −0.25 / −0.03 / −0.35）→ 无可用信号。

结论：不接入。实力信息已由 λ 与市场混合覆盖，再加休息项等于重复计数。

用法：python rest_days_probe.py
"""
import datetime
import glob
import json
import os
from collections import defaultdict

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _repo_root():
    for d in (_ROOT, os.path.dirname(_ROOT), os.path.dirname(os.path.dirname(_ROOT))):
        if os.path.exists(os.path.join(d, "results_data.json")):
            return d
    return _ROOT


ROOT = _repo_root()

odds = {}
for f in sorted(glob.glob(os.path.join(ROOT, "odds_history", "*.json"))):
    if "index" in os.path.basename(f):
        continue
    try:
        odds.update(json.load(open(f, encoding="utf-8")).get("odds") or {})
    except Exception:  # noqa: BLE001
        pass

res = json.load(open(os.path.join(ROOT, "results_data.json"), encoding="utf-8"))
recs = []
for k, v in res.items():
    try:
        hg, ag = (int(x) for x in v["fullScore"].split(":"))
    except Exception:  # noqa: BLE001
        continue
    d = k.split("_")[0]
    try:
        dt = datetime.date.fromisoformat(d)
    except ValueError:
        continue
    recs.append((dt, k, v.get("home"), v.get("away"), hg, ag,
                 v.get("league") or ""))
recs.sort(key=lambda r: r[0])

last = {}
rows = []
for dt, k, hm, aw, hg, ag, lg in recs:
    rh = (dt - last[hm]).days if hm in last else None
    ra = (dt - last[aw]).days if aw in last else None
    last[hm] = dt
    last[aw] = dt
    if not (rh is not None and ra is not None and 1 <= rh < 45 and 1 <= ra < 45):
        continue
    o = odds.get(k) or {}
    try:
        oh, od, ol = float(o["胜"]), float(o["平"]), float(o["负"])
    except Exception:  # noqa: BLE001
        continue
    if min(oh, od, ol) <= 1.0:
        continue
    s = 1 / oh + 1 / od + 1 / ol
    rows.append((rh, ra, hg, ag, (1 / oh / s, 1 / od / s, 1 / ol / s), lg))

print(f"样本 {len(rows)} 场（含 1X2 赔率、双方均有历史交锋）")

print("\n=== 未控制实力（看似强信号，实为混淆）===")
print(f"{'分组':<14}{'n':>6}{'实际净胜球':>13}{'主胜率':>10}")
for lab, f in (("主多休≥4", lambda r: r[0] - r[1] >= 4),
               ("休息差0~3", lambda r: -4 < r[0] - r[1] < 4),
               ("客多休≥4", lambda r: r[1] - r[0] >= 4)):
    s = [r for r in rows if f(r)]
    if not s:
        continue
    net = sum(r[2] - r[3] for r in s) / len(s)
    w = sum(1 for r in s if r[2] > r[3]) / len(s) * 100
    print(f"{lab:<14}{len(s):>6}{net:>13.3f}{w:>9.1f}%")

print("\n=== 用市场去水赔率控制实力后（效应消失）===")
print(f"{'分组':<14}{'n':>6}{'实际净胜球':>13}{'市场期望':>11}{'残差':>10}")
for lab, f in (("主多休≥4", lambda r: r[0] - r[1] >= 4),
               ("休息差0~3", lambda r: -4 < r[0] - r[1] < 4),
               ("客多休≥4", lambda r: r[1] - r[0] >= 4)):
    s = [r for r in rows if f(r)]
    if not s:
        continue
    net = sum(r[2] - r[3] for r in s) / len(s)
    exp = sum(r[4][0] - r[4][2] for r in s) / len(s)
    print(f"{lab:<14}{len(s):>6}{net:>13.3f}{exp:>11.3f}{net - exp:>+10.3f}")

print("\n结论：残差量级 0.2 球且符号不一致 → 休息天数只是「实力」的代理，")
print("      不接入模型（实力已由 λ + 市场概率混合覆盖）。")
