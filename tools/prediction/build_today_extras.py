#!/usr/bin/env python3
"""为 2026-09-06 的 24 场比赛构建引擎附加数据（H2H/近期状态/排名/伤停新闻）。

来源：
- H2H + home_recent/away_recent：results_data.json（2025-12-31 至今 2928 场赛果）
- home_rank/away_rank：旧报告 predictions/2026-09-06/index.html 的 team-rank 小字
  （上午网络调研成果，回收复用）
- news：旧报告各详情卡「伤停与赛前动态」段落

输出：直接注入 scripts/matches_data.json 的每个 match 条目（引擎合并使用）。
"""
import json
import os
import re
import sys

import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
TODAY = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()

md = json.load(open(os.path.join(BASE, "scripts", "matches_data.json"), encoding="utf-8"))
matches = md["matches"]
results = json.load(open(os.path.join(BASE, "results_data.json"), encoding="utf-8"))

# ---------- 1. 赛果索引 ----------
# 按队索引：team -> [(date, gf, ga)]        （不分主客，现行基础λ口径）
# 分主客索引：team -> [(date, gf, ga)]      （该队作为主队 / 作为客队的战绩）
# 【2026-09-10】主客场分拆：同一支球队在主场与客场的进球/失球能力差异显著，
# 分主客观测比「不分主客 + 固定系数 1.15/0.90」更准。回测见 venue_probe.py /
# venue_brier_check.py（1X2 Brier 0.6292→0.6247，Z=+5.41，5/5 时序段改善）。
team_idx = {}
home_idx = {}   # 作为主队
away_idx = {}   # 作为客队
for key, v in results.items():
    d, h, a = key.split("_", 2) if key.count("_") >= 2 else (None, None, None)
    fs = v.get("fullScore") or ""
    m = re.match(r"(\d+)\s*[:-]\s*(\d+)", fs)
    if not (d and h and a and m):
        continue
    hg, ag = int(m.group(1)), int(m.group(2))
    team_idx.setdefault(h, []).append((d, hg, ag))
    team_idx.setdefault(a, []).append((d, ag, hg))
    home_idx.setdefault(h, []).append((d, hg, ag))
    away_idx.setdefault(a, []).append((d, ag, hg))
for t in team_idx:
    team_idx[t].sort(key=lambda x: x[0], reverse=True)  # 最新在前
for t in home_idx:
    home_idx[t].sort(key=lambda x: x[0], reverse=True)
for t in away_idx:
    away_idx[t].sort(key=lambda x: x[0], reverse=True)

# ---------- 2. 旧报告解析：排名 + 伤停新闻（当日已生成过报告才有，缺失则跳过） ----------
rank_map = {}
news_map = {}
_old_path = os.path.join(BASE, "predictions", TODAY, "index.html")
old_html = ""
if os.path.exists(_old_path):
    old_html = open(_old_path, encoding="utf-8").read()
    # 剥离 IDE 注入的 data-page-node-id 属性，避免污染解析
    old_html = re.sub(r'\s*data-page-node-id="[^"]*"', "", old_html)

def _strip(s):
    return re.sub(r"<[^>]+>", "", s).strip()

rank_map = {}
for m in re.finditer(r'<span class="(home|away)"[^>]*>([^<]+?)(?:<sub class="team-rank">联赛第(\d+)</sub>)?</span>', old_html):
    name = m.group(2).strip()
    if m.group(3):
        rank_map[name] = int(m.group(3))

# 按 home-span 切分详情卡，段内找「伤停与赛前动态」后的 <p>
news_map = {}
home_spans = []
for sp in re.finditer(r'<span class="home"[^>]*>(.*?)</span>', old_html, re.S):
    name = _strip(sp.group(1).split("<sub")[0])
    if name:
        home_spans.append((name, sp.end()))
for i, (name, pos) in enumerate(home_spans):
    seg_end = home_spans[i + 1][1] if i + 1 < len(home_spans) else len(old_html)
    seg = old_html[pos:seg_end]
    nm = re.search(r'伤停[^<]*</h4>\s*<p[^>]*>(.*?)</p>', seg, re.S)
    if nm:
        txt = _strip(nm.group(1))
        if txt:
            news_map[name] = txt

# ---------- 3. 逐场注入 ----------
n_h2h = n_recent = n_rank = n_news = n_venue = 0
for m in matches:
    home, away = m["home"], m["away"]
    # 【2026-09-08】窗口 10 → RECENT_N(25)，与 _calc_engine 的 RECENT_N/DECAY 保持一致。
    # 依据 window_sweep.py 回测：近 25 场 + 0.96 衰减 优于 近 10 场 + 0.85（logL +0.026/场, MSE -0.041）
    hr = team_idx.get(home, [])[:25]
    ar = team_idx.get(away, [])[:25]
    m["home_recent"] = [{"gf": g, "ga": a} for _, g, a in hr]
    m["away_recent"] = [{"gf": g, "ga": a} for _, g, a in ar]
    # 分主客观测：home_recent_home = 今日主队「作为主队」时的近期战绩
    #             away_recent_away = 今日客队「作为客队」时的近期战绩
    # 引擎据此计算分主客 λ，缺失时自动回退到不分主客口径。
    hrh = home_idx.get(home, [])[:25]
    ara = away_idx.get(away, [])[:25]
    m["home_recent_home"] = [{"gf": g, "ga": a} for _, g, a in hrh]
    m["away_recent_away"] = [{"gf": g, "ga": a} for _, g, a in ara]
    if hr and ar:
        n_recent += 1
    if hrh and ara:
        n_venue += 1

    # H2H：两队交手记录（任意主客），home_goals 归一为今日主队视角，最新在前
    h2h = []
    hset = team_idx.get(home, [])
    aset = team_idx.get(away, [])
    by_key = {}
    for key, v in results.items():
        fs = v.get("fullScore") or ""
        mm = re.match(r"(\d+)\s*[:-]\s*(\d+)", fs)
        if not mm:
            continue
        parts = key.split("_", 2)
        if len(parts) < 3:
            continue
        d, fh, fa = parts
        if {fh, fa} == {home, away}:
            hg, ag = int(mm.group(1)), int(mm.group(2))
            if fh == home:
                by_key[d] = (hg, ag)
            else:
                by_key[d] = (ag, hg)
    for d in sorted(by_key, reverse=True):
        hg, ag = by_key[d]
        h2h.append({"date": d, "home_goals": hg, "away_goals": ag})
    m["h2h"] = h2h
    if len(h2h) >= 3:
        n_h2h += 1

    rk_h, rk_a = rank_map.get(home), rank_map.get(away)
    if rk_h:
        m["home_rank"] = rk_h
    if rk_a:
        m["away_rank"] = rk_a
    if rk_h and rk_a:
        n_rank += 1

    nw = news_map.get(home)
    if nw:
        m["news"] = nw
        n_news += 1

    print(f"{m['matchNumStr']} {home}vs{away}: h2h={len(h2h)} recent={len(hr)}/{len(ar)} "
          f"venue={len(hrh)}/{len(ara)} rank={rk_h}/{rk_a} news={'Y' if nw else '-'}")

json.dump(md, open(os.path.join(BASE, "scripts", "matches_data.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n注入完成：H2H≥3场 {n_h2h}/24 | 近期状态 {n_recent}/24 | 主客场分拆 {n_venue}/24 "
      f"| 排名 {n_rank}/24 | 新闻 {n_news}/24")
