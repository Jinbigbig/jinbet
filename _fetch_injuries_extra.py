# -*- coding: utf-8 -*-
"""补充赛前信息源 -> injuries_extra.json（伤停 + 赛前军情原文）

两个源：
A. 7M 足球新闻联赛页（港式中文「軍情」段，格式统一）：
       <队名>停賽：… 上陣成疑：… 受傷／缺陣：…
   命中当日对阵后，既抽结构化伤停，也保留军情整段原文供页面展示。
B. lineupstoday 联赛伤停汇总页（英文队名，含全联赛所有球队）：
       https://lineupstoday.com/<slug>/injuries/

产出：
    {"date": "...", "updated": "...",
     "teams": {"布雷达": {"out": [...], "doubt": [...], "susp": [...]}},
     "moods": {"周五002": {"title": "...", "text": "..."}}}

用法：
    python _fetch_injuries_extra.py
    python _fetch_injuries_extra.py --date 2026-10-23
    python _fetch_injuries_extra.py --verbose
"""
import datetime as dt
import json
import re
import ssl
import sys
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
TIMEOUT = 40
OUT = 'injuries_extra.json'

# ---- 源 A：7M 联赛新闻页（联赛 -> id，id 由 /matches/<id>/index.shtml 探测所得）----
SEVEN_M = {
    '英超': 92, '西甲': 85, '意甲': 34, '德甲': 39, '法甲': 93,
    '英冠': 177, '荷甲': 99, '荷乙': 202, '葡超': 88,
    '德乙': 140, '瑞超': 103, '澳超': 339, '土超': 180, '比甲': 100,
    '苏超': 138, '日职': 102, '韩K联': 250, '美职': 107, '巴甲': 160, '阿甲': 108,
}

# ---- 源 B：lineupstoday 联赛伤停汇总页（联赛 -> slug）----
LT_SLUG = {
    '英超': 'premier-league', '西甲': 'laliga', '意甲': 'serie-a', '德甲': 'bundesliga',
    '法甲': 'ligue-1', '英冠': 'championship', '荷甲': 'eredivisie',
    '荷乙': 'eerste-divisie', '土超': 'super-lig',
}

# 7M 港译（繁体）-> 竞彩统一名。补一行就多覆盖一队；无映射的队不会被误配。
HK2CN = {
    # 德乙
    '波琴': '波鸿', '禾夫斯堡': '沃夫斯堡', '達斯泰特': '达姆施塔特', '聖保利': '圣保利',
    '馬格德堡': '马格德堡', '卡爾斯魯厄': '卡尔斯鲁厄', '特雷斯登': '德累斯顿', '漢堡': '汉堡',
    '凱沙羅頓': '凯泽斯劳滕', '哈化柏林': '柏林赫塔', '格雷特霍夫': '菲尔特', '紐倫堡': '纽伦堡',
    '柏達邦': '柏德博恩', '布倫瑞克': '不伦瑞克', '漢諾威': '汉诺威', '基爾': '基尔',
    '海登咸': '海登海姆', '艾華斯堡': '埃沃斯堡', '奧斯納貝克': '奥斯纳布吕克',
    '科特布斯': '科特布斯', '比勒費爾德': '比勒菲尔德', '史浩克04': '沙尔克04',
    '科隆': '科隆', '普斯辛蒙斯特': '普鲁士明斯特',
    # 澳超
    '布里斯班獅吼': '布里斯班', '布里斯本獅吼': '布里斯班', '珀斯光輝': '珀斯',
    '墨爾本勝利': '墨尔本胜利', '墨爾本城': '墨尔本城', '悉尼FC': '悉尼FC', 'FC悉尼': '悉尼FC',
    '西悉尼流浪者': '西悉尼漫步者', '中岸水手': '中央海岸水手', '威靈頓鳳凰': '惠灵顿凤凰',
    '阿德萊德聯': '阿德莱德联', '紐卡素噴射機': '纽卡斯尔喷气机', 'FC麥克阿瑟': '麦克阿瑟FC',
    '奧克蘭FC': '奥克兰FC', '西部聯': '西部联',
    # 瑞超
    '馬模': '马尔默', '艾夫斯堡': '埃夫斯堡', '埃爾夫斯堡': '埃夫斯堡', '佐加頓斯': '佐加顿斯',
    '哈馬比': '哈马比', 'AIK蘇納': 'AIK索尔纳', '哥登堡': '哥德堡', '希爾星堡': '赫尔辛堡',
    '諾高平': '北雪平', '米亞爾比': '米亚尔比', '天狼星': '天狼星', '加爾斯': '加尔斯',
    '迪加科斯': '代格福什', '華斯特拉斯': '韦斯特罗斯', '奧斯達': '奥斯达',
    # 葡超
    '甘馬雷斯': '吉马良斯', '馬里迪莫': '马里迪莫', '賓菲加': '本菲卡', '波圖': '波尔图',
    '士砵亭': '里斯本竞技', '布拉加': '布拉加', '里奧艾維': '里奥阿维', '博維斯塔': '博阿维斯塔',
    '法馬利卡奧': '法马利康', '伊斯托里爾': '埃斯托里尔', '艾斯杜尼': '埃斯托里尔',
    '國民隊': '国民', '辛達卡拉': '圣克拉拉', '摩里倫斯': '莫雷拉人', '基維辛迪': '吉维森特',
    '阿洛卡': '阿罗卡', '卡薩比亞': '卡萨比亚', '甘馬雷斯': '吉马良斯',
    # 意甲
    '國際米蘭': '国米', 'AC米蘭': 'AC米兰', '祖雲達斯': '尤文', '拿玻里': '那不勒斯',
    '羅馬': '罗马', '拉素': '拉齐奥', '阿特蘭大': '亚特兰大', '費倫天拿': '佛罗伦萨',
    '博洛尼亞': '博洛尼亚', '都靈': '都灵', '拖連奴': '都灵', '蒙扎': '蒙扎', '蒙沙': '蒙扎',
    '烏甸尼斯': '乌迪内斯', '熱拿亞': '热那亚', '卡利亞里': '卡利亚里', '萊切': '莱切',
    '恩波里': '恩波利', '維羅納': '维罗纳', '帕爾馬': '帕尔马', '科木': '科莫',
    # 德甲
    '拜仁慕尼黑': '拜仁', '多蒙特': '多特蒙德', '利華古遜': '勒沃库森', 'RB萊比錫': '莱红牛',
    '法蘭克福': '法兰克福', '史特加': '斯图加特', '慕遜加柏': '门兴', '沃爾夫斯堡': '沃夫斯堡',
    '弗賴堡': '弗赖堡', '賀芬咸': '霍芬海姆', '緬恩斯': '美因茨', '雲達不來梅': '云达不来梅',
    '柏林聯': '柏林联合', '奧格斯堡': '奥格斯堡', '聖保利': '圣保利', '海登咸': '海登海姆',
    '波琴': '波鸿', '基爾': '基尔', '哈化柏林': '柏林赫塔',
    # 西甲
    '皇家馬德里': '皇马', '巴塞隆拿': '巴萨', '馬德里體育會': '马竞', '西維爾': '塞维利亚',
    '維拉利爾': '比利亚雷', '貝迪斯': '贝蒂斯', '皇家蘇斯達': '皇家社会', '畢爾包': '毕尔巴鄂',
    '華倫西亞': '巴伦西亚', '基羅納': '赫罗纳', '奧沙辛拿': '奥萨苏纳', '切爾達': '塞尔塔',
    '馬略卡': '马洛卡', '加泰': '赫塔费', '愛斯賓奴': '西班牙人', '阿拉維斯': '阿拉维斯',
    '艾拉維斯': '阿拉维斯', '馬拉加': '马拉加', '拉斯彭馬斯': '拉斯帕尔马斯', '華拉度列': '巴利亚多利德',
    # 法甲
    '巴黎聖日耳門': '巴黎圣曼', '馬賽': '马赛', '摩納哥': '摩纳哥', '里昂': '里昂',
    '里爾': '里尔', '尼斯': '尼斯', '雷恩': '雷恩', '朗斯': '朗斯', '南特': '南特',
    '斯特拉斯堡': '斯特拉斯堡', '圖盧茲': '图卢兹', '蒙彼利埃': '蒙彼利埃', '比斯特': '布雷斯特',
    '布雷斯特': '布雷斯特', '歐塞爾': '欧塞尔', '昂熱': '昂热', '勒哈弗爾': '勒阿弗尔',
    '羅連安特': '洛里昂', '梅斯': '梅斯', '聖伊天': '圣埃蒂安',
    # 英超
    '曼城': '曼城', '曼聯': '曼联', '利物浦': '利物浦', '阿仙奴': '阿森纳', '車路士': '切尔西',
    '熱刺': '热刺', '紐卡素': '纽卡斯尔', '阿士東維拉': '维拉', '白禮頓': '布莱顿',
    '韋斯咸': '西汉姆', '水晶宮': '水晶宫', '愛華頓': '埃弗顿', '富咸': '富勒姆',
    '賓福特': '布伦特福德', '諾定咸森林': '诺丁汉', '狼隊': '狼队', '般尼茅夫': '伯恩茅斯',
    '葉士域治': '伊普斯', '李斯特城': '莱切斯特', '修咸頓': '南安普敦', '錫菲聯': '谢菲联',
    # 英冠
    '列斯聯': '利兹联', '般尼': '伯恩利', '錫周三': '谢周三', '米杜士堡': '米堡',
    '西布朗': '西布朗', '高雲地利': '考文垂', '新特蘭': '桑德兰', '屈福特': '沃特福德',
    '諾域治': '诺维奇', '布里斯托城': '布里斯托', '史篤城': '斯托克城', '史雲斯': '斯旺西',
    '卡迪夫城': '卡迪夫城', '伯明翰': '伯明翰', '哈特斯菲爾德': '哈德斯菲尔德',
    # 荷甲
    '阿積士': '阿贾克斯', '燕豪芬': '埃因霍温', '飛燕諾': '费耶诺德', '阿爾克馬爾': '阿尔克马尔',
    '川迪': '特温特', '烏德勒支': '乌德勒支', '前進之鷹': '前进之鹰', '伊高斯': '前进之鹰',
    '海倫芬': '海伦芬', '海牙': '海牙', '鹿特丹斯巴達': '斯巴达', '泰斯達': '斯达',
    '伊高斯': '前进之鹰', '奈梅亨': '奈梅亨', '荷華高斯': '赫拉克勒', '威廉二世': '威廉二世',
    # 荷乙
    '比達': '布雷达', 'NAC': '布雷达', '荷華高斯': '赫拉克勒', '海牙': '海牙',
}

# lineupstoday 英文队名 -> 竞彩统一名（按需增量补充）
EN2CN = {
    'Almere City': '阿尔梅勒', 'De Graafschap': '格拉夫夏普', 'FC Den Bosch': '登博斯',
    'FC Dordrecht': '多德勒支', 'FC Eindhoven': '埃因霍温FC', 'FC Emmen': '埃门',
    'FC Volendam': '福伦丹', 'Helmond Sport': '海尔蒙德', 'Heracles Almelo': '赫拉克勒',
    'Jong Ajax': '阿贾克斯青年', 'Jong AZ': '阿尔克马尔青年', 'Jong FC Utrecht': '乌德勒支青年',
    'Jong PSV': '埃因霍温青年', 'MVV Maastricht': '马斯特里赫特', 'NAC Breda': '布雷达',
    'RKC Waalwijk': '瓦尔韦克', 'Roda JC': '罗达JC', 'TOP Oss': '奥斯',
    'Vitesse': '维迪斯', 'VVV-Venlo': '芬洛',
    'Ajax': '阿贾克斯', 'PSV': '埃因霍温', 'Feyenoord': '费耶诺德', 'AZ': '阿尔克马尔',
    'Twente': '特温特', 'Utrecht': '乌德勒支', 'Sparta Rotterdam': '斯巴达',
    'Go Ahead Eagles': '前进之鹰', 'NEC': '奈梅亨', 'Heerenveen': '海伦芬',
    'Fortuna Sittard': '福图纳锡塔德', 'Groningen': '格罗宁根', 'Zwolle': '兹沃勒',
    'Heracles': '赫拉克勒', 'Almere': '阿尔梅勒', 'Waalwijk': '瓦尔韦克',
    'Telstar': '特尔斯达', 'Excelsior': '埃克塞尔西奥', 'NAC': '布雷达',
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def _get(url: str, retry: int = 2) -> str:
    last = None
    for i in range(retry + 1):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA,
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            })
            raw = urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX).read()
            for enc in ('utf-8', 'gb18030', 'big5'):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
            return raw.decode('utf-8', 'ignore')
        except Exception as e:
            last = e
            if i < retry:
                import time
                time.sleep(1.5)
    raise last


def _plain(html: str) -> str:
    t = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'&nbsp;|&#160;', ' ', t)
    for a, b in (('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'")):
        t = t.replace(a, b)
    return re.sub(r'\s+', ' ', t).strip()


def _t2s(s: str) -> str:
    """繁体 -> 简体（球员名/伤因/正文）。"""
    try:
        from opencc import OpenCC
        return OpenCC('t2s').convert(s)
    except Exception:
        return s


def _players(val: str) -> list:
    # 页面在文章末尾会截断，遇到省略号就切掉，避免把后续正文当球员名
    for cut in ('……', '...', '…'):
        i = val.find(cut)
        if i >= 0:
            val = val[:i]
    val = val.strip().strip('、，。, 　')
    if not val or val in ('／', '/', '-', '—', '无', '無'):
        return []
    out = []
    for it in re.split(r'[、，,]', val):
        it = it.strip()
        if not it or it in ('／', '/'):
            continue
        # 页面截断会留下未闭合括号，去掉残缺的后半截
        it = re.sub(r'[（(][^）)]*$', '', it).strip()
        if not it:
            continue
        # 球员名长度合理且不含句读（句读说明已经串到正文）
        if len(it) > 20 or re.search(r'[。！？；]', it):
            continue
        m = re.match(r'^([^（(]+?)\s*[（(]([^）)]*)[）)]', it)
        if m:
            out.append({'name': _t2s(m.group(1).strip()), 'reason': _t2s(m.group(2).strip())})
        elif 2 <= len(it):
            out.append({'name': _t2s(it), 'reason': ''})
    return out


_FIELDS = (('受傷／缺陣：', 'out'), ('上陣成疑：', 'doubt'), ('停賽：', 'susp'),
           ('缺陣：', 'out'), ('受傷：', 'out'), ('成疑：', 'doubt'))


def _seg_fields(seg: str) -> dict:
    res = {'out': [], 'doubt': [], 'susp': []}
    hits = []
    for pat, key in _FIELDS:
        for m in re.finditer(re.escape(pat), seg):
            hits.append((m.start(), m.end(), key))
    hits.sort(key=lambda x: x[0])
    # 去掉被更长标记包住的短标记（如「上陣成疑：」里的「成疑：」）
    clean = []
    for h in hits:
        if clean and h[0] < clean[-1][1]:
            continue
        clean.append(h)
    for i, (s, e, key) in enumerate(clean):
        end = clean[i + 1][0] if i + 1 < len(clean) else len(seg)
        res[key].extend(_players(seg[e:end]))
    for k in res:
        seen, uniq = set(), []
        for p in res[k]:
            if p['name'] and p['name'] not in seen:
                seen.add(p['name'])
                uniq.append(p)
        res[k] = uniq
    return res


def _cn_mood(text: str) -> str:
    """军情原文：繁体转简体 + 港译队名换成竞彩名。"""
    s = _t2s(text)
    # 港译（转简前后都可能出现，逐个试）
    for hk, cn in sorted(HK2CN.items(), key=lambda x: -len(x[0])):
        s = s.replace(hk, cn).replace(_t2s(hk), cn)
    return s.strip()


def fetch_7m(league: str, lid: int, matches: list, verbose=False):
    """7M 联赛页 -> ({队名: 伤停}, {编号: {title, text}})。"""
    url = f'https://news.7m.com.cn/matches/{lid}/index.shtml'
    text = _plain(_get(url))
    if '軍情' not in text and '军情' not in text:
        if verbose:
            print(f'  [7M] {league}: 无军情段')
        return {}, {}

    # 按 Tags 切文章（Tags 在文末，故 chunk i 是第 i 篇正文）
    chunks = re.split(r'Tags[：:]', text)
    teams_out: dict[str, dict] = {}
    moods: dict[str, dict] = {}
    for num, home, away in matches:
        hk_h = next((h for h, c in HK2CN.items() if c == home), None)
        hk_a = next((h for h, c in HK2CN.items() if c == away), None)
        if not hk_h or not hk_a:
            continue
        for ch in chunks:
            if hk_h not in ch or hk_a not in ch:
                continue
            if '軍情' not in ch and '军情' not in ch:
                continue
            # 军情段：从「軍情」到「近況」/「近况」
            i = ch.find('軍情')
            if i < 0:
                i = ch.find('军情')
            body = ch[i:]
            for end_key in ('近況', '近况', 'Tags'):
                j = body.find(end_key)
                if j > 0:
                    body = body[:j]
                    break
            body = body.strip()
            if len(body) < 8:
                continue
            # 标题：军情前一串文字的最后一段
            head = ch[:i].strip()
            title = head.split(' ')[-1] if head else ''
            moods[num] = {'title': _cn_mood(title)[:40], 'text': _cn_mood(body)[:1200]}
            # 结构化：按两队港译名切段（队名须紧邻字段标记，避免命中正文叙述里的队名）
            _MARK = r'(?:停賽：|上陣成疑：|受傷／缺陣：|受傷：|缺陣：)'
            for hk, cn in ((hk_h, home), (hk_a, away)):
                m = re.search(re.escape(hk) + _MARK, body)
                if not m:
                    continue
                pos = m.start()
                nxt = len(body)
                for hk2 in (hk_h, hk_a):
                    if hk2 == hk:
                        continue
                    m2 = re.search(re.escape(hk2) + _MARK, body[pos + len(hk):])
                    if m2:
                        nxt = min(nxt, pos + len(hk) + m2.start())
                got = _seg_fields(body[pos:nxt])
                if any(got.values()):
                    teams_out[cn] = got
            if verbose:
                print(f'  [7M] {league} {num} {home}vs{away}: 军情 {len(moods[num]["text"])} 字')
            break
    return teams_out, moods


def fetch_lineupstoday(league: str, slug: str, teams_cn: list, verbose=False) -> dict:
    html = _get(f'https://lineupstoday.com/{slug}/injuries/')
    panels = re.split(r'<div class="ov-panel ov-bl__club"', html)[1:]
    res = {}
    for p in panels:
        m = re.search(r'<a href="[^"]*">([^<]+)</a>', p)
        if not m:
            continue
        en = m.group(1).strip()
        cn = EN2CN.get(en)
        if not cn or cn not in teams_cn:
            continue
        rows = re.findall(
            r'<tr>\s*<td>\s*([^<]+?)\s*(?:<span[^>]*>[^<]*</span>)?\s*</td>\s*<td>\s*([^<]*)</td>',
            p, flags=re.S)
        out = []
        for name, reason in rows:
            name = re.sub(r'\s+', ' ', name).strip()
            if name:
                out.append({'name': name, 'reason': (reason or '').strip()})
        if out:
            res[cn] = {'out': out, 'doubt': [], 'susp': []}
            if verbose:
                print(f'  [LT] {league} {en}->{cn}: {len(out)} 条')
    return res


def main() -> int:
    argv = sys.argv[1:]
    verbose = '--verbose' in argv
    date = None
    if '--date' in argv:
        date = argv[argv.index('--date') + 1]
    if not date:
        try:
            date = json.load(open('_calc_result.json', encoding='utf-8'))['today']
        except Exception:
            date = dt.date.today().isoformat()

    try:
        calc = json.load(open('_calc_result.json', encoding='utf-8'))
        raw = calc['matches'] if calc.get('today') == date else []
    except Exception:
        raw = []
    if not raw:
        print(f'[补充伤停] {date} 无当日对阵（_calc_result.json today 不符），跳过')
        return 0

    by_league: dict[str, list] = {}
    for m in raw:
        lg = str(m.get('league', '')).strip()
        by_league.setdefault(lg, []).append(
            (str(m.get('matchNumStr', '')).strip(),
             str(m.get('home', '')).strip(), str(m.get('away', '')).strip()))

    teams: dict[str, dict] = {}
    moods: dict[str, dict] = {}
    errors = []

    for lg, lid in SEVEN_M.items():
        pairs = by_league.get(lg) or []
        if not pairs:
            continue
        try:
            t, mo = fetch_7m(lg, lid, pairs, verbose)
            teams.update(t)
            moods.update(mo)
        except Exception as e:
            errors.append(f'7M {lg}: {type(e).__name__}')
            print(f'[补充伤停] 7M {lg} 失败（跳过）：{type(e).__name__}')

    for lg, slug in LT_SLUG.items():
        pairs = by_league.get(lg) or []
        if not pairs:
            continue
        wanted = [x for _, h, a in pairs for x in (h, a)]
        try:
            teams.update(fetch_lineupstoday(lg, slug, wanted, verbose))
        except Exception as e:
            errors.append(f'LT {lg}: {type(e).__name__}')
            print(f'[补充伤停] lineupstoday {lg} 失败（跳过）：{type(e).__name__}')

    payload = {
        'date': date,
        'updated': dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'teams': teams,
        'moods': moods,
    }
    json.dump(payload, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    tot = sum(len(v) for rec in teams.values() for v in rec.values())
    print(f'[补充伤停] {date} 伤停 {len(teams)} 队 / {tot} 条 | 赛前军情 {len(moods)} 场 → {OUT}')
    if errors:
        print('[补充伤停] 失败源：' + '；'.join(errors))
    return 0


if __name__ == '__main__':
    sys.exit(main())
