#!/usr/bin/env python3
"""从网易体育抓取赔率数据，解析后生成odds_data.json文件，供网页在线查看最新赔率。"""
import re, json, html, sys, os, datetime, urllib.request, urllib.error
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'odds_data.json')

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

def nparse(val):
    """递归解析网易 [tag, data] 格式"""
    if isinstance(val, list) and len(val) == 2:
        tag, data = val
        if tag == 0: return nparse(data)  # 递归解析，避免 [0, [0, X]] 嵌套
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

def estimate_1x2_from_handicap(handicap, home_odds, draw_odds, away_odds):
    """从让球盘反推 1X2 赔率"""
    try:
        h = float(str(handicap).replace('+', ''))
        h_prob = 1/float(home_odds) if home_odds else 0.33
        d_prob = 1/float(draw_odds) if draw_odds else 0.25
        a_prob = 1/float(away_odds) if away_odds else 0.33
        total = h_prob + d_prob + a_prob
        h_prob, d_prob, a_prob = h_prob/total, d_prob/total, a_prob/total
        
        if h >= 1:
            a_actual = min(0.85, a_prob + 0.15 * h)
            h_actual = max(0.03, h_prob - 0.12 * h)
            d_actual = max(0.05, 1 - a_actual - h_actual)
        elif h <= -1:
            h_actual = min(0.85, h_prob + 0.15 * abs(h))
            a_actual = max(0.03, a_prob - 0.12 * abs(h))
            d_actual = max(0.05, 1 - h_actual - a_actual)
        else:
            return '', '', ''
        
        total = h_actual + d_actual + a_actual
        h_actual, d_actual, a_actual = h_actual/total, d_actual/total, a_actual/total
        margin = 1.05
        return round(margin/h_actual, 2), round(margin/d_actual, 2), round(margin/a_actual, 2)
    except:
        return '', '', ''

def to_odds_data(matches):
    result = {}
    for m in matches:
        h, g = m['home'], m['guest']
        if not h or not g: continue
        key = f"{h} vs {g}"
        plays = m['plays']
        entry = {'胜': '', '平': '', '负': '', '让球': [], '比分': {}, '总进球': {}, '半全场': {}}

        hda = plays.get('HDA', {})
        if hda.get('concede') == '0':
            for n, o in hda.get('items', {}).items():
                if n == '主胜': entry['胜'] = o
                elif n == '平': entry['平'] = o
                elif n == '客胜': entry['负'] = o
        
        # 如果没有 HDA，尝试从让球盘反推
        if not entry['胜']:
            hhda = plays.get('HHDA', {})
            if hhda:
                hc = hhda.get('concede', '0')
                items = hhda.get('items', {})
                h_odds = items.get('主胜', '')
                d_odds = items.get('平', '')
                a_odds = items.get('客胜', '')
                if hc and h_odds:
                    h_est, d_est, a_est = estimate_1x2_from_handicap(hc, h_odds, d_odds, a_odds)
                    entry['胜'] = h_est
                    entry['平'] = d_est
                    entry['负'] = a_est
                    log(f"  {key}: 从让球{hc}反推 1X2 = {h_est}/{d_est}/{a_est}")

        hhda = plays.get('HHDA', {})
        if hhda:
            c = hhda.get('concede', '0')
            im = {k: v for k, v in hhda.get('items', {}).items()}
            if im: entry['让球'] = [{'handicap': c, '胜': im.get('主胜',''), '平': im.get('平',''), '负': im.get('客胜','')}]

        for n, o in plays.get('FBF', {}).get('items', {}).items():
            entry['比分'][n] = o

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
