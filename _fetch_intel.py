#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""赛前情报抓取（直播吧赛前新闻）→ intel.json

覆盖人家文案里的「关键因素」：战意（告别战/争冠/保级）、伤停动态、
换帅、交锋纪录、首发轮换——都是公开新闻，可溯源（带标题+URL+来源）。

发现机制（复用 _fetch_referee.py 已验证的直播吧直连链路）：
  https://news.zhibo8.com/zuqiu/more.htm?day=YYYY-MM-DD&page=1  当日完整文章列表
  抓「今天 + 明天」两天，覆盖提前发布的赛前前瞻。

匹配：队名用别名表（直播吧用「国足/日本男足」等，竞彩用简称）；
  强匹配=标题含双方队名；弱匹配=含单方队名且带情报关键词（伤/首发/主帅…）。
  每场最多 MAX_ARTICLES 篇，强匹配优先，正文截取前 MAX_CHARS 字。

输出 intel.json：
  {"updated": "...", "matches": {"周二002": [
     {"title":..., "url":..., "source":..., "text":..., "strong":bool}]}}
按 matchNumStr 索引，下游 14:00 报告按编号直接注入，无需队名再匹配。
"""
import html as _html
import json
import re
import sys
import time
import urllib.request
from datetime import date, timedelta

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0 Safari/537.36')
BASE_LIST = 'https://news.zhibo8.com/zuqiu/more.htm?day={d}&page=1'
OUT = 'intel.json'
MAX_ARTICLES = 6
MAX_CHARS = 1400

# 竞彩简称 → 直播吧标题可能出现的叫法
ALIAS = {
    '中国': ['国足', '中国男足', '中国队', '中国'],
    '日本': ['日本男足', '日本队', '日本', '蓝武士', '森保'],
    '巴西': ['巴西'], '新加坡': ['新加坡'], '巴林': ['巴林'],
    '巴拉圭': ['巴拉圭'], '波黑': ['波黑', '波斯尼亚'],
    '罗马尼亚': ['罗马尼亚'], '波兰': ['波兰'], '瑞典': ['瑞典'],
    '丹麦': ['丹麦'], '挪威': ['挪威'], '威尔士': ['威尔士'],
    '葡萄牙': ['葡萄牙'], '匈牙利': ['匈牙利'], '北爱尔兰': ['北爱尔兰'],
    '爱尔兰': ['爱尔兰'], '科索沃': ['科索沃'], '智利': ['智利'],
    '哥伦比亚': ['哥伦比亚'],
}
# 弱匹配的情报关键词
INTEL_KW = ('首发', '伤', '缺', '停赛', '主帅', '告别', '轮换', '复仇', '交锋',
            '前瞻', '聚焦', '看点', '赛前', '出战', '恢复', '训练', '名单',
            '退出', '离队', '就任', '执教', '征召', '入选', '回归', '复出')
# 标题噪音：青年队/女足等非本站赛事
TITLE_BAD = ('U17', 'U21', 'U23', 'U20', '女足', '青年', '国奥', 'U19', 'U18',
             '名人堂', '电竞', '篮球', '排球', '网球', ' NHL', 'NBA',
             '库巴西', '比利亚雷亚尔', '黄潜')
RE_LINK = re.compile(
    r'<span class="articleTitle"><a href="([^"]+)">([^<]+)</a></span>')


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': 'https://news.zhibo8.com/zuqiu/'})
    return urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'ignore')


def aliases(name: str) -> list[str]:
    return ALIAS.get(name, [name])


def source_of(title: str) -> str:
    """从「北青：xxx」「巴媒：xxx」前缀取来源；没有则留整标题前缀空。"""
    m = re.match(r'^([^：:]{2,8})[：:]', title)
    return m.group(1).strip() if m else ''


def article_text(url: str) -> str:
    try:
        h = fetch(url)
    except Exception as e:
        print(f'    [正文失败] {type(e).__name__} {url}')
        return ''
    i = h.find('class="content"')
    if i < 0:
        return ''
    seg = h[i:i + MAX_CHARS * 6]
    # 整块剔除 script/style/iframe/noscript（含块内代码）
    seg = re.sub(r'<(script|style|iframe|noscript)\b[^>]*>.*?</\1\s*>', ' ',
                 seg, flags=re.S | re.I)
    # 去 HTML 注释（<!-- 推广位Id… --> 这类整段）
    seg = re.sub(r'<!--.*?-->', ' ', seg, flags=re.S)
    txt = re.sub(r'<[^>]+>', '', seg)
    txt = _html.unescape(txt)          # &nbsp; → 空格，&amp; → & 等
    txt = re.sub(r'\s+', '', txt)
    txt = txt.replace('class="content">', '', 1)
    # 尾部页脚/广告残片：命中即整段截断（含漏网的推广位、版权条、声明）
    for cut in ('特别声明', '免责声明', '返回搜狐', '责任编辑', '版权保护指引',
                '推广位', '扫码关注', '原文链接', '相关阅读', '相关推荐',
                '本文由', '作者：', '来源：', '点击进入', '更多精彩',
                '举报电话', '举报邮箱', '不良信息举报', '违法和不良信息',
                'ICP备', '营业执照', '公网安备', '增值电信', '互联网新闻',
                '卫生城市', '网文(', '网文（', '文明城市', '新闻网站',
                '友情链接', '联系我们', '用户协议', '隐私政策', '报错反馈',
                '投诉反馈', '有害信息举报专区', '巩固国家', '合作网站',
                '网址导航', '不错过', 'Copyright', 'All Rights Reserved'):
        p = txt.find(cut)
        if p > 0:
            txt = txt[:p]
    # 残留的JS/属性碎片兜底：仅在贴近末尾处出现才砍（阈值放宽到 90%，避免误伤正文域名）
    for token in ('iframe_sdk', 'v12.cn', '.cn"', 'var ', 'window.', 'function('):
        p = txt.rfind(token)
        if p > MAX_CHARS * 0.9:
            txt = txt[:p]
    # 按完整句子截取：在 MAX_CHARS 内最后一个句末标点断开，避免半句
    if len(txt) > MAX_CHARS:
        head = txt[:MAX_CHARS]
        ends = [head.rfind(m) for m in ('。', '！', '？', '!', '?')]
        last = max(ends)
        txt = head[:last + 1] if last >= MAX_CHARS * 0.6 else head
    # 剥掉新闻导语电头：「直播吧11月14日讯/消息」及紧随的「据XX报道/消息，」
    txt = re.sub(r'^直播吧\d{1,2}月\d{1,2}日(?:讯|消息)', '', txt)
    txt = re.sub(r'^据[^，,。？！]{0,30}?(?:报道|消息)(?:称)?[，,]?', '', txt)
    return txt.strip()


# ── 懂球帝赛前情报源（补充直播吧对小联赛的覆盖空缺）─────────────────
DQD_LIST = 'https://m.dongqiudi.com/jingcai/'
DQD_MATCH = 'https://m.dongqiudi.com/jingcai/{mid}'
DQD_NEWS = 'https://m.dongqiudi.com{xid}'
DQD_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
          'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 '
          'Mobile/15E148 Safari/604.1')
DQD_TITLE_BAD = ('战报', '复盘', '集锦', '视频', '进球大战', '全场', '赛后',
                 '专家方案', ' predicts', '预测：', '进球数预测', '比分预测')


def dqd_fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        'User-Agent': DQD_UA, 'Referer': 'https://m.dongqiudi.com/'})
    return urllib.request.urlopen(req, timeout=25).read().decode('utf-8', 'ignore')


def dqd_article_text(h: str) -> str:
    """懂球帝 /xinwen/ 正文：zbm-body 容器 → 去标签、解实体、按句截断。"""
    m = re.search(r'<div class="zbm-body"[^>]*>(.*?)</div>\s*</div>', h, re.S)
    seg = m.group(1) if m else ''
    seg = re.sub(r'<(script|style)\b[^>]*>.*?</\1\s*>', ' ', seg,
                 flags=re.S | re.I)
    txt = _html.unescape(re.sub(r'<[^>]+>', '', seg))
    txt = re.sub(r'\s+', '', txt)
    for cut in ('本文根据', '查看原文', '点击查看完整内容', '懂球帝App里',
                '广告', '相关阅读', '版权声明'):
        p = txt.find(cut)
        if p > 20:
            txt = txt[:p]
    if len(txt) > MAX_CHARS:
        head = txt[:MAX_CHARS]
        last = max(head.rfind(m) for m in ('。', '！', '？', '!', '?'))
        txt = head[:last + 1] if last >= MAX_CHARS * 0.6 else head
    return txt.strip()


def dqd_scan(matches: list) -> dict:
    """从懂球帝竞彩页发现当日比赛 → 按竞彩编号/队名匹配 → 抓各场赛前文章。

    返回 {code: [{'title','url','source','strong'}, ...]}，与直播吧结构一致。
    懂球帝文章是客观赛前数据（积分/近况/交锋/伤停/首发），作为主源。
    """
    assigned: dict[str, list] = {}
    try:
        h = dqd_fetch(DQD_LIST)
    except Exception as e:
        print(f'[懂球帝] 赛程页失败 {type(e).__name__} {e}')
        return assigned
    # 比赛条目：href=/jingcai/<id> + 文案含「周五001」等竞彩编号和队名
    games = {}
    for m in re.finditer(r'href="/jingcai/(\d+)"[^>]*>(.*?)</a>', h, re.S):
        mid = m.group(1)
        label = html_unescape_text(re.sub(r'<[^>]+>', '', m.group(2)))
        if mid not in games:
            games[mid] = label
    print(f'[懂球帝] 赛程页发现 {len(games)} 场')
    if not games:
        return assigned

    # 每场我们的比赛 → 找懂球帝比赛 id（先按竞彩编号，再按双方队名）
    for mm in matches:
        code, home, away = mm['matchNumStr'], mm['home'], mm['away']
        hit_id = ''
        for mid, label in games.items():
            if code and code in label:
                hit_id = mid
                break
        if not hit_id:
            ha, aa = aliases(home), aliases(away)
            for mid, label in games.items():
                if any(x in label for x in ha) and any(x in label for x in aa):
                    hit_id = mid
                    break
        if not hit_id:
            print(f'[懂球帝] {code} {home}vs{away}：未找到比赛页')
            continue
        try:
            gh = dqd_fetch(DQD_MATCH.format(mid=hit_id))
        except Exception as e:
            print(f'[懂球帝] {code} 比赛页失败 {type(e).__name__}')
            continue
        arts, seen = [], set()
        for m in re.finditer(r'href="(/xinwen/\d+)"[^>]*>(.*?)</a>', gh, re.S):
            xid, raw = m.group(1), m.group(2)
            # 来源/时间包在 <i> 里（「懂球帝数据 · 11-20 16:31」），整块剔除
            raw = re.sub(r'<i\b[^>]*>.*?</i\s*>', '', raw, flags=re.S | re.I)
            title = html_unescape_text(re.sub(r'<[^>]+>', '', raw)).strip()
            if not title or len(title) < 6 or xid in seen:
                continue
            seen.add(xid)
            if any(b in title for b in DQD_TITLE_BAD):
                continue
            arts.append({'title': title, 'url': DQD_NEWS.format(xid=xid),
                         'source': '懂球帝', 'strong': True})
        # 关键因素分层排序后取前 N（懂球帝文章多为客观赛前数据，默认 strong）
        TIERS = (
            ('伤', '缺阵', '停赛', '存疑', '伤退', '受伤', '缺席', '无缘'),
            ('首发', '轮换', '出战', '出场', '名单', '征召', '入选', '大名单'),
            ('告别', '主帅', '执教', '离队', '退出', '换帅', '上任'),
            ('前瞻', '数据', '近况', '交锋', '战绩', '往绩', '不败', '交手'),
        )
        def _tier(a):
            for i, ks in enumerate(TIERS):
                if any(k in a['title'] for k in ks):
                    return i
            return len(TIERS)
        arts.sort(key=_tier)
        picked = arts[:MAX_ARTICLES]
        assigned[code] = picked
        print(f'[懂球帝] {code} {home}vs{away}：{len(arts)}篇 取{len(picked)}')
    return assigned


def html_unescape_text(s: str) -> str:
    return _html.unescape(s)


def main() -> int:
    today = date.today()
    days = [str(today), str(today + timedelta(days=1))]
    matches = json.load(open('scripts/matches_data.json', encoding='utf-8'))['matches']

    # 1) 扫列表
    seen, links = set(), []
    for d in days:
        try:
            h = fetch(BASE_LIST.format(d=d))
        except Exception as e:
            print(f'[情报] 列表 {d} 失败：{type(e).__name__} {e}')
            continue
        for u, t in RE_LINK.findall(h):
            u = 'https:' + u if u.startswith('//') else u
            if u not in seen:
                seen.add(u)
                links.append((u, t.strip()))
        print(f'[情报] {d} 列表累计 {len(links)} 篇')
    print(f'[情报] 列表合计 {len(links)} 篇候选')

    # 2) 懂球帝为主源（客观赛前数据，覆盖小联赛），直播吧补充
    assigned = dqd_scan(matches)
    used_url = {a['url'] for arts in assigned.values() for a in arts}
    all_alias = [a for m in matches for x in (m['home'], m['away']) for a in aliases(x)]
    for m in matches:
        code = m['matchNumStr']
        assigned.setdefault(code, [])
        ha, aa = aliases(m['home']), aliases(m['away'])
        mine = set(ha + aa)
        other_alias = set(all_alias) - mine
        strong, weak = [], []
        for u, t in links:
            if u in used_url or any(b in t for b in TITLE_BAD):
                continue
            # 花边噪音：社媒/晒照/合影/热捧/抵达这类无情报价值的标题
            if any(x in t for x in ('社媒', '晒', '合影', '热捧', '球迷', '抵达',
                                    '照片', '飞机', '参观', '观光')):
                continue
            hm = any(x in t for x in ha)
            am = any(x in t for x in aa)
            if hm and am:
                strong.append((u, t))
            elif (hm or am) and any(k in t for k in INTEL_KW):
                # 弱匹配防串场：满足任一即可
                #   a) 含客队名/对手指向词（战某队、对某队）
                #   b) 含重大动态词（告别/主帅/执教/离队/退出/停赛/伤退）——
                #      这类单队新闻本身就是关键情报，如「森保一告别战」
                has_target = am or any(
                    re.search(r'(?:战|对|迎|碰|遇|抗)' + re.escape(x), t) for x in aa)
                major = any(k in t for k in
                            ('告别', '主帅', '执教', '离队', '退出', '停赛',
                             '伤退', '伤势', '缺战', '入选', '征召', '年薪'))
                # 排串场：标题命中别的比赛队名，或「执教/主帅+外部球队」→ 跳过弱匹配
                crosstalk = any(x in t for x in other_alias if x not in mine)
                foreign_club = re.search(
                    r'(?:执教|主帅|教练|出任|接手|离任)\s*([\u4e00-\u9fa5]{2,6})(?:队|国家队|主帅)', t)
                fclub = foreign_club.group(1) if foreign_club else ''
                club_bad = bool(fclub) and fclub not in mine and not any(
                    x in fclub for x in mine)
                if (has_target or major) and not crosstalk and not club_bad:
                    weak.append((u, t))
        # 伤停 > 首发/轮换 > 告别战/换帅 > 战意/走势 > 历史交锋：关键因素优先入选
        TIERS = (
            ('伤', '缺阵', '停赛', '存疑', '伤退', '受伤', '缺席', '无缘'),
            ('首发', '轮换', '出战', '出场', '名单', '征召', '入选', '大名单'),
            ('告别', '主帅', '执教', '离队', '退出', '换帅', '教鞭', '上任'),
            ('复仇', '反弹', '战意', '力争', '冲击', '连败', '连胜', '保级', '争冠'),
            ('历史', '交锋', '战绩', '往绩', '不败', '纪录', '交手'),
        )
        def _tier(t):
            s = t
            for i, ks in enumerate(TIERS):
                if any(k in s for k in ks):
                    return i
            return len(TIERS)
        pool = strong + weak
        pool.sort(key=lambda ut: (_tier(ut[1]), 0 if ut in strong else 1))
        room = max(0, MAX_ARTICLES - len(assigned[code]))
        picked = pool[:room]
        print(f'[情报] {code} {m["home"]}vs{m["away"]}：强{len(strong)}弱{len(weak)} '
              f'懂球帝已{MAX_ARTICLES - room} 直播吧补{len(picked)}')
        for u, t in picked:
            used_url.add(u)
            assigned[code].append({'title': t, 'url': u, 'source': source_of(t),
                                   'strong': (u, t) in strong})

    # 3) 抓正文（懂球帝与直播吧页面结构不同，分流处理）
    for code, arts in assigned.items():
        for a in arts:
            if '/xinwen/' in a['url']:
                try:
                    a['text'] = dqd_article_text(dqd_fetch(a['url']))
                except Exception as e:
                    print(f'    [懂球帝正文失败] {type(e).__name__} {a["url"]}')
                    a['text'] = ''
            else:
                a['text'] = article_text(a['url'])
            if a['text']:
                print(f'    ✅ {code} [{a["source"] or "直播吧"}] '
                      f'{a["title"][:36]} → {len(a["text"])}字')

    result = {'updated': time.strftime('%Y-%m-%d %H:%M'), 'matches': assigned}
    json.dump(result, open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    total = sum(len(v) for v in assigned.values())
    withtext = sum(1 for v in assigned.values() for a in v if a.get('text'))
    print(f'[情报] 合计 {total} 篇 → {OUT}（正文成功 {withtext}）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
