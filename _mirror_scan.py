# -*- coding: utf-8 -*-
"""扫描 results_history 中的镜像/重复记录。

定义（从严到宽）：
  A. 同 matchId 出现 ≥2 次（任何主客顺序）
  B. 同 matchId 且主客互换（镜像）
  C. 同主客对调 + 跨日 ≤3 天 + 同 matchNumStr（无 matchId 时的兜底判据）

只读，不写任何文件。
"""
import json
import glob
import os
import collections

ROOT = os.path.dirname(os.path.abspath(__file__))
FS = sorted(glob.glob(os.path.join(ROOT, "results_history", "*.json")))

recs = []  # (date, key, obj)
for f in FS:
    date = os.path.basename(f)[:-5]
    d = json.load(open(f, encoding="utf-8"))
    for k, v in d.items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v["_date"] = date
        v["_key"] = k
        v["_file"] = f
        recs.append(v)

print(f"总记录 {len(recs)}  文件 {len(FS)}")

# ---------- A: 同 matchId ----------
by_id = collections.defaultdict(list)
for r in recs:
    mid = str(r.get("matchId") or "").strip()
    if mid:
        by_id[mid].append(r)

dup_id = {k: v for k, v in by_id.items() if len(v) > 1}
print(f"\n[A] 同 matchId 出现多次：{len(dup_id)} 个 id / {sum(len(v) for v in dup_id.values())} 条记录")

# ---------- B: 镜像（主客互换） ----------
mirror_id = {}
same_id = {}
for mid, v in dup_id.items():
    combos = set((str(x.get("home") or ""), str(x.get("away") or "")) for x in v)
    if len(combos) > 1:
        # 含互换
        pairs = list(combos)
        swapped = any((b, a) in combos for a, b in combos if (b, a) != (a, b))
        if swapped:
            mirror_id[mid] = v
        else:
            same_id[mid] = v
    else:
        same_id[mid] = v

print(f"[B] 其中主客互换（镜像）：{len(mirror_id)} 个 id")
print(f"    主客同向重复（真重复）：{len(same_id)} 个 id")

# ---------- 明细输出 ----------
def brief(r):
    return (f"{r['_date']} {r.get('matchNumStr','?'):<6} id={str(r.get('matchId')):<9} "
            f"{r.get('home')} vs {r.get('away')}  {r.get('fullScore')}  [{r.get('league')}]")

print("\n========== 镜像明细（同 matchId 主客互换） ==========")
for mid, v in sorted(mirror_id.items(), key=lambda kv: kv[1][0]["_date"]):
    print(f"-- matchId {mid}:")
    for r in sorted(v, key=lambda x: x["_date"]):
        print("    ", brief(r))

print("\n========== 同向重复明细 ==========")
for mid, v in sorted(same_id.items(), key=lambda kv: kv[1][0]["_date"]):
    print(f"-- matchId {mid}:")
    for r in sorted(v, key=lambda x: x["_date"]):
        print("    ", brief(r))

# ---------- C: 无 matchId 的兜底：同队对调 + 同日/近3日 + 同编号 ----------
print("\n========== C: 队对调 + 近 3 日内 + 同编号（无 matchId 兜底） ==========")
by_pair = collections.defaultdict(list)
for r in recs:
    h, a = str(r.get("home") or ""), str(r.get("away") or "")
    by_pair[tuple(sorted((h, a)))].append(r)

import datetime
def _d(s):
    try:
        return datetime.date.fromisoformat(s)
    except Exception:
        return None

extra = []
for pair, lst in by_pair.items():
    if len(lst) < 2:
        continue
    for i in range(len(lst)):
        for j in range(i + 1, len(lst)):
            x, y = lst[i], lst[j]
            if (x.get("home"), x.get("away")) != (y.get("away"), y.get("home")):
                continue
            if str(x.get("matchId") or "") == str(y.get("matchId") or ""):
                continue  # 已在 A/B 里
            dx, dy = _d(x["_date"]), _d(y["_date"])
            if not dx or not dy:
                continue
            gap = abs((dx - dy).days)
            same_num = str(x.get("matchNumStr") or "") == str(y.get("matchNumStr") or "")
            if gap <= 3 and same_num:
                extra.append((x, y, gap))

print(f"疑似 {len(extra)} 对")
for x, y, gap in sorted(extra, key=lambda t: t[0]["_date"]):
    print(f"  gap={gap}d  {brief(x)}")
    print(f"          vs {brief(y)}")

# ---------- D: 按联赛统计镜像 ----------
print("\n========== D: 镜像/重复 按联赛统计 ==========")
cnt = collections.Counter()
for mid, v in {**mirror_id, **same_id}.items():
    for r in v:
        cnt[r.get("league") or r.get("leagueAbbr") or "?"] += 1
for lg, n in cnt.most_common():
    print(f"  {lg:<8} {n}")
