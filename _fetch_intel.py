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
TITLE_BAD = ('U17', 'U21', 'U23', 'U20', '女足', '青年', '国奥', 'U19', 'U18')
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
    return txt.strip()


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

    # 2) 按场次匹配（强/弱分级）
    assigned: dict[str, list[dict]] = {m['matchNumStr']: [] for m in matches}
    used_url = set()
    all_alias = [a for m in matches for x in (m['home'], m['away']) for a in aliases(x)]
    for m in matches:
        code = m['matchNumStr']
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
        picked = (strong + weak)[:MAX_ARTICLES]
        print(f'[情报] {code} {m["home"]}vs{m["away"]}：强{len(strong)}弱{len(weak)} 取{len(picked)}')
        for u, t in picked:
            used_url.add(u)
            assigned[code].append({'title': t, 'url': u, 'source': source_of(t),
                                   'strong': (u, t) in strong})

    # 3) 抓正文
    for code, arts in assigned.items():
        for a in arts:
            a['text'] = article_text(a['url'])
            if a['text']:
                print(f'    ✅ {code} {a["title"][:40]} → {len(a["text"])}字')

    result = {'updated': time.strftime('%Y-%m-%d %H:%M'), 'matches': assigned}
    json.dump(result, open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    total = sum(len(v) for v in assigned.values())
    withtext = sum(1 for v in assigned.values() for a in v if a.get('text'))
    print(f'[情报] 合计 {total} 篇 → {OUT}（正文成功 {withtext}）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
