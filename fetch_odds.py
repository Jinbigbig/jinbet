#!/usr/bin/env python3
"""
GitHub Actions 赔率抓取脚本
输出 odds_data.json，供网页在线查看
"""
import re, json, html, sys, os, datetime, urllib.request, urllib.error

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'odds_data.json')

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

def nparse(val):
    """递归解析网易 [tag, data] 格式"""
    if isinstance(val, list) and len(val) == 2:
        tag, data = val
        if tag == 0: return data
        if tag == 1 and isinstance(data, list): return [nparse(i) for i in data]
    if isinstance(val, dict): return {k: nparse(v) for k, v in val.items()}
    if isinstance(val, list): return [nparse(i) for i in val]
    return val

def nget(obj, key):
    if not isinstance(obj, dict): return None
    raw = obj.get(key)
    return nparse(raw) if raw is not None else None

def parse_play_items(play_item_list):
    items = {}
    parsed = nparse(play_item_list)
    if not isinstance(parsed, list): return items
    for item in parsed:
        if not isinstance(item, dict): continue
        name = nget(item, 'playItemName')
        odds = nget(item, 'odds')
        if name and odds is not None:
            items[name] = str(odds)
    return items

def fetch():
    url = "https://sports.163.com/caipiao/bet/football"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://sports.163.com/',
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8')

def extract_matches(raw):
    m = re.search(
        r'<astro-island[^>]+component-url="[^"]*PageSports[^"]*"[^>]*props="([^"]*)"',
        raw, re.DOTALL)
    if not m: raise ValueError("未找到 PageSports props 数据")
    props = json.loads(html.unescape(m.group(1)))
    init_list = nparse(nget(props, 'initList'))
    if not isinstance(init_list, list): raise ValueError("initList 格式异常")

    matches = []
    for grp in init_list:
        if not isinstance(grp, dict): continue
        for raw_match in (nparse(nget(grp, 'matchList')) or []):
            if not isinstance(raw_match, dict): continue
            home_raw = nget(raw_match, 'homeTeam')
            guest_raw = nget(raw_match, 'guestTeam')
            if not home_raw or not guest_raw: continue

            plays = {}
            play_map = nget(raw_match, 'playMap')
            if isinstance(play_map, dict):
                for code, pval in play_map.items():
                    if not isinstance(pval, dict): continue
                    plays[code] = {
                        'concede': nget(pval, 'concede'),
                        'items': parse_play_items(nget(pval, 'playItemList')),
                    }

            matches.append({
                'home': nget(home_raw, 'teamName'),
                'guest': nget(guest_raw, 'teamName'),
                'plays': plays,
            })
    return matches

def to_odds_data(matches):
    result = {}
    for m in matches:
        h, g = m['home'], m['guest']
        if not h or not g: continue
        key = f"{h} vs {g}"
        plays = m['plays']
        entry = {'胜': '', '平': '', '负': '', '让球': [], '比分': {}, '总进球': {}, '其他': {}, '半全场': {}}

        hda = plays.get('HDA', {})
        if hda.get('concede') == '0':
            for n, o in hda.get('items', {}).items():
                if n == '主胜': entry['胜'] = o
                elif n == '平': entry['平'] = o
                elif n == '客胜': entry['负'] = o

        hhda = plays.get('HHDA', {})
        if hhda:
            c = hhda.get('concede', '0')
            im = {k: v for k, v in hhda.get('items', {}).items()}
            if im: entry['让球'] = [{'concede': c, '胜': im.get('主胜',''), '平': im.get('平',''), '负': im.get('客胜','')}]

        for n, o in plays.get('FBF', {}).get('items', {}).items():
            entry['比分'][n] = o
            if '胜其他' in n: entry['其他']['胜其他'] = o
            elif '平其他' in n: entry['其他']['平其他'] = o
            elif '负其他' in n: entry['其他']['负其他'] = o

        for n, o in plays.get('FJQ', {}).get('items', {}).items():
            entry['总进球'][n] = o

        for n, o in plays.get('FBQC', {}).get('items', {}).items():
            entry['半全场'][n] = o

        result[key] = entry
    return result

log("抓取网易赔率...")
html_content = fetch()
log(f"页面大小: {len(html_content)} bytes")
matches = extract_matches(html_content)
log(f"解析到 {len(matches)} 场比赛")

data = to_odds_data(matches)

# 检查是否有胜平负数据
has_odds = sum(1 for v in data.values() if v.get('胜'))
log(f"其中有胜平负数据: {has_odds} 场")

output = {'updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'count': len(data), 'data': data}
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
log(f"✅ 成功: {len(data)} 场 → {OUTPUT}")
