# -*- coding: utf-8 -*-
"""从网易体育抓取赔率，替换index.html中的赛程和赔率数据，并更新odds_data.json。GitHub Actions每日调用。"""
import sys, os, json, re, subprocess, urllib.request

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, 'index.html')

TEAM_NAME_MAP = {
    '民主刚果': '刚果（金）', '刚果金': '刚果（金）', '刚果(金)': '刚果（金）',
    '乌兹别克': '乌兹别克斯坦', '乌兹别克斯坦': '乌兹别克斯坦',
    '阿尔及利': '阿尔及利亚', '阿尔及利亚': '阿尔及利亚',
    '沙特': '沙特阿拉伯',
    # 体彩API队名 → 网易队名 映射（用于key统一）
    '贝西克塔斯': '贝西克塔', '斯普利特海杜克': '斯海杜克',
    '安德莱赫特': '安德莱', '费伦茨瓦罗斯': '费伦茨',
    '巴拉纳竞技': '巴竞技', '多伦多FC': '多伦多',
    '利勒斯特罗姆': '利勒斯特',
}

# 竞彩联赛名称映射（当网易抓取数据中 league 为空时的兜底）
LEAGUE_MAP = {
    '济州SK': '韩职', '江原FC': '韩职', '全北现代': '韩职', '大田市民': '韩职',
    '蔚山现代': '韩职', '仁川联': '韩职', '首尔FC': '韩职', '浦项制铁': '韩职',
    '光州FC': '韩职', '金泉尚武': '韩职', '富川FC': '韩职', '安养FC': '韩职',
    '水原FC': '韩职', '大邱FC': '韩职', '江原': '韩职', '浦项': '韩职',
    '米竞技': '巴西甲', '巴伊亚': '巴西甲', '弗拉门戈': '巴西甲', '沙佩科': '巴西甲',
    '圣保罗': '巴西甲', '巴竞技': '巴西甲', '科林蒂安': '巴西甲', '博塔弗戈': '巴西甲',
    '维多利亚': '巴西甲', '里莫': '巴西甲', '克鲁塞罗': '巴西甲', '格雷米奥': '巴西甲',
    '萨巴赫': '欧冠', '库奥皮奥': '欧冠', '奥胡斯': '欧冠', '波兹南': '欧冠',
    '格风暴': '欧冠', '哈茨': '欧冠', '奥莫尼亚': '欧冠', '阿拉木图': '欧冠',
}


def decode_netease_value(s):
    s = re.sub(r'\[0,\s*"([^"]+)"\]', r'"\1"', s)
    s = re.sub(r'\[0,\s*(\d+\.?\d*)\]', r'\1', s)
    s = re.sub(r'\[0,\s*true\]', r'true', s)
    s = re.sub(r'\[0,\s*false\]', r'false', s)
    s = re.sub(r'\[0,\s*(\d+)\]', r'\1', s)
    return s




def parse_odds_from_html(html_content):
    import html
    html_content = html.unescape(html_content)
    
    odds_data = {}
    schedule_data = {}
    
    group_positions = [m.start() for m in re.finditer(r'\{"group"\s*:\s*\[0,\s*"', html_content)]
    
    for group_idx, start_pos in enumerate(group_positions):
        next_start = group_positions[group_idx+1] if group_idx+1 < len(group_positions) else len(html_content)
        
        match_list_start = html_content.find('"matchList":[1,', start_pos)
        if match_list_start == -1:
            continue
        
        depth = 2
        pos = match_list_start + len('"matchList":[1,')
        while pos < next_start and depth > 0:
            if html_content[pos] == '[':
                depth += 1
            elif html_content[pos] == ']':
                depth -= 1
            elif html_content[pos] == '{':
                depth += 1
            elif html_content[pos] == '}':
                depth -= 1
            pos += 1
        
        match_list_content = html_content[match_list_start+len('"matchList":[1,'):pos]
        
        group_date_match = re.search(r'\{"group"\s*:\s*\[0,\s*"([^"]+)"', html_content[start_pos:match_list_start])
        group_date = group_date_match.group(1) if group_date_match else ''
        
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', group_date)
        if not date_match:
            continue
        match_date = date_match.group(1)
        
        game_blocks = []
        depth = 0
        block_start = -1
        in_bracket = False
        
        for i, c in enumerate(match_list_content):
            if c == '"':
                in_bracket = not in_bracket
            elif c == '[' and not in_bracket:
                depth += 1
                if depth == 2 and block_start == -1:
                    block_start = i
            elif c == ']' and not in_bracket:
                depth -= 1
                if depth == 1 and block_start != -1:
                    inner = match_list_content[block_start+len('[0,'):i]
                    game_blocks.append(inner)
                    block_start = -1
        
        for game_block in game_blocks:
            home_match = re.search(r'homeTeam"\s*:\s*\[0,\s*\{[^}]*?teamName"\s*:\s*\[0,\s*"([^"]+)"', game_block)
            away_match = re.search(r'guestTeam"\s*:\s*\[0,\s*\{[^}]*?teamName"\s*:\s*\[0,\s*"([^"]+)"', game_block)
            
            if not home_match or not away_match:
                continue
            
            home = home_match.group(1)
            away = away_match.group(1)
            
            league_match = re.search(r'leagueMatchName"\s*:\s*\[0,\s*"([^"]+)"', game_block)
            league = league_match.group(1) if league_match else ''
            
            for map_home, standard_home in TEAM_NAME_MAP.items():
                if map_home in home:
                    home = standard_home
                    break
            
            for map_away, standard_away in TEAM_NAME_MAP.items():
                if map_away in away:
                    away = standard_away
                    break
            
            key = f'{match_date}_{home}_{away}'
            
            if key not in odds_data:
                odds_data[key] = {'胜': '', '平': '', '负': '', '让球': [], '比分': {}, '总进球': {}, '半全场': {}, 'league': league}
            else:
                # 同步更新 league（防止旧数据中 league 为空）
                if not odds_data[key].get('league'):
                    odds_data[key]['league'] = league
            
            if match_date not in schedule_data:
                schedule_data[match_date] = []
            if {'home': home, 'away': away, 'league': league} not in schedule_data[match_date]:
                schedule_data[match_date].append({'home': home, 'away': away, 'league': league})
            
            hda_pattern = r'"HDA"\s*:\s*\[0,\s*\{[\s\S]*?playItemList"\s*:\s*\[1,\s*(\[\[0,\s*\{[\s\S]*?\}\]\])'
            hda_match = re.search(hda_pattern, game_block)
            if hda_match:
                hda_item_list = hda_match.group(1)
                hda_names = re.findall(r'playItemName"\s*:\s*\[0,\s*"([^"]+)"', hda_item_list)
                hda_odds = re.findall(r'odds"\s*:\s*\[0,\s*(\d+\.?\d*)', hda_item_list)
                for j, name in enumerate(hda_names):
                    if j < len(hda_odds):
                        if name == '主胜':
                            odds_data[key]['胜'] = hda_odds[j]
                        elif name == '平':
                            odds_data[key]['平'] = hda_odds[j]
                        elif name == '客胜':
                            odds_data[key]['负'] = hda_odds[j]
            
            hhda_pattern = r'"HHDA"\s*:\s*\[0,\s*\{[\s\S]*?playItemList"\s*:\s*\[1,\s*(\[\[0,\s*\{[\s\S]*?\}\]\])'
            hhda_match = re.search(hhda_pattern, game_block)
            if hhda_match:
                hhda_item_list = hhda_match.group(1)
                concede_match = re.search(r'"HHDA"\s*:\s*\[0,\s*\{[\s\S]*?concede"\s*:\s*\[0,\s*"([^"]+)"', game_block)
                handicap = concede_match.group(1) if concede_match else ''
                hhda_names = re.findall(r'playItemName"\s*:\s*\[0,\s*"([^"]+)"', hhda_item_list)
                hhda_odds = re.findall(r'odds"\s*:\s*\[0,\s*(\d+\.?\d*)', hhda_item_list)
                let_odds = {'handicap': handicap, '胜': '', '平': '', '负': ''}
                for j, name in enumerate(hhda_names):
                    if j < len(hhda_odds):
                        if name == '主胜':
                            let_odds['胜'] = hhda_odds[j]
                        elif name == '平':
                            let_odds['平'] = hhda_odds[j]
                        elif name == '客胜':
                            let_odds['负'] = hhda_odds[j]
                if let_odds['胜'] or let_odds['平'] or let_odds['负']:
                    odds_data[key]['让球'].append(let_odds)
            
            fbf_pattern = r'"FBF"\s*:\s*\[0,\s*\{[\s\S]*?playItemList"\s*:\s*\[1,\s*(\[\[0,\s*\{[\s\S]*?\}\]\])'
            fbf_match = re.search(fbf_pattern, game_block)
            if fbf_match:
                fbf_item_list = fbf_match.group(1)
                fbf_names = re.findall(r'playItemName"\s*:\s*\[0,\s*"([^"]+)"', fbf_item_list)
                fbf_odds = re.findall(r'odds"\s*:\s*\[0,\s*(\d+\.?\d*)', fbf_item_list)
                for j, name in enumerate(fbf_names):
                    if j < len(fbf_odds):
                        odds_data[key]['比分'][name] = fbf_odds[j]
            
            fjq_pattern = r'"FJQ"\s*:\s*\[0,\s*\{[\s\S]*?playItemList"\s*:\s*\[1,\s*(\[\[0,\s*\{[\s\S]*?\}\]\])'
            fjq_match = re.search(fjq_pattern, game_block)
            if fjq_match:
                fjq_item_list = fjq_match.group(1)
                fjq_names = re.findall(r'playItemName"\s*:\s*\[0,\s*"([^"]+)"', fjq_item_list)
                fjq_odds = re.findall(r'odds"\s*:\s*\[0,\s*(\d+\.?\d*)', fjq_item_list)
                for j, name in enumerate(fjq_names):
                    if j < len(fjq_odds):
                        odds_data[key]['总进球'][name] = fjq_odds[j]
            
            fbqc_pattern = r'"FBQC"\s*:\s*\[0,\s*\{[\s\S]*?playItemList"\s*:\s*\[1,\s*(\[\[0,\s*\{[\s\S]*?\}\]\])'
            fbqc_match = re.search(fbqc_pattern, game_block)
            if fbqc_match:
                fbqc_item_list = fbqc_match.group(1)
                fbqc_names = re.findall(r'playItemName"\s*:\s*\[0,\s*"([^"]+)"', fbqc_item_list)
                fbqc_odds = re.findall(r'odds"\s*:\s*\[0,\s*(\d+\.?\d*)', fbqc_item_list)
                for j, name in enumerate(fbqc_names):
                    if j < len(fbqc_odds):
                        odds_data[key]['半全场'][name] = fbqc_odds[j]
    
    return odds_data, schedule_data


def fetch_odds_from_net():
    url = 'https://sports.163.com/caipiao/bet/football'
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode('utf-8')
        return content
    except Exception as e:
        print(f'[错误] 获取网易赔率失败: {e}')
        return ''


# 比分key映射：API中 crs 的 sXXsYY 格式 → 比分文本
# sXXsYY = 主队进球XX, 客队进球YY
_CRS_KEY_MAP = {}
for _h in range(6):
    for _a in range(6):
        _key = f's{_h:02d}s{_a:02d}'
        _CRS_KEY_MAP[_key] = f'{_h}:{_a}'
# 胜其他/平其他/负其他
_CRS_KEY_MAP['s1sh'] = '胜其他'
_CRS_KEY_MAP['s1sd'] = '平其他'
_CRS_KEY_MAP['s1sa'] = '负其他'

# 总进球key映射：API中 ttg 的 s0-s7 → 0-7+
_TTG_KEY_MAP = {f's{i}': str(i) for i in range(7)}
_TTG_KEY_MAP['s7'] = '7+'

# 半全场key映射：API中 hafu 的 key → 半全场文本
_HAFU_KEY_MAP = {
    'hh': '胜胜', 'hd': '胜平', 'ha': '胜负',
    'dh': '平胜', 'dd': '平平', 'da': '平负',
    'ah': '负胜', 'ad': '负平', 'aa': '负负',
}


def fetch_odds_from_lottery():
    """从体彩官网API获取赔率数据（备用方案），返回JSON文本"""
    url = 'https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c'
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.sporttery.cn/jc/jsq/zqhhgg/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode('utf-8')
        return content
    except Exception as e:
        print(f'[错误] 获取体彩赔率失败: {e}')
        return ''


def parse_lottery_json(json_text):
    """解析体彩官网API返回的JSON数据，返回赔率和赛程"""
    odds_data = {}
    schedule_data = {}

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f'[错误] JSON解析失败: {e}')
        return odds_data, schedule_data

    if not data.get('success') or not data.get('value'):
        print(f'[错误] API返回失败: {data.get("errorMessage", "未知错误")}')
        return odds_data, schedule_data

    value = data['value']
    match_info_list = value.get('matchInfoList', [])
    league_list = value.get('leagueList', [])

    # 构建联赛ID→名称映射
    league_map = {}
    for l in league_list:
        lid = l.get('leagueId', '')
        lname = l.get('leagueNameAbbr', '') or l.get('leagueName', '')
        if lid and lname:
            league_map[str(lid)] = lname

    for date_info in match_info_list:
        business_date = date_info.get('businessDate', '')
        sub_matches = date_info.get('subMatchList', [])

        for m in sub_matches:
            home = m.get('homeTeamAllName', '') or m.get('homeTeamAbbName', '')
            away = m.get('awayTeamAllName', '') or m.get('awayTeamAbbName', '')
            if not home or not away:
                continue

            # 清理队名中的联赛排名标记
            home = re.sub(r'\[[^\]]+\]', '', home).strip()
            away = re.sub(r'\[[^\]]+\]', '', away).strip()

            # 标准化队名（体彩API → 网易）
            for map_name, standard_name in TEAM_NAME_MAP.items():
                if map_name in home:
                    home = standard_name
                    break
            for map_name, standard_name in TEAM_NAME_MAP.items():
                if map_name in away:
                    away = standard_name
                    break

            # 获取联赛名
            league_id = str(m.get('leagueId', ''))
            league = league_map.get(league_id, '')

            # 胜平负赔率
            had = m.get('had', {})
            h = had.get('h', '')
            d = had.get('d', '')
            a = had.get('a', '')

            # 让球胜平负赔率
            hhad = m.get('hhad', {})
            handicap = hhad.get('goalLine', '') or hhad.get('goalLineValue', '')
            hhad_h = hhad.get('h', '')
            hhad_d = hhad.get('d', '')
            hhad_a = hhad.get('a', '')

            # 比分赔率
            crs = m.get('crs', {})
            score_odds = {}
            for crs_key, score_name in _CRS_KEY_MAP.items():
                val = crs.get(crs_key, '')
                if val and float(val) > 0:
                    score_odds[score_name] = val

            # 总进球赔率
            ttg = m.get('ttg', {})
            zjq_odds = {}
            for ttg_key, zjq_name in _TTG_KEY_MAP.items():
                val = ttg.get(ttg_key, '')
                if val and float(val) > 0:
                    zjq_odds[zjq_name] = val

            # 半全场赔率
            hafu = m.get('hafu', {})
            bqc_odds = {}
            for hafu_key, bqc_name in _HAFU_KEY_MAP.items():
                val = hafu.get(hafu_key, '')
                if val and float(val) > 0:
                    bqc_odds[bqc_name] = val

            # 构建key
            key = f'{business_date}_{home}_{away}'

            odds_data[key] = {
                '胜': h,
                '平': d,
                '负': a,
                '让球': [],
                '比分': score_odds,
                '总进球': zjq_odds,
                '半全场': bqc_odds,
                'league': league,
            }

            # 如果有让球数据
            if handicap and (hhad_h or hhad_d or hhad_a):
                odds_data[key]['让球'].append({
                    'handicap': handicap,
                    '胜': hhad_h,
                    '平': hhad_d,
                    '负': hhad_a,
                })

            # 保存赛程
            if business_date not in schedule_data:
                schedule_data[business_date] = []
            schedule_data[business_date].append({
                'home': home,
                'away': away,
                'league': league,
            })

    return odds_data, schedule_data


def update_html_schedule(html_content, new_schedule):
    schedule_pattern = r'const SCHEDULE = \{([\s\S]*?)\};'
    
    schedule_str = "const SCHEDULE = {\n"
    
    dates = sorted(new_schedule.keys())
    for i, date in enumerate(dates):
        games = new_schedule[date]
        games_str = ',\n        '.join([f"{{ home: '{g['home']}', away: '{g['away']}', league: '{g.get('league', '')}' }}" for g in games])
        comma = ',' if i < len(dates) - 1 else ''
        schedule_str += f"    '{date}': [\n        {games_str}\n      ]{comma}\n"
    
    schedule_str += "};"
    
    html_content = re.sub(schedule_pattern, schedule_str, html_content)
    
    return html_content


def update_html_odds(html_content, schedule, odds_data):
    odds_pattern = r'const ODDS = \{([\s\S]*?)\};'
    
    odds_str = "const ODDS = {\n"
    
    all_keys = []
    for date, games in schedule.items():
        for game in games:
            key = f'{date}_{game["home"]}_{game["away"]}'
            all_keys.append(key)
    # 同时包含 odds_data 中有但 schedule 中可能缺失的 key
    for key in odds_data:
        if key not in all_keys:
            all_keys.append(key)
    
    for i, key in enumerate(all_keys):
        if key in odds_data:
            odds = odds_data[key]
        else:
            odds = {'胜': '', '平': '', '负': '', '让球': [], '比分': {}, '总进球': {}, '半全场': {}}
        
        let_str = json.dumps(odds['让球'], ensure_ascii=False)
        score_str = json.dumps(odds['比分'], ensure_ascii=False)
        zjq_str = json.dumps(odds['总进球'], ensure_ascii=False)
        bqc_str = json.dumps(odds['半全场'], ensure_ascii=False)
        
        comma = ',' if i < len(all_keys) - 1 else ''
        
        odds_str += f"    '{key}': {{ '胜': '{odds['胜']}', '平': '{odds['平']}', '负': '{odds['负']}', '让球': {let_str}, '比分': {score_str}, '总进球': {zjq_str}, '半全场': {bqc_str} }}{comma}\n"
    
    odds_str += "};"
    
    html_content = re.sub(odds_pattern, odds_str, html_content)
    
    return html_content


def update_localstorage_injection(html_content, odds_data):
    injection_pattern = r'var data = \{([\s\S]*?)\};\s*var order = \[.*?\];\s*localStorage\.setItem\('
    match = re.search(injection_pattern, html_content)
    if match:
        new_data_str = '{\n'
        
        keys = sorted(odds_data.keys())
        order_list = []
        
        for i, key in enumerate(keys):
            odds = odds_data[key]
            date, home, away = key.split('_', 2)
            
            let_str = json.dumps(odds['让球'], ensure_ascii=False)
            score_str = json.dumps(odds['比分'], ensure_ascii=False)
            zjq_str = json.dumps(odds['总进球'], ensure_ascii=False)
            bqc_str = json.dumps(odds['半全场'], ensure_ascii=False)
            
            comma = ',' if i < len(keys) - 1 else ''
            
            new_data_str += f'  "{key}": {{\n'
            new_data_str += f'    "胜": "{odds["胜"]}",\n'
            new_data_str += f'    "平": "{odds["平"]}",\n'
            new_data_str += f'    "负": "{odds["负"]}",\n'
            new_data_str += f'    "让球": {let_str},\n'
            new_data_str += f'    "比分": {score_str},\n'
            new_data_str += f'    "总进球": {zjq_str},\n'
            new_data_str += f'    "半全场": {bqc_str}\n'
            new_data_str += f'  }}{comma}\n'
            
            order_list.append(f'"{home} vs {away}"')
        
        new_data_str += '}'
        
        order_str = '[' + ', '.join(order_list) + ']'
        
        new_injection = f'var data = {new_data_str};\n    var order = {order_str};\n    localStorage.setItem('
        
        html_content = re.sub(injection_pattern, new_injection, html_content)
    
    return html_content


def update_odds_json(matched_odds):
    import time
    odds_json_path = os.path.join(BASE_DIR, 'odds_data.json')
    
    online_data = {}
    for key, odds in matched_odds.items():
        date, home, away = key.split('_', 2)
        vs_key = f'{home} vs {away}'
        online_data[vs_key] = {
            '胜': odds['胜'],
            '平': odds['平'],
            '负': odds['负'],
            '让球': odds['让球'],
            '比分': odds['比分'],
            '总进球': odds['总进球'],
            '半全场': odds['半全场'],
            'league': odds.get('league', ''),
            'date_key': key
        }
    
    json_data = {
        'updated': time.strftime('%Y-%m-%d %H:%M'),
        'count': len(online_data),
        'data': online_data
    }
    
    with open(odds_json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)


def archive_old_data(schedule, odds, removed_dates):
    """将超过保留天数的旧数据归档到 odds_history/YYYY-MM-DD.json"""
    if not removed_dates:
        return

    archive_dir = os.path.join(BASE_DIR, 'odds_history')
    os.makedirs(archive_dir, exist_ok=True)

    for date in removed_dates:
        day_schedule = schedule.get(date, [])
        day_odds = {}
        for key, val in odds.items():
            if key.startswith(date + '_'):
                day_odds[key] = val
            elif val.get('date_key', '').startswith(date + '_'):
                day_odds[key] = val

        # 从 odds 补全 schedule 中缺失的比赛（schedule 可能被覆盖过）
        schedule_teams = set((g['home'], g['away']) for g in day_schedule)
        for key in day_odds:
            parts = key.split('_', 2)
            if len(parts) == 3 and parts[0] == date:
                home, away = parts[1], parts[2]
                if (home, away) not in schedule_teams:
                    league = day_odds[key].get('league', '')
                    day_schedule.append({'home': home, 'away': away, 'league': league})
                    schedule_teams.add((home, away))
        
        archive = {
            'date': date,
            'schedule': day_schedule,
            'odds': day_odds
        }
        
        archive_path = os.path.join(archive_dir, f'{date}.json')
        with open(archive_path, 'w', encoding='utf-8') as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
        print(f'    📁 归档: {date}.json ({len(day_schedule)}场, {len(day_odds)}条赔率)')
    
    # 更新归档索引
    update_archive_index(archive_dir)


def update_archive_index(archive_dir):
    """更新 odds_history/index.json 索引，供前端归档查看器使用"""
    weekdays = ['一', '二', '三', '四', '五', '六', '日']
    dates = []
    for filename in sorted(os.listdir(archive_dir)):
        if filename == 'index.json' or not filename.endswith('.json'):
            continue
        date_str = filename.replace('.json', '')
        filepath = os.path.join(archive_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            count = len(data.get('schedule', []))
        except:
            count = 0
        try:
            from datetime import datetime
            weekday = weekdays[datetime.strptime(date_str, '%Y-%m-%d').weekday()]
        except:
            weekday = '?'
        dates.append({'date': date_str, 'weekday': weekday, 'count': count})
    
    index_path = os.path.join(archive_dir, 'index.json')
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump({'dates': dates}, f, ensure_ascii=False, indent=2)
    print(f'    📋 归档索引已更新（{len(dates)} 个日期）')


def push_to_gh_pages():
    def run_git(*args):
        cmd = ['git', '--no-pager'] + list(args)
        print(f'\n> git {" ".join(args)}')
        env = os.environ.copy()
        res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, encoding='utf-8', errors='replace', env=env)
        if res.stdout.strip():
            print(res.stdout.rstrip())
        if res.stderr.strip():
            print(res.stderr.rstrip(), file=sys.stderr)
        return res
    
    run_git('add', 'index.html', 'odds_data.json')
    
    r = run_git('commit', '-m', '更新赔率数据（网易）')
    if r.returncode == 0:
        r = run_git('push', '--force-with-lease', 'origin', 'gh-pages')
        if r.returncode != 0:
            print('\n[警告] --force-with-lease 失败，尝试 --force 推送：')
            r = run_git('push', '--force', 'origin', 'gh-pages')
            if r.returncode != 0:
                print('\n[错误] 推送失败')
                return False
    
    print(f'\n✅ 已推送更新')
    return True


def parse_js_obj_to_json(js_str):
    js_str = re.sub(r"'", '"', js_str)
    js_str = re.sub(r",\s*\]", ']', js_str)
    js_str = re.sub(r",\s*\}", '}', js_str)
    js_str = re.sub(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', js_str)
    return js_str


def main():
    no_push = '--no-push' in sys.argv

    print('=' * 60)
    print('  从彩票网站获取赔率数据')
    print('=' * 60)

    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html_content = f.read()

    schedule_pattern = r'const SCHEDULE = \{([\s\S]*?)\};'
    match = re.search(schedule_pattern, html_content)

    if not match:
        print('[错误] 未找到 SCHEDULE 定义')
        sys.exit(1)

    schedule_str = '{' + match.group(1) + '}'
    schedule_str = parse_js_obj_to_json(schedule_str)
    schedule = json.loads(schedule_str)

    print(f'\n当前赛程包含 {len(schedule)} 个日期')

    # 尝试从网易获取数据
    print('\n[1/3] 尝试从网易体育获取赔率数据...')
    net_html = fetch_odds_from_net()
    odds_data = {}
    schedule_data = {}
    source = '网易体育'

    if net_html:
        print('  ✅ 网易体育获取成功')
        print('\n[2/3] 解析网易赔率数据...')
        odds_data, schedule_data = parse_odds_from_html(net_html)
        print(f'  ✅ 解析完成，共 {len(odds_data)} 场比赛赔率')

        # 如果网易解析返回0场比赛，尝试体彩官网API
        if len(odds_data) == 0:
            print('  ⚠️ 网易数据为0场，尝试从体彩官网API获取...')
            source = '体彩官网'
            lottery_json = fetch_odds_from_lottery()

            if lottery_json:
                print('  ✅ 体彩官网API获取成功')
                print('\n[2/3] 解析体彩赔率数据...')
                odds_data, schedule_data = parse_lottery_json(lottery_json)
                print(f'  ✅ 解析完成，共 {len(odds_data)} 场比赛赔率')
            else:
                print('[错误] 网易数据为0且体彩官网API获取失败')
                sys.exit(1)
    else:
        # 网易获取失败，尝试体彩官网API
        print('  ❌ 网易体育获取失败')
        print('\n[备用方案] 尝试从体彩官网API获取赔率数据...')
        source = '体彩官网'
        lottery_json = fetch_odds_from_lottery()

        if lottery_json:
            print('  ✅ 体彩官网API获取成功')
            print('\n[2/3] 解析体彩赔率数据...')
            odds_data, schedule_data = parse_lottery_json(lottery_json)
            print(f'  ✅ 解析完成，共 {len(odds_data)} 场比赛赔率')
        else:
            print('[错误] 无法从任何数据源获取赔率数据')
            sys.exit(1)

    print(f'\n📊 本次数据源: {source}')
    
    for key, odds in odds_data.items():
        print(f'    {key}: 胜={odds["胜"]}, 平={odds["平"]}, 负={odds["负"]}')
    
    print('\n[2.5/3] 合并赛程与赔率数据...')
    print(f'    原有赛程: {len(schedule)} 个日期')
    print(f'    新增赛程: {len(schedule_data)} 个日期')

    # 合并新旧赛程（追加新比赛，保留已有比赛，避免覆盖丢失）
    for date, games in schedule_data.items():
        if date not in schedule:
            schedule[date] = games
        else:
            existing_keys = set((g['home'], g['away']) for g in schedule[date])
            for g in games:
                if (g['home'], g['away']) not in existing_keys:
                    schedule[date].append(g)
    # 补全旧日期赛程中缺失的 league（从 schedule_data 中查找 + 映射表兜底）
    for date in schedule:
        for g in schedule[date]:
            if g.get('league'):
                continue
            if date in schedule_data:
                for ng in schedule_data[date]:
                    if ng['home'] == g['home'] and ng['away'] == g['away'] and ng.get('league'):
                        g['league'] = ng['league']
                        break
            if not g.get('league'):
                if g['home'] in LEAGUE_MAP:
                    g['league'] = LEAGUE_MAP[g['home']]
                elif g['away'] in LEAGUE_MAP:
                    g['league'] = LEAGUE_MAP[g['away']]
    print(f'    合并后赛程: {len(schedule)} 个日期')

    # 从现有 index.html 提取已有的 ODDS 数据
    odds_pattern = r'const ODDS = \{([\s\S]*?)\};'
    odds_match = re.search(odds_pattern, html_content)
    existing_odds = {}
    if odds_match:
        odds_str = '{' + odds_match.group(1) + '}'
        odds_str = parse_js_obj_to_json(odds_str)
        try:
            existing_odds = json.loads(odds_str)
            print(f'    原有赔率: {len(existing_odds)} 条')
        except:
            print('    读取历史赔率失败，将使用新数据')

    # 合并新旧赔率
    merged_odds = dict(existing_odds)
    for key, odds in odds_data.items():
        merged_odds[key] = odds
    print(f'    合并后赔率: {len(merged_odds)} 条')

    # 补全旧赔率中缺失的 league（从 schedule 和 schedule_data 中查找，最后用映射表兜底）
    league_filled = 0
    for key in list(merged_odds.keys()):
        if not merged_odds[key].get('league'):
            parts = key.split('_')
            date = parts[0]
            home = parts[1]
            away = '_'.join(parts[2:])
            filled = False
            # 先从合并后的 schedule 中查找
            if date in schedule:
                for g in schedule[date]:
                    if g['home'] == home and g['away'] == away and g.get('league'):
                        merged_odds[key]['league'] = g['league']
                        league_filled += 1
                        filled = True
                        break
            # 再从 schedule_data（网易新抓取）中查找
            if not filled and date in schedule_data:
                for g in schedule_data[date]:
                    if g['home'] == home and g['away'] == away and g.get('league'):
                        merged_odds[key]['league'] = g['league']
                        league_filled += 1
                        filled = True
                        break
            # 最后用映射表兜底
            if not filled:
                if home in LEAGUE_MAP:
                    merged_odds[key]['league'] = LEAGUE_MAP[home]
                    league_filled += 1
                elif away in LEAGUE_MAP:
                    merged_odds[key]['league'] = LEAGUE_MAP[away]
                    league_filled += 1
    if league_filled:
        print(f'    补全 league 字段: {league_filled} 条')

    # 归档并清理超过7天的旧数据
    from datetime import datetime, timedelta
    KEEP_DAYS = 7
    cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime('%Y-%m-%d')
    removed_dates = []
    for date in list(schedule.keys()):
        if date < cutoff:
            removed_dates.append(date)

    if removed_dates:
        archive_old_data(schedule, merged_odds, removed_dates)
        for date in removed_dates:
            del schedule[date]
        print(f'    清理旧赛程: {len(removed_dates)} 个日期（{cutoff} 之前）')
    else:
        print(f'    无需清理旧数据（保留最近 {KEEP_DAYS} 天）')

    # 清理超过7天的旧赔率
    removed_odds = []
    for key in list(merged_odds.keys()):
        date = key.split('_')[0]
        if not date.startswith('20'):
            date = merged_odds[key].get('date_key', '').split('_')[0]
        if date < cutoff:
            removed_odds.append(key)
            del merged_odds[key]
    if removed_odds:
        print(f'    清理旧赔率: {len(removed_odds)} 条（{cutoff} 之前）')

    for date, games in schedule.items():
        for game in games:
            print(f'    {date} {game["home"]} vs {game["away"]}')
    print(f'  ✅ 赛程合并完成')

    # 为当前 schedule 中的所有比赛构建 matched_odds
    matched_odds = {}
    for date, games in schedule.items():
        for game in games:
            home = game['home']
            away = game['away']
            key = f'{date}_{home}_{away}'
            if key in merged_odds:
                matched_odds[key] = merged_odds[key]
            else:
                matched_odds[key] = {
                    '胜': '', '平': '', '负': '',
                    '让球': [], '比分': {}, '总进球': {}, '半全场': {}
                }

    # 显示匹配结果
    for date, games in schedule.items():
        for game in games:
            key = f'{date}_{game["home"]}_{game["away"]}'
            has_odds = bool(matched_odds.get(key, {}).get('胜'))
            icon = '✅' if has_odds else '⬜'
            print(f'  {date} {game["home"]} vs {game["away"]}: {icon}')

    print('\n[4/4] 更新 index.html...')
    new_html = update_html_schedule(html_content, schedule)
    new_html = update_html_odds(new_html, schedule, matched_odds)
    new_html = update_localstorage_injection(new_html, matched_odds)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print('  ✅ index.html 已更新')

    print('\n[5/5] 更新 odds_data.json...')
    update_odds_json(matched_odds)
    print('  ✅ odds_data.json 已更新')
    
    if not no_push:
        push_to_gh_pages()
    
    print('\n' + '=' * 60)
    print('  赔率更新完成！')
    print('=' * 60)


# === 赛果抓取 ===

# 体彩赛果API队名 → 网易队名 映射（用于key统一）
RESULT_TEAM_NAME_MAP = {
    '布斯巴达': '布斯巴达', '布拉格斯巴达': '布斯巴达',
    '圣吉联合': '圣吉联合', '圣吉尔联合': '圣吉联合',
    '奥林匹亚': '奥林匹亚', '奥林匹亚科斯': '奥林匹亚',
    '米亚尔比': '米亚尔比',
    '布拉迪斯': '布拉迪斯', '布拉加': '布拉迪斯',
    '奈梅亨': '奈梅亨', 'NEC奈梅亨': '奈梅亨',
    '里昂': '里昂',
    '博德闪耀': '博德闪耀',
    '塞伊奈': '塞伊奈', '塞伊奈约基': '塞伊奈',
    '哈尔姆斯': '哈尔姆斯', '哈尔姆斯塔德': '哈尔姆斯',
    '天狼星': '天狼星',
    '佐加顿斯': '佐加顿斯',
    '韦斯特罗': '韦斯特罗', '韦斯特罗斯': '韦斯特罗',
    '巴竞技': '巴竞技', '巴拉纳竞技': '巴竞技',
    '维多利亚': '维多利亚',
    '里莫': '里莫', '里奥阿维': '里莫',
    '桑托斯': '桑托斯',
    '奥胡斯': '奥胡斯',
    '费内巴切': '费内巴切',
    '格风暴': '格风暴', '格拉茨风暴': '格风暴',
    '弗鲁米嫩': '弗鲁米嫩塞',
    '达伽马': '达伽马', '瓦斯科达伽马': '达伽马',
    '赫尔辛基': '赫尔辛基',
    'TPS图尔': 'TPS图尔', 'TPS图尔库': 'TPS图尔',
    '玛丽港': '玛丽港',
    '拉赫蒂': '拉赫蒂',
    '雅罗': '雅罗', '雅罗足球': '雅罗',
    '腓特烈': '腓特烈斯塔',
    '桑纳菲': '桑纳菲尤尔',
    '赫根': '赫根',
    '卡尔马': '卡尔马',
    '浦项制铁': '浦项',
    '金泉尚武': '金泉尚武',
    '全北现代': '全北现代',
    '首尔FC': '首尔FC',
    '江原FC': '江原FC',
    '富川FC': '富川FC',
    '波特兰': '波特兰', '波特兰伐木工': '波特兰',
    '西雅图': '西雅图', '西雅图海湾人': '西雅图',
    '洛城银河': '洛城银河', '洛杉矶银河': '洛城银河',
    '达拉斯': '达拉斯', '达拉斯FC': '达拉斯',
    '圣路易城': '圣路易城', '圣路易斯城': '圣路易城',
    '盐湖城': '盐湖城', '皇家盐湖城': '盐湖城',
    '芝加哥': '芝加哥', '芝加哥火焰': '芝加哥',
    '夏洛特FC': '夏洛特FC',
    '温哥华': '温哥华', '温哥华白帽': '温哥华',
    '洛杉矶FC': '洛杉矶FC',
    '迈国际': '迈国际', '迈阿密国际': '迈国际',
    '哥伦布': '哥伦布', '哥伦布机员': '哥伦布',
    '赫尔火花': '赫尔辛基火花',
    '库奥皮奥': '库奥皮奥',
    '斯达': '斯达', '斯塔贝克': '斯达',
    '维京': '维京',
}


def fetch_results(days_back=7):
    """从体彩官网API获取赛果数据"""
    from datetime import datetime, timedelta
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

    url = (
        f'https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'
        f'?matchBeginDate={start_date}&matchEndDate={end_date}'
        f'&leagueId=&pageSize=50&pageNo=1&isFix=0&matchPage=1&pcOrWap=1'
    )
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.sporttery.cn/jc/zqsgkj/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode('utf-8')
        return content
    except Exception as e:
        print(f'[错误] 获取体彩赛果失败: {e}')
        return ''


def normalize_result_team(name):
    """归一化体彩赛果API队名"""
    return RESULT_TEAM_NAME_MAP.get(name, name)


def parse_results_json(json_text):
    """解析体彩赛果API返回的JSON数据，返回赛果字典 {key: result_data}"""
    results = {}

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f'[错误] 赛果JSON解析失败: {e}')
        return results

    if not data.get('success') or not data.get('value'):
        print(f'[错误] 赛果API返回失败: {data.get("errorMessage", "未知错误")}')
        return results

    value = data['value']
    matches = value.get('matchResult', [])
    if not matches:
        print('[警告] 赛果API返回0场比赛')
        return results

    for m in matches:
        home_api = m.get('homeTeam', '')
        home_full = m.get('allHomeTeam', '')
        away_api = m.get('awayTeam', '')
        away_full = m.get('allAwayTeam', '')

        home = normalize_result_team(home_api)
        away = normalize_result_team(away_api)
        match_date = m.get('matchDate', '')

        if not match_date or not home or not away:
            continue

        key = f'{match_date}_{home}_{away}'

        handicap = m.get('goalLine', '0')
        if handicap in ('0', '', None):
            handicap = '0'

        result_data = {
            'halfScore': m.get('sectionsNo1', ''),
            'fullScore': m.get('sectionsNo999', ''),
            'winFlag': m.get('winFlag', ''),
            'handicap': handicap,
            'league': m.get('leagueName', ''),
            'leagueAbbr': m.get('leagueNameAbbr', ''),
            'home': home,
            'away': away,
            'matchId': m.get('matchId', ''),
            'status': m.get('matchResultStatus', ''),
        }

        if m.get('h'):
            result_data['胜'] = m['h']
        if m.get('d'):
            result_data['平'] = m['d']
        if m.get('a'):
            result_data['负'] = m['a']

        if result_data['fullScore']:
            results[key] = result_data

    print(f'  解析完成，共 {len(results)} 场比赛有赛果')
    return results


def update_html_results(html_content, results_data):
    """更新 index.html 中的 RESULTS 变量"""
    results_pattern = r'const RESULTS = \{[\s\S]*?\n\};'

    results_str = "const RESULTS = {\n"
    keys = sorted(results_data.keys())

    for i, key in enumerate(keys):
        r = results_data[key]
        val_parts = []
        for field in ['halfScore', 'fullScore', 'winFlag', 'handicap', 'league', 'leagueAbbr', 'home', 'away', 'matchId', 'status', '胜', '平', '负']:
            if field in r and r[field]:
                val_parts.append("'{}': '{}'".format(field, str(r[field]).replace("'", "\\'")))
        val_str = ', '.join(val_parts)

        comma = ',' if i < len(keys) - 1 else ''
        results_str += f"    '{key}': {{ {val_str} }}{comma}\n"

    results_str += "};"

    if re.search(results_pattern, html_content):
        html_content = re.sub(results_pattern, results_str, html_content)
    else:
        html_content = re.sub(
            r'(const ODDS = \{[\s\S]*?\n\};)',
            r'\1\n\n' + results_str,
            html_content
        )

    return html_content


def save_results_json(results_data):
    """保存赛果数据到 results_data.json"""
    json_path = os.path.join(BASE_DIR, 'results_data.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results_data, f, ensure_ascii=False, indent=2)
    print(f'  ✅ results_data.json 已更新 ({len(results_data)} 条)')


def archive_results(results_data, days=30):
    """归档超过指定天数的旧赛果"""
    from datetime import datetime, timedelta
    archive_dir = os.path.join(BASE_DIR, 'results_history')
    os.makedirs(archive_dir, exist_ok=True)

    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    archived_count = 0

    for key in list(results_data.keys()):
        date = key.split('_')[0]
        if date < cutoff:
            archive_file = os.path.join(archive_dir, f'{date}.json')
            existing = {}
            if os.path.exists(archive_file):
                with open(archive_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            existing[key] = results_data[key]
            with open(archive_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            del results_data[key]
            archived_count += 1

    if archived_count:
        print(f'  归档旧赛果: {archived_count} 条到 results_history/')

    # 更新归档索引
    index = {'dates': []}
    for filename in sorted(os.listdir(archive_dir)):
        if filename.endswith('.json') and filename != 'index.json':
            date_str = filename.replace('.json', '')
            filepath = os.path.join(archive_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            count = len(data)
            from datetime import datetime as dt
            weekday_cn = ['一', '二', '三', '四', '五', '六', '日']
            try:
                weekday = weekday_cn[dt.strptime(date_str, '%Y-%m-%d').weekday()]
            except:
                weekday = ''
            index['dates'].append({'date': date_str, 'weekday': weekday, 'count': count})

    with open(os.path.join(archive_dir, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return results_data


def fetch_and_save_results():
    """主函数：抓取赛果并保存"""
    print('\n' + '=' * 60)
    print('  从体彩官网获取赛果数据')
    print('=' * 60)

    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 抓取赛果
    print('\n[1/3] 获取体彩赛果数据...')
    json_text = fetch_results(days_back=7)

    if not json_text:
        print('[错误] 无法获取赛果数据')
        return False

    print('  ✅ 赛果API获取成功')

    # 解析赛果
    print('\n[2/3] 解析赛果数据...')
    new_results = parse_results_json(json_text)

    # 读取已有RESULTS
    results_pattern = r'const RESULTS = \{([\s\S]*?)\};'
    match = re.search(results_pattern, html_content)
    existing_results = {}
    if match:
        results_str = '{' + match.group(1) + '}'
        try:
            results_json = parse_js_obj_to_json(results_str)
            existing_results = json.loads(results_json)
            print(f'  原有赛果: {len(existing_results)} 条')
        except:
            print('  读取历史赛果失败，将使用新数据')

    # 合并
    merged_results = dict(existing_results)
    for key, val in new_results.items():
        merged_results[key] = val
    print(f'  合并后赛果: {len(merged_results)} 条')

    # 归档旧赛果
    merged_results = archive_results(merged_results, days=30)

    # 更新HTML
    print('\n[3/3] 更新 index.html 中的赛果数据...')
    html_content = update_html_results(html_content, merged_results)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print('  ✅ index.html 已更新')

    # 保存JSON
    save_results_json(merged_results)

    print('\n' + '=' * 60)
    print('  赛果更新完成！')
    print('=' * 60)
    return True


if __name__ == '__main__':
    if '--results-only' in sys.argv:
        fetch_and_save_results()
    elif '--full' in sys.argv:
        print('\n' + '#' * 60)
        print('  完整模式: 赔率 + 赛果 一键更新')
        print('#' * 60)
        main()
        print('\n' + '#' * 60)
        print('  赔率更新完成，开始抓取赛果...')
        print('#' * 60)
        fetch_and_save_results()
    else:
        main()
