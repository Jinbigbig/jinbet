# -*- coding: utf-8 -*-
"""
把「我的报告队名」（简体缩写，如 巴萨/马竞/曼联）映射到 7M 积分榜队名（繁体全名，如
巴塞隆拿/馬德里體育會/曼聯），用于在第⑥节里高亮今日交锋双方并标注其当前积分排名。

匹配优先级：
  1) 简->繁转换后精确相等；
  2) 别名表 ALIAS（my_name -> 7M_name）；
  3) 简->繁后子串包含（双向）。
匹配失败返回 None（调用方优雅显示「—」，绝不编造）。
"""
import json
import os

# 我的联赛名 -> 7M id（已逐一验证；美职(MLS) 在 7M 数据库未收录，剔除）
LEAGUE_7M_ID = {
    '英超': 92, '西甲': 85, '德甲': 39, '意甲': 34, '法甲': 93, '荷甲': 99, '葡超': 88,
    '瑞超': 103, '芬超': 105, '挪超': 104, '巴甲': 160, '日职': 102, '日乙': 347,
    '法乙': 171, '意乙': 95, '西乙': 96, '德乙': 140,
}
# 美职(MLS) 数据源缺失标记
UNAVAILABLE = {'美职': '7M 数据库未收录美职联(MLS)积分榜'}

# 简体 -> 繁体（仅覆盖足球队名中出现的差异字）
_SIMP2TRAD = {
    '马': '馬', '竞': '競', '兰': '蘭', '滨': '濱', '冈': '岡', '萨': '薩', '维': '維',
    '纳': '納', '伦': '倫', '贝': '貝', '尔': '爾', '库': '庫', '奥': '奧', '罗': '羅',
    '亚': '亞', '苏': '蘇', '华': '華', '赖': '賴', '乌': '烏', '帮': '幫', '别': '別',
    '边': '邊', '东': '東', '离': '離', '帅': '帥', '乐': '樂', '门': '門', '问': '問',
    '头': '頭', '实': '實', '学': '學', '国': '國', '图': '圖', '韦': '韋', '决': '決',
    '义': '義', '艺': '藝', '结节': '結節', '万': '萬', '历': '歷', '测': '測', '汉': '漢',
    '汉': '漢', '书': '書', '长': '長', '队': '隊', '乡': '鄉', '庙': '廟', '丰': '豐',
    '戈尔': '戈爾', '马洛': '馬洛', '达': '達', '尔': '爾', '顿': '頓', '诺': '諾',
    '莱': '萊', '盖': '蓋', '圣': '聖', '盖': '蓋', '伦': '倫', '萨': '薩', '赫': '赫',
}

# 我的队名 -> 7M 队名（解决缩写/异译，仅收录今日有交锋的队）
ALIAS = {
    # 巴甲
    '弗拉门戈': '法林明高', '科林蒂安': '哥連泰斯',
    # 德甲
    '埃沃斯堡': '艾華斯堡', '拜仁': '拜仁慕尼黑', '汉堡': '漢堡', '莱红牛': 'RB萊比錫',
    # 意甲
    '博洛尼亚': '博洛尼亞', '尤文图斯': '祖雲達斯', '莱切': '萊切', '萨索洛': '莎索羅',
    '蒙扎': '蒙沙', '那不勒斯': '拿玻里',
    # 挪超
    '汉坎': '咸卡姆', '莫尔德': '莫迪',
    # 日乙
    '仙台七夕': '仙台維加泰', '札幌冈萨': '札幌岡薩多',
    # 日职
    '东京绿茵': '東京綠茵', '千叶市原': '千葉市原',
    # 法甲
    '巴黎圣曼': '巴黎聖日門', '布雷斯特': '比斯特', '特鲁瓦': '特魯瓦', '里尔': '利爾',
    # 瑞超
    '哈马比': '哈馬比',
    # 芬超
    '库奥皮奥': '古比斯', '赫尔辛基': '赫爾辛基',
    # 英超
    '曼联': '曼聯',
    # 荷甲
    '埃因霍温': 'PSV燕豪芬', '海伦芬': '海倫維恩', '鹿斯巴达': '鹿特丹斯巴達',
    # 葡超
    '本菲卡': '賓菲加', '法马利康': '法馬利卡奧', '里斯本': '士砵亭',
    # 西甲
    '塞尔塔': '切爾達', '巴萨': '巴塞隆拿', '拉科': '拉科魯尼亞', '皇家社会': '皇家蘇斯達',
    '莱万特': '利雲特', '赫塔费': '華歷簡奴', '马拉加': '馬拉加', '马竞': '馬德里體育會',
    # 2026-09-14 补充（意甲/挪超/瑞超/芬超/英超/葡超/西甲）
    '科莫': '科木', '都灵': '拖連奴', '国际米兰': '國際米蘭', '乌迪内斯': '烏甸尼斯',
    '博德闪耀': '波杜基林特', '桑纳菲': '辛迪夫佐特',
    '盖斯': '加爾斯',
    '国际图': '英特杜古', '瓦萨': 'VPS華沙',
    '利兹联': '列斯聯', '纽卡斯尔': '紐卡素',
    '布拉迪斯': '布拉加', '埃斯托里': '伊斯托里爾',
    '比利亚雷': '維拉利爾', '贝蒂斯': '貝迪斯',
    # 法乙
    '圣旺红星': '紅星',
}


def _trad(s):
    out = []
    for ch in s:
        out.append(_SIMP2TRAD.get(ch, ch))
    return ''.join(out)


def build_index(league_data):
    """league_data: 来自 league_data.json 的 {lg: parsed}。返回 {lg: {name: row}}。"""
    idx = {}
    for lg, parsed in league_data.items():
        m = {}
        for t in parsed.get('teams', []):
            m[t['name']] = t
        idx[lg] = m
    return idx


def match_team(my_name, lg, index):
    """返回该队在 lg 积分榜中的 row dict；匹配不到返回 None。"""
    rows = index.get(lg)
    if not rows:
        return None
    # 1) 简->繁精确
    tn = _trad(my_name)
    if tn in rows:
        return rows[tn]
    # 2) 别名
    alias = ALIAS.get(my_name)
    if alias and alias in rows:
        return rows[alias]
    # 3) 子串（双向）
    for nm, row in rows.items():
        if tn and (tn in nm or nm in tn):
            return row
    return None


def match_team_strict(my_name, lg, index):
    """严格匹配（仅 简->繁精确 或 ALIAS 命中），不启用子串回退。
    用于反填「联赛排名」：宁可留空（显示「—」），也不因模糊匹配写错名次。"""
    rows = index.get(lg)
    if not rows:
        return None
    tn = _trad(my_name)
    if tn in rows:
        return rows[tn]
    alias = ALIAS.get(my_name)
    if alias and alias in rows:
        return rows[alias]
    return None


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    ld = json.load(open(os.path.join(here, 'league_data.json'), encoding='utf-8'))['leagues']
    md = json.load(open(os.path.join(here, 'scripts', 'matches_data.json'), encoding='utf-8'))
    idx = build_index(ld)
    from collections import defaultdict
    mine = defaultdict(set)
    for m in md['matches']:
        mine[m['league']].add(m['home']); mine[m['league']].add(m['away'])
    total = matched = 0
    for lg in sorted(mine):
        if lg in UNAVAILABLE:
            print(f'[{lg}] 数据源缺失：{UNAVAILABLE[lg]}')
            continue
        for t in sorted(mine[lg]):
            total += 1
            r = match_team(t, lg, idx)
            if r:
                matched += 1
                print('  [ok] %s %s -> #%s %s (%s分)' % (lg, t, r['rank'], r['name'], r['pts']))
            else:
                print(f'  [--] {lg} {t} -> 未匹配')
    print(f'\n覆盖 {matched}/{total} 队')
