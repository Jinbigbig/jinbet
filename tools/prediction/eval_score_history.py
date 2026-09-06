#!/usr/bin/env python3
"""历史预测比分 vs 实际赛果 回测评估。

数据源：
- predictions/<date>/index.html 第四节「比分预测汇总」表（首选/备选比分）
- results_data.json 实际赛果（fullScore）

回答：首选比分命中率多少？「首选偏小」是否真的误导总量判断？
若按大球导向调整比分选择，命中率会变好还是变坏？
"""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
results = json.load(open(os.path.join(BASE, "results_data.json"), encoding="utf-8"))

# ---------- 1. 解析各日报告的第四节表 ----------
def parse_report(path):
    html = open(path, encoding="utf-8").read()
    i = html.find("比分预测汇总")
    if i < 0:
        return []
    seg = html[i:html.find("</table>", i)]
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", seg, re.S):
        if "<td" not in tr:
            continue
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        mnum = re.search(r"(?:周[一二三四五六日])?\d{1,3}", cells[0])
        if not mnum:
            continue
        # 队名：兼容「对阵」合并列与主/客分列
        home = away = None
        for c in cells[1:5]:
            if " vs " in c:
                home, away = [x.strip() for x in c.split(" vs ", 1)]
                break
        if not home:
            subs = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            names = []
            for c in subs[1:5]:
                t = re.sub(r"<sub.*?</sub>", "", c)
                t = re.sub(r"<[^>]+>", "", t).strip()
                t = re.sub(r"\s*\[\d+\]\s*", "", t)  # 去掉排名后缀 [18]
                if t and t != "VS" and not re.match(r"^\d+\.\d+%", t) and len(t) > 1:
                    names.append(t)
                if len(names) == 2:
                    break
            if len(names) == 2:
                home, away = names
        scores = []
        for c in cells:
            sm = re.match(r"^(\d{1,2})-(\d{1,2})$", c)
            if sm:
                scores.append((int(sm.group(1)), int(sm.group(2))))
        if home and away and scores:
            rows.append({"num": mnum.group(0), "home": home, "away": away,
                         "top1": scores[0], "top2": scores[1] if len(scores) > 1 else None})
    return rows

def norm(s):
    return re.sub(r"[\s·]", "", s or "")

def find_actual(date, home, away):
    for h, a in [(home, away), (away, home)]:
        v = results.get(f"{date}_{norm(h)}_{norm(a)}")
        if v:
            fs = v.get("fullScore") or ""
            m = re.match(r"(\d+)\s*[:-]\s*(\d+)", fs)
            if m:
                gh, ga = int(m.group(1)), int(m.group(2))
                return (gh, ga) if h == home else (ga, gh), v
    # 模糊：日期下包含队名
    for k, v in results.items():
        if not k.startswith(date + "_"):
            continue
        nh, na = norm(home), norm(away)
        if (nh in k and na in k) or (na in k and nh in k):
            fs = v.get("fullScore") or ""
            m = re.match(r"(\d+)\s*[:-]\s*(\d+)", fs)
            if m:
                kh_home = norm(home) in k.split("_")[1]
                gh, ga = int(m.group(1)), int(m.group(2))
                return ((gh, ga) if kh_home else (ga, gh)), v
    return None, None

all_rows = []
for d in sorted(os.listdir(os.path.join(BASE, "predictions"))):
    p = os.path.join(BASE, "predictions", d, "index.html")
    if not (os.path.isdir(os.path.join(BASE, "predictions", d)) and os.path.exists(p)):
        continue
    if d >= "2026-09-06":  # 当日未开赛
        continue
    for r in parse_report(p):
        act, v = find_actual(d, r["home"], r["away"])
        if act:
            r["date"] = d
            r["actual"] = act
            r["league"] = (v.get("league") or "")
            all_rows.append(r)

print(f"覆盖: {len(all_rows)} 场有实际结果可对照")

# ---------- 2. 指标 ----------
n = len(all_rows)
hit1 = sum(1 for r in all_rows if r["top1"] == r["actual"])
hit2 = sum(1 for r in all_rows if r["top1"] == r["actual"] or (r["top2"] and r["top2"] == r["actual"]))
print(f"\n【总体】Top1 命中率 {hit1}/{n} = {hit1/n*100:.1f}% | Top2(首选+备选) {hit2}/{n} = {hit2/n*100:.1f}%")

# 按月
by_month = {}
for r in all_rows:
    by_month.setdefault(r["date"][:7], []).append(r)
print("\n【按月】")
for mo, rs in sorted(by_month.items()):
    h = sum(1 for r in rs if r["top1"] == r["actual"])
    print(f"  {mo}: {h}/{len(rs)} = {h/len(rs)*100:.1f}%")

# 首选比分总进球 vs 实际总进球
mae = sum(abs(sum(r["top1"]) - sum(r["actual"])) for r in all_rows) / n
print(f"\n【总量】首选比分总进球 vs 实际总进球 MAE = {mae:.2f} 球")

# 关键检验：首选为小球(≤2球)时，实际大球(≥3)的比例 —— 量化「误导」
small_top1 = [r for r in all_rows if sum(r["top1"]) <= 2]
big_actual = sum(1 for r in small_top1 if sum(r["actual"]) >= 3)
print(f"首选≤2球 {len(small_top1)} 场 → 实际≥3球 {big_actual} 场 ({big_actual/len(small_top1)*100:.1f}%)")
big_top1 = [r for r in all_rows if sum(r["top1"]) >= 3]
small_actual = sum(1 for r in big_top1 if sum(r["actual"]) <= 2)
print(f"首选≥3球 {len(big_top1)} 场 → 实际≤2球 {small_actual} 场 ({small_actual/len(big_top1)*100:.1f}%)")

# 1:1 专项：预测1:1时的实际命中率 vs 基准
p11 = [r for r in all_rows if r["top1"] == (1, 1)]
h11 = sum(1 for r in p11 if r["actual"] == (1, 1))
base11 = sum(1 for r in all_rows if r["actual"] == (1, 1)) / n
if p11:
    print(f"\n【1:1专项】预测1:1 {len(p11)} 场 → 实际1:1 {h11} 场 ({h11/len(p11)*100:.1f}%) | 全体实际1:1基准率 {base11*100:.1f}%")

# 用户假设检验：若在首选≤2球时改选备选（若备选≥3球），命中率变化
switch_better = switch_worse = same = 0
for r in all_rows:
    if r["top2"] and sum(r["top1"]) <= 2 <= sum(r["top2"]):  # 首选小球、备选大球
        if r["actual"] == r["top1"]:
            switch_worse += 1
        elif r["actual"] == r["top2"]:
            switch_better += 1
        else:
            same += 1
tot = switch_better + switch_worse + same
if tot:
    print(f"\n【调整实验】首选≤2球且备选≥3球的场次 {tot} 场：")
    print(f"  保持首选命中 {switch_worse} ({switch_worse/tot*100:.1f}%) | 改选备选命中 {switch_better} ({switch_better/tot*100:.1f}%) | 都不中 {same}")

# 备选比分整体命中率（选择器价值）
if all(r["top2"] for r in all_rows):
    h2 = sum(1 for r in all_rows if r["top2"] == r["actual"])
    print(f"\n【备选单独】备选比分命中率 {h2}/{n} = {h2/n*100:.1f}%")

# 按联赛大球率
print("\n【说明】以上首选比分来自历史各版本引擎（07-21旧版~09-05 V2.2），结果代表历史整体水平")
