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
                odds_data[key] = {'胜': '', '平': '', '负': '', '让球': [], '比分': {}, '总进球': {}, '半全场': {}}
            
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
            'league': '',
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
    print('  从网易彩票获取赔率数据')
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
    
    print('\n[1/3] 获取网易赔率数据...')
    net_html = fetch_odds_from_net()
    if not net_html:
        print('[错误] 无法获取赔率数据')
        sys.exit(1)
    
    print('  ✅ 获取成功')
    
    print('\n[2/3] 解析赔率数据...')
    odds_data, schedule_data = parse_odds_from_html(net_html)
    print(f'  ✅ 解析完成，共 {len(odds_data)} 场比赛赔率')
    
    for key, odds in odds_data.items():
        print(f'    {key}: 胜={odds["胜"]}, 平={odds["平"]}, 负={odds["负"]}')
    
    print('\n[2.5/3] 合并赛程与赔率数据...')
    print(f'    原有赛程: {len(schedule)} 个日期')
    print(f'    新增赛程: {len(schedule_data)} 个日期')

    # 合并新旧赛程
    for date, games in schedule_data.items():
        schedule[date] = games
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


if __name__ == '__main__':
    main()
