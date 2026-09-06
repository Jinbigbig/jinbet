#!/usr/bin/env python3
"""本地版 prepare.sh 步骤3：从 index.html 提取当日比赛与赔率。

适配 Windows 本地路径（原脚本硬编码 /workspace）。
输出: scripts/matches_data.json
"""
import re
import json
import datetime
import os

TODAY = datetime.date.today().isoformat()
BASE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(BASE, "index.html")
OUTPUT = os.path.join(BASE, "scripts", "matches_data.json")

print(f"今天日期: {TODAY}")

with open(HTML, "r", encoding="utf-8") as f:
    html = f.read()

# 提取当日比赛
matches = []
sm = re.search(r"const SCHEDULE\s*=\s*\{([\s\S]*?)\};", html)
if sm:
    ds = re.search(r"['\"]?" + re.escape(TODAY) + r"['\"]?\s*:\s*\[([\s\S]*?)\n\s*\]", sm.group(1))
    if not ds:
        ds = re.search(r"['\"]?" + re.escape(TODAY) + r"['\"]?\s*:\s*\[([\s\S]*?)\]", sm.group(1))
    if ds:
        for e in re.findall(r"\{([^}]+)\}", ds.group(1)):
            def g(key):
                m = re.search(key + r":\s*'([^']*)'", e)
                return m.group(1) if m else ""
            home, away = g("home"), g("away")
            if home and away:
                matches.append({
                    "matchNumStr": g("matchNumStr"),
                    "home": home,
                    "away": away,
                    "league": g("league"),
                    "matchId": g("matchId"),
                    "odds": {},
                })
print(f"从 SCHEDULE 提取到 {len(matches)} 场 {TODAY} 的比赛")

# 提取 ODDS
odds_obj = {}
start_marker = "const ODDS = {"
o = html.find(start_marker)
if o >= 0:
    start = html.find("{", o)
    depth, i = 0, start
    while i < len(html):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    raw = html[start:i + 1]
    for attempt in (raw, re.sub(r",\s*([}\]])", r"\1", raw)):
        try:
            odds_obj = json.loads(attempt)
            break
        except json.JSONDecodeError:
            continue
    for m in matches:
        key = f"{TODAY}_{m['home']}_{m['away']}"
        if key in odds_obj:
            m["odds"] = odds_obj[key]

# 用 odds_data.json 补全
try:
    with open(os.path.join(BASE, "odds_data.json"), "r", encoding="utf-8") as f:
        raw_odds = json.load(f)
    for m in matches:
        if not (m.get("odds") or {}).get("胜"):
            tk = f"{m['home']} vs {m['away']}"
            rk = f"{m['away']} vs {m['home']}"
            if tk in raw_odds:
                src = raw_odds[tk]
                if m.get("odds"):
                    for k, v in src.items():
                        m["odds"].setdefault(k, v)
                else:
                    m["odds"] = dict(src)
            elif rk in raw_odds and not m.get("odds"):
                m["odds"] = dict(raw_odds[rk])
except Exception as e:
    print(f"读取 odds_data.json 失败: {e}")

ok = 0
for m in matches:
    od = m.get("odds") or {}
    good = bool(od.get("胜"))
    ok += good
    flag = "[OK]" if good else "[缺赔率]"
    print(f"  {m['matchNumStr']:<8} {m['league']:<10} {m['home']} vs {m['away']}  "
          f"胜={od.get('胜','')} 平={od.get('平','')} 负={od.get('负','')} {flag}")

matches.sort(key=lambda x: x.get("matchNumStr", ""))
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump({"today": TODAY, "match_count": len(matches), "matches": matches},
              f, ensure_ascii=False, indent=2)

print(f"\n赔率完整: {ok}/{len(matches)}")
print(f"数据已保存: {OUTPUT}")
