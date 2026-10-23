# -*- coding: utf-8 -*-
"""赛前阵容 / 伤停 / 开球时间抓取（lineupstoday.com）-> lineups.json

站点是 WordPress，逐场页面 URL 可预测：
    https://lineupstoday.com/<league-slug>/<home-slug>-<away-slug>-<DD-MM-YYYY>/

页面里两个区块是结构化 HTML，直接正则即可，不需要浏览器：
    id="opstelling"  Predicted lineups：<strong>队名</strong><em>4-2-3-1</em>
                     + 每个 ov-veld__speler 含球衣号与球员名（主客各 11 人）
    id="absenties"   Injuries and suspensions：每队一个 ov-panel，
                     逐条 <li class="ov-absentie">（球员名 / 原因 / 状态）

状态类：ov-status--out      缺阵
        ov-status--twijfel  存疑
        ov-status--rood     停赛（红牌）

用法：
    python _fetch_lineups.py                 # 按 _calc_result.json 的 today
    python _fetch_lineups.py --date 2026-10-22
    python _fetch_lineups.py --dry           # 只打印要抓的 URL，不发请求
"""
import io
import json
import os
import re
import sys
import html as _html
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = 'https://lineupstoday.com'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
WORKERS = 4
TIMEOUT = 30

# ---------------------------------------------------------------- 联赛名映射
LEAGUE_SLUG = {
    '英超': 'premier-league',
    '英冠': 'championship',
    '西甲': 'laliga',
    '意甲': 'serie-a',
    '德甲': 'bundesliga',
    '法甲': 'ligue-1',
    '荷甲': 'eredivisie',
    '比甲': 'pro-league',
    '土超': 'super-lig',
    '欧冠': 'champions-league',
    '欧罗巴': 'europa-league',
    '欧联': 'europa-league',
    '欧罗巴杯': 'europa-league',
    '欧会杯': 'conference-league',
    '欧协联': 'conference-league',
    '欧会联': 'conference-league',
}

# 竞彩简称 -> 站点 slug（同一队可给多个别名，用 / 分隔）
_RAW_TEAMS = {
    'premier-league': """
        曼城=manchester-city 阿森纳=arsenal 布赖顿=布菜顿=brighton 切尔西=chelsea
        利物浦=liverpool 布伦特福德=布伦特=brentford 利兹联=利兹=leeds-united
        埃弗顿=everton 赫尔城=hull-city 伊普斯维奇=伊普斯=ipswich-town
        纽卡斯尔=纽卡=newcastle-united 维拉=阿斯顿维拉=aston-villa
        曼联=曼彻斯特联=manchester-united 水晶宫=crystal-palace 伯恩茅斯=bournemouth
        热刺=托特纳姆=tottenham-hotspur 考文垂=coventry-city 富勒姆=fulham
        诺丁汉森林=诺丁汉=nottingham-forest 桑德兰=sunderland
    """,
    'championship': """
        斯旺西=swansea-city 西汉姆联=西汉姆=west-ham-united 米德尔斯堡=米堡=middlesbrough
        伯明翰=birmingham-city 西布罗姆=西布罗姆维奇=west-bromwich-albion
        斯托克城=斯托克=stoke-city 狼队=伍尔弗汉普顿=wolverhampton-wanderers
        南安普敦=南安普顿=southampton 女王公园=女王公园巡游者=queens-park-rangers
        布莱克本=blackburn-rovers 谢菲联=谢菲尔德联=sheffield-united 米尔沃尔=millwall
        朴茨茅斯=portsmouth 雷克斯汉姆=雷克瑟姆=wrexham 博尔顿=bolton-wanderers
        布城=布里斯托尔城=bristol-city 查尔顿=charlton-athletic 林肯城=lincoln-city
        加的夫城=卡迪夫=cardiff-city 沃特福德=watford 诺维奇=norwich-city
        伯恩利=burnley 德比郡=德比=derby-county 普雷斯顿=preston-north-end
    """,
    'laliga': """
        巴萨=巴塞罗那=barcelona 马竞=马德里竞技=atletico-madrid 皇马=皇家马德里=real-madrid
        贝蒂斯=皇家贝蒂斯=real-betis 皇家社会=real-sociedad 塞维利亚=seville=sevilha=sevilla
        阿拉维斯=deportivo-alaves 塞尔塔=celta-de-vigo 拉科鲁尼亚=deportivo-la-coruna
        奥萨苏纳=osasuna 莱万特=levante 比利亚雷亚尔=比利亚=黄潜=villarreal
        毕尔巴鄂=毕尔巴鄂竞技=athletic-bilbao 巴列卡诺=rayo-vallecano 赫塔菲=getafe
        西班牙人=espanyol 桑坦德=桑坦德竞技=racing-santander 埃尔切=elche
        瓦伦西亚=valencia 马拉加=malaga
    """,
    'serie-a': """
        国际米兰=国米=inter 拉齐奥=lazio 罗马=as-roma AC米兰=米兰=ac-milan 科莫=como
        弗洛西诺内=frosinone 卡利亚里=cagliari 尤文图斯=尤文=juventus 那不勒斯=napoli
        都灵=torino 亚特兰大=atalanta 莱切=lecce 萨索洛=sassuolo 蒙扎=monza
        博洛尼亚=bologna 乌迪内斯=udinese 热那亚=genoa 佛罗伦萨=fiorentina
        帕尔马=parma 威尼斯=venezia
    """,
    'bundesliga': """
        拜仁=拜仁慕尼黑=bayern-munchen 多特蒙德=多特=borussia-dortmund
        弗莱堡=弗赖堡=sc-freiburg 勒沃库森=药厂=bayer-leverkusen 美因茨=mainz-05
        埃尔弗斯贝格=埃尔弗=elversberg 莱红牛=莱比锡=rb-leipzig 不来梅=云达不来梅=werder-bremen
        汉堡=汉堡SV=hamburger-sv 奥格斯堡=fc-augsburg 法兰克福=eintracht-frankfurt
        科隆=fc-koln 斯图加特=vfb-stuttgart 霍芬海姆=hoffenheim 沙尔克04=沙尔克=schalke-04
        帕德博恩=sc-paderborn 柏林联合=union-berlin 门兴=门兴格拉德巴赫=borussia-monchengladbach
    """,
    'ligue-1': """
        里昂=lyon 巴黎圣曼=巴黎=巴黎圣日耳曼=psg 巴黎FC=paris-fc 里尔=lille 摩纳哥=monaco
        雷恩=rennes 洛里昂=lorient 朗斯=lens 马赛=marseille 布雷斯特=brest 图卢兹=toulouse
        欧塞尔=auxerre 尼斯=nice 斯特拉斯堡=strasbourg 昂热=angers 勒芒=le-mans
        特鲁瓦=troyes 勒阿弗尔=le-havre
    """,
    'eredivisie': """
        费耶诺德=feyenoord 阿尔克马尔=az 埃因霍温=psv=埃因霍溫 阿贾克斯=ajax 特温特=fc-twente
        福图纳=福图纳锡塔德=fortuna-sittard 格罗宁根=fc-groningen 海伦芬=sc-heerenveen
        前进之鹰=go-ahead-eagles 埃克塞尔西奥=sbv精英=excelsior 乌得勒支=乌德勒支=fc-utrecht
        尼美根=奈梅亨=nec 鹿特丹斯巴达=sparta-rotterdam 坎布尔=sc-cambuur 兹沃勒=pec-zwolle
        特尔斯达=telstar 海牙=ado-den-haag 威廉二世=蒂尔堡威廉二世=willem-ii
    """,
    'pro-league': """
        根特=kaa-gent 布鲁日=club-brugge 沙勒罗瓦=charleroi 圣吉尔联=圣吉罗斯=union-sint-gillis
        安德莱赫特=anderlecht 韦斯特洛=kvc-westerlo 亨克=krc-genk 泽尔特瓦赫姆=zulte-waregem
        标准列日=standard-luik 洛默尔=lommel 贝弗伦=sk-beveren 圣特鲁登=圣图尔登=stvv
        安特卫普=royal-antwerp 梅赫伦=kv-mechelen 奥哈瓦里=oh-leuven 拉卢维耶=raal-la-louviere
        科特赖克=kv-kortrijk 色格拉布鲁日=cercle-brugge
    """,
    'super-lig': """
        加拉塔萨=加拉塔萨雷=galatasaray 阿梅德斯堡=阿梅德=amedspor 费内巴切=fenerbahce
        特拉布宗=特拉布宗体育=trabzonspor 贝西克塔斯=贝西克塔=besiktas 乔鲁姆=corum-fk
        卡斯帕萨=kasimpasa 科贾埃利=kocaelispor 阿拉尼亚=阿兰亚=alanyaspor
        巴萨克塞希尔=伊斯坦布尔BB=basaksehir 埃尔祖鲁姆=erzurumspor 里泽=rizespor
        戈兹特佩=goztepe 加济安泰普=gaziantep-fk 根奇莱尔=genclerbirligi 科尼亚=konyaspor
        萨姆松=samsunspor 埃于普=eyupspor
    """,
    # 欧战里出现、但不在上述各国联赛清单中的球队
    'europe': """
        里斯本=里斯本竞技=sporting-portugal 波尔图=fc-porto=porto 本菲卡=benfica
        布拉加=sc-braga 凯尔特人=celtic 流浪者=格拉斯哥流浪者=rangers
        顿涅茨克矿工=矿工=shakhtar-donetsk 奥林匹亚科斯=olympiacos 红星=贝尔格莱德红星=crvena-zvezda
        哥本哈根=copenhagen 博德闪耀=博多格林特=bodo-glimt 维京=viking LASK林茨=LASK林茨=lask
        萨尔茨堡=红牛萨尔茨堡=red-bull-salzburg 巴塞尔=basel 布拉迪斯拉发=slovan-bratislava
        萨巴赫=sabah 帕纳辛纳科斯=panathinaikos 费伦茨瓦罗斯=费伦茨=ferencvaros
        米迪兰特=中日德兰=midtjylland 贝尔谢巴=贝尔谢巴工人=hapoel-beer-sheva
        格拉茨=格拉茨风暴=格风暴=sturm-graz 萨格勒布迪纳摩=萨迪纳摩=dinamo-zagreb 波兹南莱赫=莱赫波兹南=波兹南=lech-poznan
        OFI克里特=OFI=克里特=ofi 亚美尼亚阿拉拉特=ararat-armenia 利勒斯特罗姆=利勒斯特=lillestrom
        亚盖洛尼亚=乔治罗尼亚=jagiellonia 卢加诺=fc-lugano 中洛锡安=哈茨=heart-of-midlothian
        亚布洛内茨=fk-jablonec 林肯红魔=林肯城红魔=lincoln-red-imps AEK雅典=aek-athene
        布拉格斯拉维亚=斯拉维亚=slavia-praag 采列=celje 布兰=brann 特罗姆瑟=tromso
        帕尔蒂赞=游击队=fk-partizan 伏伊伏丁那=vojvodina 卡拉巴赫=qarabag
        古尔尼克=扎布热矿工=gornik-zabrze 马瑟韦尔=motherwell 海法马卡比=maccabi-haifa
        卡拉特=卡拉特阿拉木图=kairat-almaty 奥莫尼亚=omonia-nicosia 萨尔基里斯=kauno-zalgiris
        哈马比=hammarby-ff 基辅迪纳摩=基辅发电机=dynamo-kyiv 舍里夫=蒂拉斯波尔警长=sheriff
        弗罗拉=塔林弗洛拉=flora 里加=里加FC=riga 利耶帕亚=liepaja 图恩=thun
    """,
}


def _build_team_map():
    zh2slug, slug2zh = {}, {}
    for lg, raw in _RAW_TEAMS.items():
        for tok in raw.split():
            if '=' not in tok:
                continue
            parts = tok.split('=')
            slug = parts[-1]
            for zh in parts[:-1]:
                zh2slug.setdefault(zh, slug)
            slug2zh.setdefault(slug, parts[0])
    return zh2slug, slug2zh


TEAM_SLUG, SLUG_TEAM = _build_team_map()

# ---------------------------------------------------------------- 文案翻译
# 英文伤因 -> 中文短语（长词优先匹配）
_RSN = [
    ('hamstring', '腿筋伤'), ('ankle', '踝伤'), ('knee', '膝伤'), ('groin', '腹股沟伤'),
    ('calf', '小腿伤'), ('thigh', '大腿伤'), ('achilles', '跟腱伤'), ('heel', '足跟伤'),
    ('foot', '足伤'), ('toe', '脚趾伤'), ('hip', '髋伤'), ('back', '背伤'),
    ('shoulder', '肩伤'), ('wrist', '腕伤'), ('hand', '手伤'), ('elbow', '肘伤'),
    ('head', '头部伤'), ('concussion', '脑震荡'), ('neck', '颈伤'), ('rib', '肋骨伤'),
    ('muscle', '肌肉伤'), ('muscular', '肌肉伤'), ('groin', '腹股沟伤'),
    ('illness', '疾病'), ('virus', '疾病'), ('fitness', '体能不足'),
    ('surgery', '术后'), ('operation', '术后'), ('knock', '碰撞伤'),
    ('suspended', '停赛'), ('red card', '红牌停赛'), ('second yellow', '两黄停赛'),
    ('yellow card', '累积黄牌停赛'), ('personal', '个人原因'), ('rest', '轮休'),
    ('fatigue', '疲劳'), ('load management', '负荷管理'), ('international duty', '国家队'),
    ('loan', '租借条款'), ('cup-tied', '杯赛资格'), ('ineligible', '无出场资格'),
    ('cruciate', '十字韧带伤'), ('acl', '十字韧带伤'), ('metatarsal', '跖骨伤'),
    ('cartilage', '软骨伤'), ('tendon', '肌腱伤'), ('pelvis', '骨盆伤'),
    ('infection', '感染'), ('broken', '骨折'), ('fracture', '骨折'),
    ('dead leg', '腿部撞伤'), ('cramp', '抽筋'), ('hernia', '疝气'),
    ('not in the squad', '未进名单'), ('not registered', '未注册'), ('unused', '未进名单'),
    ('coach', '教练决定'), ('disciplinary', '纪律处分'), ('bereavement', '家庭原因'),
    ('paternity', '家庭原因'), ('suspension', '停赛'),
    # 兜底词（必须排在具体部位之后，否则会先命中泛词）
    ('health problems', '健康问题'), ('ill health', '健康问题'),
    ('leg', '腿伤'), ('body', '身体不适'), ('unavailable', '伤情未明'),
    ('injury', '伤情'), ('injured', '伤情'), ('issue', '伤情'), ('problems', '伤情'),
]


def rsn_zh(raw):
    """把英文伤因翻成中文短语；认不出就保留原文（截断 18 字）。"""
    s = (raw or '').strip()
    if not s:
        return ''
    low = s.lower()
    for k, v in _RSN:
        if k in low:
            return v
    return s[:18]


# 状态类 -> (内部键, 中文词)
_ST = {
    'out': ('out', '缺阵'),
    'twijfel': ('doubt', '存疑'),
    'rood': ('susp', '停赛'),
    'geschorst': ('susp', '停赛'),
}


def _clean(x):
    return re.sub(r'\s+', ' ', _html.unescape(x or '')).strip()


def _get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-GB,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode('utf-8', 'replace')


def _sec(page, sid):
    """截取 class="ov-blok" id="sid" 这一块（到下一个 ov-blok 为止）。"""
    m = re.search(r'<section class="ov-blok" id="%s">' % sid, page)
    if not m:
        return ''
    rest = page[m.end():]
    n = re.search(r'<section class="ov-blok"', rest)
    return rest[:n.start()] if n else rest


def parse_lineup(page):
    """返回 [{'team':英文名,'formation':'4-2-3-1','xi':[{'no':1,'name':'Raya'}]}]"""
    seg = _sec(page, 'opstelling')
    out = []
    for blk in re.split(r'<div class="ov-panel ov-elftal"', seg)[1:]:
        m = re.search(r'<strong>([^<]+)</strong>\s*<em>\s*([^<]*)</em>', blk)
        if not m:
            continue
        # 赛前只有阵型（4-2-3-1），赛后是「阵型 · 主教练」，取前段
        fm = re.match(r'\s*(\d+(?:-\d+)+)', m.group(2))
        xi = []
        for p in re.split(r'<div class="ov-veld__speler[^"]*"', blk)[1:]:
            no = re.search(r'ov-veld__nr">(\d+)<', p)
            nm = re.search(r'ov-veld__naam">([^<]+)<', p)
            if nm:
                xi.append({'no': int(no.group(1)) if no else 0, 'name': _clean(nm.group(1))})
        out.append({'team': _clean(m.group(1)),
                    'formation': fm.group(1) if fm else '',
                    'xi': xi[:11]})
    return out


def parse_absences(page):
    """返回 {英文队名: {'out':[{name,reason,reason_en}], 'doubt':[], 'susp':[]}}"""
    seg = _sec(page, 'absenties')
    res = {}
    for blk in re.split(r'<div class="ov-panel">', seg)[1:]:
        tm = re.search(r'class="ov-clubcel"[^>]*>.*?<span>([^<]+)</span>', blk, re.S)
        if not tm:
            continue
        team = _clean(tm.group(1))
        bucket = res.setdefault(team, {'out': [], 'doubt': [], 'susp': []})
        for li in re.split(r'<li class="ov-absentie">', blk)[1:]:
            nm = re.search(r'class="ov-absentie__naam"[^>]*>([^<]+)<', li)
            if not nm:
                continue
            rsn = re.search(r'class="ov-absentie__reden"[^>]*>([^<]*)<', li)
            st = re.search(r'ov-status--([a-z]+)"\s*title="([^"]*)"', li)
            key = 'out'
            if st:
                key = _ST.get(st.group(1), ('susp', '停赛') if 'suspend' in st.group(2).lower() else ('out', '缺阵'))[0]
            reason_en = _clean(rsn.group(1)) if rsn else ''
            # 「未进名单 / 未注册 / 未使用」不是伤病，属报名噪声，丢掉
            if any(x in reason_en.lower() for x in ('not in the squad', 'not registered', 'unused')):
                continue
            bucket[key].append({'name': _clean(nm.group(1)), 'reason': rsn_zh(reason_en), 'reason_en': reason_en})
    return res


def parse_event(page):
    """JSON-LD SportsEvent -> {'start': 开球时间, 'home': 英文主队, 'away': 英文客队}。"""
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            o = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(o, dict) and o.get('@type') == 'SportsEvent':
            return {'start': o.get('startDate') or '',
                    'home': ((o.get('homeTeam') or {}).get('name') or '').strip(),
                    'away': ((o.get('awayTeam') or {}).get('name') or '').strip()}
    return {}


def build_url(league, home, away, date_iso):
    lg = LEAGUE_SLUG.get((league or '').strip())
    hs = TEAM_SLUG.get((home or '').strip())
    as_ = TEAM_SLUG.get((away or '').strip())
    if not (lg and hs and as_):
        return None, (lg, hs, as_)
    y, m, d = date_iso.split('-')
    return f'{BASE}/{lg}/{hs}-{as_}-{d}-{m}-{y}/', (lg, hs, as_)


def fetch_one(m, date_iso):
    url, miss = build_url(m.get('league'), m.get('home'), m.get('away'), date_iso)
    num = m.get('matchNumStr') or ''
    if not url:
        return num, None, {'reason': 'unmapped', 'league': m.get('league'),
                           'home': m.get('home'), 'away': m.get('away'), 'miss': miss}
    for attempt in range(2):
        try:
            page = _get(url)
            break
        except Exception as e:  # 404 / 超时 / 连接重置
            if attempt == 1:
                return num, None, {'reason': 'http', 'url': url, 'err': str(e)[:80]}
    if 'id="absenties"' not in page and 'id="opstelling"' not in page:
        return num, None, {'reason': 'no-block', 'url': url}

    lines = parse_lineup(page)
    absn = parse_absences(page)
    ev = parse_event(page)
    # JSON-LD 缺失时，用阵容面板顺序兜底（面板恒为主队在前）
    if not ev.get('home') and len(lines) >= 2:
        ev = {'start': ev.get('start') or '',
              'home': lines[0]['team'], 'away': lines[1]['team']}
    rec = {'url': url, 'kickoff': ev.get('start') or '', 'home': {}, 'away': {},
           'played': 'id="samenvatting"' in page}

    def _pick_abs(en, idx):
        if en and en in absn:
            return absn[en]
        low = (en or '').lower()
        for k in absn:
            if low and (k.lower() == low or k.lower() in low or low in k.lower()):
                return absn[k]
        keys = [k for k in absn if k]
        return absn[keys[idx]] if len(keys) > idx else None

    for idx, (side, zh) in enumerate((('home', m.get('home')), ('away', m.get('away')))):
        en = ev.get(side) or ''
        row = {'team': zh, 'team_en': en}
        # 阵容面板按英文队名对齐；名字对不上就按主客顺序取
        pick = None
        for lp in lines:
            if en and (lp['team'].lower() == en.lower()
                       or lp['team'].lower().startswith(en.lower()[:6])):
                pick = lp
                break
        if pick is None and len(lines) > idx:
            pick = lines[idx]
        if pick:
            row['formation'] = pick['formation']
            row['xi'] = pick['xi']
        a = _pick_abs(en, idx)
        row.update({k: (a or {}).get(k, []) for k in ('out', 'doubt', 'susp')})
        rec[side] = row
    return num, rec, None


def main():
    args = sys.argv[1:]
    date_iso = None
    if '--date' in args:
        date_iso = args[args.index('--date') + 1]
    dry = '--dry' in args
    if not date_iso:
        try:
            date_iso = json.load(io.open('_calc_result.json', encoding='utf-8'))['today']
        except Exception:
            print('[lineups] 找不到 _calc_result.json，请用 --date 指定日期')
            return 1

    try:
        calc = json.load(io.open('_calc_result.json', encoding='utf-8'))
    except Exception as e:
        print(f'[lineups] 读取 _calc_result.json 失败：{e}')
        return 1
    matches = calc.get('matches') or []

    todo = [m for m in matches if (m.get('league') or '').strip() in LEAGUE_SLUG]
    print(f'[lineups] {date_iso} 共 {len(matches)} 场，其中联赛被站点覆盖 {len(todo)} 场')

    if dry:
        for m in todo:
            url, miss = build_url(m.get('league'), m.get('home'), m.get('away'), date_iso)
            print(('  OK  ' if url else '  MISS') + f" {m.get('matchNumStr')} {m.get('home')} vs {m.get('away')}"
                  + (f'  -> {url}' if url else f'  未映射={miss}'))
        return 0

    out = {'updated': '', 'date': date_iso, 'matches': {}, 'skipped': []}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, m, date_iso): m for m in todo}
        for fu in futs:
            num, rec, err = fu.result()
            if rec:
                out['matches'][num] = rec
            else:
                sk = {'matchNumStr': num}
                sk.update(err or {})
                out['skipped'].append(sk)

    import datetime
    out['updated'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    # 统计
    n_out = sum(len(rec[s]['out']) + len(rec[s]['doubt']) + len(rec[s]['susp'])
                for rec in out['matches'].values() for s in ('home', 'away'))
    n_xi = sum(1 for rec in out['matches'].values() for s in ('home', 'away') if rec[s].get('xi'))
    print(f'[lineups] 命中 {len(out["matches"])}/{len(todo)} 场，伤停 {n_out} 人，首发 {n_xi} 队')
    for sk in out['skipped'][:8]:
        print(f'   跳过 {sk.get("matchNumStr")}: {sk.get("reason")} {sk.get("league") or ""} '
              f'{sk.get("home") or ""} vs {sk.get("away") or ""}'.rstrip())

    io.open('lineups.json', 'w', encoding='utf-8').write(
        json.dumps(out, ensure_ascii=False, indent=1))
    print('[lineups] -> lineups.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
