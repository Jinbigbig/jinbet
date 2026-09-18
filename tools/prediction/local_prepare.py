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
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _repo_root(start=_SCRIPT_DIR):
    """向上爬找有 results_history/ 的目录作为仓库根（V3.4 统一路径基准）。"""
    here = start
    for _ in range(4):
        if os.path.isdir(os.path.join(here, "results_history")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return start

BASE = _repo_root()
HTML = os.path.join(BASE, "index.html")
OUTPUT = os.path.join(BASE, "scripts", "matches_data.json")

print(f"今天日期: {TODAY}")

with open(HTML, "r", encoding="utf-8") as f:
    html = f.read()

# 提取当日比赛
# 注意：SCHEDULE 偶发同一 matchNumStr 出现两行（官方简称 + 长名/旧ID 的别名行），
#      别名行的赔率与战绩全空。若不去重，下游按「后写胜」保留别名行 →
#      该场丢掉让球盘/比分盘/球队战绩（曾致 4 场报告显示「无让球盘」）。
_sched = {}
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
                rec = {
                    "matchNumStr": g("matchNumStr"),
                    "home": home,
                    "away": away,
                    "league": g("league"),
                    "matchId": g("matchId"),
                    "odds": {},
                }
                key = rec["matchNumStr"] or f"{home}_{away}"
                prev = _sched.get(key)
                # 取舍：带官方 matchId 的一行为准；都带或都不带时保留先出现的
                if prev is None or (not prev.get("matchId") and rec["matchId"]):
                    if prev is not None:
                        print(f"  [去重] {key} {home} vs {away} 覆盖别名行 "
                              f"{prev['home']} vs {prev['away']}")
                    _sched[key] = rec
matches = list(_sched.values())
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
    def _squash(s):
        """队名粗归一：去空格/数字/常见后缀，便于容错匹配（不改变落库名称）。"""
        s = re.sub(r"[\s\d\u3000]", "", str(s or ""))
        for suf in ("足球俱乐部", "足球", "俱乐部", "亚足", "足"):
            if s.endswith(suf) and len(s) > len(suf):
                s = s[: -len(suf)]
        return s

    def _find_odds(home, away):
        """精确键优先；未命中则同日按队名容错匹配（防同义写法静默丢盘口）。"""
        key = f"{TODAY}_{home}_{away}"
        if key in odds_obj:
            return odds_obj[key], key
        sh, sa = _squash(home), _squash(away)
        for k, v in odds_obj.items():
            if not k.startswith(TODAY + "_"):
                continue
            parts = k[len(TODAY) + 1:].split("_")
            if len(parts) < 2:
                continue
            kh, ka = _squash(parts[0]), _squash("_".join(parts[1:]))
            if (kh == sh and ka == sa) or (len(sh) >= 3 and len(sa) >= 3
                                           and (sh in kh or kh in sh) and (sa in ka or ka in sa)):
                return v, k
        return None, None

    _miss = []
    for m in matches:
        v, k = _find_odds(m["home"], m["away"])
        if v is not None:
            m["odds"] = v
            if k != f"{TODAY}_{m['home']}_{m['away']}":
                print(f"  [盘口容错] {m['matchNumStr']} {m['home']} vs {m['away']} "
                      f"→ 命中键 {k}")
        else:
            _miss.append(f"{m['matchNumStr']} {m['home']} vs {m['away']}")
    if _miss:
        print(f"  [注意] {len(_miss)} 场未在 ODDS 找到键：{'；'.join(_miss)}")

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

# ---------- 从比分盘反推 1X2（补齐「有比分盘但缺胜平负」的场次） ----------
# 背景：竞彩 ODDS 天天都有若干场 1X2 为空但比分盘（31 档）完整，且常在豪门场次
#      （2026-09-13 就有 5/24：埃沃斯堡vs拜仁、莱万特vs巴萨、本菲卡、埃因霍温、哈马比）。
#      这些场次原本降级为「纯模型 λ」，而项目结论是 纯市场去水1X2 > 生产@0.80 > 纯模型
#      ⇒ 缺市场输入 = 已知更差的口径。
# 依据（_score2hda_probe.py，按日拆分的对照验证）：
#      在 1X2 与比分盘都齐全的场次上比较 devig(真实1X2) 与「比分盘聚合出的 1X2」：
#      2026-09-03 起的数据 **方向一致率 100%、平均偏差 1.0~2.2pp、约 80~90% 场次 ≤2pp**；
#      2026-09-01/02 及更早为 0%（归档比分盘主客被翻转的脏数据，勿用）。
#      故本反推**只对当日新鲜抓取的比分盘**使用，不做历史回填。
HDA_HOME = ['1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '4:0', '4:1', '4:2',
            '5:0', '5:1', '5:2', '胜其他']
HDA_DRAW = ['0:0', '1:1', '2:2', '3:3', '平其他']
HDA_AWAY = ['0:1', '0:2', '1:2', '0:3', '1:3', '2:3', '0:4', '1:4', '2:4',
            '0:5', '1:5', '2:5', '负其他']


def hda_from_scores(sc):
    """比分盘赔率 → 去水 1X2 概率；不足 20 档视为不可用（防残缺盘）。"""
    if not isinstance(sc, dict):
        return None
    raw = {}
    for k, v in sc.items():
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 1.0:
            raw[k] = 1.0 / f
    if len(raw) < 20:
        return None
    tot = sum(raw.values())
    if tot <= 0:
        return None
    ph = sum(raw.get(c, 0.0) for c in HDA_HOME) / tot
    pd = sum(raw.get(c, 0.0) for c in HDA_DRAW) / tot
    pa = sum(raw.get(c, 0.0) for c in HDA_AWAY) / tot
    s = ph + pd + pa
    if s <= 0 or min(ph, pd, pa) / s < 0.005:
        return None
    return ph / s, pd / s, pa / s


derived_n = 0
for m in matches:
    od = m.get("odds") or {}
    if od.get("胜"):
        continue
    p = hda_from_scores(od.get("比分"))
    if not p:
        continue
    # 输出「能去水还原该概率」的等效赔率（od=1/p ⇒ devig 后恒等于 p）
    od["胜"], od["平"], od["负"] = (f"{1/p[0]:.4f}", f"{1/p[1]:.4f}", f"{1/p[2]:.4f}")
    od["_hda_src"] = "比分盘反推"
    m["odds"] = od
    m["hda_derived"] = True
    derived_n += 1
if derived_n:
    print(f"[1X2 反推] 比分盘 → 1X2 补齐 {derived_n} 场（来源已标注 odds._hda_src）")

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
