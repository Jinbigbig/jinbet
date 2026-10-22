#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""赛前伤停/停赛（结构化源）→ injuries.json

【为什么只有这两个源】
2026-10-22 对用户提供的 20 条赛前源逐一实测（curl + 浏览器 UA）：
  ✅ 可用：FCUpdate 荷甲（SSR，每队一块）、Bundesliga 官方 Team News（SSR 文本）
  ⚠️ 半可用：Soccerway（站点通，伤停需逐场子页）、Fantacalcio（需按轮次子页）
  ❌ Transfermarkt 全系（西甲/意甲/法甲/葡超/土超）：本机 IP 全域名返回 405 拦截页
  ❌ premierinjuries.com 403；Sports.ru 403；OTempo 连接失败
  ❌ premierleague.com 官方：名单由 JS 渲染，HTML 内 0 个球员名
  ❌ 百度体育（西甲/俄超/土超）：SPA 空壳，未找到公开接口
  ❌ Ligue1 / Lance!：只有文章列表，无结构化伤停

故本脚本只固化「实测可解析」的两源；其余联赛的伤停由报告生成前的人工核查
补充进 injuries_manual.json（同结构，脚本会自动合并，人工优先）。

输出 injuries.json：
  {"updated": "...", "teams": {"拜仁": {"league":"德甲","out":[{"name","reason"}],
                                        "doubtful":[...]}, ...}}
队名统一为竞彩官方简称，供 _gen_report.py 直接按 m['home']/m['away'] 取用。
"""
import html
import json
import os
import re
import sys
import time
import urllib.request

OUT = 'injuries.json'
MANUAL = 'injuries_manual.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0 Safari/537.36')

BUNDESLIGA_URL = ('https://www.bundesliga.com/en/bundesliga/news/'
                  'team-news-line-ups-2026-27-bayern-dortmund-fantasy-20707')
FCUPDATE_URL = ('https://www.fcupdate.nl/voetbalcompetities/nederland/eredivisie/'
                'schorsingen-blessures')

# 英文/荷兰语队名 → 竞彩官方简称
EN2ZH = {
    # 德甲
    'bayern munich': '拜仁', 'bayern': '拜仁',
    'borussia dortmund': '多特', 'dortmund': '多特',
    'rb leipzig': '莱红牛', 'leipzig': '莱红牛',
    'bayer leverkusen': '勒沃库森', 'leverkusen': '勒沃库森',
    'vfb stuttgart': '斯图加特', 'stuttgart': '斯图加特',
    'eintracht frankfurt': '法兰克福', 'frankfurt': '法兰克福',
    'werder bremen': '云达不来梅', 'bremen': '云达不来梅',
    'sc freiburg': '弗莱堡', 'freiburg': '弗莱堡',
    'borussia monchengladbach': '门兴', 'borussia mönchengladbach': '门兴',
    'monchengladbach': '门兴', 'mönchengladbach': '门兴', 'gladbach': '门兴',
    'vfl wolfsburg': '沃夫斯堡', 'wolfsburg': '沃夫斯堡',
    'tsg hoffenheim': '霍芬海姆', 'hoffenheim': '霍芬海姆',
    'mainz 05': '美因茨', 'mainz': '美因茨',
    'fc augsburg': '奥格斯堡', 'augsburg': '奥格斯堡',
    'union berlin': '柏林联合', '1. fc union berlin': '柏林联合',
    'hamburger sv': '汉堡', 'hamburg': '汉堡',
    'fc cologne': '科隆', '1. fc köln': '科隆', 'koln': '科隆', 'köln': '科隆', 'cologne': '科隆',
    '1. fc heidenheim': '海登海姆', 'heidenheim': '海登海姆',
    'fc st. pauli': '圣保利', 'st. pauli': '圣保利', 'pauli': '圣保利',
    'elversberg': '埃弗斯堡', 'sv elversberg': '埃弗斯堡',
    # 荷甲
    'ajax': '阿贾克斯', 'psv': '埃因霍温', 'psv eindhoven': '埃因霍温',
    'feyenoord': '费耶诺德', 'fc twente': '特温特', 'twente': '特温特',
    'fc utrecht': '乌德勒支', 'utrecht': '乌德勒支', 'az': '阿尔克马', 'az alkmaar': '阿尔克马',
    'sc heerenveen': '海伦芬', 'heerenveen': '海伦芬',
    'sparta rotterdam': '鹿特丹斯巴达', 'nec': '奈梅亨', 'nec nijmegen': '奈梅亨',
    'fc groningen': '格罗宁根', 'groningen': '格罗宁根',
    'pec zwolle': '兹沃勒', 'zwolle': '兹沃勒',
    'fortuna sittard': '福图纳', 'heracles': '赫拉克勒斯', 'heracles almelo': '赫拉克勒斯',
    'willem ii': '威廉二世', 'nac breda': '布雷达', 'telstar': '特尔斯达',
    'go ahead eagles': '前进之鹰', 'excelsior': '精英队',
}


# 伤病部位/性质 → 中文（德甲英文缩写、荷甲荷兰语）
REASON_ZH = {
    'thigh': '大腿', 'knee': '膝', 'hamstring': '腿筋', 'abdominals': '腹肌',
    'muscular': '肌肉', 'muscle': '肌肉', 'shoulder': '肩', 'foot': '足',
    'ankle': '脚踝', 'hip': '髋', 'back': '背', 'head': '头部', 'illness': '疾病',
    'ill': '疾病', 'concussion': '脑震荡', 'groin': '腹股沟', 'calf': '小腿',
    'quad': '股四头肌', 'cruciate': '十字韧带', 'acl': '十字韧带',
    'metatarsal': '跖骨', 'toe': '脚趾', 'hand': '手', 'wrist': '腕',
    'arm': '手臂', 'leg': '腿', 'knock': '碰撞伤', 'fitness': '体能',
    'suspension': '停赛', 'cartilage': '软骨', 'tendon': '肌腱',
    'surgery': '手术', 'infection': '感染', 'pelvis': '骨盆', 'rib': '肋骨',
    'borstbeenblessure': '胸骨伤', 'knieblessure': '膝伤', 'enkelblessure': '脚踝伤',
    'blessure': '伤病', 'onbekend': '伤情未明', 'onbekende blessure': '伤情未明',
    'fysieke klachten': '身体不适', 'operatie': '手术', 'hamstringblessure': '腿筋伤',
    'liesblessure': '腹股沟伤', 'voetblessure': '足伤', 'heupblessure': '髋伤',
    'rugblessure': '背伤', 'hoofdblessure': '头部伤', 'ziekte': '疾病',
    'kuitblessure': '小腿伤', 'dijblessure': '大腿伤', 'schouderblessure': '肩伤',
    'handblessure': '手伤', 'teenblessure': '脚趾伤', 'schorsing': '停赛',
    'niet fit': '体能不足', 'fit': '体能不足',
}


def tr_reason(raw):
    """把英文/荷兰语的伤病描述翻成中文短语，保留未知原文。"""
    low = (raw or '').strip().lower()
    if not low:
        return ''
    # 长词优先，避免 'blessure' 吃掉 'knieblessure'
    for k in sorted(REASON_ZH, key=len, reverse=True):
        if k in low:
            return REASON_ZH[k]
    return (raw or '').strip()[:20]


def parse_nl_desc(desc):
    """'Knieblessure (Sinds 22-09-2026, Verwacht terug 10-10-2026)' → 中文+日期"""
    m_s = re.search(r'Sinds\s*(\d{2})-(\d{2})-(\d{4})', desc)
    m_b = re.search(r'[Vv]erwacht[e]?\s*terug\w*\s*(\d{2})-(\d{2})-(\d{4})', desc)
    rec = {'reason': tr_reason(desc)}
    if m_s:
        rec['since'] = f'{m_s.group(3)}-{m_s.group(2)}-{m_s.group(1)}'
    if m_b:
        rec['back'] = f'{m_b.group(3)}-{m_b.group(2)}-{m_b.group(1)}'
    return rec


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9,nl;q=0.8',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ('utf-8', 'latin-1'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode('utf-8', 'replace')


def _norm(name):
    return re.sub(r'\s+', ' ', name or '').strip().lower()


def canon(name):
    """队名归一为竞彩简称；匹配不到返回 None。"""
    n = _norm(name)
    if n in EN2ZH:
        return EN2ZH[n]
    for k, v in EN2ZH.items():
        if k and (k in n or n in k) and len(n) >= 4:
            return v
    return None


def parse_players(seg):
    """'Diehl (thigh), Malanga (abdominals)' → [{'name','reason'}]"""
    out = []
    for m in re.finditer(r'([A-ZÀ-Þ][\w\.\'\-À-ÿ]+(?:\s+[A-ZÀ-Þ][\w\.\'\-À-ÿ]+)*)\s*\(([^)]*)\)', seg):
        nm, rsn = m.group(1).strip(), m.group(2).strip()
        if nm and len(nm) > 2:
            out.append({'name': nm, 'reason': tr_reason(rsn)})
    return out


# ---------------- 德甲：bundesliga.com 官方 Team News ----------------
def _article_body(page):
    """bundesliga.com 的名单在 JSON-LD 的 articleBody 里（\\n/\\t 为字面转义）。"""
    for js in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            obj = json.loads(html.unescape(js))
        except Exception:
            continue
        for item in (obj if isinstance(obj, list) else [obj]):
            body = (item or {}).get('articleBody')
            if body and ('Out:' in body or 'Doubtful:' in body):
                return body
    return ''


def fetch_bundesliga():
    page = _get(BUNDESLIGA_URL)
    txt = _article_body(page)
    if not txt:
        # 兜底：整页去标签（部分文章直接在正文里）
        txt = html.unescape(re.sub(r'<[^>]+>', '\n', page))
    txt = txt.replace('\u00a0', ' ').replace('\xa0', ' ')
    teams = {}
    for line in txt.split('\n'):
        line = line.strip()
        if 'Out:' not in line and 'Doubtful:' not in line:
            continue
        m = re.match(r'^([A-Z][A-Za-z0-9\.\'\-À-ÿ ]{2,30}):\s', line)
        if not m:
            continue
        zh = canon(m.group(1))
        if not zh:
            continue
        rec = teams.setdefault(zh, {'league': '德甲', 'out': [], 'doubtful': []})
        mo = re.search(r'Out:\s*(.*?)(?:Doubtful:|Coach:|$)', line)
        md = re.search(r'Doubtful:\s*(.*?)(?:Coach:|$)', line)
        if mo:
            rec['out'] = parse_players(mo.group(1))
        if md:
            rec['doubtful'] = parse_players(md.group(1))
    return teams


# ---------------- 荷甲：FCUpdate 停赛/伤病专页 ----------------
def fetch_fcupdate():
    page = _get(FCUPDATE_URL)
    teams = {}
    blocks = re.split(r'<div class="matches-block[^"]*matches-block--suspension-injury"', page)
    for blk in blocks[1:]:
        mh = re.search(r'<h2[^>]*>(.*?)</h2>', blk, re.S)
        if not mh:
            continue
        raw_team = html.unescape(re.sub(r'<[^>]+>', '', mh.group(1))).strip()
        zh = canon(raw_team)
        if not zh:
            continue
        rec = teams.setdefault(zh, {'league': '荷甲', 'out': [], 'doubtful': []})
        for row in re.split(r'<div class="matches-panel d-flex align-center">', blk)[1:]:
            mn = re.search(r'<div class="player-name">\s*(.*?)\s*</div>', row, re.S)
            md = re.search(r'<span class="fld-description">\s*<span>(.*?)</span>', row, re.S)
            if not (mn and md):
                continue
            nm = html.unescape(re.sub(r'<[^>]+>', '', mn.group(1))).strip()
            desc = html.unescape(re.sub(r'<[^>]+>', '', md.group(1))).strip()
            if not nm or nm in ('Naam', 'Name'):
                continue
            item = {'name': nm}
            item.update(parse_nl_desc(desc))
            rec['out'].append(item)
    return teams


def main():
    result = {'updated': time.strftime('%Y-%m-%d %H:%M'), 'teams': {}}
    for tag, fn in (('德甲', fetch_bundesliga), ('荷甲', fetch_fcupdate)):
        try:
            got = fn()
            result['teams'].update(got)
            n_p = sum(len(v['out']) + len(v['doubtful']) for v in got.values())
            print(f'[伤停] {tag}：{len(got)} 队 / {n_p} 人')
        except Exception as e:
            print(f'[伤停] {tag} 抓取失败：{type(e).__name__} {e}')
    # 人工核查补充，优先级最高
    if os.path.exists(MANUAL):
        try:
            man = json.load(open(MANUAL, encoding='utf-8')).get('teams') or {}
            result['teams'].update(man)
            print(f'[伤停] 人工核查补充 {len(man)} 队')
        except Exception as e:
            print(f'[伤停] injuries_manual.json 读取失败：{e}')
    json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'[伤停] 合计 {len(result["teams"])} 队 → {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
