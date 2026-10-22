#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 UEFA 官方欧协联积分榜（用户指定的数据源 uefa.com）。

页面（league phase 榜直接渲染在 HTML 里）：
  https://www.uefa.com/uefaconferenceleague/standings/
  （fr.uefa.com 同构；队行带 /api/v1/linkrules/team/<id>/?competitionId=2019 链接）

输出：uefa_standings.json
  {"fetched_at": "...", "source": "...", "leagues": {"欧协联": {"slug": "...",
   "type": "league", "groups": [{"name": "联赛阶段", "teams": [
     {"rank":1,"name":"Brighton","zh":"布莱顿","p":1,"w":1,"d":0,"l":0,
      "gf":4,"ga":0,"gd":4,"pts":3}, ...]}]}}}

说明：
- uefa.com 队名英文，展示层优先 zh（内置对照表只收能确认的，缺则保留英文，不音译臆造）。
- ⚠️ 本机直连 uefa.com 可能被 CDN 拒绝（实测 urllib 两域名均 read timeout）。
  失败时**保留原 uefa_standings.json 不动**；此时可由 WorkBuddy WebFetch 通道
  抓官方页面后人工/自动落盘，格式与本脚本输出一致。
- 赛制口径（公开页 note 用）：联赛阶段 36 队单循环 6 轮，前 8 直接进 16 强，
  第 9-24 名进淘汰赛附加赛，第 25-36 名直接淘汰。
"""
import gzip
import json
import re
import sys
import urllib.request
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml',
      'Accept-Language': 'en-GB,en;q=0.9', 'Accept-Encoding': 'gzip'}

PAGE = 'https://www.uefa.com/uefaconferenceleague/standings/'

# 英文队名 → 中文（只收能确认的；未列出的保留英文原名，绝不音译臆造）
EN_ZH = {
    'Brighton': '布莱顿', 'Copenhagen': '哥本哈根', 'Trabzonspor': '特拉布宗体育',
    'Atalanta': '亚特兰大', 'Mjällby': '米亚尔比', 'Sint-Truidense': '圣图尔登',
    'Freiburg': '弗赖堡', 'Lugano': '卢加诺', 'Monaco': '摩纳哥', 'Brann': '布兰',
    'Hajduk Split': '哈伊杜克', 'Panathinaikos': '帕纳辛奈科斯', 'Gent': '根特',
    'Twente': '特温特', 'Getafe': '赫塔费', 'Kairat Almaty': '阿拉木图凯拉特',
    'Midtjylland': '中日德兰', 'Nordsjælland': '北西兰', 'Hearts': '哈茨',
    'Riga': '里加', 'Univ. Craiova': '克拉约瓦大学', 'Crvena Zvezda': '贝尔格莱德红星',
    'Jablonec': '亚布洛内茨', 'Ajax': '阿贾克斯', 'L. Red Imps': '林肯红魔',
    'CSKA Sofia': '索菲亚中央陆军', 'Aarhus': '奥胡斯', 'Thun': '图恩',
    'KuPS Kuopio': '库奥皮奥', 'Pafos': '帕福斯', 'Iberia Tbilisi': '第比利斯伊比利亚',
    'Braga': '布拉加',
}


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
    return raw.decode('utf-8', 'ignore')


def parse_standings(page):
    """从官方页 HTML 抽联赛阶段 36 行：队名链接 + 7 个数字格。"""
    teams = []
    # 每个队行：linkrules 队链 + 队名，随后 8 个 <td>（P/W/D/L/GF/GA/GD/Pts）
    for m in re.finditer(
            r'linkrules/team/\d+/\?competitionId=\d+"[^>]*>([^<]+)</a>\s*'
            r'(?:</td>\s*){0,2}((?:<td[^>]*>\s*[-\d]+\s*</td>\s*){7,8})',
            page):
        name = m.group(1).strip()
        nums = [int(x) for x in re.findall(r'>\s*(-?\d+)\s*<', m.group(2))]
        if len(nums) < 7:
            continue
        if len(nums) == 8:      # 含净胜球
            p, w, d, l, gf, ga, gd, pts = nums[:8]
        else:                   # 无净胜球列
            p, w, d, l, gf, ga, pts = nums[:7]
            gd = gf - ga
        teams.append({'name': name, 'p': p, 'w': w, 'd': d, 'l': l,
                      'gf': gf, 'ga': ga, 'gd': gd, 'pts': pts})
    # UEFA 页按名次顺序输出 4 个分区；校验 36 队后按积分重排名次
    if len(teams) != 36:
        return None
    teams.sort(key=lambda t: (t['pts'], t['gd'], t['gf']), reverse=True)
    seen, out = set(), []
    for i, t in enumerate(teams, 1):
        t['rank'] = i
        t['zh'] = EN_ZH.get(t['name'], '')
        out.append(t)
    return out


def main():
    print(f'[UEFA榜] 抓取 {PAGE}')
    try:
        page = _get(PAGE)
    except Exception as e:
        print(f'[UEFA榜] 直连失败：{type(e).__name__} {e}；保留原 uefa_standings.json 不动',
              file=sys.stderr)
        return 1
    teams = parse_standings(page)
    if not teams:
        print('[UEFA榜] 页面解析未得 36 队（页面结构可能变化）；保留原文件不动',
              file=sys.stderr)
        return 1
    out = {'fetched_at': datetime.now().isoformat(timespec='seconds'),
           'source': 'UEFA 官方（uefa.com/uefaconferenceleague/standings/）',
           'leagues': {'欧协联': {'slug': 'uefaconferenceleague', 'type': 'league',
                                  'groups': [{'name': '联赛阶段', 'teams': teams}]}}}
    json.dump(out, open('uefa_standings.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'[UEFA榜] 欧协联：{len(teams)} 队已写入 uefa_standings.json')
    for t in teams[:3]:
        print('  ', t['rank'], t['name'], t.get('zh'), t['pts'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
