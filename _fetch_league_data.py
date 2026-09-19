# -*- coding: utf-8 -*-
"""
抓取 7M 数据库（data.7m.com.cn）各联赛当前积分榜，输出 league_data.json。

数据源：每个联赛的 standing.js 以并行 JS 数组给出完整积分榜，例如
  var f_sds_tn  = ['巴塞隆拿','皇家馬德里', ...]   # 队名（繁体）
  var f_sds_mnum= [4,5,5,...]                       # 已赛场次
  var f_sds_mw / _md / _ml                          # 胜/平/负
  var f_sds_mgs / _mga                             # 进/失球
  var f_sds_pt   = [12,12,10,...]                   # 积分
  var f_sds_memo = ['歐冠盃','歐冠盃','',...]        # 备注（欧冠/欧联/降级区等）
  var sds_mn     = '2026-2027 西班牙甲組聯賽'         # 联赛+赛季名
  var sdss_last_update = '2026/9/13 6:52:39'        # 更新时间

说明：data.7m.com.cn 数据库只含历史/当前积分榜与赛果，不含未来赛程；
未来赛程若需接入，应另寻数据源（本脚本只处理积分榜）。

7M 原始队名/分区标注为繁体；本脚本在抓取时用 opencc(t2s) 额外生成简体字段
（name_zh / note_zh / season_zh）。报告渲染读简体字段即可全简体显示；
若运行环境无 opencc，简体字段回退为原始繁体（降级但不报错）。
匹配器 _league_match.py 仍使用原始繁体 name 字段，不受影响。
"""
import json
import re
import os
import sys
import urllib.request
import gzip
from datetime import datetime, date

# 我的联赛名 -> 7M country/league id（已逐一验证 18 个联赛均存在）
LEAGUE_7M_ID = {
    '英超': 92, '西甲': 85, '德甲': 39, '意甲': 34, '法甲': 93, '荷甲': 99, '葡超': 88,
    '瑞超': 103, '芬超': 105, '挪超': 104, '巴甲': 160, '日职': 102, '日乙': 347, '美职': 459,
    '法乙': 171, '意乙': 95, '西乙': 96, '德乙': 140,
}

BASE = 'https://data.7m.com.cn/matches_data/{id}/big/standing.js'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
      'Accept-Language': 'zh-CN,zh;q=0.9', 'Accept-Encoding': 'gzip'}


def _fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
        return raw.decode('utf-8', 'ignore')


def _parse_array(txt, varname):
    """提取 var VAR = [ ... ]; 的内容并解析为 Python 列表。空数组返回 []。"""
    m = re.search(r'var\s+' + re.escape(varname) + r'\s*=\s*\[(.*?)\];', txt, re.S)
    if not m:
        return []
    body = m.group(1).strip()
    if not body:
        return []
    try:
        return list(ast.literal_eval('[' + body + ']'))
    except Exception:
        # 容错：逐元素粗提
        items = re.findall(r"'([^']*)'|(-?\d+\.?\d*)", body)
        out = []
        for s, n in items:
            out.append(s if s != '' else (float(n) if '.' in n else int(n)))
        return out


import ast

try:
    from opencc import OpenCC
    _CC = OpenCC('t2s')  # 繁体 -> 简体
    def _t2s(s):
        return _CC.convert(s) if s else s
except Exception:
    _CC = None
    def _t2s(s):
        return s  # 缺 opencc 时降级：简体字段回退为原始（繁体）文本


def parse_standing(txt):
    """把 standing.js 文本解析为结构化 dict。"""
    season = re.search(r"var sds_mn\s*=\s*'([^']*)'", txt)
    updated = re.search(r"var sdss_last_update\s*=\s*'([^']*)'", txt)
    ti = _parse_array(txt, 'f_sds_ti')
    tn = _parse_array(txt, 'f_sds_tn')
    mnum = _parse_array(txt, 'f_sds_mnum')
    mw = _parse_array(txt, 'f_sds_mw')
    md = _parse_array(txt, 'f_sds_md')
    ml = _parse_array(txt, 'f_sds_ml')
    mgs = _parse_array(txt, 'f_sds_mgs')
    mga = _parse_array(txt, 'f_sds_mga')
    pt = _parse_array(txt, 'f_sds_pt')
    memo = _parse_array(txt, 'f_sds_memo')
    memo_type = _parse_array(txt, 'f_sds_memo_type')
    n = len(tn)
    teams = []
    for i in range(n):
        gf = mgs[i] if i < len(mgs) else 0
        ga = mga[i] if i < len(mga) else 0
        teams.append({
            'rank': i + 1,
            'tid': ti[i] if i < len(ti) else 0,
            'name': tn[i] if i < len(tn) else '',
            'name_zh': _t2s(tn[i]) if i < len(tn) else '',
            'p': mnum[i] if i < len(mnum) else 0,
            'w': mw[i] if i < len(mw) else 0,
            'd': md[i] if i < len(md) else 0,
            'l': ml[i] if i < len(ml) else 0,
            'gf': gf, 'ga': ga,
            'gd': (gf - ga) if isinstance(gf, (int, float)) and isinstance(ga, (int, float)) else 0,
            'pts': pt[i] if i < len(pt) else 0,
            'note': memo[i] if i < len(memo) else '',
            'note_zh': _t2s(memo[i]) if i < len(memo) else '',
            'note_type': memo_type[i] if i < len(memo_type) else 0,
        })
    # 联赛汇总（平均进球等），用于形势描述
    def _num(var, default=0):
        a = _parse_array(txt, var)
        return a[0] if a else default
    summary = {
        'avg_goals': _num('sdss_dqavg'),
        'avg_goals_total': _num('sdss_avg'),  # 可能不存在
        'last_update': updated.group(1) if updated else '',
    }
    return {
        'season': season.group(1) if season else '',
        'season_zh': _t2s(season.group(1)) if season else '',
        'teams': teams,
        'summary': summary,
    }


def fetch_league_data(leagues):
    """leagues: 我的联赛名列表。返回 {league: parsed}。"""
    out = {}
    for lg in leagues:
        cid = LEAGUE_7M_ID.get(lg)
        if not cid:
            print(f'  [skip] 未知联赛 {lg}（无 7M id 映射）', file=sys.stderr)
            continue
        url = BASE.format(id=cid)
        try:
            txt = _fetch(url)
            parsed = parse_standing(txt)
            if not parsed['teams']:
                print(f'  [warn] {lg} 解析为空', file=sys.stderr)
                continue
            out[lg] = parsed
            print(f'  [ok] {lg} ({cid}) 赛季={parsed["season"]} 队数={len(parsed["teams"])}')
        except Exception as e:
            print(f'  [err] {lg} ({cid}): {e}', file=sys.stderr)
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    md = os.path.join(here, 'scripts', 'matches_data.json')
    with open(md, encoding='utf-8') as f:
        data = json.load(f)
    leagues = sorted(set(m['league'] for m in data['matches']))
    print(f'今日联赛 {len(leagues)} 个：{leagues}')
    result = fetch_league_data(leagues)
    out_path = os.path.join(here, 'league_data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'date': data.get('today', str(date.today())),
                   'fetched_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   'leagues': result}, f, ensure_ascii=False, indent=1)
    print(f'已写入 {out_path}（{len(result)} 个联赛）')


if __name__ == '__main__':
    main()
