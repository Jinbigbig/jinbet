#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""赛前裁判执法（直播吧「裁判分析」文章）→ referee.json

【为什么选直播吧】2026-10-23 实测：
  ❌ Transfermarkt 全系：本机 IP 返回 405 / Human Verification（浏览器也过不去）
  ❌ weltfussball.de：403 / "请稍候…" 验证页
  ✅ news.zhibo8.com 国内直连、无需验证；每天对主要赛事发布
     「A队vsB队裁判分析」文章，含主裁判姓名/国籍/年龄 + 近 20 场执法战绩
     （主队X胜Y平Z负、黄牌N、红牌M、点球K）——正是我们要的结构化数字。

发现机制：
  https://news.zhibo8.com/zuqiu/more.htm?day=YYYY-MM-DD&page=1 为完整日列表
  （约 5500 条链接，一页即覆盖全天），抓「今天 + 明天」两天即可覆盖提前
  发布的裁判前瞻（欧战裁判通常提前 2-3 天由官方公布、媒体随即发稿）。

输出 referee.json：
  {"updated": "...", "matches": [{"home": "尤文图斯", "away": "雷恩",
    "ref": "莫滕·克罗", "nation": "丹麦", "age": 38,
    "h": 5, "d": 9, "a": 6,          # 近20场 主队胜/平/负
    "yellow": 75, "red": 5, "pen": 8,  # 黄牌/红牌/点球
    "title": "...", "url": "..."}]}
队名保留文章原文（全名），匹配竞彩简称交给下游 import 按包含关系处理。
"""
import json
import re
import sys
import time
import urllib.request
from datetime import date, timedelta

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0 Safari/537.36')
OUT = 'referee.json'
TITLE_KEYS = ('裁判分析', '裁判组', '裁判信息', '主哨')

RE_LINK = re.compile(
    r'<span class="articleTitle"><a href="([^"]+)">([^<]+)</a></span>')
RE_PAIR = re.compile(r'^([\u4e00-\u9fa5A-Za-z0-9·\.]+)vs([\u4e00-\u9fa5A-Za-z0-9·\.]+)')
RE_REF = re.compile(
    r'主裁判(?:是|：)?(?:(\d{2})岁的)?(?:([\u4e00-\u9fa5]{1,4})(?:籍|裁判))?'
    r'([\u4e00-\u9fa5·A-Za-z]{2,12})[，,]')
RE_STAT = re.compile(
    r'(?:近|执法)\s*20\s*场[^。]*?主队(\d+)胜(\d+)平(\d+)负[^。]*?'
    r'出示(?:了)?黄牌(\d+)\s*张[、,，]?\s*红牌(\d+)\s*张[，,]?\s*(?:判罚|出示)?点球(\d+)\s*个')


def clean_name(n: str | None) -> str | None:
    if not n:
        return n
    for p in ('裁判', '名哨', '主裁', '国际级'):
        if n.startswith(p):
            return clean_name(n[len(p):])
    return n


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': 'https://news.zhibo8.com/zuqiu/'})
    return urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'ignore')


def collect_titles(days: list[str]) -> list[tuple[str, str]]:
    """按日列表收集裁判类文章链接（去重）。"""
    seen, out = set(), []
    for d in days:
        try:
            h = fetch(f'https://news.zhibo8.com/zuqiu/more.htm?day={d}&page=1')
        except Exception as e:
            print(f'[裁判] 列表 {d} 抓取失败：{type(e).__name__} {e}')
            continue
        for u, t in RE_LINK.findall(h):
            if any(k in t for k in TITLE_KEYS) and 'vs' in t:
                u = 'https:' + u if u.startswith('//') else u
                if u not in seen:
                    seen.add(u)
                    out.append((t.strip(), u))
        print(f'[裁判] {d} 列表扫描完成，累计 {len(out)} 篇候选')
    return out


def parse_article(title: str, url: str) -> dict | None:
    try:
        h = fetch(url)
    except Exception as e:
        print(f'[裁判] 文章抓取失败 {title}：{e}')
        return None
    m = re.search(r'<div class="content">(.*?)</div>', h, re.S)
    txt = re.sub(r'<[^>]+>', '', m.group(1) if m else h)
    txt = re.sub(r'\s+', '', txt)
    pm = RE_PAIR.match(title)
    if not pm:
        return None
    rec = {'home': pm.group(1), 'away': pm.group(2), 'title': title, 'url': url}
    rf = RE_REF.search(txt)
    if rf:
        rec['age'] = int(rf.group(1)) if rf.group(1) else None
        rec['nation'] = rf.group(2)
        rec['ref'] = clean_name(rf.group(3))
    st = RE_STAT.search(txt)
    if st:
        rec['h'], rec['d'], rec['a'] = (int(st.group(i)) for i in (1, 2, 3))
        rec['yellow'], rec['red'], rec['pen'] = (int(st.group(i)) for i in (4, 5, 6))
    # 至少要有主裁名或战绩之一才算有效
    return rec if rec.get('ref') or st else None


def main() -> int:
    today = date.today()
    days = [str(today), str(today + timedelta(days=1))]
    arts = collect_titles(days)
    matches, seen_pair = [], set()
    for t, u in arts:
        rec = parse_article(t, u)
        if rec:
            key = rec['home'] + '|' + rec['away']
            if key in seen_pair:   # 同对阵多篇文章取最新
                matches = [m for m in matches if m['home'] + '|' + m['away'] != key]
            seen_pair.add(key)
            matches.append(rec)
            print(f'[裁判] ✅ {rec["home"]} vs {rec["away"]}：{rec.get("ref", "?")}'
                  + (f'（近20场 主队{rec["h"]}胜{rec["d"]}平{rec["a"]}负 黄{rec["yellow"]}红{rec["red"]}点{rec["pen"]}）'
                     if 'h' in rec else '（无战绩段）'))
        else:
            print(f'[裁判] 跳过（无对阵/无结构化信息）：{t}')
    result = {'updated': time.strftime('%Y-%m-%d %H:%M'), 'matches': matches}
    json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'[裁判] 合计 {len(matches)} 场 → {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
