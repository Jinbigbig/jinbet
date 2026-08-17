# -*- coding: utf-8 -*-
"""从网易体育抓取赔率，替换index.html中的赛程和赔率数据，并更新odds_data.json。GitHub Actions每日调用。"""
import sys, os, json, re, subprocess, urllib.request

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, 'index.html')

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

# 体彩赛果API队名 → SCHEDULE队名 映射（用于key统一）
# 映射方向：API可能返回的变体名称 → SCHEDULE中使用的标准名称
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
    '弗鲁米嫩': '弗鲁米嫩', '弗鲁米嫩塞': '弗鲁米嫩',
    '达伽马': '达伽马', '瓦斯科达伽马': '达伽马',
    '赫尔辛基': '赫尔辛基',
    'TPS图尔': 'TPS图尔', 'TPS图尔库': 'TPS图尔',
    '玛丽港': '玛丽港',
    '拉赫蒂': '拉赫蒂',
    '雅罗': '雅罗', '雅罗足球': '雅罗',
    '腓特烈': '腓特烈', '腓特烈斯塔': '腓特烈',
    '桑纳菲': '桑纳菲', '桑纳菲尤尔': '桑纳菲',
    '萨尔普斯堡': '萨尔普斯堡', '萨普斯堡': '萨尔普斯堡',
    '厄尔格里特': '厄尔格里特', '厄格里特': '厄尔格里特',
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
    '赫尔火花': '赫尔火花', '赫尔辛基火花': '赫尔火花',
    '坦佩雷山猫': '坦佩雷山猫', '坦山猫': '坦佩雷山猫',
    '库奥皮奥': '库奥皮奥',
    '斯达': '斯达', '斯塔贝克': '斯达',
    '维京': '维京',
    # 新增缺失的队名映射
    '阿拉木图': '阿拉木图', '阿拉木图凯拉特': '阿拉木图',
    '索列夫': '索列夫', '索菲亚列夫斯基': '索列夫',
    '里独立': '里独立', '里瓦达维亚独立': '里独立',
    '巴黎圣曼': '巴黎圣曼', '巴黎圣日尔曼': '巴黎圣曼',
    '帕梅拉斯': '帕梅拉斯', '帕尔梅拉斯': '帕梅拉斯',
    '波特诺': '波特诺', '波特诺山丘': '波特诺',
    # === 体彩官方全简称对照表（2026-05/06/07/08月竞彩网通知，长名→SCHEDULE标准名）===
    # 规则：标准名=SCHEDULE当前在用名；API可能返回官方简称或全名，都要能归一到标准名
    # 【瑞超】体彩官方全简称（2026-04-21通知）
    'AIK索尔纳': '索尔纳', '索尔纳': '索尔纳',
    '布鲁马波卡纳': '布鲁马波', '布鲁马': '布鲁马波',  # SCHEDULE标准=布鲁马波（比官方简称多1字，避免"布鲁马"误匹配其他）
    '代格福什': '代格福什', '代格福': '代格福什',
    '佐加顿斯': '佐加顿斯', '佐加顿': '佐加顿斯',
    '埃尔夫斯堡': '埃夫斯堡', '埃尔夫': '埃夫斯堡',  # SCHEDULE标准=埃夫斯堡（之前已修复方向）
    '哥德堡盖斯': '盖斯', '盖斯': '盖斯',
    'IFK哥德堡': '哥德堡', '哥德堡': '哥德堡',
    '哈尔姆斯塔德': '哈尔姆斯', '哈尔姆': '哈尔姆斯',  # SCHEDULE标准=哈尔姆斯
    '马尔默': '马尔默',
    '米亚尔比': '米亚尔比', '米亚尔': '米亚尔比',
    '厄尔格里特': '厄尔格里特', '厄格里': '厄尔格里特',
    '天狼星': '天狼星',
    '韦斯特罗斯': '韦斯特罗', '韦斯罗': '韦斯特罗',
    # 【芬超】体彩官方全简称（2026-04-21通知）
    'AC奥卢': 'AC奥卢',
    '赫尔辛基火花': '赫尔火花', '赫火花': '赫尔火花',
    '赫尔辛基': '赫尔辛基', '赫尔辛': '赫尔辛基',
    '坦佩雷山猫': '坦佩雷山猫', '坦山猫': '坦佩雷山猫',
    '国际图尔库': '国际图', '国际图尔': '国际图', '国际图': '国际图',
    '库奥皮奥': '库奥皮奥', '库奥皮': '库奥皮奥',
    '塞伊奈约基': '塞伊奈', '塞伊奈': '塞伊奈',
    'TPS图尔库': 'TPS图尔', 'TP图尔': 'TPS图尔',
    '瓦萨': '瓦萨',
    # 【葡超】体彩官方全简称（2026-08-04通知）
    '阿尔维卡': '阿尔维卡', '阿维卡': '阿尔维卡',
    '阿马多拉': '阿马多拉', '阿马多': '阿马多拉',
    '卡萨皮亚': '卡萨皮亚', '卡萨': '卡萨皮亚',
    '埃斯托里尔': '埃斯托里', '埃斯托': '埃斯托里',  # SCHEDULE标准=埃斯托里（之前已修复）
    '法马利康': '法马利康', '法马利': '法马利康',
    '吉维森特': '吉维森特', '吉维森': '吉维森特',
    '吉马良斯': '吉马良斯', '吉马良': '吉马良斯',
    '马里迪莫': '马里迪莫', '马里迪': '马里迪莫',
    '摩雷伦斯': '摩雷伦斯', '摩雷伦': '摩雷伦斯',
    '葡萄牙国民': '葡国民',
    '里奥阿维': '里莫', '里奥阿': '里莫',  # SCHEDULE标准=里莫
    '里斯本竞技': '里斯本', '里斯本': '里斯本',
    '圣克拉拉': '圣克拉拉', '圣克拉': '圣克拉拉',
    # 【巴甲】体彩官方全简称（2026-07-14通知）
    '米内罗竞技': '米内罗', '米内罗': '米内罗',
    '巴拉纳竞技': '巴竞技', '巴拉竞': '巴竞技',  # SCHEDULE标准=巴竞技
    '巴伊亚': '巴伊亚',
    '博塔弗戈': '博塔弗戈', '博塔弗': '博塔弗戈',
    '沙佩科恩斯': '沙佩科恩斯', '沙佩科': '沙佩科恩斯',
    '科里蒂巴': '科里蒂巴', '科里蒂': '科里蒂巴',
    '科林蒂安': '科林蒂安', '科林蒂': '科林蒂安',
    '克鲁塞罗': '克鲁塞罗', '克鲁塞': '克鲁塞罗',
    '弗拉门戈': '弗拉门戈', '弗拉门': '弗拉门戈',
    '格雷米奥': '格雷米奥', '格雷米': '格雷米奥',
    '巴西国际': '巴西国际', '巴国际': '巴西国际',
    '米拉索尔': '米拉索尔', '米拉索': '米拉索尔',
    '帕尔梅拉斯': '帕梅拉斯', '帕尔梅': '帕梅拉斯',  # SCHEDULE标准=帕梅拉斯
    '布拉干蒂诺RB': '布拉干蒂诺RB', '布拉RB': '布拉干蒂诺RB',
    '圣保罗': '圣保罗',
    '维多利亚': '维多利亚', '维多利': '维多利亚',
    # 【解放者杯】体彩官方全简称（2026-04-21通知）
    '巴兰基亚青年': '巴兰基亚青年', '巴兰基': '巴兰基亚青年',
    '时刻准备': '时刻准备', '时准备': '时刻准备',
    '瓜亚基尔巴塞罗那': '瓜亚基尔巴塞罗那', '瓜亚基': '瓜亚基尔巴塞罗那',
    '玻利瓦尔': '玻利瓦尔', '玻利瓦': '玻利瓦尔',
    '博卡青年': '博卡青年', '博卡': '博卡青年',
    '普拉滕斯': '普拉滕斯', '普拉滕': '普拉滕斯',
    '科金博联': '科金博联', '科金博': '科金博联',
    '拉瓜伊拉': '拉瓜伊拉', '拉瓜伊': '拉瓜伊拉',
    '托利马体育': '托利马体育', '托利马': '托利马体育',
    '拉普拉塔大学生': '拉普拉塔大学生', '拉大学': '拉普拉塔大学生',
    '德尔瓦耶独立': '德尔瓦耶独立', '德尔瓦': '德尔瓦耶独立',
    '麦德林独立': '麦德林独立', '麦独立': '麦德林独立',
    '圣菲独立': '圣菲独立', '菲独立': '圣菲独立',
    '基多体育大学': '基多体育大学', '基体大': '基多体育大学',
    '亚松森自由': '亚松森自由', '亚自由': '亚松森自由',
    '蒙得维的亚国民': '蒙得维的亚国民', '蒙国民': '蒙得维的亚国民',
    '佩纳罗尔': '佩纳罗尔', '佩纳罗': '佩纳罗尔',
    '罗萨里奥中央': '罗萨里奥中央', '罗萨里': '罗萨里奥中央',
    '水晶体育': '水晶体育', '水晶体': '水晶体育',
    '天主大学': '天主大学', '天主大': '天主大学',
    '大学生体育': '大学生体育', '大体育': '大学生体育',
    '委内瑞拉中央大学': '委内瑞拉中央大学', '中央大': '委内瑞拉中央大学',
    # 【世界杯/国家队】体彩官方全简称（2026-06-02通知）
    '阿尔及利亚': '阿尔及利亚', '阿尔及': '阿尔及利亚',
    '澳大利亚': '澳大利亚', '澳大利': '澳大利亚',
    '哥伦比亚': '哥伦比亚', '哥伦比': '哥伦比亚',
    '厄瓜多尔': '厄瓜多尔', '厄瓜多': '厄瓜多尔',
    '塞内加尔': '塞内加尔', '塞内加': '塞内加尔',
    # === 补充缺失的变体映射（统一到短名，与已完赛赛果 key 一致，避免重复比赛） ===
    # 瑞超：埃夫斯堡/埃尔夫斯堡 统一
    '埃夫斯堡': '埃夫斯堡',
    # 荷甲：鹿斯巴达/鹿特丹斯巴达 统一
    '鹿斯巴达': '鹿斯巴达', '鹿特丹斯巴达': '鹿斯巴达',
    # 葡超：葡国民/葡萄牙国民、埃斯托里/埃斯托里尔 统一
    '葡国民': '葡国民',
    '埃斯托里': '埃斯托里',
    # 英冠：狼队/伍尔弗汉普顿/伍尔弗 统一（API可能返回截断短名"伍尔弗"）
    '狼队': '狼队', '伍尔弗汉普顿': '狼队', '伍尔弗': '狼队',
    # 英超/社区盾：曼城/曼彻斯特城 统一
    '曼城': '曼城', '曼彻斯特城': '曼城',
    # === 从原 TEAM_NAME_MAP 合并的有用变体映射（国家队/联赛，消除变体差异） ===
    '民主刚果': '刚果（金）', '刚果金': '刚果（金）', '刚果(金)': '刚果（金）',
    '乌兹别克': '乌兹别克斯坦', '乌兹别克斯坦': '乌兹别克斯坦',
    '阿尔及利': '阿尔及利亚', '阿尔及利亚': '阿尔及利亚',
    '沙特': '沙特阿拉伯', '沙特阿拉伯': '沙特阿拉伯',
    '贝西克塔斯': '贝西克塔', '斯普利特海杜克': '斯海杜克',
    '安德莱赫特': '安德莱', '费伦茨瓦罗斯': '费伦茨',
    '多伦多FC': '多伦多', '多伦多': '多伦多',
    '利勒斯特罗姆': '利勒斯特', '利勒斯特': '利勒斯特',
    '布鲁马波卡纳': '布鲁马波', '克里蒂安松': '克里斯蒂',
    '莫雷伦斯': '摩雷伦斯', '摩雷伦斯': '摩雷伦斯',
    '奥林匹亚科斯': '奥林匹亚', '布拉格斯巴达': '布斯巴达',
    '阿拉木图凯拉特': '阿拉木图', '索菲亚列夫斯基': '索列夫',
    '里瓦达维亚独立': '里独立', '巴黎圣日尔曼': '巴黎圣曼',
    '帕尔梅拉斯': '帕梅拉斯', '波特诺山丘': '波特诺',
}


def _get_sorted_team_mapping():
    """返回按模式长度从长到短排序的队名映射列表，确保更具体的模式先匹配"""
    return sorted(RESULT_TEAM_NAME_MAP.items(), key=lambda x: len(x[0]), reverse=True)


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

            # 编号信息：jcNum / matchInfoId / matchCode（网易赔率API原生自带）
            jcNum_match = re.search(r'"jcNum"\s*:\s*\[0,\s*"(周[一二三四五六日]\d{3})"', game_block)
            jcNum = jcNum_match.group(1) if jcNum_match else ''
            infoId_match = re.search(r'"matchInfoId"\s*:\s*\[0,\s*(\d+)', game_block)
            matchId = infoId_match.group(1) if infoId_match else ''
            code_match = re.search(r'"matchCode"\s*:\s*\[0,\s*(\d+)', game_block)
            matchCode = code_match.group(1) if code_match else ''
            matchNo_int = 0
            if jcNum and jcNum[2:].isdigit():
                try:
                    matchNo_int = int(jcNum[2:])
                except Exception:
                    matchNo_int = 0

            # 标准化队名，使用 RESULT_TEAM_NAME_MAP 按长度从长到短匹配
            for map_home, standard_home in _get_sorted_team_mapping():
                if map_home in home:
                    home = standard_home
                    break

            for map_away, standard_away in _get_sorted_team_mapping():
                if map_away in away:
                    away = standard_away
                    break

            key = f'{match_date}_{home}_{away}'

            if key not in odds_data:
                odds_data[key] = {'胜': '', '平': '', '负': '', '让球': [], '比分': {}, '总进球': {}, '半全场': {}, 'league': league, 'matchId': matchId or matchCode, 'matchNumStr': jcNum, 'matchNo': matchNo_int}
            else:
                # 同步更新 league / 编号（防止旧数据中为空）
                if not odds_data[key].get('league') and league:
                    odds_data[key]['league'] = league
                if not odds_data[key].get('matchId') and matchId:
                    odds_data[key]['matchId'] = matchId
                if not odds_data[key].get('matchNumStr') and jcNum:
                    odds_data[key]['matchNumStr'] = jcNum
                if not odds_data[key].get('matchNo') and matchNo_int:
                    odds_data[key]['matchNo'] = matchNo_int

            if match_date not in schedule_data:
                schedule_data[match_date] = []
            schedule_entry = {'home': home, 'away': away, 'league': league, 'matchId': matchId or matchCode, 'matchNumStr': jcNum, 'matchNo': matchNo_int}
            if schedule_entry not in schedule_data[match_date]:
                schedule_data[match_date].append(schedule_entry)
            
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

            # 标准化队名（体彩API → 网易），调用全局统一 canonical_team_name
            home = canonical_team_name(home)
            away = canonical_team_name(away)

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

            match_id = str(m.get('matchId', ''))
            match_num_str = m.get('matchNumStr', '')
            match_no = str(m.get('matchNum', ''))

            odds_data[key] = {
                '胜': h,
                '平': d,
                '负': a,
                '让球': [],
                '比分': score_odds,
                '总进球': zjq_odds,
                '半全场': bqc_odds,
                'league': league,
                'matchId': match_id,
                'matchNo': match_no,
                'matchNumStr': match_num_str,
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
                'matchId': match_id,
                'matchNo': match_no,
                'matchNumStr': match_num_str,
            })

    return odds_data, schedule_data


def update_html_schedule(html_content, new_schedule):
    schedule_pattern = r'const SCHEDULE = \{([\s\S]*?)\};'
    
    def sort_key(g):
        """按 matchNumStr 完整编号排序（周几+数字），其次用 matchNo"""
        num_str = g.get('matchNumStr', '')
        if num_str:
            # 提取"周几"前缀和数字部分
            # 例如：周日018 -> ('周日', 18), 周六015 -> ('周六', 15)
            import re as _re
            match = _re.match(r'^(周[一二三四五六日]|周五|周六|周日|周一|周二|周三|周四|周五|周六|周日)(\d+)$', num_str)
            if match:
                prefix = match.group(1)
                num = int(match.group(2))
                # 周几的顺序映射
                weekday_order = {'周五': 0, '周六': 1, '周日': 2, '周一': 3, '周二': 4, '周三': 5, '周四': 6}
                prefix_order = weekday_order.get(prefix, 99)
                return (prefix_order, num)
            # 其他格式，提取所有数字
            digits = _re.findall(r'\d+', num_str)
            if digits:
                return (99, int(digits[0]))
        # 如果有 matchNo，用它
        match_no = g.get('matchNo', '')
        if match_no and match_no.isdigit():
            return (50, int(match_no))
        return (999, 999999)  # 没有编号的排最后
    
    schedule_str = "const SCHEDULE = {\n"
    
    dates = sorted(new_schedule.keys())
    for i, date in enumerate(dates):
        games = new_schedule[date]
        # 按编号排序
        games_sorted = sorted(games, key=sort_key)
        games_parts = []
        for g in games_sorted:
            parts = [f"home: '{g['home']}'", f"away: '{g['away']}'"]
            if g.get('league'):
                parts.append(f"league: '{g['league']}'")
            if g.get('matchId'):
                parts.append(f"matchId: '{g['matchId']}'")
            if g.get('matchNumStr'):
                parts.append(f"matchNumStr: '{g['matchNumStr']}'")
            if g.get('matchNo'):
                parts.append(f"matchNo: '{g['matchNo']}'")
            games_parts.append('{ ' + ', '.join(parts) + ' }')
        games_str = ',\n        '.join(games_parts)
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
        
        extra_parts = []
        if odds.get('matchId'):
            extra_parts.append(f"'matchId': '{odds['matchId']}'")
        if odds.get('matchNumStr'):
            extra_parts.append(f"'matchNumStr': '{odds['matchNumStr']}'")
        if odds.get('matchNo'):
            extra_parts.append(f"'matchNo': '{odds['matchNo']}'")
        extra = ', ' + ', '.join(extra_parts) if extra_parts else ''
        
        comma = ',' if i < len(all_keys) - 1 else ''
        
        odds_str += f"    '{key}': {{ '胜': '{odds['胜']}', '平': '{odds['平']}', '负': '{odds['负']}', '让球': {let_str}, '比分': {score_str}, '总进球': {zjq_str}, '半全场': {bqc_str}{extra} }}{comma}\n"
    
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
        entry = {
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
        # 保留编号信息
        if odds.get('matchId'):
            entry['matchId'] = odds['matchId']
        if odds.get('matchNumStr'):
            entry['matchNumStr'] = odds['matchNumStr']
        if odds.get('matchNo'):
            entry['matchNo'] = odds['matchNo']
        online_data[vs_key] = entry
    
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


def push_to_gh_pages(commit_message='更新赔率数据（网易）', extra_files=None,
                     sync_master_first=True, skip_ghpages=False):
    """
    统一的 master 提交 + gh-pages 静态文件同步工具函数。

    args:
      commit_message: master 分支 commit 信息
      extra_files: 除 index.html / odds_data.json 外，还要 add 的文件列表（比如
                   results_data.json / results_history/* / odds_history/* 等）
      sync_master_first: True=先把本地 master push 到 origin/master（拉取 rebase），
                         False=只 gh-pages 同步（results-only 模式下不做 master commit）
      skip_ghpages: True=只提交/push master，不切 gh-pages（适用于纯 CI 配置或脚本代码改动场景）
    """
    def run_git(*args, _check=False, _allow_nonzero=False):
        cmd = ['git', '--no-pager'] + list(args)
        print(f'\n> git {" ".join(args)}')
        env = os.environ.copy()
        res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, encoding='utf-8', errors='replace', env=env)
        if res.stdout.strip():
            print(res.stdout.rstrip())
        if res.stderr.strip():
            print(res.stderr.rstrip(), file=sys.stderr)
        if _check and res.returncode != 0 and not _allow_nonzero:
            raise RuntimeError(f'git {" ".join(args)} failed ({res.returncode})')
        return res

    # 当前分支必须是 master
    branch_res = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                cwd=BASE_DIR, capture_output=True, encoding='utf-8')
    current_branch = branch_res.stdout.strip()
    if current_branch != 'master':
        print(f'\n[错误] push_to_gh_pages 必须在 master 分支运行，当前：{current_branch}')
        return False

    # --- 第一部分：master 提交 + push ---
    if sync_master_first:
        files = ['index.html', 'odds_data.json']
        if extra_files:
            files.extend(extra_files)
        # 过滤不存在的文件，避免 add 报错
        files = [f for f in files if os.path.exists(os.path.join(BASE_DIR, f))]
        run_git('add', *files)
        r = run_git('commit', '-m', commit_message)
        # "nothing to commit" 不算失败（commit ret 1），继续后面的 push
        if r.returncode == 0:
            print(f'    ✅ 已提交 master commit (msg: {commit_message})')
        else:
            print(f'    ℹ️  无需要提交的改动，或提交失败 (rc={r.returncode})，继续 push master')

        # 普通 push：先 pull --rebase，避免分支分叉；禁止 --force 推 master
        pull = run_git('pull', '--rebase', 'origin', 'master')
        if pull.returncode != 0:
            # rebase 冲突：终止，不要做任何 push，把冲突留给人工
            print('\n[致命错误] master pull --rebase 失败，存在冲突。请人工处理后再同步。')
            # 尝试 abort rebase 让工作区回到可操作状态
            run_git('rebase', '--abort', _allow_nonzero=True)
            return False
        push_master = run_git('push', 'origin', 'master')
        if push_master.returncode != 0:
            print('\n[致命错误] push origin master 失败')
            return False
        print('    ✅ master 已推送到远端')

    if skip_ghpages:
        return True

    # --- 第二部分：gh-pages 静态文件同步（从 master 拷贝文件到 gh-pages 再 commit + push）---
    # 原则：master 改源码 / 配置 / 脚本；gh-pages 只保留可访问静态文件。
    # 绝对禁止把 master 的 HEAD 直接 --force 推到 gh-pages，否则会把脚本/测试/文档暴露给用户访问。
    print('\n--- 同步 gh-pages 生产静态文件 ---')

    # stash 防止切换分支时未暂存改动报错（master 上可能有 odds_history/results_history 新文件）
    stash = run_git('stash', '--include-untracked', _allow_nonzero=True)
    stashed = stash.returncode == 0 and 'No local changes' not in (stash.stdout + stash.stderr)

    switched = run_git('checkout', 'gh-pages')
    if switched.returncode != 0:
        print('\n[致命错误] 切换到 gh-pages 失败')
        if stashed:
            run_git('stash', 'pop', _allow_nonzero=True)
        return False

    # 先 pull --rebase gh-pages
    pull_gh = run_git('pull', '--rebase', 'origin', 'gh-pages')
    if pull_gh.returncode != 0:
        print('\n[致命错误] gh-pages pull --rebase 失败')
        run_git('rebase', '--abort', _allow_nonzero=True)
        run_git('checkout', 'master', _allow_nonzero=True)
        if stashed:
            run_git('stash', 'pop', _allow_nonzero=True)
        return False

    # 从 master 取出允许出现在 gh-pages 的静态文件
    static_assets = [
        'index.html',
        'odds_data.json',
        'results_data.json',
        'favicon.ico', 'favicon.png', 'favicon.svg',
        '.nojekyll',
        'version.txt',
    ]
    # 目录整体复制
    static_dirs = ['predictions/', 'results_history/', 'odds_history/']
    checkout_args = static_assets + static_dirs
    run_git('checkout', 'master', '--', *checkout_args, _allow_nonzero=True)

    # 只 add 上述白名单路径 + 目录内改动，避免 master 中开发文件意外泄露到 gh-pages
    run_git('add', *static_assets)
    for d in static_dirs:
        run_git('add', d.rstrip('/'), _allow_nonzero=True)

    r_commit_gh = run_git('commit', '-m', commit_message)
    if r_commit_gh.returncode == 0:
        print('    ✅ gh-pages commit 完成')
    else:
        print('    ℹ️  gh-pages 无需要提交的改动')

    push_gh = run_git('push', 'origin', 'gh-pages')
    if push_gh.returncode != 0:
        # gh-pages 也禁止 --force；如果 push 失败，让人工介入判断
        print('\n[致命错误] push origin gh-pages 失败')
        run_git('checkout', 'master', _allow_nonzero=True)
        if stashed:
            run_git('stash', 'pop', _allow_nonzero=True)
        return False

    # 回到 master，恢复 stash
    run_git('checkout', 'master')
    if stashed:
        run_git('stash', 'pop', _allow_nonzero=True)

    print(f'\n✅ 已推送更新（master + gh-pages）')
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

    # 去重：清理 SCHEDULE 中可能存在的重复比赛
    dedup_total = 0
    for date in schedule:
        games = schedule[date]
        seen = {}
        deduped = []
        for g in games:
            key = g.get('matchId', '') or f"{g.get('home', '')}_{g.get('away', '')}"
            if key not in seen:
                seen[key] = g
                deduped.append(g)
            else:
                dedup_total += 1
        schedule[date] = deduped
    if dedup_total > 0:
        print(f'  ⚠️ 清理了 {dedup_total} 场重复比赛')

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
    
    # 改进的匹配函数：使用多种策略匹配队名，支持日期约束（在 try 块前定义，确保全局可访问）
    def find_best_match(home, away, id_map_dict, date=None):
        """在 id_map 中查找最佳匹配，可选日期约束"""
        
        # 先标准化输入的队名（使用 RESULT_TEAM_NAME_MAP，按长度从长到短匹配）
        def normalize_team_name(name):
            """标准化队名（按长度从长到短匹配，确保更具体的模式先匹配）"""
            for map_name, standard_name in _get_sorted_team_mapping():
                if map_name in name:
                    return standard_name
            return name
        
        home = normalize_team_name(home)
        away = normalize_team_name(away)
        
        # 策略1：精确匹配（带日期约束）
        for key, ids in id_map_dict.items():
            key_date = key[:10]
            key_home = key[11:].rsplit('_', 1)[0]
            key_away = key[11:].rsplit('_', 1)[1] if '_' in key[11:] else ''
            # 标准化 key 中的队名
            key_home = normalize_team_name(key_home)
            key_away = normalize_team_name(key_away)
            if date and key_date != date:
                continue
            if home == key_home and away == key_away:
                return key, ids
        
        # 策略2：子串包含匹配（带日期约束）
        for key, ids in id_map_dict.items():
            key_date = key[:10]
            key_home = key[11:].rsplit('_', 1)[0]
            key_away = key[11:].rsplit('_', 1)[1] if '_' in key[11:] else ''
            key_home = normalize_team_name(key_home)
            key_away = normalize_team_name(key_away)
            if date and key_date != date:
                continue
            if (home in key_home or key_home in home) and (away in key_away or key_away in away):
                return key, ids
        
        # 策略3：首词匹配（处理"布鲁马波卡纳"vs"布鲁马波"等情况，带日期约束）
        for key, ids in id_map_dict.items():
            key_date = key[:10]
            key_home = key[11:].rsplit('_', 1)[0]
            key_away = key[11:].rsplit('_', 1)[1] if '_' in key[11:] else ''
            key_home = normalize_team_name(key_home)
            key_away = normalize_team_name(key_away)
            if date and key_date != date:
                continue
            # 检查队名是否有相同的前缀（至少2个字符）
            if len(home) >= 2 and len(key_home) >= 2:
                home_match = home[:2] == key_home[:2] or key_home.startswith(home[:2]) or home.startswith(key_home[:2])
            else:
                home_match = home == key_home
            if len(away) >= 2 and len(key_away) >= 2:
                away_match = away[:2] == key_away[:2] or key_away.startswith(away[:2]) or away.startswith(key_away[:2])
            else:
                away_match = away == key_away
            if home_match and away_match:
                return key, ids
        
        # 如果有日期约束但没找到，尝试不限制日期
        if date:
            for key, ids in id_map_dict.items():
                key_home = key[11:].rsplit('_', 1)[0]
                key_away = key[11:].rsplit('_', 1)[1] if '_' in key[11:] else ''
                key_home = normalize_team_name(key_home)
                key_away = normalize_team_name(key_away)
                if home == key_home and away == key_away:
                    return key, ids
            for key, ids in id_map_dict.items():
                key_home = key[11:].rsplit('_', 1)[0]
                key_away = key[11:].rsplit('_', 1)[1] if '_' in key[11:] else ''
                key_home = normalize_team_name(key_home)
                key_away = normalize_team_name(key_away)
                if (home in key_home or key_home in home) and (away in key_away or key_away in away):
                    return key, ids
        
        return None, None
    
    # 从体彩赛果API补充完整的matchId等编号信息（获取所有联赛的完整编号）
    print('\n[补充] 从体彩赛果API获取完整比赛编号信息...')
    id_map = {}  # 在 try 块前初始化，确保 try 块外可访问
    try:
        # 计算日期范围：覆盖当前赛程的所有日期（往前推1天，往后推2天）
        from datetime import datetime, timedelta
        all_dates = set()
        for date in schedule_data.keys():
            all_dates.add(date)
        for date in schedule.keys():
            all_dates.add(date)
        if not all_dates:
            # 如果没有日期，使用最近7天
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        else:
            sorted_dates = sorted(all_dates)
            start_date = sorted_dates[0]
            end_date = sorted_dates[-1]
            # 扩展范围
            start_date = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            end_date = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=2)).strftime('%Y-%m-%d')
        
        print(f'  获取日期范围: {start_date} 至 {end_date}')
        id_map = fetch_match_numbers(start_date, end_date)
        print(f'  赛果API返回 {len(id_map)} 场比赛的编号信息')
        
        # 额外从赔率API获取即将进行比赛的编号（补充赛果API没有的未来比赛）
        try:
            lottery_json = fetch_odds_from_lottery()
            if lottery_json:
                _, lottery_schedule = parse_lottery_json(lottery_json)
                lottery_count = 0
                for ldate, lgames in lottery_schedule.items():
                    for lg in lgames:
                        lkey = f'{ldate}_{lg["home"]}_{lg["away"]}'
                        if lg.get('matchId') and lkey not in id_map:
                            id_map[lkey] = {
                                'matchId': lg['matchId'],
                                'matchNumStr': lg.get('matchNumStr', ''),
                                'matchNo': lg.get('matchNo', ''),
                                'home': lg['home'],
                                'away': lg['away'],
                                'league': lg.get('league', '')
                            }
                            lottery_count += 1
                if lottery_count:
                    print(f'  赔率API补充 {lottery_count} 场即将进行比赛的编号')
        except Exception as e:
            print(f'  ⚠️ 赔率API获取编号失败: {e}')
        
        print(f'  合并后共 {len(id_map)} 场比赛的编号信息')
        
        # 调试：显示一些 id_map 和 odds_data 的 key
        if id_map:
            print(f'  id_map 示例 key: {list(id_map.keys())[:3]}')
        if odds_data:
            print(f'  odds_data 示例 key: {list(odds_data.keys())[:3]}')
        
        # 合并到 odds_data
        matched_odds = 0
        for key, ids in id_map.items():
            if key in odds_data:
                odds_data[key]['matchId'] = ids.get('matchId', '')
                odds_data[key]['matchNumStr'] = ids.get('matchNumStr', '')
                odds_data[key]['matchNo'] = ids.get('matchNo', '')
                if ids.get('league') and not odds_data[key].get('league'):
                    odds_data[key]['league'] = ids['league']
                matched_odds += 1
        
        # 如果精确匹配的少，尝试用模糊匹配
        if matched_odds < len(odds_data) * 0.5:
            for okey in odds_data:
                if not odds_data[okey].get('matchId'):
                    parts = okey.split('_', 2)
                    if len(parts) == 3:
                        o_home, o_away = parts[1], parts[2]
                        mkey, mids = find_best_match(o_home, o_away, id_map)
                        if mkey and mids:
                            odds_data[okey]['matchId'] = mids.get('matchId', '')
                            odds_data[okey]['matchNumStr'] = mids.get('matchNumStr', '')
                            odds_data[okey]['matchNo'] = mids.get('matchNo', '')
                            if mids.get('league') and not odds_data[okey].get('league'):
                                odds_data[okey]['league'] = mids['league']
                            matched_odds += 1
        
        # 合并到 schedule_data
        matched_schedule = 0
        for sdate, games in schedule_data.items():
            for sg in games:
                # 尝试用模糊匹配查找编号
                mkey, mids = find_best_match(sg['home'], sg['away'], id_map)
                if mkey and mids:
                    sg['matchId'] = mids.get('matchId', '')
                    sg['matchNumStr'] = mids.get('matchNumStr', '')
                    sg['matchNo'] = mids.get('matchNo', '')
                    if mids.get('league') and not sg.get('league'):
                        sg['league'] = mids['league']
                    matched_schedule += 1
        
        print(f'  ✅ 已补充 {matched_odds} 场赔率、{matched_schedule} 场赛程的编号信息')
    except Exception as e:
        import traceback
        print(f'  ⚠️ 获取编号信息失败: {e}')
        traceback.print_exc()
    
    print('\n[2.5/3] 合并赛程与赔率数据...')
    print(f'    原有赛程: {len(schedule)} 个日期')
    print(f'    新增赛程: {len(schedule_data)} 个日期')

    # 标准化现有赛程中的队名（所有路径统一使用全局 canonical_team_name）
    # 标准化现有 schedule 中的队名
    for date in schedule:
        for g in schedule[date]:
            g['home'] = canonical_team_name(g['home'])
            g['away'] = canonical_team_name(g['away'])
    
    # 标准化 schedule_data 中的队名
    for date in schedule_data:
        for g in schedule_data[date]:
            g['home'] = canonical_team_name(g['home'])
            g['away'] = canonical_team_name(g['away'])
    
    print('    已标准化所有队名 (canonical_team_name 全局统一)')
    
    # 合并新旧赛程（追加新比赛，保留已有比赛，避免覆盖丢失）
    for date, games in schedule_data.items():
        if date not in schedule:
            schedule[date] = games
        else:
            # 去重：matchId 优先，其次使用 canonical pair（归一化队名的无序对），避免别名漏网
            existing_match_ids = set(g.get('matchId', '') for g in schedule[date] if g.get('matchId'))
            existing_canonical_pairs = set()
            for g in schedule[date]:
                c_home = canonical_team_name(g['home'])
                c_away = canonical_team_name(g['away'])
                existing_canonical_pairs.add((c_home, c_away))
                existing_canonical_pairs.add((c_away, c_home))  # 无序对，兼容主客写反情况
            for g in games:
                g_match_id = g.get('matchId', '')
                c_home = canonical_team_name(g['home'])
                c_away = canonical_team_name(g['away'])
                canon_pair = (c_home, c_away)
                canon_pair_rev = (c_away, c_home)
                if g_match_id and g_match_id in existing_match_ids:
                    continue
                if canon_pair in existing_canonical_pairs or canon_pair_rev in existing_canonical_pairs:
                    continue
                schedule[date].append(g)
                existing_canonical_pairs.add(canon_pair)
                existing_canonical_pairs.add(canon_pair_rev)
                if g_match_id:
                    existing_match_ids.add(g_match_id)
    
    # 合并后去重（清理可能存在的重复）
    dedup_total = 0
    for date in schedule:
        games = schedule[date]
        seen_ids = set()
        seen_canonical_pairs = set()
        deduped = []
        for g in games:
            g_match_id = g.get('matchId', '')
            c_home = canonical_team_name(g['home'])
            c_away = canonical_team_name(g['away'])
            canon_pair = (c_home, c_away) if c_home <= c_away else (c_away, c_home)
            # 优先用 matchId 去重
            if g_match_id and g_match_id in seen_ids:
                dedup_total += 1
                continue
            # 其次用 canonical 无序 pair 去重（消除队名别名/写法差异造成的重复）
            if canon_pair in seen_canonical_pairs:
                dedup_total += 1
                continue
            if g_match_id:
                seen_ids.add(g_match_id)
            seen_canonical_pairs.add(canon_pair)
            deduped.append(g)
        schedule[date] = deduped
    if dedup_total > 0:
        print(f'    ⚠️ 合并后清理了 {dedup_total} 场重复比赛 (canonical pair 去重)')
    
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

    # P0-2：canonical 清洗 merged_odds 的 key（队名变体归一化 + 同方向去重）
    # 旧 index.html 可能残留 "国际图尔" / "IFK哥德堡" / "布鲁马波卡纳" 等非标准队名 key，
    # 需重算 canonical key 并合并到标准 key，避免 ODDS 字典里出现重复条目污染前端展示。
    canon_dedup_count = 0
    canon_merged = {}
    for old_key, odds in merged_odds.items():
        parts = old_key.split('_', 2)
        if len(parts) < 3:
            canon_merged[old_key] = odds
            continue
        date, home, away = parts
        c_home = canonical_team_name(home)
        c_away = canonical_team_name(away)
        new_key = f'{date}_{c_home}_{c_away}'
        if new_key == old_key:
            canon_merged.setdefault(new_key, odds)
            continue
        # key 发生变化 → 合并到 canonical key（优先保留有赔率值/matchId 的条目）
        if new_key in canon_merged:
            existing = canon_merged[new_key]
            existing_has_data = bool(existing.get('胜') or existing.get('matchId'))
            new_has_data = bool(odds.get('胜') or odds.get('matchId'))
            if new_has_data and not existing_has_data:
                canon_merged[new_key] = {**existing, **odds}
            else:
                # 字段级补全
                for k, v in odds.items():
                    if k not in existing or not existing[k]:
                        existing[k] = v
        else:
            canon_merged[new_key] = odds
        canon_dedup_count += 1
    if canon_dedup_count:
        print(f'    [CLEAN] canonical 归一化 {canon_dedup_count} 条队名变体 key')
    merged_odds = canon_merged
    print(f'    合并后赔率（canonical 归一化）: {len(merged_odds)} 条')

    # P0-1：过滤 matchNumStr 星期与 key 中 date 实际星期不一致的残留错日期条目
    # 对应前端 v7.100.4 的 updateScheduleFromOdds 星期校验，双端一致避免脏数据累积
    bad_keys = []
    for key in list(merged_odds.keys()):
        match_odds = merged_odds[key]
        match_num_str = match_odds.get('matchNumStr') if isinstance(match_odds, dict) else None
        if not match_num_str:
            continue
        key_date = key.split('_', 1)[0]
        if not is_weekday_match(key_date, match_num_str):
            bad_keys.append((key, match_num_str))
    if bad_keys:
        for k, mn in bad_keys:
            print(f'    [CLEAN] 丢弃错日期赔率 key: {k} (matchNumStr={mn})')
            merged_odds.pop(k, None)
        print(f'    [CLEAN] 合计丢弃错日期残留: {len(bad_keys)} 条')

    print(f'    合并后赔率（已过滤错日期）: {len(merged_odds)} 条')

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

    # 对 matched_odds 中的所有条目补充编号信息（从 id_map）
    print('\n[补充] 为所有赔率补充编号信息...')
    id_added = 0
    for key in matched_odds:
        if not matched_odds[key].get('matchId'):
            parts = key.split('_', 2)
            if len(parts) == 3:
                mdate, mhome, maway = parts[0], parts[1], parts[2]
                mkey, mids = find_best_match(mhome, maway, id_map, date=mdate)
                if mkey and mids:
                    matched_odds[key]['matchId'] = mids.get('matchId', '')
                    matched_odds[key]['matchNumStr'] = mids.get('matchNumStr', '')
                    matched_odds[key]['matchNo'] = mids.get('matchNo', '')
                    if mids.get('league') and not matched_odds[key].get('league'):
                        matched_odds[key]['league'] = mids['league']
                    id_added += 1
    print(f'  ✅ 为 {id_added} 场赔率补充了编号信息')

    # 对 schedule 中的所有条目补充编号信息
    print('\n[补充] 为所有赛程补充编号信息...')
    s_id_added = 0
    s_date_fixed = 0
    weekday_map = {'周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6}
    
    dates_to_remove = {}  # 记录需要移动的比赛
    
    for sdate, games in schedule.items():
        for game in games:
            # 补充编号信息（如果没有 matchId）
            if not game.get('matchId'):
                mkey, mids = find_best_match(game['home'], game['away'], id_map, date=sdate)
                if mkey and mids:
                    game['matchId'] = mids.get('matchId', '')
                    game['matchNumStr'] = mids.get('matchNumStr', '')
                    game['matchNo'] = mids.get('matchNo', '')
                    if mids.get('league') and not game.get('league'):
                        game['league'] = mids['league']
                    s_id_added += 1
            
            # 根据 matchNumStr 修正日期（无论是否已有 matchId）
            match_num_str = game.get('matchNumStr', '')
            if match_num_str and sdate:
                new_date = get_label_date_from_match_num(sdate, match_num_str)
                if new_date != sdate:
                    dates_to_remove.setdefault(sdate, []).append((game, new_date))
                    s_date_fixed += 1
    
    # 执行日期修正（移动比赛到正确的日期）
    for old_date, moves in dates_to_remove.items():
        if old_date in schedule:
            new_date_games = {}
            games = schedule[old_date]
            new_games = []
            for g in games:
                moved = False
                for game, new_date in moves:
                    if g is game:
                        if new_date not in new_date_games:
                            new_date_games[new_date] = []
                        new_date_games[new_date].append(g)
                        moved = True
                        break
                if not moved:
                    new_games.append(g)
            schedule[old_date] = new_games
            for new_date, new_games_list in new_date_games.items():
                if new_date not in schedule:
                    schedule[new_date] = []
                schedule[new_date].extend(new_games_list)
    
    print(f'  ✅ 为 {s_id_added} 场赛程补充了编号信息')
    if s_date_fixed > 0:
        print(f'  ✅ 修正了 {s_date_fixed} 场比赛的日期')

    # 用 id_map 数据补充 schedule 中缺失的历史比赛条目
    print('\n[补充] 从赛果API补充缺失的赛程条目...')
    new_added = 0
    dup_by_id = 0
    dup_by_name = 0
    dup_by_substr = 0
    for key, ids in id_map.items():
        id_date = key[:10]
        rest = key[11:]
        # 找到第一个下划线（第一个下划线分隔主队和客队）
        idx = rest.find('_')
        if idx > 0:
            id_home = rest[:idx]
            id_away = rest[idx+1:]
        else:
            id_home = rest
            id_away = ''
        id_match_id = ids.get('matchId', '')
        # id_map 中的队名同样走 canonical 归一化，避免与 schedule 中别名无法对上
        c_id_home = canonical_team_name(id_home)
        c_id_away = canonical_team_name(id_away)
        id_canon_pair = (c_id_home, c_id_away) if c_id_home <= c_id_away else (c_id_away, c_id_home)

        # 检查是否已在 schedule 中（matchId 优先，其次 canonical pair，最后精确匹配+子串）
        exists = False
        if id_date in schedule:
            for g in schedule[id_date]:
                g_match_id = g.get('matchId', '')
                # 优先用 matchId 去重（两者都有 matchId 时）
                if id_match_id and g_match_id and id_match_id == g_match_id:
                    exists = True
                    dup_by_id += 1
                    break
                # 其次用 canonical pair（无序）匹配，彻底消除别名差异
                c_g_home = canonical_team_name(g['home'])
                c_g_away = canonical_team_name(g['away'])
                g_canon_pair = (c_g_home, c_g_away) if c_g_home <= c_g_away else (c_g_away, c_g_home)
                if g_canon_pair == id_canon_pair and c_id_home and c_id_away:
                    exists = True
                    dup_by_name += 1
                    break
                # 再用精确匹配（原文相同的快速路径，已被 canonical 覆盖但保留用于统计）
                if g['home'] == id_home and g['away'] == id_away:
                    exists = True
                    dup_by_name += 1
                    break
                # 最后用子串匹配
                if (id_home and id_away) and \
                   (id_home in g['home'] or g['home'] in id_home) and \
                   (id_away in g['away'] or g['away'] in id_away):
                    exists = True
                    dup_by_substr += 1
                    break
        
        if not exists:
            # 添加到 schedule
            if id_date not in schedule:
                schedule[id_date] = []
            schedule[id_date].append({
                'home': id_home,
                'away': id_away,
                'league': ids.get('league', ''),
                'matchId': id_match_id,
                'matchNumStr': ids.get('matchNumStr', ''),
                'matchNo': ids.get('matchNo', ''),
            })
            new_added += 1
            # 同步添加到 matched_odds
            if key not in matched_odds:
                matched_odds[key] = {
                    '胜': '', '平': '', '负': '',
                    '让球': [], '比分': {}, '总进球': {}, '半全场': {},
                    'matchId': ids.get('matchId', ''),
                    'matchNumStr': ids.get('matchNumStr', ''),
                    'matchNo': ids.get('matchNo', ''),
                    'league': ids.get('league', ''),
                }
    if new_added:
        print(f'  ✅ 新增 {new_added} 场比赛到赛程')
        print(f'     去重: matchId={dup_by_id}, 队名={dup_by_name}, 子串={dup_by_substr}')
    else:
        print(f'  所有比赛已在赛程中，无需新增')

    # 最终去重：清理所有重复的比赛（canonical pair + matchId 双层去重）
    final_dedup = 0
    for date in schedule:
        games = schedule[date]
        seen_ids = set()
        seen_canonical_pairs = set()
        deduped = []
        has_dup_in_date = False

        # 调试：检查是否有比赛有 matchId
        has_match_id = sum(1 for g in games if g.get('matchId', ''))
        if date == '2026-08-09':
            print(f'    [DEBUG] {date}: {len(games)} 场比赛, {has_match_id} 场有 matchId')

        for g in games:
            g_match_id = g.get('matchId', '')
            c_home = canonical_team_name(g['home'])
            c_away = canonical_team_name(g['away'])
            canon_pair = (c_home, c_away) if c_home <= c_away else (c_away, c_home)
            # 优先用 matchId 去重
            if g_match_id and g_match_id in seen_ids:
                final_dedup += 1
                has_dup_in_date = True
                if date == '2026-08-09':
                    print(f'    [DEBUG] 发现重复: matchId={g_match_id}, {g["home"]} vs {g["away"]}')
                continue
            # 其次用 canonical 无序 pair 去重（消除别名差异）
            if canon_pair in seen_canonical_pairs:
                final_dedup += 1
                has_dup_in_date = True
                if date == '2026-08-09':
                    print(f'    [DEBUG] 发现重复: canon_pair={canon_pair} (原文 {g["home"]} vs {g["away"]})')
                continue
            if g_match_id:
                seen_ids.add(g_match_id)
            seen_canonical_pairs.add(canon_pair)
            deduped.append(g)
        if has_dup_in_date:
            print(f'    {date}: {len(games)} -> {len(deduped)} 场 (移除 {len(games) - len(deduped)} 场重复, canonical 去重)')
        schedule[date] = deduped
    if final_dedup > 0:
        print(f'\n[最终去重] 清理了 {final_dedup} 场重复比赛 (canonical pair)')
    else:
        print(f'\n[最终去重] 未发现重复比赛')

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
        # 赔率阶段只推 master commit + gh-pages 静态文件拷贝
        push_to_gh_pages(
            commit_message='更新赔率数据（网易）',
            extra_files=['results_data.json', 'results_history/', 'odds_history/'],
            sync_master_first=True,
            skip_ghpages=False,
        )
    
    print('\n' + '=' * 60)
    print('  赔率更新完成！')
    print('=' * 60)


# === 赛果抓取 ===

def fetch_match_numbers(start_date, end_date):
    """从体彩赛果API获取完整的比赛编号信息（含所有联赛），返回 {key: {matchId, matchNumStr, matchNo, home, away, league}}"""
    import time
    from datetime import datetime, timedelta
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.sporttery.cn/jc/zqsgkj/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    
    id_map = {}
    page = 1
    total = None
    
    while True:
        url = (
            f'https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'
            f'?matchBeginDate={start_date}&matchEndDate={end_date}'
            f'&leagueId=&pageSize=50&pageNo={page}&isFix=0&matchPage=1&pcOrWap=1'
        )
        
        page_data = None
        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    page_data = json.loads(resp.read().decode('utf-8'))
                break
            except Exception as e:
                if attempt < 3:
                    time.sleep(attempt * 3)
                else:
                    print(f'  [警告] 获取编号第{page}页失败: {e}')
                    return id_map
        
        if not page_data or not page_data.get('success'):
            break
        
        value = page_data.get('value', {})
        matches = value.get('matchResult', [])
        if not matches:
            break
        
        for m in matches:
            home = m.get('homeTeam', '')
            away = m.get('awayTeam', '')
            if not home or not away:
                continue
            
            # 清理队名中的联赛排名标记
            home = re.sub(r'\[[^\]]+\]', '', home).strip()
            away = re.sub(r'\[[^\]]+\]', '', away).strip()
            
            match_date = m.get('matchDate', '')[:10]
            match_id = str(m.get('matchId', ''))
            match_num_str = m.get('matchNumStr', '') or m.get('matchNum', '')
            match_no = str(m.get('matchNo', ''))
            league = m.get('leagueNameAbbr', '') or m.get('leagueName', '')
            
            # 根据 matchNumStr 修正日期（体彩编号中的"周几"表示比赛所属日期）
            # 比赛可能跨天（深夜→凌晨），matchDate 可能比编号日期晚一天，需往前修正
            match_date = get_label_date_from_match_num(match_date, match_num_str)
            
            # 标准化队名（按长度从长到短匹配，确保更具体的模式先匹配）
            for map_name, standard_name in _get_sorted_team_mapping():
                if map_name in home:
                    home = standard_name
                    break
            for map_name, standard_name in _get_sorted_team_mapping():
                if map_name in away:
                    away = standard_name
                    break
            
            key = f'{match_date}_{home}_{away}'
            if key not in id_map:
                id_map[key] = {
                    'matchId': match_id,
                    'matchNumStr': match_num_str,
                    'matchNo': match_no,
                    'home': home,
                    'away': away,
                    'league': league
                }
        
        # 检查是否还有更多页
        if total is None:
            total = value.get('total', 0)
        if page * 50 >= total:
            break
        page += 1
    
    return id_map


def fetch_163_results(days_back=7):
    """
    网易竞彩足球赛果主源：通过 jczq 页日期筛选 input 触发的 API 接口抓取多日历史赛果。
    API: https://sports.163.com/caipiao/api/web/match/list/jingcai/matchList/1?days=YYYY-MM-DD HH:MM:SS
    days 参数对应 jczq 页日期筛选 input，按"投注周期日"返回该日及次日在售/已售场次，
    包含全部已完赛场次的 jcNum / league / matchId / score / halfScore / playMap 赔率。

    周日 001-0** 编号比赛可能部分周日完赛、部分周一凌晨完赛（matchTime 落在周一），
    但 jcNum 前缀仍为"周日"，投注周期日仍为周日。本函数遍历过去 days_back 天逐日调用 API
    并按 jcNum 去重，确保跨天完赛的周日比赛也能被完整捕获。
    key 日期推算：优先用 matchTime（开赛时间，Unix 毫秒，北京时间），
      - 若 matchTime 的 weekday == jcNum 前缀的 weekday → key 日期 = matchTime 日期
      - 否则（matchTime 落在次日凌晨，如周日022 实际 8-17 01:00 开赛）→ key 日期 = matchTime 日期 - 1 天
    matchTime 缺失时用 jcNum 前缀推算最近过去的同周X日期作兜底。

    参数:
      days_back: 回溯天数，默认 7（CI 日常使用）。传入 228+ 可回填 2026 全年历史数据。

    每条结果自包含：score/halfScore/fullScore/handicap/胜/平/负/hda胜/hda平/hda负/winFlag
    返回格式与 parse_results_json 一致: {key: result_entry}
    """
    import urllib.request, urllib.parse, json
    from datetime import datetime, timedelta, timezone

    beijing_tz = timezone(timedelta(hours=8))
    today = datetime.now(beijing_tz)
    today_wd = today.weekday()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'application/json,text/plain,*/*',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept-Encoding': 'identity',
        'Referer': 'https://sports.163.com/caipiao/match/football/jczq',
    }

    # 遍历过去 days_back 天（含今日），逐日调用 API；
    # 去重注意：jcNum 在不同周次会复用（如8-9周日017 和 8-16周日017 是不同比赛），
    # 必须用 (jcNum, matchInfoId) 或 (jcNum, 投注周期日) 联合去重，否则早期数据会被近期覆盖。
    all_matches = {}
    for d_back in range(days_back):
        day_dt = today - timedelta(days=d_back)
        days_val = day_dt.strftime('%Y-%m-%d') + ' 12:00:00'
        url = 'https://sports.163.com/caipiao/api/web/match/list/jingcai/matchList/1?days=' + urllib.parse.quote(days_val)
        try:
            req = urllib.request.Request(url, data=b'', headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode('utf-8', errors='ignore')
            data = json.loads(raw)
            day_matches = data.get('data', []) or []
        except Exception as e:
            print(f'  ⚠️ 网易赛果API请求失败 (days={days_val}): {e}')
            continue
        for m in day_matches:
            jcNum = m.get('jcNum', '')
            if not jcNum:
                continue
            # 用 (jcNum, matchInfoId) 联合去重，同一比赛可能在相邻日的API响应中重复
            mid = str(m.get('matchInfoId') or m.get('matchCode') or '')
            dedup_key = (jcNum, mid) if mid else jcNum
            if dedup_key not in all_matches:
                all_matches[dedup_key] = m

    print(f'  🎯 网易API赛果: 累计解析到 {len(all_matches)} 场唯一比赛 ((jcNum,matchId) 去重，过去{days_back}日)')

    # 周几汉字 -> weekday int (0=周一 ... 6=周日)
    weekday_map = {'周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6}
    matches = {}

    for dedup_key, m in all_matches.items():
        # all_matches 的 key 是 (jcNum, matchId) tuple 或裸 jcNum 字符串，统一解出 jcNum
        jcNum = dedup_key[0] if isinstance(dedup_key, tuple) else dedup_key
        # 仅保留已完赛：matchStatus==3 且 footballLiveScore.status=='完'
        matchStatus = m.get('matchStatus', -1)
        live_score = m.get('footballLiveScore') or {}
        live_status = live_score.get('status', '')
        if not (matchStatus == 3 and live_status == '完'):
            continue

        # 队名（统一走 canonical_team_name 归一化，确保 key 与 SCHEDULE/历史赛果一致）
        home = canonical_team_name((m.get('homeTeam') or {}).get('teamName', '') or '')
        away = canonical_team_name((m.get('guestTeam') or {}).get('teamName', '') or '')
        if not home or not away:
            continue

        # 比分（全场 + 半场）
        homeScore = live_score.get('homeScore', 0) or 0
        guestScore = live_score.get('guestScore', 0) or 0
        homeHalf = live_score.get('homeHalfScore', 0) or 0
        guestHalf = live_score.get('guestHalfScore', 0) or 0
        half_score = f"{homeHalf}:{guestHalf}"
        full_score = f"{homeScore}:{guestScore}"
        # 胜负标志：H=主胜 D=平 A=客胜（与历史 sporttery 格式一致）
        if homeScore > guestScore:
            win_flag = 'H'
        elif homeScore < guestScore:
            win_flag = 'A'
        else:
            win_flag = 'D'

        # 联赛与比赛ID
        league = (m.get('leagueMatch') or {}).get('leagueName', '') or ''

        # 让球赔率：从 playMap 提取 HHDA（让球胜平负）+ HDA（不让球胜平负）
        # playMap.HHDA: {concede: "+1"/"-1"/"0", playItemList: [{W:主胜}, {D:平}, {L:客胜}]}
        # playMap.HDA: 同结构但 concede 固定为 "0"
        play_map = m.get('playMap') or {}
        handicap = ''
        rq_win = rq_draw = rq_loss = ''
        hda_win = hda_draw = hda_loss = ''
        bf_odds = {}   # 比分: { "1:0": 21, "胜其他": 80, ... }
        zjq_odds = {}  # 总进球: { "0": 25, "1": 7.8, ..., "7+": 14 }
        bqc_odds = {}  # 半全场: { "胜胜": 8.25, "平平": 8.1, ... }
        hhda = play_map.get('HHDA') or {}
        if hhda:
            handicap = str(hhda.get('concede', '') or '')
            items = hhda.get('playItemList') or []
            for it in items:
                code = it.get('playItemCode', '')
                odds_val = it.get('odds', 0)
                if code == 'W':
                    rq_win = odds_val
                elif code == 'D':
                    rq_draw = odds_val
                elif code == 'L':
                    rq_loss = odds_val
        hda = play_map.get('HDA') or {}
        if hda:
            items = hda.get('playItemList') or []
            for it in items:
                code = it.get('playItemCode', '')
                odds_val = it.get('odds', 0)
                if code == 'W':
                    hda_win = odds_val
                elif code == 'D':
                    hda_draw = odds_val
                elif code == 'L':
                    hda_loss = odds_val
        # 比分 FBF：playItemName = "1:0" / "胜其他" 等体彩标准命名
        fbf = play_map.get('FBF') or {}
        if fbf:
            for it in fbf.get('playItemList') or []:
                name = it.get('playItemName', '')
                odds_val = it.get('odds', 0)
                if name and odds_val and isinstance(odds_val, (int, float)) and odds_val > 0:
                    bf_odds[name] = float(odds_val)
        # 总进球 FJQ：playItemName = "0"~"7+"
        fjq = play_map.get('FJQ') or {}
        if fjq:
            for it in fjq.get('playItemList') or []:
                name = it.get('playItemName', '')
                odds_val = it.get('odds', 0)
                if name and odds_val and isinstance(odds_val, (int, float)) and odds_val > 0:
                    zjq_odds[name] = float(odds_val)
        # 半全场 FBQC：playItemName = "胜胜" / "胜平" 等
        fbqc = play_map.get('FBQC') or {}
        if fbqc:
            for it in fbqc.get('playItemList') or []:
                name = it.get('playItemName', '')
                odds_val = it.get('odds', 0)
                if name and odds_val and isinstance(odds_val, (int, float)) and odds_val > 0:
                    bqc_odds[name] = float(odds_val)
        matchId = str(m.get('matchInfoId') or m.get('matchCode') or '')

        # key 日期推算（投注周期日）：
        # 优先用 matchTime，处理跨天完赛（周日022 实际周一 01:00 开赛 → key 日期 = 周日 8-16）
        prefix_cn = jcNum[:2]
        target_wd = weekday_map.get(prefix_cn)
        match_time_ms = m.get('matchTime')
        date_str = None
        if match_time_ms:
            try:
                kick_dt = datetime.fromtimestamp(match_time_ms / 1000.0, tz=beijing_tz)
                kick_wd = kick_dt.weekday()
                if target_wd is not None and kick_wd != target_wd:
                    # matchTime 落在次日凌晨，投注周期日为前一天
                    cycle_dt = kick_dt - timedelta(days=1)
                else:
                    cycle_dt = kick_dt
                date_str = cycle_dt.strftime('%Y-%m-%d')
            except Exception:
                date_str = None
        if not date_str:
            # 兜底：jcNum 前缀推算最近过去的同周X日期
            if target_wd is None:
                date_str = today.strftime('%Y-%m-%d')
            else:
                diff_back = (today_wd - target_wd) % 7
                date_str = (today - timedelta(days=diff_back)).strftime('%Y-%m-%d')

        # matchNo
        num_part = jcNum[2:] if len(jcNum) > 2 else ''
        try:
            matchNo_int = int(num_part) if num_part.isdigit() else 0
        except Exception:
            matchNo_int = 0

        key = f"{date_str}_{home}_{away}"
        if key in matches:
            continue
        score = full_score

        # 反序：让球符号取反（提前计算，rev_key 分支及 rev_rq_list 均用到）
        rev_handicap = handicap
        if handicap:
            try:
                h_int = int(handicap)
                if h_int > 0:
                    rev_handicap = str(-h_int)         # +1 → -1
                elif h_int < 0:
                    rev_handicap = '+' + str(-h_int)   # -1 → +1
                else:
                    rev_handicap = '0'
            except Exception:
                rev_handicap = handicap
        # 胜负标志 H/A 对调，D 不变（提前计算）
        rev_win_flag = 'A' if win_flag == 'H' else ('H' if win_flag == 'A' else 'D')

        # 让球数组结构（正序）：若 handicap 非 0 且有 rq 三项则生成单元素数组
        rq_list = []
        if handicap and str(handicap) != '0' and rq_win and rq_draw and rq_loss:
            rq_list = [{
                'handicap': str(handicap),
                '胜': float(rq_win) if isinstance(rq_win, (int, float)) and rq_win > 0 else rq_win,
                '平': float(rq_draw) if isinstance(rq_draw, (int, float)) and rq_draw > 0 else rq_draw,
                '负': float(rq_loss) if isinstance(rq_loss, (int, float)) and rq_loss > 0 else rq_loss,
            }]
        # 反序让球数组：让球符号取反，胜/负赔率对调
        rev_rq_list = []
        if rev_handicap and str(rev_handicap) != '0' and rq_win and rq_draw and rq_loss:
            rev_rq_list = [{
                'handicap': str(rev_handicap),
                '胜': float(rq_loss) if isinstance(rq_loss, (int, float)) and rq_loss > 0 else rq_loss,
                '平': float(rq_draw) if isinstance(rq_draw, (int, float)) and rq_draw > 0 else rq_draw,
                '负': float(rq_win) if isinstance(rq_win, (int, float)) and rq_win > 0 else rq_win,
            }]
        # 反序比分、总进球、半全场：比分对调（W↔L，"胜其他"↔"负其他"）
        rev_bf_odds = {}
        for score, v in bf_odds.items():
            if score in ('胜其他', '平其他', '负其他'):
                rev_score = '负其他' if score == '胜其他' else ('胜其他' if score == '负其他' else '平其他')
            elif ':' in score:
                try:
                    a, b = score.split(':')
                    rev_score = f"{b}:{a}"
                except Exception:
                    rev_score = score
            else:
                rev_score = score
            rev_bf_odds[rev_score] = v
        # 反序半全场：首位对调（胜胜→负负，胜平→负平，胜负→负胜，平胜→平负，平平→平平，平负→平胜，负胜→胜负，负平→胜平，负负→胜胜）
        rev_bqc_odds = {}
        _bqc_map = {'胜胜':'负负','胜平':'负平','胜负':'负胜','平胜':'平负','平平':'平平','平负':'平胜','负胜':'胜负','负平':'胜平','负负':'胜胜'}
        for k, v in bqc_odds.items():
            rev_bqc_odds[_bqc_map.get(k, k)] = v
        # 总进球不涉及主客，rev=直接复制
        rev_zjq_odds = dict(zjq_odds)

        # 完整赛果条目：兼容新格式（score/halfScore）与历史 sporttery 格式（fullScore/handicap/胜/平/负/winFlag/leagueAbbr）
        # 注意：顶层「胜/平/负」 = 体彩标准"胜平负(让球0)"赔率 = HDA，前端 SPF 0行使用；
        #       让球胜平负应放在「让球: [{handicap,胜,平,负}, ...]」数组中，对应 HHDA。
        result_entry = {
            'home': home,
            'away': away,
            'score': score,
            'halfScore': half_score,
            'fullScore': score,
            'winFlag': win_flag,
            'handicap': handicap,
            'league': league,
            'leagueAbbr': league,
            'matchId': matchId,
            'matchNumStr': jcNum,
            'matchNo': matchNo_int,
            'status': '2',
            '胜': hda_win,  # 普通胜平负 = HDA (让球0)
            '平': hda_draw,
            '负': hda_loss,
            'hda胜': hda_win,
            'hda平': hda_draw,
            'hda负': hda_loss,
            'hhda胜': rq_win,  # 让球胜平负 = HHDA (具体 handicap 数字)
            'hhda平': rq_draw,
            'hhda负': rq_loss,
            '让球': rq_list,
            '比分': bf_odds,
            '总进球': zjq_odds,
            '半全场': bqc_odds,
        }
        matches[key] = result_entry
        # 主客场反序双写（SCHEDULE 的主客场顺序可能和网易页面相反）
        rev_key = f"{date_str}_{away}_{home}"
        if rev_key not in matches and rev_key != key:
            matches[rev_key] = {
                'home': away,
                'away': home,
                'score': f"{guestScore}:{homeScore}",
                'halfScore': half_score,
                'fullScore': f"{guestScore}:{homeScore}",
                'winFlag': rev_win_flag,
                'handicap': rev_handicap,
                'league': league,
                'leagueAbbr': league,
                'matchId': matchId,
                'matchNumStr': jcNum,
                'matchNo': matchNo_int,
                'status': '2',
                '胜': hda_loss,  # 反序后主胜 = 原普通客胜 (HDA)
                '平': hda_draw,
                '负': hda_win,   # 反序后主负 = 原普通主胜 (HDA)
                'hda胜': hda_loss,
                'hda平': hda_draw,
                'hda负': hda_win,
                'hhda胜': rq_loss,   # 反序后让球主胜 = 原让球客胜
                'hhda平': rq_draw,
                'hhda负': rq_win,
                '让球': rev_rq_list,
                '比分': rev_bf_odds,
                '总进球': rev_zjq_odds,
                '半全场': rev_bqc_odds,
            }

    uniq_pairs = set()
    for k in matches:
        parts = k.split('_', 2)
        if len(parts) == 3:
            uniq_pairs.add((parts[0], tuple(sorted(parts[1:]))))
    print(f'  🎯 网易API赛果: 解析到 {len(uniq_pairs)} 场已完赛比赛 (正反序key共{len(matches)}条)')
    shown = 0
    seen_pairs = set()
    for k, v in sorted(matches.items()):
        parts = k.split('_', 2)
        pair = (parts[0], tuple(sorted(parts[1:]))) if len(parts) == 3 else None
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        lg_s = f"（{v['league']}）" if v.get('league') else ''
        mid_s = f" id={v['matchId']}" if v.get('matchId') else ''
        print(f'    [{v["matchNumStr"]}] {k} → {v["score"]} {lg_s}{mid_s}')
        shown += 1
        if shown >= 12:
            break
    return matches


def fetch_results(days_back=7, max_retries=3):
    """从体彩官网API获取赛果数据，支持分页和重试，返回合并后的JSON字符串"""
    import time
    from datetime import datetime, timedelta

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Referer': 'https://www.sporttery.cn/jc/zqsgkj/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'identity',
        'Origin': 'https://www.sporttery.cn',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
    }

    all_matches = []
    page = 1
    total = None

    while True:
        url = (
            f'https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'
            f'?matchBeginDate={start_date}&matchEndDate={end_date}'
            f'&leagueId=&pageSize=50&pageNo={page}&isFix=0&matchPage=1&pcOrWap=1'
        )

        page_data = None
        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    page_data = json.loads(resp.read().decode('utf-8'))
                break
            except Exception as e:
                if attempt < max_retries:
                    wait = attempt * 5
                    print(f'  [重试 {attempt}/{max_retries}] 第{page}页请求失败: {e}，{wait}秒后重试...')
                    time.sleep(wait)
                else:
                    print(f'  [错误] 第{page}页请求失败（已重试{max_retries}次）: {e}')
                    print(f'  请求URL: {url[:120]}...')
                    if page == 1:
                        return ''
                    # 如果不是第一页失败，返回已获取的数据
                    break

        if not page_data:
            break

        matches = page_data.get('value', {}).get('matchResult', [])
        all_matches.extend(matches)

        if total is None:
            total = page_data.get('value', {}).get('total', 0)
            if total:
                print(f'  API共 {total} 场比赛，开始分页获取...')

        print(f'  第{page}页: 获取 {len(matches)} 场 (累计 {len(all_matches)}/{total})')

        if len(matches) < 50:
            break
        if total and len(all_matches) >= total:
            break

        page += 1
        time.sleep(0.5)  # 礼貌性延迟

    if not all_matches:
        return ''

    # 构造合并后的JSON
    merged = {
        'success': True,
        'value': {
            'matchResult': all_matches,
            'total': len(all_matches)
        }
    }
    return json.dumps(merged, ensure_ascii=False)


def normalize_result_team(name):
    """归一化体彩赛果API队名 - 统一调用全局 canonical_team_name"""
    return canonical_team_name(name)

_LABEL_WEEKDAY_MAP = {'周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6}
# 中国体彩 "周X" 编号星期 → Python datetime.weekday()（周一=0...周日=6），与 _LABEL_WEEKDAY_MAP 一致
# JS Date.getDay() 不同（周日=0...周六=6），前端自行适配，Python 端这里只按 Python 语义校验

_WEEKDAY_PREFIX_RE = re.compile(r'^周([一二三四五六日])\d+$')


def canonical_team_name(name):
    """全局唯一的队名标准化函数（按 key 长度从长到短匹配 RESULT_TEAM_NAME_MAP）。
    所有路径：parse_lottery_json / main 归一化 / id_map 去重 / 最终去重 必须统一调用此处。"""
    if not name:
        return ''
    name = str(name).strip()
    for map_name, standard_name in _get_sorted_team_mapping():
        if map_name in name:
            return standard_name
    return name


def is_weekday_match(match_date, match_num_str):
    """校验 match_date 的实际星期与 matchNumStr 的"周X"前缀是否一致。
    match_numStr 缺失时视为通过；无法解析 match_date 时视为通过。
    返回 True = 通过，False = 不一致（应丢弃）。"""
    from datetime import datetime
    if not match_num_str or not match_date:
        return True
    md = _WEEKDAY_PREFIX_RE.match(str(match_num_str))
    if not md:
        return True
    target_weekday = _LABEL_WEEKDAY_MAP.get(md.group(1))
    if target_weekday is None:
        return True
    try:
        actual_weekday = datetime.strptime(match_date, '%Y-%m-%d').weekday()
    except ValueError:
        return True
    return target_weekday == actual_weekday

def get_label_date_from_match_num(match_date, match_num_str):
    """
    根据 matchNumStr（体彩编号，如"周六001"）计算该比赛所属的标签日期。
    分类标准：同一编号前缀"周X"的比赛归入同一天；matchDate 只能比标签日期相同或晚1-2天（跨天凌晨）。
    若 match_num_str 缺失则直接返回 match_date。
    """
    from datetime import datetime, timedelta
    import re
    if not match_num_str or not match_date:
        return match_date
    md = re.match(r'(周[一二三四五六日])\d+', str(match_num_str))
    if not md:
        return match_date
    target_weekday = _LABEL_WEEKDAY_MAP.get(md.group(1))
    if target_weekday is None:
        return match_date
    try:
        dt = datetime.strptime(match_date, '%Y-%m-%d')
    except ValueError:
        return match_date
    current_weekday = dt.weekday()
    # 向前修正到编号的"周X"：比赛可能跨天（深夜→凌晨），matchDate最多比编号日期晚2天
    if target_weekday < current_weekday:
        diff = current_weekday - target_weekday
    elif target_weekday > current_weekday:
        # 例如：matchDate=周一(0)，编号是"周日017"(6) → 往前 0+7-6=1 天到上一个周日
        diff = current_weekday + 7 - target_weekday
    else:
        diff = 0
    if diff > 0:
        dt = dt - timedelta(days=diff)
    return dt.strftime('%Y-%m-%d')


def parse_results_json(json_text):
    """解析体彩赛果API返回的JSON数据，返回赛果字典 {key: result_data}"""
    results = {}

    # 构建反向映射：API队名 → SCHEDULE队名
    reverse_team_map = {}
    for k, v in RESULT_TEAM_NAME_MAP.items():
        if v not in reverse_team_map:
            reverse_team_map[v] = k

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f'  [错误] 赛果JSON解析失败: {e}')
        print(f'  原始数据前200字符: {json_text[:200]}')
        return results

    if not data.get('success') or not data.get('value'):
        print(f'  [错误] 赛果API返回失败: {data.get("errorMessage", "未知错误")}')
        print(f'  API响应前300字符: {json_text[:300]}')
        return results

    value = data['value']
    matches = value.get('matchResult', [])
    if not matches:
        print('  [警告] 赛果API返回0场比赛')
        print(f'  API响应前300字符: {json_text[:300]}')
        return results

    from datetime import datetime, timedelta

    for m in matches:
        home_api = m.get('homeTeam', '')
        home_full = m.get('allHomeTeam', '')
        away_api = m.get('awayTeam', '')
        away_full = m.get('allAwayTeam', '')

        home = normalize_result_team(home_api)
        away = normalize_result_team(away_api)
        match_date = m.get('matchDate', '')[:10]  # 只取日期部分
        match_num_str = m.get('matchNumStr', '') or m.get('matchNum', '')

        if not match_date or not home or not away:
            continue

        # 根据 matchNumStr 修正日期（体彩编号中的"周几"表示比赛所属日期）
        # 比赛可能跨天（深夜→凌晨），matchDate 可能比编号日期晚一天，需往前修正
        match_date = get_label_date_from_match_num(match_date, match_num_str)

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
            'matchNumStr': match_num_str,
            'status': m.get('matchResultStatus', ''),
        }

        if m.get('h'):
            result_data['胜'] = m['h']
        if m.get('d'):
            result_data['平'] = m['d']
        if m.get('a'):
            result_data['负'] = m['a']

        # P2-1：有完整比分 → 写入主/别名 key；无完整比分但有 matchId / matchNumStr → 保留占位 key，供下一次 CI 回填比分
        # 这样不会因体彩 API 延迟丢场次，占位 entry 含完整身份元数据便于下次匹配
        has_score = bool(result_data['fullScore'])
        has_identity = bool(result_data.get('matchId') or result_data.get('matchNumStr'))
        if has_score or has_identity:
            # 主key: 使用归一化后的队名
            key = f'{match_date}_{home}_{away}'
            # 若已有相同 key 且旧值带 fullScore 而新值不带，则不覆盖（避免回填时清掉已存比分）
            if key in results and results[key].get('fullScore') and not result_data['fullScore']:
                pass
            else:
                results[key] = result_data

            if has_score:
                # 附加 key 仅对有比分的情况生成（别名 key 用于查找，无需占位占用）
                # 附加key: 使用API原始队名（短名）
                if home_api != home or away_api != away:
                    orig_key = f'{match_date}_{home_api}_{away_api}'
                    results[orig_key] = result_data

                # 附加key: 使用SCHEDULE风格的短名（反向映射）
                home_short = reverse_team_map.get(home, home)
                away_short = reverse_team_map.get(away, away)
                if home_short != home or away_short != away:
                    short_key = f'{match_date}_{home_short}_{away_short}'
                    if short_key not in results:
                        results[short_key] = result_data

    placeholders = sum(1 for v in results.values() if not v.get('fullScore') and (v.get('matchId') or v.get('matchNumStr')))
    scored = sum(1 for v in results.values() if v.get('fullScore'))
    print(f'  解析完成，共 {len(results)} 条：有比分 {scored} 场，占位（等下次回填） {placeholders} 场')
    return results


def update_html_results(html_content, results_data):
    """更新 index.html 中的 RESULTS 变量"""
    results_pattern = r'const RESULTS = \{[\s\S]*?\n\};'

    results_str = "const RESULTS = {\n"
    keys = sorted(results_data.keys())

    for i, key in enumerate(keys):
        r = results_data[key]
        val_parts = []
        for field in ['halfScore', 'fullScore', 'winFlag', 'handicap', 'league', 'leagueAbbr', 'home', 'away', 'matchId', 'matchNumStr', 'matchNo', 'status', '胜', '平', '负']:
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


def archive_results(results_data, days=7):
    """归档超过指定天数的旧赛果（days=7 表示近7天保留，更早归档；只归档有有效matchNumStr的比赛）"""
    from datetime import datetime, timedelta
    archive_dir = os.path.join(BASE_DIR, 'results_history')
    os.makedirs(archive_dir, exist_ok=True)

    # days=7: 今天 + 6 天前 = 7天窗口，窗口之前的日期归档
    cutoff = (datetime.now() - timedelta(days=days - 1)).strftime('%Y-%m-%d')
    archived_count = 0

    def _has_valid_match_num(r):
        sn = r.get('matchNumStr', '')
        return bool(re.match(r'^周[一二三四五六日]\d+$', str(sn)))

    for key in list(results_data.keys()):
        date = key.split('_')[0]
        # 归档日期严格早于 cutoff，且比赛必须有有效matchNumStr
        r = results_data[key]
        if date < cutoff and _has_valid_match_num(r):
            # P2-2：日期编号一致性审计 —— 发现错日期立即告警，拒绝写入错误归档
            match_num = r.get('matchNumStr', '')
            if not is_weekday_match(date, match_num):
                print(f'    [AUDIT][SKIP] 归档发现日期/编号不一致，拒绝写入: key={key} matchNumStr={match_num}')
                continue
            archive_file = os.path.join(archive_dir, f'{date}.json')
            existing = {}
            if os.path.exists(archive_file):
                with open(archive_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            # 写归档文件前同样复核该 key 的日期一致性
            if key in existing and not is_weekday_match(date, existing[key].get('matchNumStr', '')):
                print(f'    [AUDIT][FIX] 归档文件内旧条目同样冲突，剔除后再写: key={key}')
                existing.pop(key, None)
            existing[key] = r
            with open(archive_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            del results_data[key]
            archived_count += 1

    if archived_count:
        print(f'  归档旧赛果: {archived_count} 条到 results_history/')
    else:
        print(f'  本次无新增归档（截止日期 {cutoff} 之前）')

    # P2-2 全量审计归档目录：扫描所有已归档 JSON，标记任何"日期与matchNumStr星期不一致"的脏数据
    audit_bad = 0
    for filename in sorted(os.listdir(archive_dir)):
        if not filename.endswith('.json') or filename == 'index.json':
            continue
        filepath = os.path.join(archive_dir, filename)
        file_date = filename.replace('.json', '')
        with open(filepath, 'r', encoding='utf-8') as f:
            entries = json.load(f)
        bad_in_file = [k for k, v in entries.items()
                       if v.get('matchNumStr') and not is_weekday_match(file_date, v.get('matchNumStr', ''))]
        if bad_in_file:
            audit_bad += len(bad_in_file)
            print(f'    [AUDIT][脏数据] {filename} 含 {len(bad_in_file)} 条错日期条目: {bad_in_file}')
    if audit_bad:
        print(f'  ⚠️ [AUDIT] 全量归档审计发现 {audit_bad} 条脏数据，建议人工复核 results_history/')
    else:
        print(f'  ✅ [AUDIT] 全量归档审计通过，无错日期条目')

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


def fetch_and_save_results(days_back=7, archive_days=7):
    """主函数：抓取赛果并保存，返回 (success, stats_dict)。

    网易为主源（fetch_163_results），体彩为备用（fetch_results + parse_results_json）。
    网易主源自带 jcNum/league/matchId/playMap赔率，无需再调体彩编号接口；仅当降级到体彩时才补充编号。
    参数:
      days_back: 回溯天数，默认 7（CI 日常）。传入 228+ 可回填 2026 全年历史数据。
      archive_days: 归档阈值天数，默认 7。backfill 模式应设为 365 以保留全年历史数据在 results_data.json。
    """
    print('\n' + '=' * 60)
    print(f'  获取赛果数据（网易主源 / 体彩备用，回溯 {days_back} 天）')
    print('=' * 60)

    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 抓取赛果：网易为主源，体彩为备用
    print('\n[1/3] 获取赛果数据（网易主源）...')
    new_results = fetch_163_results(days_back=days_back)
    source = '163'
    fetched_bytes = 0

    if not new_results:
        print('  ⚠️ 网易赛果为空，降级到体彩赛果API...')
        json_text = fetch_results(days_back=days_back)
        if json_text:
            fetched_bytes = len(json_text)
            print(f'  ✅ 体彩赛果API获取成功 ({fetched_bytes} 字节)')
            new_results = parse_results_json(json_text)
            source = 'sporttery'
        if not new_results:
            print('\n[错误] 网易主源 + 体彩备用 均无可用赛果')
            return False, {'fetched': 0, 'parsed': 0, 'merged': 0, 'source': source}

    print(f'  ✅ 解析成功: {len(new_results)} 场比赛 (来源: {source})')

    # 体彩编号信息合并（仅体彩可用时补充；CI被封时跳过，网易主源自带jcNum/league/matchId）
    id_map = {}
    if source == 'sporttery':
        print('\n  [补充] 获取完整比赛编号信息...')
        try:
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            id_map = fetch_match_numbers(start_date, end_date)
            print(f'  赛果API返回 {len(id_map)} 场比赛的编号信息')
            id_matched = 0
            for key, ids in id_map.items():
                if key in new_results:
                    new_results[key]['matchId'] = ids.get('matchId', '')
                    new_results[key]['matchNumStr'] = ids.get('matchNumStr', '')
                    new_results[key]['matchNo'] = ids.get('matchNo', '')
                    if ids.get('league') and not new_results[key].get('league'):
                        new_results[key]['league'] = ids['league']
                    id_matched += 1
            print(f'  ✅ 已补充 {id_matched} 场比赛的编号信息到赛果')
        except Exception as e:
            print(f'  ⚠️ 获取编号信息失败: {e}')
    else:
        print(f'\n  [跳过] 网易主源自带编号/联赛，无需体彩编号接口')

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

    # canonical 清洗 merged_results 的 key（队名变体归一化 + 同方向去重）
    # 旧 RESULTS 可能残留 "国际图尔" / "IFK哥德堡" / "布鲁马波卡纳" 等非标准队名 key，
    # 需重算 canonical key 并合并到标准 key，避免前端展示赛果时出现重复/缺失。
    canon_dedup_count = 0
    canon_merged = {}
    for old_key, rec in merged_results.items():
        parts = old_key.split('_', 2)
        if len(parts) < 3:
            canon_merged[old_key] = rec
            continue
        date, home, away = parts
        c_home = canonical_team_name(home)
        c_away = canonical_team_name(away)
        new_key = f'{date}_{c_home}_{c_away}'
        if new_key == old_key:
            canon_merged.setdefault(new_key, rec)
            continue
        # key 发生变化 → 合并到 canonical key（优先保留有 fullScore 的条目）
        if new_key in canon_merged:
            existing = canon_merged[new_key]
            existing_has_score = bool(existing.get('fullScore'))
            new_has_score = bool(rec.get('fullScore'))
            if new_has_score and not existing_has_score:
                canon_merged[new_key] = {**existing, **rec}
            else:
                # 字段级补全
                for k, v in rec.items():
                    if k not in existing or not existing[k]:
                        existing[k] = v
        else:
            canon_merged[new_key] = rec
        canon_dedup_count += 1
    if canon_dedup_count:
        print(f'  [CLEAN] canonical 归一化 {canon_dedup_count} 条队名变体 key')
    merged_results = canon_merged
    print(f'  合并后赛果（canonical 归一化）: {len(merged_results)} 条')

    # 归档旧赛果
    archived_count = len(merged_results)
    merged_results = archive_results(merged_results, days=archive_days)
    archived_count -= len(merged_results)
    if archived_count > 0:
        print(f'  归档旧赛果: {archived_count} 条')

    # 更新HTML：先回填赛果API拿到的完整编号到SCHEDULE，再写回赛果
    # 解决问题：抓赔率步骤时体彩API可能还没全部入库，导致SCHEDULE缺编号；
    # 抓赛果步骤时fetch_match_numbers通常能拿到完整编号，此时补写SCHEDULE即可修复编号缺失。
    if id_map:
        id_count_before = 0
        id_count_after = 0
        schedule_before_pattern = r'const SCHEDULE = \{([\s\S]*?)\};'
        sm = re.search(schedule_before_pattern, html_content)
        if sm:
            sched_str = '{' + sm.group(1) + '}'
            sched_json_str = parse_js_obj_to_json(sched_str)
            try:
                schedule = json.loads(sched_json_str)
            except Exception:
                schedule = {}
            # 构建 id_map 的 canonical 无序对索引（方便 SCHEDULE 球队匹配）
            canon_id_map = {}
            for raw_key, ids in id_map.items():
                parts = raw_key.split('_', 2)
                if len(parts) != 3:
                    continue
                _, h, a = parts
                ch = canonical_team_name(h)
                ca = canonical_team_name(a)
                if ch <= ca:
                    ckey = (ch, ca)
                else:
                    ckey = (ca, ch)
                canon_id_map[ckey] = ids
            for date in schedule:
                for g in schedule[date]:
                    had = bool(g.get('matchNumStr'))
                    if had:
                        id_count_before += 1
                        continue
                    gh = canonical_team_name(g.get('home', ''))
                    ga = canonical_team_name(g.get('away', ''))
                    if gh <= ga:
                        ckey = (gh, ga)
                    else:
                        ckey = (ga, gh)
                    if ckey in canon_id_map:
                        ids = canon_id_map[ckey]
                        if ids.get('matchNumStr'):
                            g['matchNumStr'] = ids['matchNumStr']
                        if ids.get('matchNo') and not g.get('matchNo'):
                            g['matchNo'] = ids['matchNo']
                        if ids.get('matchId') and not g.get('matchId'):
                            g['matchId'] = ids['matchId']
                    if g.get('matchNumStr'):
                        id_count_after += 1
            if id_count_after > 0:
                schedule_js = schedule_to_js(schedule)
                full_schedule_decl = f'const SCHEDULE = {schedule_js};'
                html_content = re.sub(schedule_before_pattern, lambda _: full_schedule_decl, html_content, count=1)
                print(f'  ✅ 编号回填：补了 {id_count_after} 场缺失matchNumStr（之前SCHEDULE有编号共 {id_count_before} 场）')

    # === 从 merged_results 中提取赔率同步写入 ODDS（index.html 内联 + odds_data.json） ===
    # 赛果API已经通过 playMap 拿到了 2026 全年的 HDA / HHDA / 比分 / 总进球 / 半全场 赔率，
    # 需要同步到 ODDS 让「赔率管理」页面能直接展示（而不只是 RESULTS 里有）
    print('\n[3/4] 从赛果提取历史赔率并同步到 ODDS...')
    odds_pattern = r'const ODDS = \{([\s\S]*?)\};'
    odds_match = re.search(odds_pattern, html_content)
    existing_odds = {}
    if odds_match:
        existing_odds_str = '{' + odds_match.group(1) + '}'
        try:
            existing_odds = json.loads(parse_js_obj_to_json(existing_odds_str))
            print(f'  原有ODDS: {len(existing_odds)} 条')
        except Exception:
            existing_odds = {}
    added_from_results = 0
    updated_from_results = 0
    for res_key, rec in merged_results.items():
        parts = res_key.split('_', 2)
        if len(parts) < 3:
            continue
        date, home, away = parts
        # 只合并有可用赔率字段的记录
        has_odds = (rec.get('胜') or rec.get('让球') or rec.get('比分') or
                    rec.get('总进球') or rec.get('半全场'))
        if not has_odds:
            continue
        existing = existing_odds.get(res_key, {})
        # 若现有记录已有完整胜/平/负，不覆盖（用户手工录入 / 赔率API更优），只补缺失字段
        existing_has_core = bool(existing.get('胜') and existing.get('平') and existing.get('负'))
        new_entry = dict(existing) if existing else {}
        new_entry['home'] = new_entry.get('home', home)
        new_entry['away'] = new_entry.get('away', away)
        if rec.get('league') and not new_entry.get('league'):
            new_entry['league'] = rec['league']
        if rec.get('matchId') and not new_entry.get('matchId'):
            new_entry['matchId'] = rec['matchId']
        if rec.get('matchNumStr') and not new_entry.get('matchNumStr'):
            new_entry['matchNumStr'] = rec['matchNumStr']
        if rec.get('matchNo') and not new_entry.get('matchNo'):
            new_entry['matchNo'] = rec['matchNo']
        # 胜/平/负（HDA 让球0）：现有无核心赔率才整体替换
        if not existing_has_core:
            if rec.get('胜'): new_entry['胜'] = rec['胜']
            if rec.get('平'): new_entry['平'] = rec['平']
            if rec.get('负'): new_entry['负'] = rec['负']
        # 让球数组：合并（按 handicap 去重），优先保留现有
        rq_new = list(new_entry.get('让球') or [])
        existing_hcps = set()
        for item in rq_new:
            if isinstance(item, dict):
                existing_hcps.add(str(item.get('handicap', '')))
        for rq in rec.get('让球') or []:
            if not isinstance(rq, dict):
                continue
            hcp = str(rq.get('handicap', ''))
            if hcp and hcp not in existing_hcps:
                rq_new.append(rq)
                existing_hcps.add(hcp)
        if rq_new:
            new_entry['让球'] = rq_new
        # 比分 / 总进球 / 半全场：只补缺失项
        for field, src_field in [('比分', '比分'), ('总进球', '总进球'), ('半全场', '半全场')]:
            src = rec.get(src_field) or {}
            if not isinstance(src, dict):
                continue
            cur = new_entry.get(field) or {}
            if not isinstance(cur, dict):
                cur = {}
            changed = False
            for k, v in src.items():
                if k not in cur and v:
                    cur[k] = v
                    changed = True
            if cur and (changed or not new_entry.get(field)):
                new_entry[field] = cur
        if res_key not in existing_odds:
            existing_odds[res_key] = new_entry
            added_from_results += 1
        elif new_entry != existing:
            existing_odds[res_key] = new_entry
            updated_from_results += 1
    # canonical 清洗 existing_odds 的 key 与上面 update_html_odds 中保持一致
    canon_dedup_count_odds = 0
    canon_odds = {}
    for old_key, odds in existing_odds.items():
        parts = old_key.split('_', 2)
        if len(parts) < 3:
            canon_odds.setdefault(old_key, odds)
            continue
        date2, h2, a2 = parts
        c_home2 = canonical_team_name(h2)
        c_away2 = canonical_team_name(a2)
        new_key2 = f'{date2}_{c_home2}_{c_away2}'
        if new_key2 == old_key:
            canon_odds.setdefault(new_key2, odds)
            continue
        if new_key2 in canon_odds:
            e = canon_odds[new_key2]
            has_core_e = bool(e.get('胜') or e.get('比分') or e.get('让球'))
            has_core_n = bool(odds.get('胜') or odds.get('比分') or odds.get('让球'))
            if has_core_n and not has_core_e:
                canon_odds[new_key2] = {**e, **odds}
            else:
                for k2, v2 in odds.items():
                    if k2 not in e or not e[k2]:
                        e[k2] = v2
            canon_dedup_count_odds += 1
        else:
            canon_odds[new_key2] = odds
    existing_odds = canon_odds
    print(f'  ✅ 从赛果回填 ODDS：新增 {added_from_results} 条, 更新 {updated_from_results} 条 (canonical归一化 {canon_dedup_count_odds} 条, 共 {len(existing_odds)} 条)')

    # 写回 index.html 的 ODDS 内联常量
    odds_js = json.dumps(existing_odds, ensure_ascii=False, indent=2)
    html_content = re.sub(odds_pattern, f'const ODDS = {odds_js};', html_content, count=1)

    # 同步写入 odds_data.json (前端 fetch('odds_data.json') 读取)
    import time as _time
    online_data = {}
    for key, odds in existing_odds.items():
        key_parts = key.split('_', 2)
        if len(key_parts) < 3:
            continue
        _, h3, a3 = key_parts
        vs_key = f'{h3} vs {a3}'
        entry = {
            '胜': odds.get('胜', ''),
            '平': odds.get('平', ''),
            '负': odds.get('负', ''),
            '让球': odds.get('让球', []),
            '比分': odds.get('比分', {}),
            '总进球': odds.get('总进球', {}),
            '半全场': odds.get('半全场', {}),
            'league': odds.get('league', ''),
            'date_key': key
        }
        for mfield in ['matchId', 'matchNumStr', 'matchNo']:
            if odds.get(mfield):
                entry[mfield] = odds[mfield]
        online_data[vs_key] = entry
    odds_json_full = {
        'updated': _time.strftime('%Y-%m-%d %H:%M'),
        'count': len(online_data),
        'data': online_data
    }
    with open(os.path.join(BASE_DIR, 'odds_data.json'), 'w', encoding='utf-8') as f:
        json.dump(odds_json_full, f, ensure_ascii=False, indent=2)
    print('  ✅ ODDS 内联(index.html) + odds_data.json 已同步')

    print('\n[4/4] 更新 index.html 中的赛果数据...')
    html_content = update_html_results(html_content, merged_results)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print('  ✅ index.html 已更新')

    # 保存JSON
    save_results_json(merged_results)

    print('\n' + '=' * 60)
    print(f'  赛果更新完成！共 {len(merged_results)} 条')
    print('=' * 60)

    # === 关键防护：若"前一天"的赛果在API有但本地写入后为0条，说明赛果同步链路断裂 ===
    # 必须直接返回失败（退出码1），让CI fail而不是静默吞错，否则会出现"当天跑完比赛但线上永远无赛果"
    from datetime import datetime, timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_api = sum(1 for k in new_results if k.startswith(yesterday))
    yesterday_local = sum(1 for k in merged_results if k.startswith(yesterday))
    stats = {'fetched': fetched_bytes, 'parsed': len(new_results), 'merged': len(merged_results),
             'yesterday_api': yesterday_api, 'yesterday_local': yesterday_local, 'source': source}
    if yesterday_api > 0 and yesterday_local == 0:
        print(f'\n[致命错误] 赛果同步断裂：API拿到{yesterday}共{yesterday_api}场赛果，但写入本地后为0条')
        print('  可能根因：队名映射缺失导致key对不上、合并逻辑丢数据、归档逻辑误删。CI已阻断，请人工介入')
        return False, stats
    if yesterday_local == 0 and datetime.now().hour >= 12:
        # 过了中午12点前一天赛果还没出现，大概率API或赛果抓取出问题（极少数比赛当日凌晨踢完后下午才录）
        print(f'\n[警告] {yesterday} 赛果写入为0条（当前时间已过12点）')
    return True, stats


if __name__ == '__main__':
    exit_code = 0
    results_files = [
        'index.html',
        'results_data.json',
        'results_history/',
        'odds_history/',
    ]
    results_msg = '更新赛果数据（网易主源/体彩备用）'
    no_push = '--no-push' in sys.argv

    # --backfill 模式：回填历史赛果（默认从 2026-01-01 至今，可用 --backfill-days N 自定义天数）
    if '--backfill' in sys.argv:
        # 计算从 2026-01-01 至今的天数
        from datetime import datetime
        try:
            start_date = datetime(2026, 1, 1)
            today_dt = datetime.now()
            backfill_days = max(1, (today_dt - start_date).days + 1)
        except Exception:
            backfill_days = 228
        # 允许 --backfill-days N 覆盖默认值
        for i, arg in enumerate(sys.argv):
            if arg == '--backfill-days' and i + 1 < len(sys.argv):
                try:
                    backfill_days = int(sys.argv[i + 1])
                except ValueError:
                    pass
        print(f'\n[BACKFILL] 回填 {backfill_days} 天历史赛果（含赔率/让球/赛果）')
        success, stats = fetch_and_save_results(days_back=backfill_days, archive_days=365)
        if not success:
            print('\n[致命错误] 回填赛果失败，退出码1')
            exit_code = 1
        elif not no_push:
            pushed = push_to_gh_pages(
                commit_message=f'data: 回填{backfill_days}天历史赛果+赔率(网易jczq API)',
                extra_files=results_files,
                sync_master_first=True,
                skip_ghpages=False,
            )
            if not pushed:
                print('\n[致命错误] 回填赛果推送失败，退出码1')
                exit_code = 1
    elif '--results-only' in sys.argv:
        success, stats = fetch_and_save_results()
        if not success:
            print('\n[致命错误] 赛果抓取失败，退出码1')
            exit_code = 1
        elif not no_push:
            # results-only 模式：赛果修改必须单独 commit+push，否则就像"抓了白抓"
            pushed = push_to_gh_pages(
                commit_message=results_msg,
                extra_files=results_files,
                sync_master_first=True,
                skip_ghpages=False,
            )
            if not pushed:
                print('\n[致命错误] 赛果抓取成功但推送失败，退出码1')
                exit_code = 1
    elif '--full' in sys.argv:
        print('\n' + '#' * 60)
        print('  完整模式: 赔率 + 赛果 一键更新')
        print('#' * 60)
        main()  # main 内部已做赔率 commit + 双分支推送
        print('\n' + '#' * 60)
        print('  赔率更新完成，开始抓取赛果...')
        print('#' * 60)
        success, stats = fetch_and_save_results()
        if not success:
            print('\n[致命错误] 完整模式赛果抓取失败，未通过提交门槛。退出码1')
            print(f'  赛果统计: fetched={stats.get("fetched",0)}B, parsed={stats.get("parsed",0)}, merged={stats.get("merged",0)}')
            if stats.get('parsed', 0) == 0:
                print('  请检查网易jczq赛果页+体彩赛果API状态，稍后重试')
            exit_code = 1
        elif not no_push:
            # 关键修复：fetch_and_save_results 修改了 index.html / results_data.json / 归档目录后
            # 必须再次 commit+push 到 master 和 gh-pages，否则赛果只存在本地文件不会上线。
            # 这是今天 8-12 三场赛果"看起来没录上"的直接根因。
            pushed = push_to_gh_pages(
                commit_message=results_msg,
                extra_files=results_files,
                sync_master_first=True,
                skip_ghpages=False,
            )
            if not pushed:
                print('\n[致命错误] 赛果抓取成功但推送失败，退出码1')
                exit_code = 1
    else:
        main()

    if exit_code != 0:
        sys.exit(exit_code)
