#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 Fox Sports 足球积分榜，补充腾讯/7M 都没有的杯赛（解放者杯、欧罗巴等）。

页面（SSR，积分表直接渲染在 HTML 里，无需调 XHR）：
  https://www.foxsports.com/soccer/<slug>/standings
  表格：<table id="live-standings-table-N">
    表头 <th colspan=2><h2>GROUP A</h2>  小组名
    行 10 格：名次 / 队名 / 场次 / 积分 / 胜-平-负 / 进球 / 失球 / 净胜 / 主场胜平负 / 客场胜平负

输出：fox_standings.json
  {"fetched_at": "...", "leagues": {"解放者杯": {"slug": "...", "type": "group",
      "groups": [{"name": "A", "teams": [{"rank":1,"name":"Flamengo RJ","zh":"弗拉门戈",
        "p":6,"w":5,"d":1,"l":0,"gf":14,"ga":2,"gd":12,"pts":16}, ...]}]}}}

说明：
- fox 用英文队名，展示层优先用 zh（本脚本内置对照表，只收能确认的）；缺 zh 就保留英文原名，不猜。
- 队名对照表只服务「显示 + 与本报告中文队名匹配」，不参与任何概率计算。
"""
import gzip
import html as _html
import json
import re
import sys
import urllib.request
from datetime import datetime

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml',
      'Referer': 'https://www.foxsports.com/', 'Accept-Encoding': 'gzip'}

# 报告赛事名 → foxsports slug
COMP_MAP = {
    '解放者杯': 'copa-libertadores',
    '欧罗巴': 'europa-league',
}

# 英文队名 → 中文（仅收可确认的；未列出的原样保留英文，绝不音译臆造）
EN_ZH = {
    # ── 解放者杯 ──
    'Flamengo RJ': '弗拉门戈', 'Estudiantes': '大学生', 'Ind. Medellín': '麦德林独立',
    'Cusco FC': '库斯科', 'Coquimbo Unido': '科金博', 'Dep Tolima': '托利马',
    'Nacional': '乌拉圭国民', 'Universitario': '大学体育',
    'Independiente Rivadavia': '里瓦达维亚独立', 'Fluminense': '弗鲁米嫩塞',
    'Bolívar': '玻利瓦尔', 'Dep La Guaira': '拉瓜伊拉', 'U Católica (CHI)': '天主教大学',
    'Cruzeiro': '克鲁塞罗', 'Boca Juniors': '博卡青年', 'Barcelona': '巴塞罗那SC',
    'Corinthians': '科林蒂安', 'CA Platense': '普拉滕塞', 'Ind. Santa Fe': '圣塔菲独立',
    'Peñarol': '佩纳罗尔', 'Cerro Porteño': '波特诺山丘', 'Palmeiras': '帕尔梅拉斯',
    'Sporting Cristal': '水晶体育', 'Junior': '巴兰基亚青年', 'LDU Quito': '基多大学',
    'Mirassol FC SP': '米拉索尔', 'Lanús': '拉努斯', 'Always Ready': '阿尔维斯雷迪',
    'Ind. del Valle': '山谷独立', 'Rosario Central': '罗萨里奥中央', 'Libertad': '亚松森自由',
    # ── 欧罗巴 ──
    'Juventus': '尤文', 'Leverkusen': '勒沃库森', 'Benfica': '本菲卡', 'Besiktas': '贝西克塔斯',
    'Bournemouth': '伯恩茅斯', 'AC Omonoia': '奥莫尼亚', 'Ferencvaros': '费伦茨瓦罗斯',
    'Lyon': '里昂', 'Sunderland': '桑德兰', 'Olympiacos': '奥林匹亚科斯',
    'Sparta Prague': '布拉格斯巴达', 'Union Saint-Gilloise': '圣吉尔联', 'Rennes': '雷恩',
    'Dinamo Zagreb': '萨格勒布迪纳摩', 'Crystal Palace': '水晶宫', 'AC Milan': 'AC米兰',
    'Jagiellonia': '亚杰洛尼亚', 'OFI Crete': 'OFI克里特', 'SCU Torreense': '托雷嫩塞',
    'AZ Alkmaar': '阿尔克马尔', 'Red Bull Salz.': '萨尔茨堡', 'Real Sociedad': '皇家社会',
    'Lillestrom': '利勒斯特罗姆', "Be'er Sheva": '贝尔谢巴', 'Levski Sofia': '列夫斯基索菲亚',
    'SK Sturm Graz': '格拉茨风暴', 'NEC Nijmegen': '奈梅亨', 'Anderlecht': '安德莱赫特',
    'Celta Vigo': '塞尔塔', 'Hoffenheim': '霍芬海姆', 'Viktoria Plzen': '比尔森',
    'Marseille': '马赛', 'Celtic': '凯尔特人', 'FC Ararat-Armenia': '阿拉拉特',
    'Celje': '采列', 'Lech Poznan': '波兹南莱赫',
}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
    return raw.decode('utf-8', 'ignore')


def _txt(s):
    return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def _int(s, d=0):
    m = re.search(r'-?\d+', s or '')
    return int(m.group(0)) if m else d


def parse_standings(page):
    """→ [{'name': 'A'|'' , 'teams': [...]}]"""
    groups = []
    for tb in re.findall(r'(<table[^>]*id="live-standings-table-\d+".*?</table>)', page, re.S):
        g = re.search(r'<th[^>]*colspan="2"[^>]*><h2>(.*?)</h2>', tb)
        gname = _txt(g.group(1)) if g else ''
        gname = re.sub(r'^(GROUP|GRP)\s+', '', gname, flags=re.I).strip()
        if gname.upper() in ('CLUBS', 'TEAMS', 'STANDINGS'):
            gname = ''
        teams = []
        for tr in re.findall(r'<tr[^>]*id="tbl-row-\d+".*?</tr>', tb, re.S):
            tds = [_txt(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
            if len(tds) < 8:
                continue
            wdl = [_int(x) for x in (tds[4].split('-') + ['0', '0', '0'])[:3]]
            raw = tds[1]
            teams.append({
                'rank': _int(tds[0]), 'name': raw, 'zh': EN_ZH.get(raw, ''),
                'p': _int(tds[2]), 'pts': _int(tds[3]),
                'w': wdl[0], 'd': wdl[1], 'l': wdl[2],
                'gf': _int(tds[5]), 'ga': _int(tds[6]), 'gd': _int(tds[7]),
            })
        if teams:
            groups.append({'name': gname, 'teams': teams})
    return groups


def fetch_league(name, slug):
    page = _get(f'https://www.foxsports.com/soccer/{slug}/standings')
    groups = parse_standings(page)
    if not groups:
        return None
    n = sum(len(g['teams']) for g in groups)
    return {'slug': slug, 'type': 'group' if len(groups) > 1 else 'league',
            'groups': groups, '_n': n}


def main(only=None):
    out = {'fetched_at': datetime.now().isoformat(timespec='seconds'), 'leagues': {}}
    for name, slug in COMP_MAP.items():
        if only and name not in only:
            continue
        try:
            lg = fetch_league(name, slug)
        except Exception as e:
            print(f'[Fox榜] {name} 抓取失败：{type(e).__name__} {e}', file=sys.stderr)
            continue
        if not lg:
            print(f'[Fox榜] {name} 无榜单（{slug}）', file=sys.stderr)
            continue
        n = lg.pop('_n')
        out['leagues'][name] = lg
        print(f'[Fox榜] {name}：{n} 队 / {len(lg["groups"])} 组（{slug}）')
    if not out['leagues']:
        print('[Fox榜] 全部失败，保留原文件不动', file=sys.stderr)
        return 1
    try:
        old = json.load(open('fox_standings.json', encoding='utf-8')).get('leagues') or {}
        for k, v in old.items():
            out['leagues'].setdefault(k, v)
    except Exception:
        pass
    json.dump(out, open('fox_standings.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'[Fox榜] 已写入 fox_standings.json：{", ".join(out["leagues"])}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or None))
