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

BASE = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-09-06"

md = json.load(open(os.path.join(BASE, "scripts", "matches_data.json"), encoding="utf-8"))
matches = md["matches"]
results = json.load(open(os.path.join(BASE, "results_data.json"), encoding="utf-8"))

# ---------- 1. 赛果索引 ----------
# 按队索引：team -> [(date, gf, ga)]
team_idx = {}
for key, v in results.items():
    d, h, a = key.split("_", 2) if key.count("_") >= 2 else (None, None, None)
    fs = v.get("fullScore") or ""
    m = re.match(r"(\d+)\s*[:-]\s*(\d+)", fs)
    if not (d and h and a and m):
        continue
    hg, ag = int(m.group(1)), int(m.group(2))
    team_idx.setdefault(h, []).append((d, hg, ag))
    team_idx.setdefault(a, []).append((d, ag, hg))
for t in team_idx:
    team_idx[t].sort(key=lambda x: x[0], reverse=True)  # 最新在前

# ---------- 2. 旧报告解析：排名 + 伤停新闻 ----------
old_html = open(os.path.join(BASE, "predictions", TODAY, "index.html"),
                encoding="utf-8").read()

rank_map = {}
for m in re.finditer(r'<span class="(home|away)"[^>]*>([^<]+?)(?:<sub class="team-rank">联赛第(\d+)</sub>)?</span>', old_html):
    name = m.group(2).strip()
    if m.group(3):
        rank_map[name] = int(m.group(3))

# 按 home-span 切分详情卡，段内找「伤停与赛前动态」后的 <p>
def _strip(s):
    return re.sub(r"<[^>]+>", "", s).strip()

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
n_h2h = n_recent = n_rank = n_news = 0
for m in matches:
    home, away = m["home"], m["away"]
    hr = team_idx.get(home, [])[:10]
    ar = team_idx.get(away, [])[:10]
    m["home_recent"] = [{"gf": g, "ga": a} for _, g, a in hr]
    m["away_recent"] = [{"gf": g, "ga": a} for _, g, a in ar]
    if hr and ar:
        n_recent += 1

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
          f"rank={rk_h}/{rk_a} news={'Y' if nw else '-'}")

json.dump(md, open(os.path.join(BASE, "scripts", "matches_data.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n注入完成：H2H≥3场 {n_h2h}/24 | 近期状态 {n_recent}/24 | 排名 {n_rank}/24 | 新闻 {n_news}/24")
