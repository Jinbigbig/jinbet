# -*- coding: utf-8 -*-
# 由 _calc_result.json + _data_batch*.json 生成 2026-09-05 V2.2 报告
# 版式严格复刻 2026-07-21 风格（与上午云端旧版一致）：CSS 直接取自 _old_0905.html
import json, re, html, datetime, math
from collections import Counter

# 选取算法（比分精选 / 大胆档）统一由 selection_algo 提供，本文件只做渲染。
# 每日优化脚本 _optimize_selection.py 引用同一模块，避免两份实现口径漂移。
import selection_algo as SA

CALC = json.load(open('_calc_result.json', encoding='utf-8'))
MATCHES = CALC['matches']
CALIB = CALC['calibration']
TODAY = CALC['today']

# ---------- 引擎 B：独立比分引擎（双方进球联合分布）----------
# 三套引擎分工（互不影响，各自建模、各自参数、各自可单独回放）：
#   引擎 A 胜平负 → _calc_engine.py 的 prob / 让球盘（本报告 4.1 节）
#   引擎 B 比分   → score_engine.py 的联合分布（本报告 4.2 节与逐场卡片比分区）
#   引擎 C 两档   → selection_algo.py 的比分精选 / 大胆档
try:
    import score_engine as SE
    _SE = SE.engine_asof(TODAY)
    _SCORE = {}
    for _m in MATCHES:
        _k = '%s_%s' % (_m.get('home') or '', _m.get('away') or '')
        try:
            _SCORE[_k] = _SE.predict(_m)
        except Exception:
            _SCORE[_k] = None
    _n_ok = sum(1 for v in _SCORE.values() if v)
    print('  [引擎B·比分] 评级球队 %d 支 / 输出 %d 场' % (len(_SE.teams), _n_ok))
except Exception as _e:
    SE = None
    _SCORE = {}
    print('  [引擎B·比分] 不可用:', _e)


def score_pred(m):
    """本场比分预测（引擎 B 独立输出；不可用时返回 None，页面回退到引擎 A 口径）。"""
    return _SCORE.get('%s_%s' % (m.get('home') or '', m.get('away') or ''))


def _pub_head(m, cells=None):
    """发布首选比分（以快照 `headline` 为准 —— 它由按日统一分配的口径算出）。

    cells 给定时，概率百分比取该列表里的值（保持表格数字与自己的分布一致）；
    快照没有 headline 时才现算（此时按元素自带的 mkt 走新口径）。
    """
    hl = m.get('headline') or {}
    s = hl.get('score')
    if s:
        if cells:
            p = next((t.get('prob') for t in cells if t.get('score') == s), None)
            if p is not None:
                return s, p
        return s, hl.get('prob')
    if cells:
        return SA.headline_pick(cells, SA.direction_key(m))
    return hit_pick(m)


def head_score(m):
    """头条比分 = 发布首选（快照 headline 为准），不可用时回退引擎 B → 引擎 A。"""
    sp = score_pred(m)
    if sp and sp.get('top_scores'):
        return _pub_head(m, sp['top_scores'])
    return hit_pick(m)

# 合并采集数据中的 H2H 明细（history 表用）
H2H = {}
for i in range(1, 7):
    try:
        b = json.load(open(f'_data_batch{i}.json', encoding='utf-8'))
        for m in b['matches']:
            H2H[m['matchNumStr']] = m.get('h2h') or []
    except FileNotFoundError:
        pass
# 回退：当日 matches_data.json 内自算 H2H（results_data 标定库推导）
try:
    _md = json.load(open('scripts/matches_data.json', encoding='utf-8'))
    for m in _md.get('matches', []):
        if m['matchNumStr'] not in H2H or not H2H[m['matchNumStr']]:
            if m.get('h2h'):
                H2H[m['matchNumStr']] = m['h2h']
except FileNotFoundError:
    pass

# ---------- 球队历史底蕴档案（展示层，不参与概率计算）----------
# 数据：club_pedigree.json（联网核查的荣誉档案）
# 说明：荣誉属公开慢变量，已被市场赔率与长期战绩定价；此处仅作定性背景展示。
def _find(name):
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, name), os.path.join(here, '..', name), name,
              os.path.join(here, 'tools', 'prediction', name)):
        if os.path.exists(p):
            return p
    return None


_p = _find('club_pedigree.json')
PED = json.load(open(_p, encoding='utf-8')).get('teams', {}) if _p else {}

OLD = open('_old_0905.html', encoding='utf-8').read()
CSS = re.search(r'<style>.*?</style>', OLD, re.S).group(0)
# 追加：队名右下角排名小字（CSS 变量兜底，兼容浅/深色）
CSS += '''
<style>
  .match-teams .team-rank { display: block; font-size: 0.62rem; font-weight: 400; line-height: 1.1;
    color: var(--muted, #7a8ba0); margin-top: 0.18rem; text-align: right; opacity: 0.9; bottom: auto; }
  .league-tbl { width:100%; border-collapse:collapse; font-size:0.8rem; margin-top:0.35rem; }
  .league-tbl th, .league-tbl td { border-bottom:1px solid rgba(128,128,128,0.22); padding:0.3rem 0.45rem; text-align:left; white-space:nowrap; }
  .league-tbl th { color:var(--muted,#7a8ba0); font-weight:600; font-size:0.72rem; }
  .league-note { font-size:0.76rem; color:var(--muted,#7a8ba0); margin:0.45rem 0 0; line-height:1.55; }
  .league-tbl.standings { display:block; overflow-x:auto; }
  .league-tbl.standings td:nth-child(2) { white-space:nowrap; }
  .league-tbl.standings tr.zone-eu td { background:rgba(46,160,67,0.13); }
  .league-tbl.standings tr.zone-rel td { background:rgba(220,60,60,0.12); }
  .league-tbl.standings td:nth-child(10) { font-weight:700; }
  .league-impact { margin-top:0.6rem; border-top:1px dashed rgba(128,128,128,0.3); padding-top:0.5rem; }
  .league-impact .impact-title { font-size:0.74rem; font-weight:700; color:var(--muted,#7a8ba0); margin-bottom:0.3rem; }
  .league-impact .impact-row { font-size:0.78rem; line-height:1.7; }
  .league-impact .impact-row b { color:var(--accent,#2f7de0); }
  .league-src { font-size:0.72rem; color:var(--muted,#7a8ba0); margin-bottom:0.4rem; }
</style>'''
# 第六节已改为按当日实际联赛动态生成（见 build_league_sec），不再回收旧报告静态段落

def build_league_sec(matches):
    """六、当日赛事联赛形势：用 7M 真实积分榜，每联赛单独一张卡。
    含：当前积分榜（排名/赛/胜平负/进失/净/分，欧冠·欧联·降级区着色）
        + 本日对阵积分影响（双方当前排名与积分，及本场胜负对积分的摆动）。
    未来赛程：7M 数据库不含，本节日聚焦「当前排名 + 本日对阵影响」；
    7M 未收录的联赛（美职联 MLS、韩职 K 联赛等）改用联网核查的权威积分榜补充。"""
    import league_match as LM
    from collections import OrderedDict
    league_data = {}
    try:
        league_data = json.load(open('league_data.json', encoding='utf-8')).get('leagues', {})
    except Exception:
        league_data = {}
    idx = LM.build_index(league_data)
    grouped = OrderedDict()
    for m in matches:
        grouped.setdefault(m.get('league') or '未知', []).append(m)
    out = ['<h2>六、当日赛事联赛与杯赛形势</h2>',
           '<p style="font-size:0.85rem;color:var(--muted);margin:0 0 0.8rem;">'
           '积分榜数据来源 <b>7M 体育数据库</b>（截至各联赛最近更新）。'
           '当前数据源不含未来赛程，故本节日聚焦「当前排名 + 本日对阵对积分榜的影响」；'
           '7M 未收录的联赛（美职联 MLS、韩职 K 联赛等）用联网核查的权威积分榜补充。'
           .replace('。。', '。') + '</p>',
           '<div class="league-overview-grid">']
    for lg, ms in grouped.items():
        out.append('  <div class="league-card">')
        # 美职：数据源缺失，直接说明
        if lg in LM.UNAVAILABLE:
            out.append(f'    <h4>{esc(lg)}</h4>')
            out.append(f'    <p class="league-note">{esc(LM.UNAVAILABLE[lg])}。本节其余联赛展示真实积分榜。</p>')
            out.append('  </div>')
            continue
        if lg in CUP_EXTRA:
            out.extend(cup_card(lg, ms))
            out.append('  </div>')
            continue
        parsed = league_data.get(lg)
        if not parsed or not parsed.get('teams'):
            out.append(f'    <h4>{esc(lg)}</h4>')
            out.append('    <p class="league-note">本联赛暂无可用积分榜数据源，跳过。</p>')
            out.append('  </div>')
            continue
        season = parsed.get('season_zh') or parsed.get('season', '')
        updated = parsed.get('summary', {}).get('last_update', '')
        out.append(f'    <h4>{esc(lg)} <span style="font-weight:400;font-size:0.78rem;color:var(--muted);">· {esc(season)}</span></h4>')
        out.append(f'    <div class="league-src">数据更新：{esc(updated)} ｜ 来源 7M 体育数据库</div>')
        # 积分榜
        out.append('    <table class="league-tbl standings">')
        out.append('      <tr><th>#</th><th>球队</th><th>赛</th><th>胜</th><th>平</th><th>负</th>'
                   '<th>进</th><th>失</th><th>净</th><th>分</th></tr>')
        for t in parsed['teams']:
            note = t.get('note_zh') or t.get('note', '') or ''
            if '盃' in note or '杯' in note:
                zone = 'zone-eu'
            elif '降' in note:
                zone = 'zone-rel'
            else:
                zone = ''
            out.append(
                f'      <tr class="{zone}">'
                f'<td>{t["rank"]}</td>'
                f'<td style="text-align:left;">{esc(t.get("name_zh") or t["name"])}</td>'
                f'<td>{t["p"]}</td><td>{t["w"]}</td><td>{t["d"]}</td><td>{t["l"]}</td>'
                f'<td>{t["gf"]}</td><td>{t["ga"]}</td><td>{t["gd"]}</td>'
                f'<td>{t["pts"]}</td></tr>')
        out.append('    </table>')
        # 本日对阵 · 积分影响
        out.append('    <div class="league-impact">')
        out.append('      <div class="impact-title">本日对阵 · 积分影响</div>')
        for m in ms:
            h = LM.match_team(m['home'], lg, idx)
            a = LM.match_team(m['away'], lg, idx)
            hinfo = f'#{h["rank"]} {h["pts"]}分' if h else '排名—'
            ainfo = f'#{a["rank"]} {a["pts"]}分' if a else '排名—'
            swing = ''
            if h and a:
                gap = h['pts'] - a['pts']
                swing = f'（分差 {gap:+d}）'
                if h['rank'] != a['rank'] and abs(gap) <= 3:
                    swing += ' · 卡位对话'
            out.append(
                f'      <div class="impact-row"><span class="tag tag-blue">{esc(m["matchNumStr"])}</span> '
                f'{esc(m["home"])} <b>{hinfo}</b> vs {esc(m["away"])} <b>{ainfo}</b>{esc(swing)}</div>')
        out.append('    </div>')
        # 模型看点（一句话，公开页安全）
        _note = league_note(ms)
        if _note:
            out.append(f'    <p class="league-note">{_note}</p>')
        out.append('  </div>')
    out.append('</div>')
    return '\n'.join(out)


# ── 杯赛附加数据（英锦标赛 2026-27 小组赛）──────────────────────────────
# 来源：7M 体育数据库 / BBC Sport / ESPN（小组表）、新浪体育（赛制）
CUP_EXTRA = {
    '英锦标赛': {
        'title': "英锦标赛（Jersey Mike's Trophy）2026-27",
        'src': '小组数据来源：7M 体育数据库 / BBC Sport / ESPN ｜ 赛制来源：新浪体育',
        'rules': [
            '参赛 64 队：英甲 24 队 + 英乙 24 队 + 16 支英超一级学院(U21)队；分南北两区、每区 8 组、每组 4 队。',
            '小组赛单循环（每队 3 场），每组前 2 名晋级 32 强淘汰赛；小组第一为种子，32 强主场对阵他组第二。',
            '计分：胜 3 分、平 1 分、负 0 分；小组赛战平直接点球决胜，点球取胜方额外得 1 分（平局双方共得 2 分）。',
            '淘汰赛自 32 强起单场决胜，90 分钟战平直接点球；决赛 2027-04-11 于温布利球场举行。',
        ],
        'groups': [
            {'name': '北部 B 组', 'teams': [
                ('维冈竞技', 1, 1, 0, 0, 3, 2, 3),
                ('布莱克浦', 0, 0, 0, 0, 0, 0, 0),
                ('克鲁', 0, 0, 0, 0, 0, 0, 0),
                ('阿斯顿维拉 U21', 1, 0, 0, 1, 2, 3, 0)],
             'note': '维冈竞技已完成小组首战（3-2 胜阿斯顿维拉 U21），本场为布莱克浦的小组首秀；克鲁与阿斯顿维拉 U21 同轮相遇。'},
            {'name': '北部 F 组', 'teams': [
                ('格林斯比', 0, 0, 0, 0, 0, 0, 0),
                ('诺茨郡', 0, 0, 0, 0, 0, 0, 0),
                ('伯顿艾尔宾', 0, 0, 0, 0, 0, 0, 0),
                ('诺丁汉森林 U21', 0, 0, 0, 0, 0, 0, 0)],
             'note': '本组尚无球队出场，本轮两场同时开打：诺茨郡 vs 格林斯比、伯顿艾尔宾 vs 诺丁汉森林 U21。'},
            {'name': '南部 H 组', 'teams': [
                ('布伦特福德 U21', 0, 0, 0, 0, 0, 0, 0),
                ('布罗姆利', 0, 0, 0, 0, 0, 0, 0),
                ('克劳利镇', 0, 0, 0, 0, 0, 0, 0),
                ('米尔顿凯恩斯', 0, 0, 0, 0, 0, 0, 0)],
             'note': '本组尚无球队出场，本轮两场同时开打：米尔顿凯恩斯 vs 克劳利镇、布罗姆利 vs 布伦特福德 U21。'},
        ],
        'league_ctx': [
            '米尔顿凯恩斯：英甲第 22 位（7 战 0 胜 6 平 1 负，8:10，6 分），仍在降级区边缘，英甲仅有的两支未赢球球队之一。',
            '维冈竞技：英甲第 24 位（7 战 1 胜 1 平 5 负，5:12，4 分），积分榜垫底。',
            '克劳利镇：英乙积分榜末位（7 轮 4 分），联赛三连败，防守端 7 轮丢 13 球。',
            '诺茨郡：英甲下游（近 10 场各项赛事仅 1 胜）；格林斯比：英乙中上游（近 10 场 4 胜 4 平 2 负）。',
        ],
        'next': [
            ('2026-10-07', '布莱克浦 vs 克鲁', '北部 B 组'),
            ('2026-10-07', '米尔顿凯恩斯 vs 布伦特福德 U21', '南部 H 组'),
            ('2026-10-07', '伯顿艾尔宾 vs 格林斯比', '北部 F 组'),
        ],
    },
    '亚运男足': {
        'title': '2026 爱知名古屋亚运会男足 · 1/4 决赛',
        'src': '小组积分与赛制来源：出奇体育 ｜ 淘汰赛程来源：亚奥理事会公开赛程 ｜ 赔率：网易彩票',
        'rules': [
            '参赛 15 队（伊拉克抽签前退出）：A/B/C 组各 4 队、D 组 3 队；小组前两名晋级 8 强淘汰赛。',
            '年龄限制：参赛球员原则上须为 2003-01-01 及以后出生，每队最多报名 3 名超龄球员。',
            '淘汰赛 90 分钟战平进入上下半场各 15 分钟加时，仍平则点球决胜。',
            '小组赛已于前三轮结束，本日（09-26）为 1/4 决赛日：A1 日本 U23 vs B2 朝鲜 U23、B1 中国 U23 vs A2 泰国 U23。',
        ],
        'groups': [
            {'name': 'A 组', 'teams': [
                ('日本 U23', 3, 3, 0, 0, 12, 0, 9),
                ('泰国 U23', 3, 2, 0, 1, 8, 6, 6),
                ('吉尔吉斯斯坦 U23', 3, 1, 0, 2, 6, 10, 3),
                ('中国香港 U23', 3, 0, 0, 3, 1, 11, 0)],
             'note': '日本 U23 三战全胜且零失球（12:0）居首，泰国 U23 以小组第二出线，两队分列本日两场 1/4 决赛对阵。'},
            {'name': 'B 组', 'teams': [
                ('中国 U23', 3, 1, 2, 0, 2, 1, 5),
                ('朝鲜 U23', 3, 1, 1, 1, 5, 3, 4),
                ('伊朗 U23', 3, 1, 1, 1, 4, 5, 4),
                ('阿联酋 U23', 3, 0, 2, 1, 1, 3, 2)],
             'note': '中国 U23 以 1 胜 2 平、仅失 1 球拿下 B 组第一（失球为小组最低）；朝鲜 U23 净胜球优势压过伊朗，列小组第二晋级。'},
            {'name': 'C 组', 'teams': [
                ('乌兹别克斯坦 U23', 3, 3, 0, 0, 9, 1, 9),
                ('越南 U23', 3, 1, 1, 1, 3, 3, 4),
                ('菲律宾 U23', 3, 1, 0, 2, 3, 8, 3),
                ('科威特 U23', 3, 0, 1, 2, 2, 5, 1)],
             'note': '乌兹别克斯坦 U23 三战全胜（9:1）列 C 组第一，越南 U23 以小组第二出线。'},
            {'name': 'D 组', 'teams': [
                ('韩国 U23', 2, 2, 0, 0, 6, 1, 6),
                ('沙特阿拉伯 U23', 2, 1, 0, 1, 2, 2, 3),
                ('卡塔尔 U23', 2, 0, 0, 2, 1, 6, 0)],
             'note': 'D 组 3 队单循环、每队 2 场：韩国 U23 全胜居首，沙特阿拉伯 U23 次席，卡塔尔 U23 两连败出局。'},
        ],
        'impact_title': '本日对阵 · 晋级形势',
        'impact_note': '1/4 决赛为单场淘汰制：90 分钟战平进入加时、再平点球决胜，胜者晋级半决赛，负者直接出局（不涉及小组积分）。',
        'ctx_title': '参赛队处境与小组赛表现',
        'league_ctx': [
            '中国 U23（B 组第一）：小组赛 1 胜 2 平仅失 1 球，防守端为 B 组最稳；进攻端 3 场仅入 2 球，攻坚效率是隐患；1/4 决赛对阵 A 组第二泰国 U23。',
            '日本 U23（A 组第一）：小组赛 3 战全胜、12 球 0 失球，为赛事进攻与防守双料第一，1/4 决赛对阵 B 组第二朝鲜 U23。',
            '泰国 U23（A 组第二）：小组赛 2 胜 1 负，8 进 6 失，进攻火力仅次日本。',
            '朝鲜 U23（B 组第二）：小组赛 1 胜 1 平 1 负，5 进 3 失，与伊朗 U23 同分凭净胜球出线。',
            '其余两场 1/4 决赛：C1 乌兹别克斯坦 U23 vs D2 沙特阿拉伯 U23、D1 韩国 U23 vs C2 越南 U23。',
        ],
        'next_title': '后续赛程（淘汰赛）',
        'next': [
            ('2026-09-26', '中国 U23 vs 泰国 U23', '1/4 决赛（本日）'),
            ('2026-09-26', '日本 U23 vs 朝鲜 U23', '1/4 决赛（本日）'),
            ('待官方公布', '半决赛（1/4 决赛胜者对阵）', '亚奥理事会赛程'),
            ('待官方公布', '三四名决赛 / 决赛', '亚奥理事会赛程'),
        ],
        'next_note': '本届亚运会男足淘汰赛后续日期以亚奥理事会（OCA）官方公布为准；2 场 1/4 决赛胜者进入半决赛。',
    },
    '韩职': {
        'title': 'K 联赛 1 2026 · 第 31 轮',
        'src': '积分榜来源：WhenIsTheMatch（API-Football 数据，更新至 2026-09-24）/ SoccerStatsHub ｜ 赛程与赔率：网易彩票 ｜ 赛制：韩国职业足球联盟',
        'rules': [
            '12 队三循环共 33 轮常规赛；常规赛结束后前 6 名进入争冠组（Final A）、后 6 名进入保级组（Final B），各再打 5 轮。',
            '冠军与亚冠精英联赛资格由 Final A 最终排名决定；Final B 末位直接降级，倒数第二参加升降级附加赛。',
            '本日 周日001 江原FC（第 5，29 战 42 分）主场对阵仁川联（第 9，29 战 38 分），为争冠组席位的直接卡位战。',
        ],
        'groups': [
            {'name': 'K 联赛 1 积分榜（截至 2026-09-24）', 'teams': [
                ('FC首尔', 30, 19, 5, 6, 56, 25, 62),
                ('蔚山现代', 30, 14, 5, 11, 45, 40, 47),
                ('济州联', 30, 12, 10, 8, 35, 29, 46),
                ('全北现代', 30, 11, 11, 8, 38, 28, 44),
                ('江原FC', 29, 10, 12, 7, 36, 28, 42),
                ('大田韩亚市民', 30, 10, 10, 10, 46, 37, 40),
                ('浦项制铁', 30, 11, 7, 12, 28, 34, 40),
                ('FC安养', 30, 9, 11, 10, 38, 47, 38),
                ('仁川联', 29, 10, 8, 11, 36, 33, 38),
                ('金泉尚武', 30, 5, 18, 7, 30, 36, 33),
                ('富川1995', 30, 7, 11, 12, 31, 40, 32),
                ('光州FC', 30, 1, 12, 17, 21, 63, 15)],
             'note': 'FC首尔以 62 分领跑（领先次席 15 分）；第 5 至第 9 名（江原 42、大田 40、浦项 40、安养 38、仁川 38）仅差 4 分，争冠组席位争夺集中在 5-8 位之间；光州FC 15 分基本锁定降级区。'},
        ],
        'impact_title': '本日对阵 · 积分影响',
        'impact_note': '江原FC 42 分列第 5、仁川联 38 分列第 9，分差 4 分：江原取胜可稳住争冠组席位；仁川取胜则把差距缩小到 1 分并直接逼近前 6，是本轮最关键的卡位战。',
        'ctx_title': '本日两队处境',
        'league_ctx': [
            '江原FC（第 5，42 分）：本季 29 战 10 胜 12 平 7 负，平局率高达 41%，主场 6 胜 3 平 4 负；争冠组席位仍不稳固，剩余赛程需稳住主场拿分。',
            '仁川联（第 9，38 分）：本季 29 战 10 胜 8 平 11 负，客场 5 胜 4 平 4 负，防守端失球 33 个少于江原；若本场取胜将把分差缩小至 1 分，重燃争冠组希望。',
            '两队同处争冠组与保级组的分水岭区间，本场胜负对第二阶段分组归属影响直接。',
        ],
        'next_title': '后续赛程',
        'next': [
            ('待官方公布', 'K 联赛 1 第 32 轮', '常规赛'),
            ('待官方公布', 'K 联赛 1 第 33 轮（常规赛收官）', '常规赛'),
            ('待官方公布', 'Final A / Final B 分组赛（前 6 / 后 6 各 5 轮）', '争冠组 / 保级组'),
        ],
        'next_note': 'K 联赛 1 常规赛剩余轮次与分组赛日期以韩国职业足球联盟（K League）官方赛程为准。',
    },
    '美职': {
        'title': 'MLS 2026 美职联 · 东区',
        'src': '积分榜来源：FOX Sports（MLS Standings，2026-09-27 更新）｜ 赛程与赔率：网易彩票 ｜ 赛制：MLS 官方',
        'rules': [
            'MLS 分东、西两个分区（东区 15 队、西区 14 队），常规赛每队 34 场；积分不计加时，胜 3 分、平 1 分。',
            '季后赛名额按分区排名分配：东、西区各前 9 名进入季后赛，其中分区第 8、9 名需先进行单场外卡赛。',
            '全联盟常规赛积分最高者获得支持者盾（Supporters\u2019 Shield）；东区第 3 的迈阿密国际已处于季后赛上半区，东区第 14 的哥伦布机员须在剩余赛程大幅追分。',
        ],
        'groups': [
            {'name': 'MLS 东区积分榜（截至 2026-09-27）', 'teams': [
                ('纳什维尔SC', 27, 18, 6, 3, 55, 21, 60),
                ('新英格兰革命', 27, 14, 5, 8, 45, 33, 47),
                ('迈阿密国际', 26, 12, 10, 4, 63, 48, 46),
                ('夏洛特FC', 27, 12, 7, 8, 47, 38, 43),
                ('芝加哥火焰', 26, 12, 6, 8, 46, 38, 42),
                ('费城联合', 27, 11, 6, 10, 54, 44, 39),
                ('奥兰多城', 27, 10, 4, 13, 48, 64, 34),
                ('纽约红牛', 26, 9, 6, 11, 34, 48, 33),
                ('纽约城', 27, 8, 9, 10, 41, 36, 33),
                ('辛辛那提FC', 26, 8, 9, 9, 55, 64, 33),
                ('华盛顿联', 25, 6, 11, 8, 31, 39, 29),
                ('多伦多FC', 27, 6, 11, 10, 39, 51, 29),
                ('亚特兰大联', 27, 7, 6, 14, 32, 45, 27),
                ('哥伦布机员', 26, 7, 5, 14, 37, 42, 26),
                ('蒙特利尔', 27, 6, 6, 15, 34, 54, 24)],
             'note': '纳什维尔SC 以 60 分领跑东区；迈阿密国际 46 分列第 3（进攻端 63 球为东区最高，但 48 个失球偏多）；哥伦布机员 26 分列第 14，与东区第 9 名（33 分）相差 7 分，剩余赛程需连续拿分才能重返季后赛区。'},
        ],
        'impact_title': '本日对阵 · 积分影响',
        'impact_note': '迈阿密国际（第 3，46 分）客场取胜可巩固季后赛上半区与首轮主场优势；哥伦布机员（第 14，26 分）主场取胜才能把与季后赛区的差距缩小到 4 分。',
        'ctx_title': '本日两队处境',
        'league_ctx': [
            '迈阿密国际（东区第 3，46 分，26 战 12 胜 10 平 4 负）：进攻端 63 球为东区最高，但防守端 48 个失球在季后赛球队中偏多，近期连续高比分（6-4、5-3）说明攻强守弱特征明显。',
            '哥伦布机员（东区第 14，26 分，26 战 7 胜 5 平 14 负）：主场 5 胜 2 平 6 负明显好于客场（2 胜 3 平 8 负），剩余赛程抢分压力大。',
            '本季上次交手（2026-08-01）双方 2-2 战平，哥伦布主场对迈阿密近年并非完全处于下风。',
        ],
        'next_title': '后续赛程',
        'next': [
            ('待官方公布', 'MLS 常规赛剩余轮次', '东区'),
            ('待官方公布', 'MLS 季后赛外卡赛（东/西区第 8 vs 第 9）', '季后赛'),
            ('待官方公布', 'MLS 季后赛分区半决赛 / 决赛', '季后赛'),
        ],
        'next_note': 'MLS 常规赛收官与季后赛具体日期以 MLS 官方公布为准。',
    },
    '亚运女足': {
        'title': '2026 爱知·名古屋亚运会女足 · 半决赛',
        'src': '赛程与赔率：网易彩票 ｜ 晋级历程与球队近况：新浪体育 / 腾讯新闻 / 网易体育公开报道 ｜ 赛制：亚奥理事会（OCA）',
        'rules': [
            '亚运会女足共 12 队参赛，先进行小组单循环，随后进入 8 强单场淘汰制（1/4 决赛 → 半决赛 → 决赛）。',
            '淘汰赛为单场决胜：90 分钟战平进入加时赛，加时仍平则以点球决胜；胜者晋级、负者进入三四名决赛。',
            '本日为女足半决赛日：上半区日本女足 vs 韩国女足（静冈体育场 Ecopa），下半区朝鲜女足 vs 中国女足；两场胜者进入 10 月 2 日冠亚军决赛。',
            '本届女足赛事 9 月 14 日揭幕，冠亚军决赛与三四名决赛安排于 2026 年 10 月 2 日（爱知·名古屋亚运会女足决赛日）。',
        ],
        'groups': [],
        'impact_title': '本日对阵 · 晋级形势',
        'impact_note': '半决赛为单场淘汰、无积分计算：胜者晋级 10 月 2 日冠亚军决赛，负者转入三四名决赛；90 分钟战平将进入加时与点球。',
        'ctx_title': '四强晋级历程与关键看点',
        'league_ctx': [
            '朝鲜女足（FIFA 第 11）：本届 4 战轰入 24 球仅失 2 球，小组赛 10-0 孟加拉国、8-0 缅甸，1/4 决赛 5-1 中国台北；阵中 8 名球员来自女足亚冠冠军「我故乡女足」，高位逼抢加快速反击、得分点分散，主帅李裕一称球队「下半场更强、体系成熟」。',
            '中国女足（FIFA 第 16）：1/4 决赛对越南 30 次射门、11 次射正、17 个角球，直到王霜第 109 分钟破门才以 1-0 加时过关，进攻转化率是最大短板，且比对手多打 30 分钟消耗更大；伤停名单：陈晨（赛前伤未随队）、张琳艳（小组赛受伤）、李晴潼（1/4 决赛前热身受伤）、王爱芳（比赛中伤退）、王妍雯（累计黄牌停赛），邵子钦从葡萄牙归队补充锋线。',
            '中朝交锋：两队最近一次正式交锋为 2026 年 3 月女足亚洲杯小组赛，中国 2-1 逆转朝鲜（该场为主帅米利西奇的「帅位之战」）；中国媒体普遍提醒「90 分钟内顶住朝鲜高强度逼抢、避免被反击打穿」是本场取胜前提。',
            '日本女足（FIFA 第 8，东道主）：4 战全胜、24 球 0 失球（8-0 泰国、8-0 越南、4-0 中国台北、4-0 菲律宾），场均 6 球；宝田沙织 6 球领跑射手榜、神谷千菜前 4 场成年国家队比赛场场进球；门将与后防持续轮换，浅野菜摘预计半决赛首发，中场由盐越柚步、宝田沙织、柳濑枫菜构成。',
            '韩国女足：小组赛 5-0 缅甸、6-0 孟加拉国、1-1 朝鲜，以小组第二出线，1/4 决赛 6-3 乌兹别克斯坦（尹秀贞帽子戏法、崔宥利两球），时隔 8 年重返亚运四强；本届 4 战入 18 球失 4 球，但 1/4 决赛单场丢 3 球显示防线不稳。',
            '日韩交锋：A 级赛事韩国 4 胜 12 平 20 负全面落后，2015 年后再未击败日本，2026 年 3 月亚洲杯半决赛日本 4-1 大胜；韩国主帅申尚宇赛前表示「目标是决赛、改变奖牌颜色」，球队优势仅在进攻端的爆发力与反击速度。',
        ],
        'next_title': '后续赛程（淘汰赛）',
        'next': [
            ('2026-09-29', '朝鲜女 vs 中国女', '半决赛（本日）'),
            ('2026-09-29', '日本女 vs 韩国女', '半决赛（本日）'),
            ('2026-10-02', '三四名决赛（两场半决赛负者）', '决赛日'),
            ('2026-10-02', '冠亚军决赛（两场半决赛胜者）', '决赛日'),
        ],
        'next_note': '决赛与三四名决赛定于 2026 年 10 月 2 日（亚运会女足冠亚军决赛日）；具体开球时间以亚奥理事会与组委会官方公布为准。',
    },
    '日联赛杯': {
        'title': '2026/27 J 联赛 YBC 卢万杯 · 第二轮',
        'src': '赛制与对阵：J.LEAGUE 官方 / 懂球帝 / 7M 体育资料库 ｜ 赛程与赔率：网易彩票',
        'rules': [
            '卢万杯（YBC Levain Cup）为 J1/J2/J3 三级俱乐部混编参加的单场淘汰杯赛，2026/27 赛季共约 60 队参赛，赛制为三轮淘汰后进入半准决赛及以后阶段。',
            '首轮 22 场比赛已于 9 月 7-9 日结束（跨级别爆冷：鸟取飞翔 3-1 淘汰 J2 榜首 RB 大宫松鼠、FC 大阪 3-0 甲府风林、金泽塞甘、岐阜 FC、北九州向日葵、熊本深红等晋级）。',
            '第二轮 16 场于本日（9 月 29 日）一天内进行，浦和红钻、广岛三箭、川崎前锋、横滨水手等 J1 球队自此轮起首次亮相；第二轮为单场决胜，90 分钟战平直接点球决胜。',
            '第二轮 16 场胜者晋级 10 月 14 日进行的第三轮；本日竞彩仅投放其中 4 场（藤枝 MYFC vs 大阪樱花、枥木城 vs 广岛三箭、富山胜利 vs 浦和红钻、山形山神 vs 横滨水手），均为 J 联赛低级别主队对阵 J1 客队。',
        ],
        'groups': [],
        'impact_title': '本日对阵 · 晋级形势',
        'impact_note': '单场淘汰制：90 分钟战平直接进入点球决胜，胜者晋级 10 月 14 日第三轮；J1 客队普遍存在轮换与「尽快解决战斗」倾向，平局后点球是小比分走势的主要来源。',
        'ctx_title': '本日 4 场对阵背景',
        'league_ctx': [
            '藤枝 MYFC vs 大阪樱花（19:00）：大阪樱花为 J1 球队、本轮首次亮相，阵容深度与个人能力占优；藤枝 MYFC 经首轮晋级、主场作战，主要依靠紧凑防守与快速反击争取爆冷。',
            '枥木城 vs 广岛三箭（19:00，CITY FOOTBALL STATION）：广岛三箭为 J1 强队且本轮首次亮相，竞彩客胜低至 1.12、让两球，市场给出当日最大实力差；枥木城依靠主场氛围与单场淘汰的不确定性搏冷。',
            '富山胜利 vs 浦和红钻（19:00）：浦和红钻为 J1 传统豪门、亚冠冠军球队，本轮首次亮相；富山胜利主场迎战，让球盘仅为客队让一球，是三场「低级别主队 vs J1 客队」中让球最浅的一场。',
            '山形山神 vs 横滨水手（19:00，NDsoft 山形体育场）：横滨水手为 J1 进攻型球队，客场让一球；山形山神主场以整体防守和定位球见长，若能在前 30 分钟不失球，比赛将进入其擅长的消耗节奏。',
            '赛制提示：第二轮 16 场同日开打，J1 球队需兼顾联赛与后续杯赛，轮换幅度普遍较大，是判断比分时最重要的变量。',
        ],
        'next_title': '后续赛程（第二轮 16 场对阵 · 本日）',
        'next': [
            ('2026-09-29', '松本山雅 vs 新泻天鹅', '第二轮'),
            ('2026-09-29', '金泽塞甘 vs 清水心跳', '第二轮'),
            ('2026-09-29', '藤枝 MYFC vs 大阪樱花（竞彩）', '第二轮'),
            ('2026-09-29', '枥木城 vs 广岛三箭（竞彩）', '第二轮'),
            ('2026-09-29', '富山胜利 vs 浦和红钻（竞彩）', '第二轮'),
            ('2026-09-29', '山形山神 vs 横滨水手（竞彩）', '第二轮'),
            ('2026-09-29', '岐阜 FC vs 横滨 FC', '第二轮'),
            ('2026-09-29', '北海道札幌 vs 冈山绿雉', '第二轮'),
            ('2026-09-29', '北九州向日葵 vs 名古屋鲸鱼', '第二轮'),
            ('2026-09-29', '熊本深红 vs 川崎前锋', '第二轮'),
            ('2026-09-29', '磐田喜悦 vs 千叶市原', '第二轮'),
            ('2026-09-29', 'FC 大阪 vs 福冈黄蜂', '第二轮'),
            ('2026-09-29', '鸟栖砂岩 vs 东京绿茵', '第二轮'),
            ('2026-09-29', '鸟取飞翔 vs 长崎成功丸', '第二轮'),
            ('2026-09-29', '爱媛 FC vs FC 东京', '第二轮'),
            ('2026-09-29', '福岛联 vs 水户蜀葵', '第二轮'),
            ('2026-10-14', '第三轮（16 场胜者参加）', '第三轮'),
            ('待官方公布', '半准决赛及以后阶段', '淘汰赛'),
        ],
        'next_note': '第二轮 16 场于 2026 年 9 月 29 日进行（90 分钟战平直接点球决胜），胜者晋级 10 月 14 日第三轮；半准决赛及以后阶段的日期与参赛队以 J.LEAGUE 官方公布为准。',
    },
    '国际赛': {
        'title': '国际友谊赛 · 9 月国际比赛日',
        'src': '赛程与赔率：网易彩票 ｜ 球队近况与伤停：500 彩票 / 球迷屋 / 出奇体育等公开赛前报道',
        'rules': [
            '国际友谊赛为国际足联认定的非正式比赛，不计入世界杯或洲际杯预选赛积分，无积分榜与升降级。',
            '换人名额按国际足联现行规则通常为 5 人次（含中场），双方以磨合阵容、考察新人为主要目的，轮换幅度普遍较大。',
            '本日两场：周二002 澳大利亚 vs 巴西（布里斯班，两队本月第二场热身）与周二015 美国 vs 智利（圣路易斯）。',
        ],
        'groups': [],
        'impact_title': '本日对阵 · 比赛性质',
        'impact_note': '友谊赛胜负不影响任何积分与排名，但影响阵容试验与球员状态评估；竞猜角度需重点考虑轮换幅度、比赛强度与热身属性。',
        'ctx_title': '双方近况与伤停',
        'league_ctx': [
            '澳大利亚 vs 巴西（布里斯班，本日 18:00）：9 月 25 日首战澳大利亚主场 1-1 巴西（伊兰昆达第 68 分钟任意球破门，拉扬补时头球扳平）。澳大利亚近 6 场友谊赛 0 胜 2 平 4 负、进 3 失 9，但主场近 6 场 3 胜 3 平保持不败；伤停方面，中场沃尔帕托、特里温与后卫伯吉斯、乔丹·博斯缺阵。',
            '巴西近 6 场友谊赛 3 胜 2 平 1 负（进 14 失 8），近 6 个客场 2 胜 2 平 2 负；首战控球 65%、射正 5 次却仅靠补时扳平，主帅安切洛蒂本场预计做出约 7 处调整，奥塔维奥有望完成国家队首秀，维尼修斯继续坐镇左路。两队历史 12 次交手，澳大利亚 1 胜 3 平 8 负。',
            '美国 vs 智利（圣路易斯）：美国（FIFA 第 16）上一场主场 4-1 大胜秘鲁，全队无核心伤停，波切蒂诺麾下 17 岁阿尔伯特造点、16 岁沙利文登场，年轻化阵容主场作战体能与氛围占优。',
            '智利（FIFA 第 49）近况低迷，上一场 0-1 负加拿大且两度被罚下、长时间 9 人应战；本场队长苏亚索（两黄一红）与前锋塞佩达（直红）双双停赛，阿拉韦纳等主力伤缺，攻防两端人员折损严重。',
            '赔率结构：澳大利亚受让一球（+1）返还 1.80、巴西 -1 让球 1.80，客胜 1.23，市场倾向巴西但让球盘留有悬念；美国主胜 1.35、让一球 2.13，市场对美国取胜信心较高。',
        ],
        'next_title': '后续安排',
        'next': [
            ('2026 年 10 月国际比赛日', '双方后续热身赛安排', '友谊赛'),
            ('2026 年 11 月国际比赛日', '双方后续热身赛安排', '友谊赛'),
        ],
        'next_note': '双方后续热身赛安排以各自足协官方公布为准。',
    },
    '欧国联': {
        'title': '2026-27 欧洲国家联赛 · 联赛阶段第 2 轮',
        'src': '积分榜来源：第 1 轮赛果汇总（直播吧 / 搜狐体育 / 网易体育，2026-09-27）｜ 赛程与赔率：网易彩票 ｜ 赛制：欧足联（UEFA）',
        'rules': [
            '赛事为第 5 届欧洲国家联赛，共 54 队参赛、分 A/B/C/D 四个级别；A 级 4 组每组 4 队，B 级 4 组每组 4 队，C 级 4 组每组 4 队，D 级 2 组每组 3 队。',
            '本日为联赛阶段第 2 轮：A 级 A3 组、B 级 B1 组、C 级 C3 组与 C4 组在本日进行第二轮（各组第一轮已于 9 月 26-27 日完赛）。',
            'A 级 A3 组：西班牙、克罗地亚、英格兰、捷克（本日 捷克 vs 英格兰、西班牙 vs 克罗地亚）；B 级 B1 组：苏格兰、瑞士、斯洛文尼亚、北马其顿（本日 苏格兰 vs 瑞士、斯洛文尼亚 vs 北马其顿）；C 级 C3 组：哈萨克斯坦、斯洛伐克、法罗群岛、摩尔多瓦（本日 斯洛伐克 vs 哈萨克斯坦）；C 级 C4 组：冰岛、保加利亚、爱沙尼亚、卢森堡（本日 卢森堡 vs 冰岛、保加利亚 vs 爱沙尼亚）。',
            '赛制与晋级：各组主客双循环；A 级各组前两名晋级淘汰赛阶段（8 强），B/C 级各组头名升级，升降级附加赛与 D 级合并细则以欧足联官方公布为准。',
        ],
        'groups': [
            {'name': 'A 级第 3 组（第 1 轮后）', 'teams': [
                ('西班牙', 1, 1, 0, 0, 3, 2, 3),
                ('克罗地亚', 1, 1, 0, 0, 2, 1, 3),
                ('英格兰', 1, 0, 0, 1, 2, 3, 0),
                ('捷克', 1, 0, 0, 1, 1, 2, 0)],
             'note': '首轮：英格兰主场 2-3 遭西班牙逆转（凯恩破门并射失点球，巴埃纳、奥亚萨瓦尔替补连入两球），捷克客场 1-2 负克罗地亚。本日捷克 vs 英格兰、西班牙 vs 克罗地亚：西班牙与克罗地亚同为 3 分直接对话争夺榜首，英格兰、捷克均需止跌。'},
            {'name': 'B 级第 1 组（第 1 轮后）', 'teams': [
                ('瑞士', 1, 1, 0, 0, 3, 0, 3),
                ('苏格兰', 1, 0, 1, 0, 0, 0, 1),
                ('斯洛文尼亚', 1, 0, 1, 0, 0, 0, 1),
                ('北马其顿', 1, 0, 0, 1, 0, 3, 0)],
             'note': '首轮：瑞士客场 3-0 完胜北马其顿（阿姆杜尼两球两助），苏格兰 0-0 平斯洛文尼亚（17 次射门未破门）。本日苏格兰 vs 瑞士为榜首之争，斯洛文尼亚 vs 北马其顿为双方争取首胜的直接对话；B 级小组头名可直接升入 A 级。'},
            {'name': 'C 级第 3 组（第 1 轮后）', 'teams': [
                ('斯洛伐克', 1, 1, 0, 0, 2, 0, 3),
                ('法罗群岛', 1, 0, 1, 0, 1, 1, 1),
                ('哈萨克斯坦', 1, 0, 1, 0, 1, 1, 1),
                ('摩尔多瓦', 1, 0, 0, 1, 0, 2, 0)],
             'note': '首轮：斯洛伐克主场 2-0 胜摩尔多瓦（施兰茨、杜达进球），哈萨克斯坦客场 1-1 平法罗群岛。斯洛伐克本日主场取胜即可两连胜领跑，并扩大 C3 组头名（直接升级）的领先优势。'},
            {'name': 'C 级第 4 组（第 1 轮后）', 'teams': [
                ('卢森堡', 1, 1, 0, 0, 2, 1, 3),
                ('冰岛', 1, 0, 1, 0, 1, 1, 1),
                ('爱沙尼亚', 1, 0, 1, 0, 1, 1, 1),
                ('保加利亚', 1, 0, 0, 1, 1, 2, 0)],
             'note': '首轮：卢森堡客场 2-1 逆转保加利亚（蒂尔第 66 分钟制胜球）暂列小组第一，冰岛 1-1 平爱沙尼亚。本日卢森堡 vs 冰岛为榜首与追赶者的直接较量，保加利亚 vs 爱沙尼亚则是两队止跌保级的关键一战。'},
        ],
        'impact_title': '本日对阵 · 小组晋级形势',
        'impact_note': '联赛阶段第 2 轮：胜 3 分、平 1 分、负 0 分。本日 7 场均为组内第二轮对话——A3 组前两名晋级淘汰赛，B1 组小组头名可直接升级；C3、C4 组头名同样握有升级主动权，各组第二轮结果将基本勾勒出半程格局。',
        'ctx_title': '本日对阵 · 分组与看点',
        'league_ctx': [
            '捷克 vs 英格兰（A3）：英格兰首轮主场 2-3 遭西班牙逆转，媒体口径为残阵出击、大面积伤病；捷克 1-2 负克罗地亚。英格兰客胜赔率仅 1.20、让一球 1.73，若再度失分将基本失去争夺小组前两名的主动权。',
            '西班牙 vs 克罗地亚（A3）：两队首轮同取 3 分（西班牙 3-2 胜英格兰、克罗地亚 2-1 客胜捷克），本场胜者独占榜首；西班牙各项赛事不败已延续至 39 场，克罗地亚 41 岁的莫德里奇首轮仍有进球。',
            '苏格兰 vs 瑞士（B1）：瑞士首轮客场 3-0 完胜北马其顿，但扎卡、恩博洛等核心因疫苗相关手续缺席，本场人员仍不整；苏格兰首轮 17 次射门 0 球，进攻效率是主场最大的疑问，竞彩给瑞士客胜 1.74。',
            '斯洛文尼亚 vs 北马其顿（B1）：北马其顿首轮 0 射正、0-3 惨败，近 4 场 2 平 2 负；斯洛文尼亚首轮靠奥布拉克力保 0-0，谢什科等攻击手缺席，两队均急需首胜，主胜 1.49 与让一球 2.70 之间存在一定预期差。',
            '斯洛伐克 vs 哈萨克斯坦（C3）：斯洛伐克首轮主场 2-0 胜摩尔多瓦，哈萨克斯坦客场 1-1 平法罗群岛且赛前行程受阻；主胜 1.18、让一球 1.73，是本日欧国联中主客实力差最悬殊的一场。',
            '卢森堡 vs 冰岛（C4）：卢森堡首轮客场 2-1 逆转保加利亚列小组第一，冰岛 1-1 平爱沙尼亚；冰岛客胜 2.14 略受机构青睐，但卢森堡近年在欧国联主场多次掀翻排名更高的对手，是本日「让球方向与积分形势背离」风险最高的一场。',
            '保加利亚 vs 爱沙尼亚（C4）：保加利亚首轮 1-2 被卢森堡逆转且队长伤停，机构数据降温；爱沙尼亚伤病严重、可用人手紧缺。两队均需止跌，主胜 1.52 但让一球 2.76 偏高，平局是主要防范方向。',
        ],
        'next_title': '后续赛程（联赛阶段）',
        'next': [
            ('2026-09-29', '联赛阶段第 2 轮（A3 / B1 / C3 / C4 四组）', '本日'),
            ('2026 年 10 月国际比赛日', '联赛阶段第 3-4 轮', 'A/B/C/D 级'),
            ('2026 年 11 月国际比赛日', '联赛阶段第 5-6 轮（各级别小组收官）', 'A/B/C/D 级'),
            ('2027 年 3 月', 'A 级淘汰赛阶段（8 强 / 半决赛 / 决赛）与升降级附加赛', '淘汰赛阶段'),
        ],
        'next_note': '欧国联联赛阶段按 9 月、10 月、11 月三个国际比赛日窗口推进；具体日期与对阵以欧足联官方赛程为准。',
    },
}


def cup_card(lg, ms):
    """杯赛日第六节：赛制规则 + 小组出线形势 + 参赛队联赛处境 + 后续赛程。"""
    cfg = CUP_EXTRA[lg]
    o = []
    o.append(f'    <h4>{esc(lg)} <span style="font-weight:400;font-size:0.78rem;color:var(--muted);">· {esc(cfg["title"])}</span></h4>')
    o.append(f'    <div class="league-src">{esc(cfg["src"])}</div>')
    o.append('    <ul style="margin:0.35rem 0 0.7rem;padding-left:1.15rem;font-size:0.82rem;line-height:1.8;">'
             + ''.join(f'<li>{esc(x)}</li>' for x in cfg['rules']) + '</ul>')
    for g in cfg['groups']:
        o.append(f'    <div style="margin-top:0.55rem;"><div class="impact-title">{esc(g["name"])} 积分榜</div>')
        o.append('      <table class="league-tbl standings">')
        o.append('        <tr><th>#</th><th>球队</th><th>赛</th><th>胜</th><th>平</th><th>负</th>'
                 '<th>进</th><th>失</th><th>净</th><th>分</th></tr>')
        for i, t in enumerate(g['teams'], 1):
            name, p, w, dd, l, gf, ga, pts = t
            zone = 'zone-eu' if i <= 2 else ''
            o.append(f'        <tr class="{zone}"><td>{i}</td>'
                     f'<td style="text-align:left;">{esc(name)}</td>'
                     f'<td>{p}</td><td>{w}</td><td>{dd}</td><td>{l}</td>'
                     f'<td>{gf}</td><td>{ga}</td><td>{gf - ga:+d}</td><td>{pts}</td></tr>')
        o.append('      </table>')
        o.append(f'      <p class="league-note">{esc(g["note"])}</p>')
        o.append('    </div>')
    o.append('    <div class="league-impact">')
    o.append('      <div class="impact-title">' + esc(cfg.get('impact_title', '本日对阵 · 出线影响')) + '</div>')
    for m in ms:
        o.append(f'      <div class="impact-row"><span class="tag tag-blue">{esc(m["matchNumStr"])}</span> '
                 f'{esc(m["home"])} vs {esc(m["away"])} · '
                 + esc(cfg.get('impact_note', '小组赛阶段：胜者 3 分领跑小组，'
                                              '战平则直接点球决胜（点球胜方额外 1 分）。'))
                 + '</div>')
    o.append('    </div>')
    o.append('    <div class="league-impact">')
    o.append('      <div class="impact-title">' + esc(cfg.get('ctx_title', '参赛队联赛处境')) + '</div>')
    for x in cfg['league_ctx']:
        o.append(f'      <div class="impact-row">{esc(x)}</div>')
    o.append('    </div>')
    o.append('    <div class="league-impact">')
    o.append('      <div class="impact-title">' + esc(cfg.get('next_title', '后续赛程（小组赛下一批）')) + '</div>')
    o.append('      <div class="table-wrap"><table class="history-table"><thead>'
             '<tr><th>日期</th><th>对阵</th><th>分组</th></tr></thead><tbody>'
             + ''.join(f'<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td></tr>' for a, b, c in cfg['next'])
             + '</tbody></table></div>')
    o.append('      <p class="league-note">'
             + esc(cfg.get('next_note', '小组赛第三轮预计于 2026 年 11 月国际比赛日后进行，具体赛程以官方公布为准。'))
             + '</p>')
    o.append('    </div>')
    return o


def news_html(m):
    """逐场卡片「伤停与赛前分析」：按段落渲染，避免长句堆叠。"""
    txt = (m.get('news') or '').strip()
    if not txt:
        return '<p style="font-size:0.9rem;line-height:1.8;color:var(--muted);">暂无公开伤停 / 赛前信息。</p>'
    paras = [p.strip() for p in txt.split('\n') if p.strip()]
    return '\n  '.join(
        f'<p style="font-size:0.9rem;line-height:1.8;margin:0 0 0.45rem;">{esc(p)}</p>' for p in paras)


def esc(s): return html.escape(str(s if s is not None else ''))

def rank_tag(name, rank):
    return f'{esc(name)}<sub class="rank-tag">[{esc(rank)}]</sub>' if rank is not None else esc(name)

def team_with_rank(name, rank):
    """第三节队名右下角排名小字（缺失排名时只显示队名）"""
    if rank in (None, '', '-', 0): return esc(name)
    r = rank if str(rank).startswith('联赛第') else f'联赛第{rank}'
    return f'{esc(name)}<sub class="team-rank">{esc(r)}</sub>'

_LM_CACHE = None

def league_index():
    """懒加载 7M 积分榜索引（league_data.json + 队名匹配器），供逐场卡排名回填"""
    global _LM_CACHE
    if _LM_CACHE is None:
        try:
            import league_match as LM
            ld = json.load(open('league_data.json', encoding='utf-8')).get('leagues', {})
            _LM_CACHE = (LM, LM.build_index(ld))
        except Exception:
            _LM_CACHE = (None, None)
    return _LM_CACHE

def rank_of(team, league):
    """查 7M 当前排名；未收录（如美职）或匹配不到返回 None"""
    LM, idx = league_index()
    if LM is None or idx is None:
        return None
    row = LM.match_team(team, league, idx)
    if row and row.get('rank'):
        return row['rank']
    return None

def rank_disp(team, league, fallback=None):
    """逐场卡排名展示：第N 或 -（7M 未收录时回退到 matches_data 的 home_rank/away_rank）"""
    r = rank_of(team, league) or (fallback if fallback else None)
    return f'第{r}' if r else '-'

def dash(score): return score.replace(':', '-')

def form_str(recent, n=5):
    """近期战绩：近 n 场 胜/平/负 + 进/失球。recent = [{gf,ga}, ...]（顺序不敏感）。"""
    if not recent:
        return '—'
    games = recent[-n:] if len(recent) > n else recent
    w = sum(1 for g in games if g.get('gf', 0) > g.get('ga', 0))
    d = sum(1 for g in games if g.get('gf', 0) == g.get('ga', 0))
    l = sum(1 for g in games if g.get('gf', 0) < g.get('ga', 0))
    gf = sum(g.get('gf', 0) for g in games)
    ga = sum(g.get('ga', 0) for g in games)
    return f'{w}胜{d}平{l}负（进{gf}失{ga}）'

def league_note(ms):
    """按数据挑本联赛三档看点：进球预期最高 / 冷门风险最高 / 概率最胶着。"""
    if not ms:
        return ''
    top_lam = max(ms, key=lambda m: m.get('lam_total', 0))
    ups = [(m['upset']['prob'], m) for m in ms if m.get('upset')]
    top_up = max(ups, key=lambda x: x[0])[1] if ups else None
    closest = min(ms, key=lambda m: abs(m['prob']['home'] - m['prob']['away']))
    parts = [f'进球预期最高：{top_lam["matchNumStr"]} {top_lam["home"]}vs{top_lam["away"]}（λ{top_lam["lam_total"]:.2f}）']
    if top_up:
        parts.append(f'冷门风险最高：{top_up["matchNumStr"]} {top_up["home"]}vs{top_up["away"]}（{top_up["upset"]["prob"]:.0f}%）')
    parts.append(f'最胶着：{closest["matchNumStr"]} {closest["home"]}vs{closest["away"]}（主{closest["prob"]["home"]:.0f}% / 客{closest["prob"]["away"]:.0f}%）')
    return ' · '.join(parts)

def stars_html(n):
    return f'<span style="color:var(--accent3);font-size:1.05rem;">{"★"*n}{"☆"*(5-n)}</span>'

def first_score(m):
    ts = m['top_scores']
    return (ts[0]['score'], ts[0]['prob']/100) if ts else ('1:1', 0.0)

def score_group(m, k=5):
    """概率排序比分组：单比分众数结构性退化，改为给出前 k 个比分与累计覆盖。

    退化根因（score_mode_audit.py，2577 场 walk-forward）：
      独立泊松的联合众数 = (⌊λ主⌋, ⌊λ客⌋)；λ 落在 [1,2) 时两者 floor 均为 1
      → 众数恒为 1:1。生产口径（含联赛形状混合）下 66.8% 的场次众数=1:1，
        纯泊松口径也达 49.3%。这是数学性质，不是模型没算。
      回测命中率（V3.3 生产口径，2577 场）：单比分 13.5% / Top3 覆盖 33.3% / Top5 覆盖 49.1%。
    """
    ts = m['top_scores'][:k]
    return ' · '.join(f"{dash(t['score'])} {t['prob']:.1f}%" for t in ts)


def coverage(m, k):
    return sum(t['prob'] for t in m['top_scores'][:k])


def direction_pick(m):
    """倾向 + 该倾向象限内的众数比分（2026-09-13 起**只作内部用**，不再当头条）。

    全局众数在均衡场次几乎恒为 1:1（P≈11~14%），且众数是分布单点、必然低于均值
    （回测总进球系统性低 0.90 球/场），故头条已改用 expect_score()。
    本函数仍用于：① 判定倾向；② 约束期望比分落在倾向象限内；③ 期望比分不合法时的兜底。
    返回 (倾向中文, 倾向key, 方向比分, 方向比分概率0-1, 倾向概率0-1)。
    """
    pr = SA.prob1x2(m)
    okey = SA.direction_key(m)
    olabel = {'home': '主胜', 'draw': '平局', 'away': '客胜'}[okey]
    qt = (m.get('quad_top') or {}).get(okey) or {}
    return olabel, okey, qt.get('score', '1:1'), (qt.get('prob') or 0)/100, pr[okey]/100

def total_goals_info(m):
    """总进球倾向：λ主/客独立泊松相加，算 P(≥3球)/P(≥4球) 与总量众数。

    首选比分是单一比分众数（天然偏小），总量判断以此为准——
    防止「首选1:1」被误读为小球预测。
    """
    lt = m['lam_home'] + m['lam_away']
    pois = lambda k: math.exp(-lt) * lt**k / math.factorial(k)
    p_ge3 = 1 - sum(pois(k) for k in range(3))
    p_ge4 = 1 - sum(pois(k) for k in range(4))
    if p_ge3 >= 0.58:
        tag, cls = '大球倾向', 'tag-red'
    elif p_ge3 <= 0.42:
        tag, cls = '小球倾向', 'tag-green'
    else:
        tag, cls = '均势总量', 'tag-yellow'
    mode_k = max(range(9), key=pois)
    return {'lt': lt, 'ge3': p_ge3, 'ge4': p_ge4, 'tag': tag, 'cls': cls, 'mode': mode_k}

def score_odd(m, score):
    return m['odds'].get('比分', {}).get(score)


def band_prob(m, score):
    """参考比分的 ±1 球覆盖概率：P(|H-h0|<=1 且 |A-a0|<=1)，独立泊松（展示用，不参与选取）。"""
    try:
        h0, a0 = (int(x) for x in str(score).split(':'))
    except ValueError:
        return None
    lh, la = m['lam_home'], m['lam_away']
    pmf = lambda k, lam: math.exp(-lam) * lam ** k / math.factorial(k)
    pr = 0.0
    # 用去重格集合求和（边界格不可重复计数）
    cells = {(h, a) for h in range(max(0, h0 - 1), h0 + 2) for a in range(max(0, a0 - 1), a0 + 2)}
    for h, a in cells:
        pr += pmf(h, lh) * pmf(a, la)
    return pr


_LISTED_LABELS = SA.LISTED_LABELS

# 头条「命中比分」= 已对齐比分矩阵的联合众数（= top_scores[0] 里的首个列出比分）。
# 口径依据：目标函数为单场命中次数，argmax 即最优解，故不做任何"大胆化"变换。
# 实现统一放在 selection_algo（报告与每日优化共用同一份，禁止在此另写一份）。
hit_pick = SA.hit_pick


def _pois_cell_prob(m, score):
    """比分不在矩阵前 6 格时的兜底概率（独立泊松近似，单位 %）。"""
    try:
        h, a = (int(x) for x in str(score).split(':'))
    except (ValueError, AttributeError):
        return 0.0
    pmf = lambda k, lam: math.exp(-lam) * lam ** k / math.factorial(k)
    return round(pmf(h, m['lam_home']) * pmf(a, m['lam_away']) * 100, 1)


# 双档 = 模型排序第 2、第 3 可能比分（跳过头条）。实现同在 selection_algo。
hit_band = SA.band_scores


def quad_picks(m, k=2):
    """倾向象限内的概率前 k 个列出比分（仅内部/兼容用）。

    回测（score_rule_probe.py，1591 场生产口径）：
      Top1 15.4% → 双档 25.5% → Top3 32.2%。
    已被 hit_band() 取代：不约束象限的联合众数 Top1/Top2/Top3 = 16.6%/29.9%/39.9%，
    三项全部更高（象限约束会把跨象限的次优格，如主场场次里的 1:1，排掉）。
    """
    pr = m['prob']
    okey = max([('home',), ('draw',), ('away',)],
               key=lambda x: pr[x[0]])[0]
    q = lambda c: (c[0] > c[1]) if okey == 'home' else ((c[0] == c[1]) if okey == 'draw' else (c[0] < c[1]))
    out = []
    for t in m['top_scores']:
        try:
            h, a = (int(x) for x in str(t['score']).split(':'))
        except (ValueError, AttributeError):
            continue
        if q((h, a)):
            out.append((t['score'], t['prob']))
        if len(out) >= k:
            break
    return out


# 「量级参考比分」= λ 期望进球四舍五入（无偏口径，非押中口径）。实现同在 selection_algo。
expect_score = SA.expect_score


def score_cred(m):
    """比分可信度 = 按 λ 总量分档给出**实测命中率**（不是模型自评概率）。

    生产口径重测（2026-09-13，_grid_cache.json，4036 场 / w=0.3，联合众数口径）：
      λ≤2.0    → Top1 22.3% / Top2 34.5% / Top3 43.2% / ±1球 62.9%（n=229）
      2.0~2.3  → Top1 18.3% / Top2 30.8% / Top3 40.1% / ±1球 70.3%（n=377）
      2.3~2.6  → Top1 19.2% / Top2 32.8% / Top3 43.1% / ±1球 70.9%（n=717）
      2.6~3.0  → Top1 13.0% / Top2 23.8% / Top3 32.4% / ±1球 68.1%（n=1163）
      3.0~3.5  → Top1 13.4% / Top2 24.0% / Top3 33.4% / ±1球 66.3%（n=981）
      >3.5     → Top1 11.1% / Top2 22.7% / Top3 29.5% / ±1球 62.4%（n=569）
    语义：λ≤2.6（约 1/3 场次）单点命中 18~22%，是最值得看比分的区间；
    λ>2.6 之后单点稳定在 11~13%，且不再随 λ 单调下降 → 分档语义是「这段比分能不能照抄」，
    而不是命中率阶梯。高总进球场次请以方向与总量为主。
    （旧「λ≤2.3 单点 27.3%」为 1591 场小样本口径，已被 4036 场取代。）
    返回 (标签, class)。标签词表与方向/让球可信度统一：可用 / 慎用 / 别跟。
    """
    # 冷启动场次（任一侧无近期战绩）：λ 只能由「联赛基线 + 赔率反推」得到，
    # 与有战绩场次不可比，其单格概率常因 λ 悬殊而虚高 → 不作为「可照抄」看待。
    # （2026-09-14 实装：当日 007/014 两场冷启动占据了精选榜第 1、2 名）
    if m.get('cold') or (m.get('data_n') or {}).get('home', 1) == 0 \
            or (m.get('data_n') or {}).get('away', 1) == 0:
        return '数据不足', 'tag-red'
    lt = m['lam_home'] + m['lam_away']
    if lt <= 2.6:
        return '可用', 'tag-green'
    if lt <= 3.5:
        return '慎用', 'tag-yellow'
    return '别跟', 'tag-red'


def dir_cred(m):
    """方向可信度 = 按 1X2 三项中最高概率（方向确定性）分档。

    与 score_cred（比分口径，按 λ 总量分档）分工：
      score_cred → 「这个比分能不能照抄」（逐场卡片与比分精选榜用）
      dir_cred   → 「这个方向能不能跟」（4.1 胜负预测表用）

    分档：≥50% 可用（三率中最高者过半）／40%~50% 慎用（三者接近，方向无区分度）／<40% 别跟。
    冷启动场次也照常分档 —— 其方向概率由赔率反推（纯市场口径），方向判读依然有效；
    数据薄只影响「比分」侧（见 score_cred）。
    返回 (标签, class)。
    """
    pr = SA.prob1x2(m)
    top = max(pr.values()) if pr else 0
    if top >= 50:
        return '可用', 'tag-green'
    if top >= 40:
        return '慎用', 'tag-yellow'
    return '别跟', 'tag-red'


def rq_grade(prob, conf):
    """让球可信度分档（4.1 表与逐场卡片共用同一套词表）。

    V3.5 口径：按**选中项校准概率**分档，不再用 EV。
    校准概率≥50% 且不为低置信 → 可用；≥42% → 慎用；其余 → 别跟。
    （旧口径用 EV≥1.10 判「可用」，实盘 EV 越高命中反而越低，已废。）
    返回 (标签, class)。
    """
    p = float(prob)
    if p >= 50 and str(conf) != '低':
        return '可用', 'tag-green'
    if p >= 42:
        return '慎用', 'tag-yellow'
    return '别跟', 'tag-red'


def rq_cells(m):
    """4.1 表的「让球盘口 + 让球可信度」两格（数据来自引擎 A 的让球盘偏差结论）。

    第二格给的是**可信度**（与「方向可信度」同一套词表）：这个让球盘能不能跟。
    价值方向与 EV 以小字附在标签后，便于回查依据。
    """
    rq = m.get('rq')
    if not rq:
        return ('<td style="text-align:center;color:var(--muted);">—</td>',
                '<td style="color:var(--muted);">无让球盘</td>')
    lo = str(rq['handicap'])
    show = ('受让 ' + lo[1:]) if lo.startswith('+') else (('让 ' + lo[1:]) if lo.startswith('-') else '平手')
    b = rq['best']
    prob, conf = float(b['prob']), str(rq['conf'])
    txt, cls = rq_grade(prob, conf)
    return (f'<td style="text-align:center;white-space:nowrap;">{esc(show)}'
            f'<span style="color:var(--muted);font-weight:400;font-size:0.76rem;">（{esc(lo)}）</span></td>',
            f'<td style="white-space:nowrap;"><span class="tag {cls}">{txt}</span>'
            f' <span style="color:var(--muted);font-size:0.76rem;">'
            f'{esc(b["pick"])} · 概率 {prob:.0f}% · 置信{esc(conf)}</span></td>')


def lam_cred(lt):
    """比分区可信度 = 按该场 λ 总量分档（与逐场卡片同一口径）。

    词表与「方向可信度 / 让球可信度」统一为可用 / 慎用 / 别跟，
    语义 = 这段比分能不能照抄单点。
    """
    if lt is None:
        return '数据不足', 'tag-red'
    if lt <= 2.6:
        return '可用', 'tag-green'
    if lt <= 3.5:
        return '慎用', 'tag-yellow'
    return '别跟', 'tag-red'



# ---------- V3.3 二级盘：让球盘偏差 + 冷门风险 ----------
RQ_LABEL = {'W': '让球胜', 'D': '让球平', 'L': '让球负'}
UPSET_CLS = {'低': 'tag-green', '中': 'tag-yellow', '高': 'tag-red'}


def rq_block(m):
    """让球盘偏差提示卡：市场去水 → 纯模型 → 联合校准 → 最可能结果。

    V3.5 口径：给「校准概率最高的那注」，不追 EV（让球盘三选一抽水约 13%，
    长期两种口径都无正边际，但概率口径命中率高一档）。EV 仅作参考列展示。
    """
    rq = m.get('rq')
    if not rq:
        return ''
    b = rq['best']
    lo = rq['handicap']
    hcap_show = ('主队受让' + lo[1:] if lo.startswith('+')
                 else ('主队让' + lo[1:] if lo.startswith('-') else '平手'))
    ev_cls = 'var(--accent3)' if b['ev'] >= 1.10 else ('var(--accent2)' if b['ev'] >= 1.00 else 'var(--muted)')
    rows = ''
    for k in ('W', 'D', 'L'):
        rows += (f'<tr><td>{RQ_LABEL[k]}</td>'
                 f'<td style="font-family:monospace;">{esc(rq["odds"][k])}</td>'
                 f'<td>{rq["market"][k]:.1f}%</td>'
                 f'<td>{rq["model"][k]:.1f}%</td>'
                 f'<td><strong>{rq["calibrated"][k]:.1f}%</strong></td>'
                 f'<td style="font-family:monospace;color:{ev_cls};font-weight:700;">{rq["ev"][k]:.2f}</td></tr>')
    warn_html = ''
    if rq.get('warns'):
        warn_html = ('<br><span style="color:var(--accent3);">⚠️ ' +
                     '；'.join(esc(w) for w in rq['warns']) + ' —— 低置信，仅观察</span>')
    _gt, _gc = rq_grade(b['prob'], rq['conf'])
    return f'''
  <h4>让球盘偏差（{esc(hcap_show)} {esc(lo)} · |让球|={rq['abs']} · 最大分歧 {rq['div_pp']:.0f}pp · 置信度{rq['conf']}）</h4>
  <div class="table-wrap">
    <table class="history-table">
      <thead><tr><th>让球盘</th><th>赔率</th><th>市场去水</th><th>纯模型</th><th>联合校准</th><th>EV</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p style="font-size:0.78rem;margin:0.3rem 0 0.7rem;">
    <b>最可能结果：</b><span class="tag {'tag-green' if b['prob'] >= 50 and rq['conf'] != '低' else ('tag-yellow' if b['prob'] >= 42 else 'tag-blue')}">{esc(b['pick'])} @{esc(b['odds'])}</span>
    校准概率 <strong>{b['prob']:.1f}%</strong>（EV {b['ev']:.2f}，仅参考不参与排序），
    模型−市场分歧 {rq['calibrated'][b['key']]-rq['market'][b['key']]:+.1f}pp。
    <span style="color:var(--muted);">让球可信度分档：<b>校准概率≥50% 且置信≥中 可用</b>、<b>≥42% 慎用</b>、<b>其余别跟</b>；本场 <span class="tag {_gc}">{_gt}</span>。让球盘抽水约 13%，长期无正边际，只作方向参考。</span>{warn_html}
  </p>
'''


def upset_block(m):
    """冷门风险提示：风险概率 + 影响因素分解。"""
    u = m.get('upset')
    if not u:
        return ''
    cls = UPSET_CLS.get(u['level'], 'tag-blue')
    extra = ''
    if u['level'] == '高':
        extra = ' <strong style="color:var(--accent3);">→ 不进入信心串关，仅可小注博冷</strong>'
    return (f'<div class="warning" style="border-left-color:var(--accent3);">'
            f'🎲 <b>冷门风险 {u["prob"]:.1f}%</b> '
            f'<span class="tag {cls}">{u["level"]}风险</span>{extra}<br>'
            f'<span style="font-size:0.8rem;">市场首选「{esc(u["market_top"])}」隐含 {u["market_top_prob"]:.1f}%'
            f'（历史同档翻车率均值 {u["base_rate"]:.1f}%）；'
            f'模型−市场分歧 {u["div_pp"]:+.1f}pp、|让球|{u["abs_handicap"]:g}、'
            f'λ和 {u["lam_sum"]:.2f}、市场熵 {u["entropy"]:.3f}。'
            f'时间外低风险 1/3 翻车 ≈25% / 高风险 ≈44%。</span></div>')


def upset_pct(m):
    u = m.get('upset')
    return u['prob'] if u else None


def upset_table():
    """4.4 冷门风险明细（按风险概率降序）。"""
    rows = [(upset_pct(m), m) for m in MATCHES if upset_pct(m) is not None]
    if not rows:
        return ''
    rows.sort(key=lambda x: -x[0])
    body = ''
    for p, m in rows:
        u = m['upset']
        cls = UPSET_CLS.get(u['level'], 'tag-blue')
        body += (f'<tr><td><span class="tag tag-blue">{esc(m["matchNumStr"])}</span></td>'
                 f'<td>{rank_tag(m["home"], m["home_rank"])}</td>'
                 f'<td>{rank_tag(m["away"], m["away_rank"])}</td>'
                 f'<td><span class="tag {cls}">{u["level"]}</span></td>'
                 f'<td style="font-family:monospace;font-weight:700;">{u["prob"]:.1f}%</td>'
                 f'<td>{esc(u["market_top"])} {u["market_top_prob"]:.1f}%</td>'
                 f'<td>{u["div_pp"]:+.1f}pp</td><td>{u["abs_handicap"]:g}</td>'
                 f'<td>{u["lam_sum"]:.2f}</td><td>{u["entropy"]:.3f}</td></tr>')
    return _sub_table(
        '4.5 冷门风险明细',
        f'冷门定义 = <b>市场首选方向未命中</b>（含平局）。训练基础率 <b>{rows[0][1]["upset"]["base_rate"]:.1f}%</b>。'
        '影响因素 = 市场首选概率、模型−市场分歧、|让球|、λ和、市场熵；'
        '时间外低风险 1/3 翻车 ≈25% / 高风险 ≈44%。'
        '<b>用法</b>：高风险场次不进信心串关（可小注博冷）；中风险场次少押单场方向。'
        '⚠️ 2026-09 样本较少，分层尚不显著，模型会随样本自动向基础率收缩。'
        '<br><b>信心评级</b>：星级 = <b>胜平负方向的确定性</b>（三率中最高者的概率），'
        '实测各档方向命中 <b>37.5% / 49.5% / 50.4% / 60.4% / 74.4%</b>（★ 越多越确定）。'
        '两者互补：上表<b>预测</b>风险，星级直接<b>读</b>方向确定性。',
        '<th>编号</th><th>主队</th><th>客队</th><th>风险</th><th>冷门概率</th><th>市场首选</th>'
        '<th>模型−市场</th><th>|让球|</th><th>λ和</th><th>市场熵</th>', body)


BIG_CLS = {'高': 'tag-red', '中': 'tag-yellow', '低': 'tag-blue'}


def big_goals_table():
    """4.6 大比分（总进球 6+ / 7+）观察 —— 回答「哪场最像出大比分」。"""
    rows = [(m['big']['cal6'], m) for m in MATCHES if m.get('big')]
    if not rows:
        return ''
    rows.sort(key=lambda x: -x[0])
    body = ''
    for _p, m in rows:
        b = m['big']
        cls = BIG_CLS.get(b['level'], 'tag-blue')
        body += (f'<tr><td><span class="tag tag-blue">{esc(m["matchNumStr"])}</span></td>'
                 f'<td>{rank_tag(m["home"], m["home_rank"])}</td>'
                 f'<td>{rank_tag(m["away"], m["away_rank"])}</td>'
                 f'<td>{b["market6"]:.1f}%</td>'
                 f'<td><strong>{b["cal6"]:.1f}%</strong></td>'
                 f'<td>{b["cal7"]:.1f}%</td>'
                 f'<td>{b["cal6"] - b["cal7"]:.1f}%</td>'
                 f'<td style="font-family:monospace;">{b["odd6"]:g}</td>'
                 f'<td style="font-family:monospace;">{b["odd7"]:g}</td>'
                 f'<td style="font-family:monospace;">{b["ev7"]:.2f}</td>'
                 f'<td><span class="tag {cls}">{b["level"]}</span></td></tr>')
    top = rows[0][1]
    tb = top['big']
    p_any = (1 - math.prod(1 - m['big']['cal6'] / 100 for _p, m in rows)) * 100
    exp_n = sum(m['big']['cal6'] for _p, m in rows) / 100
    n_s = tb.get('n_samples') or 0
    return _sub_table(
        '4.6 大比分观察',
        f'口径：市场<b>总进球盘</b>去水后逐档校准（总进球盘的「6」与「7+」是两个独立档位，'
        f'6+ = 两者之和）。今日最像的一场：'
        f'<b>{esc(top["matchNumStr"])} {esc(top["home"])} vs {esc(top["away"])}</b>'
        f'（市场隐含 {tb["market6"]:.1f}% → 校准 {tb["cal6"]:.1f}%）；{len(rows)} 场里「至少一场 6+」≈'
        f'<b>{p_any:.0f}%</b>，期望 {exp_n:.2f} 场。'
        '<br>市场对高进球系统性定价偏高 —— 实测去水后 P(6+)、P(7+) 均值都明显高于实际，'
        '且概率越高偏离越大，故本表给出校准后的概率。'
        '<br><b>结论</b>：「最近天天有 6+」是<b>基础率 × 每天场次数</b>的必然，不是异象 —— '
        '每天 15 场时「至少一场 6+」本来就有 <b>62%</b>、30 场时 <b>88%</b>。'
        '直接按赔率买「恰好 6 球」「7+ 球」长期均为亏损。'
        '<b>所以本表只用于「哪场最像」，不构成投注建议</b>；要参与请只当小注娱乐。',
        '<th>编号</th><th>主队</th><th>客队</th><th>市场隐含P(6+)</th><th>校准P(6+)</th>'
        '<th>校准P(7+)</th><th>其中正好6球</th><th>6档赔率</th><th>7+档赔率</th>'
        '<th>校准EV(7+)</th><th>等级</th>', body)


def market_dev_section(matches):
    """4.4 让球盘清单（按校准概率降序，V3.5 起不再按 EV 排）。"""
    rows = []
    for m in matches:
        rq = m.get('rq')
        if not rq:
            continue
        b = rq['best']
        rows.append((b['prob'], m, rq, b))
    if not rows:
        return ''
    rows.sort(key=lambda x: (-x[0], -x[2]['best']['ev']))
    body = ''
    for prob, m, rq, b in rows:
        cls = rq_grade(prob, rq['conf'])[1]
        up = upset_pct(m)
        up_str = f'{up:.0f}%' if up is not None else '-'
        body += (f'<tr><td><span class="tag tag-blue">{esc(m["matchNumStr"])}</span></td>'
                 f'<td>{rank_tag(m["home"], m["home_rank"])}</td>'
                 f'<td>{rank_tag(m["away"], m["away_rank"])}</td>'
                 f'<td>{esc(rq["handicap"])}</td>'
                 f'<td><span class="tag {cls}">{esc(b["pick"])}</span></td>'
                 f'<td style="font-family:monospace;">{esc(b["odds"])}</td>'
                 f'<td>{rq["market"][b["key"]]:.1f}%</td>'
                 f'<td>{rq["model"][b["key"]]:.1f}%</td>'
                 f'<td><strong>{rq["calibrated"][b["key"]]:.1f}%</strong></td>'
                 f'<td style="font-family:monospace;">{rq["ev"][b["key"]]:.2f}</td>'
                 f'<td>{rq["div_pp"]:.0f}pp</td>'
                 f'<td>{esc(rq["conf"])}</td>'
                 f'<td>{up_str}</td></tr>')
    return _sub_table(
        '4.4 让球盘偏差清单',
        '这一节给的是<b>让球盘上最可能的结果</b>（市场去水 + 纯模型联合校准后的最高概率），'
        '不是「赔率最划算的那注」。让球盘三选一抽水约 <b>13%</b>，'
        '按赔率追价值长期跑不赢水钱，因此排序只看概率、EV 仅作参考列。'
        '⚠️ <b>校准概率≥50% 且置信≥中才算可用</b>（≥42% 慎用，其余别跟）；'
        '|让球|=1 置信高、=2 中、≥3 低（样本不足，不建议跟）。'
        '<b>不要用它替换 1X2 判断</b>，也不要单独拿它做串关。',
        '<th>编号</th><th>主队</th><th>客队</th><th>让球</th><th>最可能结果</th><th>赔率</th>'
        '<th>市场</th><th>纯模型</th><th>联合校准</th><th>EV(参考)</th><th>最大分歧</th><th>置信</th><th>冷门风险</th>',
        body)

def h2h_mean(m):
    hh = H2H.get(m['matchNumStr']) or []
    if not hh: return None
    return sum(x['home_goals']+x['away_goals'] for x in hh) / len(hh)

# ---------- 一、比赛总览 ----------
rows1 = ''
for m in MATCHES:
    pr = m['prob']
    best = max([('主胜', pr['home'], 'tag-green'), ('平局', pr['draw'], 'tag-yellow'), ('客胜', pr['away'], 'tag-red')], key=lambda x: x[1])
    tg = total_goals_info(m)
    o = m['odds']
    rows1 += (f'<tr><td><span class="tag tag-blue">{esc(m["matchNumStr"])}</span></td>'
              f'<td>{esc(m["league"])}</td>'
              f'<td>{rank_tag(m["home"], m["home_rank"])}</td>'
              f'<td style="text-align:center;color:var(--muted);">VS</td>'
              f'<td>{rank_tag(m["away"], m["away_rank"])}</td>'
              f'<td style="font-family:monospace;">{esc(o.get("胜","-"))}</td>'
              f'<td style="font-family:monospace;">{esc(o.get("平","-"))}</td>'
              f'<td style="font-family:monospace;">{esc(o.get("负","-"))}</td>'
              f'<td><span class="tag {best[2]}">{best[0]}</span></td>'
              f'<td><span class="tag {tg["cls"]}" title="λ总分{tg["lt"]:.2f}，≥3球{tg["ge3"]*100:.0f}%">{tg["tag"]} {tg["ge3"]*100:.0f}%</span></td></tr>')

overview_sec = f'''
<h2>一、比赛总览</h2>
<div class="card">
  <div class="table-wrap">
    <table>
      <thead><tr><th>编号</th><th>联赛</th><th>主队</th><th>VS</th><th>客队</th><th>胜赔</th><th>平赔</th><th>负赔</th><th>市场倾向</th><th>总进球倾向</th></tr></thead>
      <tbody>{rows1}</tbody>
    </table>
  </div>
</div>
'''

# ---------- 二、市场信心指数对比（模型胜平负概率） ----------
labels = json.dumps([m['matchNumStr'] for m in MATCHES], ensure_ascii=False)
ph = json.dumps([m['prob']['home'] for m in MATCHES])
pd_ = json.dumps([m['prob']['draw'] for m in MATCHES])
pa = json.dumps([m['prob']['away'] for m in MATCHES])

chart_sec = f'''
<h2>二、市场信心指数对比</h2>
<div class="card">
  <div id="confidenceChart" class="chart-container"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<script>
var chart = echarts.init(document.getElementById('confidenceChart'));
var matchLabels = {labels};
var homeWinProbs = {ph};
var drawProbs = {pd_};
var awayWinProbs = {pa};
chart.setOption({{
    title: {{ text: '模型V3.3胜平负概率分布', left: 'center', textStyle: {{ fontSize: 14 }} }},
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
  legend: {{ data: ['主胜概率', '平局概率', '客胜概率'], bottom: 0 }},
  grid: {{ left: '3%', right: '4%', bottom: '12%', containLabel: true }},
  xAxis: {{ type: 'category', data: matchLabels, axisLabel: {{ rotate: 45, fontSize: 10 }} }},
  yAxis: {{ type: 'value', name: '概率(%)', max: 80 }},
  series: [
    {{ name: '主胜概率', type: 'bar', stack: 'total', data: homeWinProbs, itemStyle: {{ color: '#2a9d8f' }} }},
    {{ name: '平局概率', type: 'bar', stack: 'total', data: drawProbs, itemStyle: {{ color: '#f4a261' }} }},
    {{ name: '客胜概率', type: 'bar', stack: 'total', data: awayWinProbs, itemStyle: {{ color: '#e63946' }} }}
  ]
}});
window.addEventListener('resize', function() {{ chart.resize(); }});
</script>
'''

# ---------- 三、逐场深度分析 ----------
TIER_CN = {'elite': '顶级豪门', 'strong': '传统劲旅', 'regular': '中坚力量', 'minnow': '底蕴薄弱'}


def pedigree_block(m):
    """球队历史底蕴对比表（展示层，不改概率）。欧冠/欧战场次突出欧战荣誉。"""
    h, a = m['home'], m['away']
    ph, pa = PED.get(h), PED.get(a)
    if not ph and not pa:
        return ''
    euro = m.get('league', '') in ('欧冠', '欧罗巴', '欧协联')
    dims = ([('欧冠冠军', 'ucl_titles'), ('近10季欧冠正赛', 'ucl_seasons_last10'),
             ('洲际冠军合计', 'cont_titles'), ('本国联赛冠军', 'league_titles')] if euro
            else [('洲际冠军', 'cont_titles'), ('本国联赛冠军', 'league_titles'),
                  ('本国杯赛冠军', 'cup_titles')])

    def cell(p, key):
        if not p:
            return '<td style="color:var(--muted);">-</td>'
        v = p.get(key)
        return f'<td>{v if v is not None else "-"}</td>'

    rows = ''.join(f'<tr><td>{lb}</td>{cell(ph, k)}{cell(pa, k)}</tr>' for lb, k in dims)
    rows += (f'<tr><td>底蕴定位</td>'
             f'<td>{TIER_CN.get((ph or {}).get("tier", ""), "-")}</td>'
             f'<td>{TIER_CN.get((pa or {}).get("tier", ""), "-")}</td></tr>')
    notes = ' · '.join(x for x in [f'{h}：{ph.get("note")}' if ph and ph.get('note') else '',
                                   f'{a}：{pa.get("note")}' if pa and pa.get('note') else ''] if x)
    tag = '（欧冠/欧战场次，突出欧战荣誉）' if euro else ''
    return f'''
  <h4>历史底蕴对比{tag}</h4>
  <div class="table-wrap">
    <table class="history-table">
      <thead><tr><th>荣誉维度</th><th>{esc(h)}</th><th>{esc(a)}</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p style="font-size:0.78rem;color:var(--muted);margin:0.3rem 0 0.7rem;">{esc(notes)}
  <br>注：荣誉是公开慢变量，已隐含在市场赔率与模型长期战绩中；本表为<b>定性背景</b>，不计入概率。</p>
'''


# 引擎因素链的步骤名（顺序即推演顺序）。用于把 m['chain'] 字符串解析回结构化「因素 → λ」。
_CHAIN_STEPS = [
    ('基础λ', '① 近期战绩 EWMA'),
    ('xG融合', '② xG 融合'),
    ('无xG数据', '② xG（本场无数据）'),
    ('联赛收缩', '③ 联赛环境收缩'),
    ('H2H调整', '④ H2H 总量+方向'),
    ('市场混合', '⑤ 市场概率混合'),
    ('动态校准', '⑥ 动态校准'),
    ('零封修正', '⑦ 零封修正'),
    # 【2026-09-13 补齐】这三步此前不在链表里，导致「比分怎么推出来」缺最后一环：
    # 形状混合决定了最终比分矩阵的长什么样（w 长期与文档口径不符却没被发现，就是因为链里看不见）。
    ('比分形状混合', '⑧ 比分形状混合（联赛经验频率）'),
    ('Platt校准', '⑨ Platt 校准（平局修正）'),
    ('比分矩阵对齐发布1X2', '⑩ 比分矩阵对齐发布三率'),
]
_CHAIN_LAM_RE = re.compile(r'主([\d.]+)客([\d.]+)\s*$')


def chain_table(m):
    """把幂等因素链解析成表：**比分是被这些因素一步步推出来的**（不是从分布里「挑」的）。

    引擎每一步都输出 (因素名, 说明, λ主, λ客)，report 里以字符串 chain 承载；
    这里解析回结构化，展示「因素 → λ」的推演过程，最后接到比分读法。
    """
    raw = (m.get('chain') or '').strip()
    if not raw:
        return ''
    by_name = {}
    for tok in raw.split(' → '):
        tok = tok.strip()
        mm = re.match(r'^([^(]+)\((.*)\)$', tok, re.S)
        if not mm:
            continue
        nm, inner = mm.group(1).strip(), mm.group(2)
        lm = _CHAIN_LAM_RE.search(inner)
        lam = None
        if lm:
            lam = (lm.group(1), lm.group(2))
            inner = inner[:lm.start()].rstrip(' ,')
        by_name.setdefault(nm, []).append((inner, lam))
    if not by_name:
        return ''
    hscore, hprob = head_score(m)
    out = ['<div class="table-wrap" style="margin-top:0.4rem;">',
           '<table class="history-table" style="font-size:0.8rem;">',
           '<thead><tr><th style="width:22%;">因素（推演顺序）</th>'
           '<th style="width:8%;">λ主</th><th style="width:8%;">λ客</th>'
           '<th>取值 / 说明</th></tr></thead><tbody>']
    last = None
    for nm, label in _CHAIN_STEPS:
        if nm not in by_name:
            continue
        inner, lam = by_name[nm][0]
        if lam is None:
            lam = last
        else:
            last = lam
        lam_cell = (f'{lam[0]}' if lam else '—'), (f'{lam[1]}' if lam else '—')
        info = inner if len(inner) <= 88 else inner[:86] + '…'
        out.append(f'<tr><td style="font-weight:600;">{esc(label)}</td>'
                   f'<td style="font-family:monospace;">{esc(lam_cell[0])}</td>'
                   f'<td style="font-family:monospace;">{esc(lam_cell[1])}</td>'
                   f'<td style="color:var(--muted);font-size:0.76rem;">{esc(info)}</td></tr>')
    lh, la = m['lam_home'], m['lam_away']
    out.append(f'<tr style="background:rgba(52,122,252,0.08);">'
               f'<td style="font-weight:700;">＝ 发布 λ</td>'
               f'<td style="font-family:monospace;font-weight:700;">{lh:.2f}</td>'
               f'<td style="font-family:monospace;font-weight:700;">{la:.2f}</td>'
               f'<td style="font-size:0.76rem;">两队期望进球 → 比分矩阵 → '
               f'<b>比分预测 {esc(dash(hscore))}</b></td></tr>')
    out.append('</tbody></table></div>')
    return '\n'.join(out)


def match_card(m):
    hh = H2H.get(m['matchNumStr']) or []
    olabel, okey, dscore, dprob, oprob = direction_pick(m)
    tg = total_goals_info(m)
    # 比分区（头条 / 双档 / ±1球覆盖 / 概率组）由引擎 B（独立比分引擎）输出；
    # 引擎 B 不可用时回退到引擎 A 的矩阵口径，保证页面永远能出。
    _sp = score_pred(m)
    if _sp and _sp.get('top_scores'):
        _tsB = _sp['top_scores']
        hscore, hprob = _pub_head(m, _tsB)
        qp = [(t['score'], t['prob']) for t in _tsB if t['score'] != hscore][:2]
        bp = _sp['cover1'] / 100.0
        _lhB, _laB = _sp['lam_h'], _sp['lam_a']
        _grpB = ' · '.join(f'{dash(t["score"])} {t["prob"]:.1f}%' for t in _tsB[:7])
        _covB = f'Top3 {_sp["top3"]:.1f}% · 榜首 {_tsB[0]["prob"]:.1f}%'
    else:
        hscore, hprob = hit_pick(m)
        qp = hit_band(m, 2)
        bp = band_prob(m, hscore)
        _lhB, _laB = m['lam_home'], m['lam_away']
        _grpB = score_group(m, 5)
        _covB = f'Top3 {coverage(m,3):.1f}% · Top5 {coverage(m,5):.1f}%'
    escore, eprob, esame = expect_score(m)
    qp_join = ' + '.join(f'{dash(s)} {p:.1f}%' for s, p in qp) or dash(dscore)
    qp_sum = sum(p for _, p in qp)
    hprob_str = f'｜模型给该比分 {hprob:.1f}%' if hprob is not None else ''
    # 联合众数落在倾向象限之外时（约 6 成场次会发生：P(主胜)>P(平) 但 P(1:1)>P(1:0)），
    # 加一句提示，避免读者以为报告自相矛盾 —— 概率高的是「方向」，命中率高的是「单格」。
    _hs_dir = ('home' if int(hscore.split(':')[0]) > int(hscore.split(':')[1])
               else ('draw' if int(hscore.split(':')[0]) == int(hscore.split(':')[1]) else 'away')
               ) if ':' in str(hscore) else okey
    hm_mark = ('' if _hs_dir == okey else
               f'<br><span style="font-size:0.78rem;color:var(--muted);">'
               f'注：该首选比分不在{olabel}象限内 —— 方向概率最高的象限与单格概率最高的比分未必一致，'
               f'双档已一并覆盖两者。</span>')
    cred_tag, cred_cls = score_cred(m)
    # 注：不再展示「全局众数」（结构性退化为 1:1），改由 score_group / coverage 呈现
    hm = h2h_mean(m)
    hm_str = f'{hm:.2f} 球' if hm else '数据不足'
    factor_str = f'{m["h2h_factor"]:.2f}' + ('（含方向再分配）' if m['dir_applied'] else '')
    zero = m['zero']
    o = m['odds']
    hist_rows = ''
    for x in hh[:6]:
        hg, ag = x['home_goals'], x['away_goals']
        cls = 'var(--win)' if hg > ag else ('var(--draw)' if hg == ag else 'var(--loss)')
        res = '主胜' if hg > ag else ('平局' if hg == ag else '客胜')
        hist_rows += f'<tr><td style="color:{cls};">{hg}-{ag}</td><td>{res}</td></tr>'
    if not hist_rows:
        hist_rows = '<tr><td colspan="2">H2H数据不足</td></tr>'
    n_h2h = len(hh) if hh else m.get('h2h_count', 0)
    # 冷门信号块
    sig_html = ''
    if m['signals'] and m['signals'] != ['无明显冷门信号']:
        sig_items = ''.join(f'<strong>{esc(s)}</strong>；' for s in m['signals'])
        sig_html = f'<div class="warning">⚠️ 冷门信号：{sig_items}</div>'
    _u = m.get('upset')
    upset_tag = (f' <span class="tag {UPSET_CLS.get(_u["level"], "tag-blue")}" '
                 f'style="margin-left:0.6rem;">冷门风险 {_u["prob"]:.0f}%（{_u["level"]}）</span>'
                 ) if _u else ''
    return f'''
<div class="card" id="match-{esc(m["matchNumStr"])}">
  <div class="card-header">
    <span class="match-id">{esc(m["matchNumStr"])}</span>
    <span class="match-league">{esc(m["league"])}</span>
    <span class="match-time">{TODAY}</span>
  </div>

  <div class="match-teams">
    <span class="home">{team_with_rank(m["home"], m["home_rank"] or rank_of(m["home"], m["league"]))}</span>
    <span class="vs">VS</span>
    <span class="away">{team_with_rank(m["away"], m["away_rank"] or rank_of(m["away"], m["league"]))}</span>
  </div>

  <div class="odds-grid">
    <div class="odds-item"><div class="label">主胜</div><div class="value win">{esc(o.get("胜","-"))}</div></div>
    <div class="odds-item"><div class="label">平局</div><div class="value draw">{esc(o.get("平","-"))}</div></div>
    <div class="odds-item"><div class="label">客胜</div><div class="value loss">{esc(o.get("负","-"))}</div></div>
  </div>

  <h4>积分排名与形势</h4>
  <div class="insight-grid">
    <div class="insight-card"><div class="insight-label">主队排名</div><div class="insight-value">{rank_disp(m["home"], m["league"], m.get("home_rank"))} / {esc(m["league"])}</div></div>
    <div class="insight-card"><div class="insight-label">客队排名</div><div class="insight-value">{rank_disp(m["away"], m["league"], m.get("away_rank"))} / {esc(m["league"])}</div></div>
    <div class="insight-card"><div class="insight-label">H2H场均进球</div><div class="insight-value">{hm_str}</div></div>
    <div class="insight-card"><div class="insight-label">H2H调整因子</div><div class="insight-value">{esc(factor_str)}</div></div>
  </div>

  {pedigree_block(m)}
  <h4>历史交锋（近{n_h2h}场）</h4>
  <div class="table-wrap">
    <table class="history-table">
      <thead><tr><th>比分</th><th>赛果</th></tr></thead>
      <tbody>{hist_rows}</tbody>
    </table>
  </div>

  <h4>伤停与赛前分析</h4>
  {news_html(m)}

  {sig_html}
  {upset_block(m)}
  {rq_block(m)}
  <div class="prediction">
    <div class="pred-title">🎯 比分与方向预测</div>
    <div class="pred-row">
      <span class="pred-label">比分预测:</span>
      <span class="pred-score">{dash(hscore)}</span>
      <span class="pred-value">（{olabel}倾向｜<b>首选比分</b>{hprob_str}）{hm_mark}</span>
    </div>
    <div class="pred-row">
      <span class="pred-label">比分双档:</span>
      <span class="pred-score">{esc(qp_join)}</span>
      <span class="pred-value">（除首选外概率最高的两个比分，合计 <b>{qp_sum:.1f}%</b>
        <span style="color:var(--muted);">· 长期双档命中约 20%</span>）</span>
    </div>
    <div class="pred-row">
      <span class="pred-label">量级参考:</span>
      <span class="pred-score">{dash(escore)}</span>
      <span class="pred-value"><span style="color:var(--muted);">λ 期望进球取整（{_lhB:.2f}:{_laB:.2f}{'' if esame else '｜象限内已修正'}）—— <b>只看进球量级，不为押中</b></span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">±1球覆盖:</span>
      <span class="pred-score">{f'{bp*100:.1f}%' if bp is not None else '-'}</span>
      <span class="pred-value"><span style="color:var(--muted);">实际比分落在头条比分上下各 1 球内的概率（约 <b>67%</b>）—— 跟单场比分最该看的容错数字</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">比分概率组:</span>
      <span class="pred-value">{esc(_grpB)}</span>
    </div>
    <div class="pred-row">
      <span class="pred-label">覆盖汇总:</span>
      <span class="pred-value">{esc(_covB)}
        <span style="color:var(--muted);">（长期命中：榜首约 15% · Top3 约 39% · ±1球 约 67%）</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">可信度:</span>
      <span class="tag {cred_cls}">{esc(cred_tag)}</span>
      <span class="pred-value"><span style="color:var(--muted);">λ总量 {m['lam_home']+m['lam_away']:.2f}，按历史同档实测。总进球越低比分越值得看；高总进球场次请以方向与总量为主</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">信心评级:</span>
      {stars_html(m['stars'])}{upset_tag}
      <span class="pred-value"><span style="color:var(--muted);">方向确定性 {max(m["prob"]["home"], m["prob"]["draw"], m["prob"]["away"]):.1f}%（★ 越多越确定）</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">总进球倾向:</span>
      <span class="tag {tg['cls']}" style="margin-right:0.5rem;">{tg['tag']}</span>
      <span class="pred-value">≥3球 {tg['ge3']*100:.0f}% · ≥4球 {tg['ge4']*100:.0f}% · 最可能{tg['mode']}球 (λ总{tg['lt']:.2f})</span>
    </div>
    <h4 style="margin-top:0.9rem;">🧩 比分是怎么推出来的（因素链）</h4>
    <div style="font-size:0.78rem;color:var(--muted);margin-bottom:0.2rem;">
      比分不是「从分布里挑一格」，而是<b>因素先定 λ、λ 再定比分</b>；换个因素取值，λ 就换，比分跟着换。
    </div>
    {chain_table(m)}
    {('<div style="margin-top:0.35rem;font-size:0.76rem;color:var(--accent3);">'
      '⚠️ 本场竞彩未开出胜平负，<b>1X2 由比分盘反推</b>（31 档比分赔率去水后按主/平/客聚合）。</div>')
     if (m.get('odds') or {}).get('_hda_src') else ''}
    <div style="margin-top:0.4rem;font-size:0.78rem;color:var(--muted);">
      λ=主{m['lam_home']:.2f}/客{m['lam_away']:.2f}（总{m['lam_total']:.2f}） → 校准后 λ×{m.get('calib_note','1.00')}
    </div>
    <div style="margin-top:0.5rem;font-size:0.78rem;color:var(--muted);">
      📊 零封修正：主队近10场零封{zero['home_rate']*100:.0f}%→P(0)×{zero['f_home']:.1f} | 客队近10场零封{zero['away_rate']*100:.0f}%→P(0)×{zero['f_away']:.1f}
    </div>
  </div>
</div>
'''

deep_sec = '<h2>三、逐场深度分析</h2>\n' + '\n'.join(match_card(m) for m in MATCHES)

# ---------- 四、预测汇总（胜负+比分合并表 / 进球数）----------
DIR_TAG = {'主胜': 'tag-green', '平局': 'tag-yellow', '客胜': 'tag-red'}
rowsA = rowsB = rowsC = ''
for m in MATCHES:
    ts = m['top_scores']
    cold = esc(m['signals'][0]) if m['signals'] and m['signals'] != ['无明显冷门信号'] else '-'
    tg = total_goals_info(m)
    pr = m['prob']
    num_cell = f'<td><span class="tag tag-blue">{esc(m["matchNumStr"])}</span></td>'
    pair = f'<td>{rank_tag(m["home"], m["home_rank"])}</td><td>{rank_tag(m["away"], m["away_rank"])}</td>'
    # 4.1 胜负预测（引擎 A）：倾向 + 方向可信度 + 让球盘口与判读。比分区已拆到 4.2。
    dlabel2, dkey2, ds2, dp2, op2 = direction_pick(m)
    _cred_t, _cred_c = dir_cred(m)
    _hc, _hj = rq_cells(m)
    _u = m.get('upset')
    _cold_cell = (f'<span class="tag {UPSET_CLS.get(_u["level"], "tag-blue")}">{_u["prob"]:.0f}%</span>'
                 if _u else '-')
    rowsA += (f'<tr>{num_cell}{pair}'
              f'<td><span class="tag {DIR_TAG.get(dlabel2, "tag-blue")}">{dlabel2} {op2*100:.1f}%</span></td>'
              f'<td><span class="tag {_cred_c}">{_cred_t}</span></td>'
              f'{_hc}{_hj}'
              f'<td style="text-align:center;white-space:nowrap;">{_cold_cell}</td></tr>')
    # 4.2 比分预测（引擎 B：双方进球联合分布 —— 主/客各进几球 + 首选比分 + 双档比分）
    sp = score_pred(m)
    if sp and sp.get('top_scores'):
        _ts2 = sp['top_scores']
        _lt = sp['lam_h'] + sp['lam_a']
        _bct, _bcc = lam_cred(_lt)
        _pk2, _pkp2 = _pub_head(m, _ts2)
        _bd2 = [(t['score'], t['prob']) for t in _ts2 if t['score'] != _pk2][:2]
        _pp = (f' <span style="color:var(--muted);font-size:0.76rem;">{float(_pkp2):.1f}%</span>'
               if _pkp2 is not None else '')
        _c1 = (f'<td style="font-family:monospace;white-space:nowrap;">'
               f'<b style="color:var(--accent);">{esc(_pk2)}</b>{_pp}</td>')
        if _bd2:
            _c2 = ('<td style="font-family:monospace;white-space:nowrap;">'
                   + ' + '.join(f'{esc(s)} <span style="color:var(--muted);font-size:0.76rem;">'
                                f'{float(p):.1f}%</span>' for s, p in _bd2)
                   + '</td>')
        else:
            _c2 = '<td style="text-align:center;color:var(--muted);">—</td>'
        _mode_h = (f'<td style="text-align:center;white-space:nowrap;"><b>{sp["home_mode"]}</b> 球'
                   f' <span style="color:var(--muted);font-size:0.76rem;">{sp["home_mode_p"]:.0f}%</span></td>')
        _mode_a = (f'<td style="text-align:center;white-space:nowrap;"><b>{sp["away_mode"]}</b> 球'
                   f' <span style="color:var(--muted);font-size:0.76rem;">{sp["away_mode_p"]:.0f}%</span></td>')
        rowsC += (f'<tr>{num_cell}{pair}'
                  f'<td style="font-family:monospace;white-space:nowrap;">{sp["lam_h"]:.2f} / {sp["lam_a"]:.2f}</td>'
                  f'{_mode_h}{_mode_a}{_c1}{_c2}'
                  f'<td>{sp["cover1"]:.0f}%</td>'
                  f'<td>{sp["top3"]:.0f}%</td>'
                  f'<td><span class="tag {_bcc}">{_bct}</span></td></tr>')
    # 4.3 进球数预测
    rowsB += (f'<tr>{num_cell}{pair}'
               f'<td><span class="tag {tg["cls"]}" title="λ总分{tg["lt"]:.2f}">{tg["tag"]}</span></td>'
               f'<td>{tg["ge3"]*100:.0f}%</td>'
               f'<td>{tg["ge4"]*100:.0f}%</td>'
               f'<td>{tg["mode"]} 球</td>'
               f'<td style="font-family:monospace;">{tg["lt"]:.2f}</td></tr>')

def _sub_table(title, note, head, body):
    return (f'<h3 style="margin:1.4rem 0 0.5rem;color:var(--accent);">{title}</h3>\n'
            f'<p style="font-size:0.82rem;color:var(--muted);margin:0 0 0.6rem;">{note}</p>\n'
            f'<div class="card"><div class="table-wrap"><table>\n'
            f'  <thead><tr>{head}</tr></thead>\n  <tbody>{body}</tbody>\n'
            f'</table></div></div>')

summary4_sec = f'''
<h2>四、预测汇总</h2>
<p style="font-size:0.85rem;color:var(--muted);">三块口径各自独立计算，互不引用：<b>4.1 胜负</b>（方向三率 + 让球盘）、
<b>4.2 比分</b>（双方进球数联合分布，给出两队各进几球与前两个可能比分）、<b>4.3 进球总量</b>（λ 泊松累加）。<b>比分预测</b> = 综合比分盘定价与模型分布选出的首选比分（小字为模型给该比分的概率，与逐场卡片一致；该比分与 4.1 的方向倾向可能不同象限，卡片会单独标注）；<b>比分双档</b> = 除首选外概率最高的两个比分（小字为各自概率，两者可能不同象限）。
单比分是 31 格划分里的一个单点，长期命中率约 <b>15%</b>，不同场次差别很大 —— 要容错就看 <b>±1球覆盖</b>；
只想跟方向，就只看 4.1 的倾向与方向可信度。</p>
{_sub_table('4.1 胜负预测', '胜/平/负三率经校准；<b>倾向</b> = 三者中概率最高者。<b>方向可信度</b> = 只看方向能不能跟：三率中最高者 <b>≥50% 可用</b>、<b>40%~50% 慎用</b>（三者接近，方向缺乏区分度）、<b>&lt;40% 别跟</b>。<b>让球盘</b> = 官方让球盘口（正数为主队受让）；<b>让球可信度</b> = 这个让球盘能不能跟，同样分 <b>可用 / 慎用 / 别跟</b>：<b>校准概率≥50% 且置信度≥中 可用</b>、<b>≥42% 慎用</b>、<b>其余别跟</b>（小字为最可能结果、概率与置信度）。',
'<th>编号</th><th>主队</th><th>客队</th><th>倾向</th><th>方向可信度</th><th>让球盘</th><th>让球可信度</th><th>冷门</th>', rowsA)}
{_sub_table('4.2 比分预测', '按<b>双方进球数的联合分布</b>给出：<b>预期进球</b> = 两队各自的期望进球（左主右客）；<b>可能进球</b> = 主队/客队各自最可能的进球数及其概率；<b>比分预测</b> = 首选比分（综合双方进球分布与比分盘定价选出的最优单格，同一比分每天最多出现 4 次以保证覆盖面，与逐场卡片一致，小字为该比分的概率）；<b>比分双档</b> = 除首选外概率最高的两个比分（小字为各自概率）。<b>可信度</b> = 这段比分能不能照抄单点：<b>可用 / 慎用 / 别跟</b>。单点长期约 <b>15%</b>，两格合计约 <b>20%</b>，<b>±1球覆盖</b>（实际比分落在可能比分1 上下各 1 球内）约 <b>67%</b> —— 跟比分先看这个。',
'<th>编号</th><th>主队</th><th>客队</th><th>预期进球(主/客)</th><th>可能进球(主)</th><th>可能进球(客)</th><th>比分预测</th><th>比分双档</th><th>±1球覆盖</th><th>Top3覆盖</th><th>可信度</th>', rowsC) if rowsC else ''}
{_sub_table('4.3 进球数预测', 'λ主/客独立泊松相加。大球: P(≥3)≥58% · 小球: ≤42% · 其余均势；"最可能"为总进球众数。',
            '<th>编号</th><th>主队</th><th>客队</th><th>总进球倾向</th><th>P(≥3球)</th><th>P(≥4球)</th><th>最可能总进球</th><th>λ总分</th>', rowsB)}
{market_dev_section(MATCHES)}
{upset_table()}
{big_goals_table()}
'''

# ---------- 五、核心策略与风险提示 ----------
by_stars = sorted(MATCHES, key=lambda m: (-m['stars'], -first_score(m)[1]))
conf_pool_all = [m for m in by_stars if m['stars'] >= 3]
# V3.3：高冷门风险场次不进信心串关（时间外高风险 1/3 翻车率 ≈44% vs 低风险 ≈25%）
_hi_risk = [m for m in conf_pool_all if (m.get('upset') or {}).get('level') == '高']
conf_pool = [m for m in conf_pool_all if m not in _hi_risk]
cold_pool = [m for m in MATCHES if any(('凯利' in s or '排名背离' in s or '爆冷' in s or '防平防冷' in s or '双平' in s) for s in m['signals'])]

def make_group(ms):
    """比分串关的腿：统一走头条口径「命中比分」（矩阵联合众数），概率取该比分模型概率。

    此处只作高赔彩票型展示：lambda_level_probe.py 回测 3 串 1（比分腿）198 天仅中 1 天（0.5%），
    故真实概率必须如实标注，不作推荐强度使用。
    """
    legs, odds_prod, prob_prod = [], 1.0, 1.0
    for m in ms:
        _ol, _ok, ds, dp, _op = direction_pick(m)
        s, hp = head_score(m)
        p = (hp / 100.0) if hp is not None else dp
        odd = score_odd(m, s)
        legs.append(f"[{m['matchNumStr']}]{m['home']}vs{m['away']} {dash(s)}")
        if odd:
            try: odds_prod *= float(odd)
            except ValueError: pass
        prob_prod *= p
    return ' × '.join(legs), odds_prod, prob_prod

# 比分串关推荐：信心串关（多组）+ 冷门串关（多组）
# 组数/腿数随当日场次缩放：每组至少2组、每组至少2腿
N = len(MATCHES)
legs_per_group = 3 if N >= 15 else 2
n_conf_groups = min(3, max(2, N // 8))     # 24场→3组，16场→2组，8场以下→2组
n_cold_groups = min(3, max(2, N // 10))    # 30场→3组，24场→2组，20场以下→2组
GROUP_NAME = ['A', 'B', 'C', 'D']

# 信心池不足时按冷门风险升序回补高冷门场次（保证组数，并在文案中显式说明）
_need_conf = n_conf_groups * legs_per_group
_conf_backfill = []
if len(conf_pool) < _need_conf:
    _pool = sorted(_hi_risk, key=lambda m: upset_pct(m) or 0)
    _conf_backfill = _pool[:_need_conf - len(conf_pool)]
    conf_pool = conf_pool + _conf_backfill

parlays = []
for i in range(n_conf_groups):
    legs = conf_pool[i*legs_per_group:(i+1)*legs_per_group]
    if len(legs) < 2:
        break
    parlays.append(('信心', GROUP_NAME[i], make_group(legs), min(m['stars'] for m in legs),
                    f"{len(legs)}串1：取评级最高（4-5★优先）的{len(legs)}场，比分腿用模型首选比分"
                    + ("；已剔除高冷门风险场次" if _hi_risk and not _conf_backfill else "")))

cold_sorted = sorted(cold_pool, key=lambda m: (-len(m['signals']), -first_score(m)[1]))
need = n_cold_groups * legs_per_group
if len(cold_sorted) < need:  # 冷门池不足：用信心池剩余场次锚定补足
    cold_sorted += [m for m in conf_pool if m not in cold_sorted][:need - len(cold_sorted)]
for i in range(n_cold_groups):
    legs = cold_sorted[i*legs_per_group:(i+1)*legs_per_group]
    if len(legs) < 2:
        break
    parlays.append(('冷门', GROUP_NAME[i], make_group(legs), min(m['stars'] for m in legs),
                    f"{len(legs)}串1：凯利异常/排名背离/德比双平等博平博冷方向，小注博高赔"))

parlay_rows = ''
for typ, gname, (comb, op, pp), st, note in parlays:
    cls = 'parlay-confident' if typ == '信心' else 'parlay-upset'
    parlay_rows += (f'<tr class="{cls}"><td><strong>{typ}串关 {gname}</strong><br>'
                    f'<span style="font-size:0.72rem;color:var(--muted);">{esc(note)}</span></td>'
                    f'<td>{esc(comb)}</td>'
                    f'<td style="font-family:monospace;font-weight:700;">{op:.2f}</td>'
                    f'<td>{pp*100:.2f}%</td><td>{stars_html(st)}</td></tr>')

# ---------- 方向串关（主口径，2026-09-13 新增）----------
# 依据 lambda_level_probe.py（1591 场，198 个比赛日）：以「倾向」为腿的 3 串 1 全中 25.3%、
# ROI −3.0%；而以「方向首选比分」为腿的 3 串 1 全中仅 0.5%（198 天中 1 天）。
DIR_ODD_KEY = {'home': '胜', 'draw': '平', 'away': '负'}


def make_dir_group(ms):
    legs, odds_prod, prob_prod = [], 1.0, 1.0
    for m in ms:
        olabel, okey, _ds, _dp, op = direction_pick(m)
        od = (m.get('odds') or {}).get(DIR_ODD_KEY.get(okey, '胜')) or ''
        legs.append(f"[{m['matchNumStr']}]{m['home']}vs{m['away']} {olabel}")
        if od:
            try:
                odds_prod *= float(od)
            except ValueError:
                pass
        prob_prod *= op
    return ' × '.join(legs), odds_prod, prob_prod


parlay_dir_rows = ''
for i in range(n_conf_groups):
    _legs = conf_pool[i*legs_per_group:(i+1)*legs_per_group]
    if len(_legs) < 2:
        break
    _comb, _op, _pp = make_dir_group(_legs)
    _st = min(m['stars'] for m in _legs)
    parlay_dir_rows += (f'<tr class="parlay-confident"><td><strong>方向串关 {GROUP_NAME[i]}</strong><br>'
                        f'<span style="font-size:0.72rem;color:var(--muted);">'
                        f'{len(_legs)}串1：评级最高（4-5★优先）的{len(_legs)}场，只取「倾向」不押比分'
                        + ("；已剔除高冷门风险场次" if _hi_risk and not _conf_backfill else "") + '</span></td>'
                        f'<td>{esc(_comb)}</td>'
                        f'<td style="font-family:monospace;font-weight:700;">{_op:.2f}</td>'
                        f'<td>{_pp*100:.1f}%</td><td>{stars_html(_st)}</td></tr>')

stars_dist = Counter(m['stars'] for m in MATCHES)
top_star = max(stars_dist) if stars_dist else 0
dist_desc = ' / '.join(f"{stars_dist.get(s,0)}场{s}★" for s in (5, 4, 3, 2, 1) if stars_dist.get(s, 0))
hi_note = '无4★以上场次——' if top_star < 4 else (f"共{stars_dist.get(4,0)+stars_dist.get(5,0)}场高信心场次，" if top_star >= 4 else '')
cold_cnt = sum(1 for m in MATCHES if m['signals'] != ['无明显冷门信号'])
dir_cnt = sum(1 for m in MATCHES if m['dir_applied'])
lam_mean = sum(m['lam_total'] for m in MATCHES) / len(MATCHES)
_lvl = Counter((m.get('upset') or {}).get('level') for m in MATCHES if m.get('upset'))
_upsets = [m['upset']['prob'] for m in MATCHES if m.get('upset')]
_upset_mean = sum(_upsets) / len(_upsets) if _upsets else 0
_rq_val = [m for m in MATCHES if m.get('rq') and m['rq']['best']['prob'] >= 50
           and m['rq']['conf'] in ('高', '中')]
_rq_void = [m for m in MATCHES if m.get('rq') and m['rq']['best']['prob'] >= 50
            and m['rq']['conf'] == '低']
_rq_hit = '、'.join(f"{m['matchNumStr']} {m['rq']['best']['pick']}({m['rq']['best']['prob']:.0f}%)"
                    for m in sorted(_rq_val, key=lambda x: -x['rq']['best']['prob'])[:4])
_bigs = sorted([m for m in MATCHES if m.get('big')], key=lambda m: -m['big']['cal6'])
_big_top = _bigs[0] if _bigs else None
_big_any = (1 - math.prod(1 - m['big']['cal6'] / 100 for m in _bigs)) * 100 if _bigs else 0
_big_card = ''
if _big_top:
    _bt = _big_top['big']
    _big_card = (
        '<div class="summary-card"><h4>🎯 大比分（6+）观察</h4>'
        '<p style="font-size:0.9rem;">今日最像出 6+ 的一场：<strong style="color:var(--accent2);">'
        f'{esc(_big_top["matchNumStr"])} {esc(_big_top["home"])}vs{esc(_big_top["away"])}</strong>'
        f'（校准 P(6+)≈<strong>{_bt["cal6"]:.1f}%</strong>，市场隐含 {_bt["market6"]:.1f}%）；'
        f'{len(_bigs)} 场「至少一场 6+」≈ <strong>{_big_any:.0f}%</strong>。'
        '<b>但别押大球</b>：市场对高进球系统性定价偏高，按赔率买「6 球」与「7+」长期均亏损。'
        '「最近天天有大球」是基础率 × 场次数的必然，不是可押的规律。</p></div>\n  ')

strategy_sec = f'''
<h2>五、核心策略与风险提示</h2>

<div class="summary-grid">
  <div class="summary-card"><h4>🎯 高信心场次</h4><p style="font-size:0.9rem;">本期最高评级 <strong style="color:var(--accent2);">{top_star}★</strong>（{dist_desc}），{hi_note}冷门信号普遍存在，串关按实际评级从严组串。</p></div>
  <div class="summary-card"><h4>⚠️ 冷门预警场次</h4><p style="font-size:0.9rem;">共 <strong style="color:var(--accent3);">{cold_cnt}</strong> 场检测到冷门信号（凯利指数异常/排名与赔率背离等），组串时应回避或仅作博冷补充。</p></div>
  <div class="summary-card"><h4>📊 大球概率</h4><p style="font-size:0.9rem;">本期场均总进球λ <strong>{lam_mean:.2f}</strong>；H2H大球因子≥1.3x的场次建议关注大球方向，H2H偏低的场次谨防闷平。</p></div>
  <div class="summary-card"><h4>🎲 冷门风险分布</h4><p style="font-size:0.9rem;">本期平均冷门概率 <strong style="color:var(--accent3);">{_upset_mean:.1f}%</strong>：低风险 <strong>{_lvl.get('低',0)}</strong> 场 · 中 <strong>{_lvl.get('中',0)}</strong> 场 · 高 <strong>{_lvl.get('高',0)}</strong> 场。<b>高风险场次已从信心串关中剔除</b>（时间外高风险 1/3 翻车率 ≈44% vs 低风险 ≈25%）。</p></div>
  {_big_card}<div class="summary-card"><h4>⚖️ 让球盘方向</h4><p style="font-size:0.9rem;">让球盘联合校准后<b>最可能结果概率≥50%</b> 且置信度≥中 的场次 <strong style="color:var(--accent2);">{len(_rq_val)}</strong> 场{('：' + _rq_hit) if _rq_hit else ''}；另有 <strong>{len(_rq_void)}</strong> 场概率达标但<b>置信度低</b>（|让球|≥3 / 分歧&gt;25pp / 无1X2锚点）已判为不可跟。让球盘抽水约 13%，<b>按概率给方向、不按赔率追价值</b>，只作参考。</p></div>
  <div class="summary-card"><h4>🔄 方向性调整</h4><p style="font-size:0.9rem;">本日 <strong style="color:var(--accent2);">{dir_cnt}</strong> 场应用了 H2H 方向性调整，胜负记录直接改变 λ 分配而非只调总进球。</p></div>
  <div class="summary-card"><h4>🚑 伤病影响</h4><p style="font-size:0.9rem;">多支球队的伤病与战意信息已纳入逐场分析，核心球员缺阵对强队战力影响显著，重点关注伤停卡片。</p></div>
  <div class="summary-card"><h4>⚖️ 凯利指数</h4><p style="font-size:0.9rem;">部分场次赔率与模型预测存在偏差，模型与市场方向背离的场次已在冷门列标注，需谨慎对待。</p></div>
</div>

<div class="warning">
  <strong>风险提示：</strong>足球比赛存在较大不确定性，伤病、红牌、点球、VAR等因素均可能影响比赛结果。本报告基于历史数据和AI模型分析，仅供参考，不构成投注建议。请理性购彩，量力而行。
</div>

<div class="parlay-section">
  <h3>方向串关推荐</h3>
  <table class="parlay-table">
    <tr><th>类型</th><th>组合</th><th>组合赔率</th><th>综合概率</th><th>信心评级</th></tr>
    {parlay_dir_rows}
  </table>
  <div class="parlay-note">注：以「倾向」（胜/平/负）为串关腿，不押具体比分。长期回测单腿方向命中约 54%、3 腿全中约 25%，是唯一接近盈亏平衡的串关口径（比分串关全中率不到 1%，仅供博高赔）。</div>
</div>

<div class="parlay-section">
  <h3>比分串关推荐</h3>
  <table class="parlay-table">
    <tr><th>类型</th><th>组合</th><th>组合赔率</th><th>综合概率</th><th>信心评级</th></tr>
    {parlay_rows}
  </table>
  <div class="parlay-note">注：综合概率为各场比分腿概率连乘。<b>比分串关 3 腿全中率不到 1%</b>，组合概率常低至 0.1%~0.4%——请当买彩票而非投资建议，切勿重注。想提高命中率请看上表 <b>Top3 覆盖 / ±1球覆盖</b>，而非串关。信心串关绿色背景，冷门串关橙色背景（博平/博冷高赔方向）；组数与腿数随当日场次数量调整。</div>
</div>

<!--RECAP_PARLAY-->
'''

# ---------- 📊 动态校准与历史命中率 ----------
cal_daily = ''.join(
    f'<div class="cal-item"><span>{d["date"]}（{d["n"]}场）</span>'
    f'<span>预测均值 <strong>{d["pred"]:.2f}</strong> | 实际均值 <strong>{d["actual"]:.2f}</strong> | 偏差比 <strong>{d["actual"]/d["pred"]:.2f}</strong></span></div>'
    for d in CALIB.get('daily', []))
calib_sec = f'''
<h2>📊 动态校准与历史命中率</h2>
<div class="calibration-box">
  <div class="cal-item">
    <span>近5期预测总进球均值</span>
    <span><strong>{CALIB['pred_mean']:.2f}球</strong> | 实际均值: <strong>{CALIB['actual_mean']:.2f}球</strong></span>
  </div>
  <div class="cal-item">
    <span>系统偏差比</span>
    <span><strong style="color:var(--accent3);">{CALIB['ratio']:.2f}</strong> → 模型系统性低估 → λ×<strong>{CALIB['factor']:.2f}</strong> 已应用</span>
  </div>
  <div class="cal-item">
    <span>H2H 方向性再分配</span>
    <span><strong style="color:var(--accent2);">{dir_cnt}</strong> 场应用总量守恒再分配，胜负记录直接参与λ分配</span>
  </div>
  <div class="cal-item">
    <span>零封修正效果</span>
    <span>零封频率≤15%→P(0)×0.6，16-25%→×0.8，26-40%→×1.0，&gt;40%→×1.2，逐场已应用</span>
  </div>
  {cal_daily}
</div>
'''

now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
league_sec = build_league_sec(MATCHES)

# ---------- 🎯 今日比分精选（该押哪几场） ----------
# 依据（_daily_top_probe.py，4036 场 / 241 个比赛日，生产口径 w=0.3）：
#   全场次单比分命中 14.94%；按「模型给该比分的概率」排序每日取前 k 场 →
#   前1场 21.16%、前2场 21.88%、前3场 20.50%、前5场 19.64%；取前3场时 49.0% 的比赛日至少中 1 场。
#   模型自评概率五等分档实测命中单调：10.8% → 12.2% → 14.1% → 17.6% → 20.0%（最强档是最弱档的 1.9 倍）。
#   等价排序器（差 ≤1.4pp，均在噪声内）：λ总量最低 21.58/21.46/20.78%；概率÷λ总量 20.75/20.83/20.78%。
#   预测本身不改动，本节只是把「模型自己最有把握的场次」挑出来。
# ---------- 双档数量 & 准确率策略（用户 2026-09-16 定调）----------
# 每档：比分精选 TIER_PK 场、大胆档 TIER_BD 场（第一档）。
# 档数规则（用户定调）：以 N_TIER_BASE 场为基准 1 档，每多 N_TIER_STEP 场加 1 档
#   （10场→1档、18场→2档、26场→3档…）；每档场数固定，故总量成倍数增加。
# 优先保证第一档准确率——所有场次按「质量」从高到低排序，第一档取质量最高的
#   前 TIER_PK/TIER_BD 场，其后每档取次优的增量场次。
# 两个档完全独立计算：比分精选按「命中比分概率 × λ 质量系数」，
# 大胆档按「进攻型参考比分（量级档/极限档）模型概率」。
# 每日复盘后由 _optimize_selection.py 刷新 selection_tuning.json（质量系数 / 降权 / 门槛），
# 报告读取该文件以持续提升准确率；缺失则用下方内联默认。
TIER_PK = SA.TIER_PK        # 比分精选每档场数
TIER_BD = SA.TIER_BD        # 大胆档每档场数
N_TIER_BASE = SA.N_TIER_BASE   # 基准：10 场 → 1 档
N_TIER_STEP = SA.N_TIER_STEP   # 每多 8 场 → 多 1 档（18场→2档、26场→3档、34场→4档…）
TIER_MAX = SA.TIER_MAX      # 档数上限（安全护栏；切片不足时该档自然不出现）


def _selection_tuning():
    return SA.load_tuning()


_TUNING = _selection_tuning()


def _pk_ref(m):
    """比分精选自带模型：本板块自己算分布，自己出头条与双档（不读引擎比分矩阵）。"""
    return SA.pk_ref(m, _TUNING)


def _lambda_quality(lt):
    return SA.lambda_quality(lt, _TUNING)


# 两块独立成榜（唯一入口 SA.split_boards）：比分精选先占位，大胆档只在剩余场次中独立选取。
# 排序、分档、冷启动排除、互斥全部由 selection_algo 负责，本文件不再自写排序。
_pk_t, _pk_flat, _bd_t, _bd_flat, _cold_matches = SA.split_boards(MATCHES, _TUNING)
_pk_tier_list = [[k + (m,) for k, m in t] for t in _pk_t]
_bd_tier_list = [[k + (m,) for k, m in t] for t in _bd_t]
_picks = [x for t in _pk_tier_list for x in t]
_bold = [x for t in _bd_tier_list for x in t]
_cold_list = [m.get('matchNumStr') or m.get('id') for m in _cold_matches]
_cold_note = ('注：' + '、'.join(esc(x) for x in _cold_list)
              + ' 缺少近期战绩，把握度与其他场次不可比，未纳入本榜。') if _cold_list else ''
_rows_pk = ''
_i = 0
for _ti, _tier in enumerate(_pk_tier_list, 1):
    if _ti >= 2:
        _rows_pk += (f'<tr><td colspan="8" style="background:rgba(128,128,128,0.10);'
                     f'font-size:0.74rem;font-weight:700;color:var(--muted);'
                     f'padding:0.35rem 0.5rem;">第{_ti}档（其余高置信场次 · 增量）</td></tr>')
    for (_s, _pf, _lt, _cf, _m) in _tier:
        _i += 1
        # 双档取本板块自己分布的第 2/3 高（不再引用引擎比分矩阵）
        _b2 = [(x[0], x[1]) for x in _pk_ref(_m)[2]]
        _b2txt = ' + '.join(dash(x[0]) for x in _b2) or dash(_s)
        _bb = band_prob(_m, _s)
        _ct, _cc = score_cred(_m)
        _rows_pk += (
            f'<tr><td style="text-align:center;font-weight:700;color:var(--accent);">{_i}</td>'
            f'<td><span class="tag tag-blue">{esc(_m["matchNumStr"])}</span> {esc(_m["league"])}</td>'
            f'<td>{esc(_m["home"])} vs {esc(_m["away"])}</td>'
            f'<td style="font-family:monospace;font-weight:700;color:var(--accent);">{dash(_s)}</td>'
            f'<td style="font-family:monospace;font-size:0.8rem;">{esc(_b2txt)}</td>'
            f'<td style="font-family:monospace;">{(f"{_bb*100:.0f}%" if _bb is not None else "-")}</td>'
            f'<td style="font-family:monospace;">{_pf:.1f}%<br>'
            f'<span style="color:var(--muted);font-size:0.7rem;">λ总{_lt:.2f}</span></td>'
            f'<td><span class="tag {_cc}">{esc(_ct.split("（")[0])}</span></td></tr>')

picks_sec = f'''
<h2>🎯 今日比分精选</h2>
<div class="card">
  <p style="font-size:0.86rem;color:var(--muted);margin-bottom:0.7rem;">
    下表按模型把握度从高到低列出今日最值得跟的比分。<b>第一档 {TIER_PK} 场（准确率优先）</b>，
    当日比赛越多则按倍数增档（今日 {len(MATCHES)} 场 → {len(_pk_t)} 档、共 {len(_picks)} 场）。
    单比分全场次平均命中约 <b>15%</b>、双档约 <b>20%</b>、±1 球覆盖约 <b>67%</b>；
    把握度高的场次命中率明显更高，因此跟单场比分只看这几场，其余场次请看方向与总进球倾向。
    本榜与下方「🔥 大胆档」各自独立成榜、同一场次不会重复出现。
  </p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>#</th><th>编号 · 联赛</th><th>对阵</th><th>命中比分</th><th>双档</th>
      <th>±1球</th><th>模型概率</th><th>可信度</th></tr></thead>
      <tbody>{_rows_pk}</tbody>
    </table>
  </div>
  <p style="font-size:0.76rem;color:var(--muted);margin-top:0.55rem;">
    排序依据 = 模型给「命中比分」的概率（小字为该场总进球 λ）。
    可信度越高 = 该场按同档 λ 的历史实测命中率越高，越值得跟。
    {_cold_note}
  </p>
<!--RECAP_PICKS-->
</div>
'''

# ---------- 🔥 大胆档（自带模型 · 进攻型参考） ----------
# 本档是独立板块：只用引擎 λ 自建比分分布，不看引擎的比分矩阵，也不与比分精选共享口径。
# 候选池在比分精选占位后互斥选取（同一场次不会两榜都上）。
#   量级档 = 该场倾向象限内、总球数按自身模型上移一档的最高概率比分；
#   极限档 = 同象限、总球数再上一档的最高概率比分。实现统一在 selection_algo.bd_ref。
def _bold_ref(m):
    return SA.bd_ref(m, _TUNING)


def _bold_rank(m):
    """排序（独立计算）：只看本档两个参考比分自身的模型概率，总 λ 仅作次级排序。

    实现统一放在 selection_algo，报告与每日优化共用同一份。"""
    return SA.bd_tuple(m, _TUNING)


_rows_bd = ''
_i = 0
for _ti, _tier in enumerate(_bd_tier_list, 1):
    if _ti >= 2:
        _rows_bd += (f'<tr><td colspan="7" style="background:rgba(128,128,128,0.10);'
                     f'font-size:0.74rem;font-weight:700;color:var(--muted);'
                     f'padding:0.35rem 0.5rem;">第{_ti}档（其余进攻型参考场次 · 增量）</td></tr>')
    for (_bp, _lt, _m) in _tier:
        _i += 1
        _s, _sp = head_score(_m)
        _e, _ep, _x, _xp = _bold_ref(_m)
        # 注：Python 3.11 的 f-string 表达式内禁止反斜杠，故把带引号的 <span> 前缀先拼好
        _MUTED_OPEN = '<span style="color:var(--muted);font-weight:400;">'
        _ep_txt = (" " + _MUTED_OPEN + f"{_ep:.1f}%" + "</span>") if _ep is not None else ""
        _xp_txt = (" " + _MUTED_OPEN + f"{_xp:.1f}%" + "</span>") if _xp is not None else ""
        _rows_bd += (
            f'<tr><td style="text-align:center;font-weight:700;color:var(--accent3);">{_i}</td>'
            f'<td><span class="tag tag-blue">{esc(_m["matchNumStr"])}</span> {esc(_m["league"])}</td>'
            f'<td>{esc(_m["home"])} vs {esc(_m["away"])}</td>'
            f'<td style="font-family:monospace;color:var(--muted);">{dash(_s)}</td>'
            f'<td style="font-family:monospace;font-weight:700;color:var(--accent3);">{dash(_e)}'
            f'{_ep_txt}</td>'
            f'<td style="font-family:monospace;font-weight:700;color:var(--accent);">{dash(_x) if _x else "—"}'
            f'{_xp_txt}</td>'
            f'<td style="font-family:monospace;">{_lt:.2f}</td></tr>')

bold_sec = f'''
<h2>🔥 大胆档</h2>
<div class="card">
  <p style="font-size:0.86rem;color:var(--muted);margin-bottom:0.7rem;">
    头条比分是分布里的单个最高格，进球数必然偏小。下表是<b>独立于比分精选的另一块榜单</b>
    （两榜不重复同一场比赛，已进入比分精选的场次不再出现在这里），
    挑出模型给出<b>高置信进攻结果</b>的场次（<b>第一档 {TIER_BD} 场</b>，
    当日比赛越多则按倍数增档，今日 {len(MATCHES)} 场 → {len(_bd_t)} 档、共 {len(_bold)} 场），
    另给两档进攻型参考：<b>量级档</b>（该场按进攻量级最可能的比分）、
    <b>极限档</b>（同倾向下总进球再上一档）。这两档赔率明显更高、命中率低于头条——
    想搏赔率看这里，跟单仍以稳档为准。
  </p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>#</th><th>编号 · 联赛</th><th>对阵</th><th>稳档（头条）</th>
      <th>量级档</th><th>极限档</th><th>λ总</th></tr></thead>
      <tbody>{_rows_bd}</tbody>
    </table>
  </div>
<!--RECAP_BOLD-->
</div>
'''

# ---------- 📅 前日回顾（比分精选 / 大胆档 昨日命中情况）----------
import datetime as _dt


def _yesterday_of(d):
    try:
        return (_dt.datetime.strptime(d, '%Y-%m-%d') - _dt.timedelta(days=1)).strftime('%Y-%m-%d')
    except Exception:
        return None


def _norm_snap_match(m):
    """快照里缺 prob/cold/data_n 字段时补默认，以便复用今日同款排序函数。"""
    nw = dict(m)
    if not isinstance(nw.get('prob'), dict):
        nw['prob'] = {
            'home': float(m.get('prob_home') or 0),
            'draw': float(m.get('prob_draw') or 0),
            'away': float(m.get('prob_away') or 0),
        }
    nw.setdefault('cold', False)
    nw.setdefault('data_n', {})
    return nw


_RESULTS_CACHE = None


def _results_cache():
    global _RESULTS_CACHE
    if _RESULTS_CACHE is not None:
        return _RESULTS_CACHE
    import os as _os, glob as _glob
    recs = {}
    for f in sorted(_glob.glob(_os.path.join('.', 'results_history', '*.json'))):
        if _os.path.basename(f) == 'index.json':
            continue
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict):
                    recs.setdefault(k, v)
    try:
        rd = json.load(open('results_data.json', encoding='utf-8'))
        if isinstance(rd, dict):
            for k, v in rd.items():
                if isinstance(v, dict):
                    recs[k] = v
    except Exception:
        pass
    _RESULTS_CACHE = recs
    return recs


def _outcome_key(score_str):
    """比数字符串 → 'home'/'draw'/'away'；解析失败返回 None。"""
    try:
        h, a = (int(x) for x in str(score_str).replace('-', ':').split(':')[:2])
    except Exception:
        return None
    return 'home' if h > a else ('away' if a > h else 'draw')


def _lookup_actual(y, home, away):
    recs = _results_cache()
    for key in (f'{y}_{home}_{away}', f'{y}_{away}_{home}'):
        rec = recs.get(key)
        if rec:
            s = rec.get('score') or rec.get('fullScore') or ''
            if isinstance(s, str) and ':' in s:
                return s
    return None


def _build_recap():
    import os as _os
    y = _yesterday_of(TODAY)
    if not y:
        return '', ''
    snap_p = f'predictions/{y}/pred_snapshot.json'
    if not _os.path.exists(snap_p):
        _note = (f'<p style="font-size:0.78rem;color:var(--muted);margin-top:0.6rem;">'
                 f'📅 前日回顾：前一日（{y}）未生成预测报告，暂无可回顾数据。</p>')
        return _note, _note
    ysnap = json.load(open(snap_p, encoding='utf-8'))
    ym = [_norm_snap_match(x) for x in (ysnap.get('matches') or [])]

    # —— 两块独立成榜（与今日同一入口：比分精选先占位，大胆档互斥分池）——
    _y_pk_t, _, _y_bd_t, _, _ = SA.split_boards(ym, _TUNING)
    y_pk_tl = [[k + (m,) for k, m in t] for t in _y_pk_t]
    y_bd_tl = [[k + (m,) for k, m in t] for t in _y_bd_t]
    y_picks = [x for t in y_pk_tl for x in t]
    y_bold = [x for t in y_bd_tl for x in t]
    rows_pk, pk_hit, pk_miss, pk_wait = '', 0, 0, 0
    y_i = 0
    for y_ti, y_tier in enumerate(y_pk_tl, 1):
        if y_ti >= 2:
            rows_pk += (f'<tr><td colspan="7" style="background:rgba(128,128,128,0.10);'
                        f'font-size:0.74rem;font-weight:700;color:var(--muted);'
                        f'padding:0.35rem 0.5rem;">第{y_ti}档（增量）</td></tr>')
        for (_s, _pf, _lt, _pf2, _m) in y_tier:
            y_i += 1
            _dbl = [s for s, _ in _pk_ref(_m)[2]]
            _act = _lookup_actual(y, _m['home'], _m['away'])
            if _act is None:
                _res, _rcls, pk_wait = '⏳ 未出', 'tag-yellow', pk_wait + 1
            elif _act == _s:
                _res, _rcls, pk_hit = '✅ 命中', 'tag-green', pk_hit + 1
            elif _act in _dbl:
                _res, _rcls, pk_hit = '🟡 双档', 'tag-green', pk_hit + 1
            else:
                _res, _rcls, pk_miss = '❌ 未中', 'tag-red', pk_miss + 1
            rows_pk += (
                f'<tr><td style="text-align:center;font-weight:700;color:var(--accent);">{y_i}</td>'
                f'<td><span class="tag tag-blue">{esc(_m.get("matchNumStr") or _m.get("id"))}</span> {esc(_m["league"])}</td>'
                f'<td>{esc(_m["home"])} vs {esc(_m["away"])}</td>'
                f'<td style="font-family:monospace;font-weight:700;color:var(--accent);">{dash(_s)}</td>'
                f'<td style="font-family:monospace;font-size:0.8rem;">{" + ".join(dash(x) for x in _dbl)}</td>'
                f'<td style="font-family:monospace;">{dash(_act) if _act else "—"}</td>'
                f'<td><span class="tag {_rcls}">{_res}</span></td></tr>')

    # —— 大胆档回顾（量级档 / 极限档 vs 实际）——
    rows_bd, bd_hit, bd_miss, bd_wait = '', 0, 0, 0
    y_i = 0
    for y_ti, y_tier in enumerate(y_bd_tl, 1):
        if y_ti >= 2:
            rows_bd += (f'<tr><td colspan="7" style="background:rgba(128,128,128,0.10);'
                        f'font-size:0.74rem;font-weight:700;color:var(--muted);'
                        f'padding:0.35rem 0.5rem;">第{y_ti}档（增量）</td></tr>')
        for (_bp, _lt, _m) in y_tier:
            y_i += 1
            _e, _ep, _x, _xp = _bold_ref(_m)
            _act = _lookup_actual(y, _m['home'], _m['away'])
            if _act is None:
                _res, _rcls, bd_wait = '⏳ 未出', 'tag-yellow', bd_wait + 1
            elif _act == _e:
                _res, _rcls, bd_hit = '✅ 量级', 'tag-green', bd_hit + 1
            elif _x and _act == _x:
                _res, _rcls, bd_hit = '✅ 极限', 'tag-green', bd_hit + 1
            else:
                _res, _rcls, bd_miss = '❌ 未中', 'tag-red', bd_miss + 1
            rows_bd += (
                f'<tr><td style="text-align:center;font-weight:700;color:var(--accent3);">{y_i}</td>'
                f'<td><span class="tag tag-blue">{esc(_m.get("matchNumStr") or _m.get("id"))}</span> {esc(_m["league"])}</td>'
                f'<td>{esc(_m["home"])} vs {esc(_m["away"])}</td>'
                f'<td style="font-family:monospace;font-weight:700;color:var(--accent3);">{dash(_e)}</td>'
                f'<td style="font-family:monospace;font-weight:700;color:var(--accent);">{dash(_x) if _x else "—"}</td>'
                f'<td style="font-family:monospace;">{dash(_act) if _act else "—"}</td>'
                f'<td><span class="tag {_rcls}">{_res}</span></td></tr>')

    _pk_done, _bd_done = pk_hit + pk_miss, bd_hit + bd_miss
    _summ_pk = (f'前日（{y}）比分精选：已出 {_pk_done} 场 · 命中/双档 {pk_hit} · 未中 {pk_miss}'
                + (f' · 未出 {pk_wait}' if pk_wait else ''))
    _summ_bd = (f'前日（{y}）大胆档：已出 {_bd_done} 场 · 命中 {bd_hit} · 未中 {bd_miss}'
                + (f' · 未出 {bd_wait}' if bd_wait else ''))
    _picks = (
        f'<p style="font-size:0.82rem;font-weight:700;margin:0.9rem 0 0.3rem;color:var(--accent);">'
        f'📅 前日回顾（{y} 比分精选落地）</p>\n'
        f'<div class="table-wrap"><table>\n'
        f'<thead><tr><th>#</th><th>编号 · 联赛</th><th>对阵</th><th>命中比分</th><th>双档</th><th>实际</th><th>结果</th></tr></thead>\n'
        f'<tbody>{rows_pk}</tbody></table></div>\n'
        f'<p style="font-size:0.78rem;color:var(--muted);margin-top:0.45rem;">{_summ_pk}。'
        f'命中 = 实际比分等于预测「命中比分」；双档命中也算命中。</p>'
        if rows_pk else
        f'<p style="font-size:0.78rem;color:var(--muted);margin-top:0.6rem;">📅 前日回顾：{y} 无比分精选场次。</p>')
    _bold = (
        f'<p style="font-size:0.82rem;font-weight:700;margin:0.9rem 0 0.3rem;color:var(--accent3);">'
        f'📅 前日回顾（{y} 大胆档落地）</p>\n'
        f'<div class="table-wrap"><table>\n'
        f'<thead><tr><th>#</th><th>编号 · 联赛</th><th>对阵</th><th>量级档</th><th>极限档</th><th>实际</th><th>结果</th></tr></thead>\n'
        f'<tbody>{rows_bd}</tbody></table></div>\n'
        f'<p style="font-size:0.78rem;color:var(--muted);margin-top:0.45rem;">{_summ_bd}。'
        f'命中 = 实际比分等于「量级档」或「极限档」。</p>'
        if rows_bd else
        f'<p style="font-size:0.78rem;color:var(--muted);margin-top:0.6rem;">📅 前日回顾：{y} 无大胆档场次。</p>')
    return _picks, _bold


def _build_parlay_recap():
    """串关推荐下的「前日回顾」：按昨日**已发布报告**的串关表格逐腿核对赛果。

    数据源 = predictions/<昨日>/index.html 的串关表（= 当时实发内容，不受后续口径迭代影响）；
    赛果走 _lookup_actual（results_history 官方锚）；另附当日单场战绩（复用 gen_review 口径）。
    """
    import os as _os
    import re as _re
    y = _yesterday_of(TODAY)
    if not y:
        return ''

    def _wrap(inner):
        return ('<div class="parlay-section">\n  <h3>📅 前日回顾</h3>\n  ' + inner + '\n</div>\n')

    page_p = f'predictions/{y}/index.html'
    if not _os.path.exists(page_p):
        return _wrap(f'<div class="parlay-note">前一日（{y}）未生成预测报告，无可回顾的串关。</div>')
    html = open(page_p, encoding='utf-8').read()

    _KIND = {'方向串关': 'direction', '信心串关': 'score', '冷门串关': 'score'}
    _DKEY = {'主胜': 'home', '平局': 'draw', '客胜': 'away'}
    groups = []
    for cls in ('parlay-confident', 'parlay-upset'):
        for row in _re.findall(r'<tr class="%s">(.*?)</tr>' % cls, html, _re.S):
            cells = _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.S)
            if len(cells) < 2:
                continue
            name = _re.sub(r'\s+', ' ', _re.sub(r'<[^>]+>', ' ', cells[0])).strip()
            mh = _re.match(r'(方向串关|信心串关|冷门串关)\s*([A-D])', name)
            if not mh:
                continue
            prefix, gname = mh.group(1), mh.group(2)
            label, kind = prefix, _KIND[prefix]
            combo = _re.sub(r'<[^>]+>', '', cells[1]).strip()
            legs_html, n_bad, n_wait = [], 0, 0
            for leg in combo.split('×'):
                m2 = _re.match(r'\s*\[([^\]]+)\](.+?)vs(.+?)\s+(\S+)\s*$', leg)
                if not m2:
                    continue
                num, home, away = m2.group(1).strip(), m2.group(2).strip(), m2.group(3).strip()
                pick = m2.group(4).strip()
                pick_sc = pick.replace('-', ':')
                act = _lookup_actual(y, home, away)
                if act is None:
                    ok, n_wait = None, n_wait + 1
                elif kind == 'direction':
                    ok = _DKEY.get(pick) == _outcome_key(act)
                else:
                    ok = pick_sc == act.replace('-', ':')
                if act is None:
                    _mark, _mc = '⏳ 待赛果', 'var(--muted)'
                else:
                    _mark, _mc = ('✅', 'var(--accent2)') if ok else ('❌', 'var(--accent3)')
                    n_bad += 0 if ok else 1
                _show = pick_sc if kind == 'score' else pick
                legs_html.append(
                    f'<span class="tag tag-blue">{esc(num)}</span> {esc(home)} vs {esc(away)} '
                    f'<b style="font-family:monospace;">{esc(_show)}</b> '
                    f'<span style="color:{_mc};font-weight:700;">{_mark}</span>'
                    + (f' <span style="color:var(--muted);font-size:0.76rem;">实际 {esc(act)}</span>' if act else ''))
            if not legs_html:
                continue
            if n_wait:
                _v, _vc = '⏳ 待赛果', 'var(--muted)'
            elif n_bad == 0:
                _v, _vc = '✅ 全中', 'var(--accent2)'
            else:
                _v, _vc = f'❌ 挂 {n_bad} 腿', 'var(--accent3)'
            groups.append({'label': label, 'name': gname, 'kind': kind, 'legs': legs_html,                           'verdict': f'<span style="font-weight:700;color:{_vc};">{_v}</span>'})

    if not groups:
        return _wrap(f'<div class="parlay-note">前一日（{y}）报告无串关表格，无可回顾内容。</div>')

    rows = ''
    for g in groups:
        rows += ('<tr><td><strong>' + esc(g['label']) + ' ' + esc(g['name']) + '</strong>'
                 '<br><span style="font-size:0.72rem;color:var(--muted);">'
                 + ('方向腿' if g['kind'] == 'direction' else '比分腿') + '</span></td>'
                 '<td style="font-size:0.84rem;line-height:1.75;">' + '<br>'.join(g['legs']) + '</td>'
                 '<td>' + g['verdict'] + '</td></tr>')
    _d = [g for g in groups if g['kind'] == 'direction']
    _s = [g for g in groups if g['kind'] == 'score']
    _full = sum(1 for g in groups if g['verdict'].find('全中') >= 0)
    _summ = (f'前日（{y}）共 {len(groups)} 组串关：方向 {len(_d)} 组、比分 {len(_s)} 组，全部命中 {_full} 组。')
    _kpi = ''
    try:
        import gen_review as _GR
        _, _rows = _GR.day_rows(y)
        if _rows:
            _n, _dh, _hh, _bh = _GR.tally(_rows)
            if _n:
                _kpi = (f' 当日单场战绩：方向 <b>{_dh}/{_n}</b>（{_dh / _n * 100:.0f}%）、'
                        f'比分单点 <b>{_hh}/{_n}</b>、双档 <b>{_bh}/{_n}</b>（{_bh / _n * 100:.0f}%）。')
    except Exception:
        pass
    return _wrap(
        '<div class="table-wrap"><table>\n'
        '<thead><tr><th>组别</th><th>逐腿核对（预测 · 结果）</th><th>整组</th></tr></thead>\n'
        '<tbody>' + rows + '</tbody></table></div>\n'
        f'  <div class="parlay-note">{_summ}{_kpi} 赛果取官方锚；方向腿错一场即整组挂，比分腿同理。</div>')


recap_picks, recap_bold = _build_recap()
picks_sec = picks_sec.replace('<!--RECAP_PICKS-->', recap_picks)
bold_sec = bold_sec.replace('<!--RECAP_BOLD-->', recap_bold)
strategy_sec = strategy_sec.replace('<!--RECAP_PARLAY-->', _build_parlay_recap())
# ── 浮动章节导航（右侧目录 + 滚动高亮，窄屏自动折叠为悬浮按钮）────────────
# 自包含：自动扫描页面内所有 h2/h3，按需分配锚点 id 并生成目录项，
# 因此板块增减时无需同步维护列表；历史报告回填也复用同一段代码。
TOC_BLOCK = '''
<style>
  h2, h3 { scroll-margin-top: 1.2rem; }
  .toc-nav {
    /* 容器 1080px 居中 ⇒ 内容右缘距视口右 = (100vw-1080)/2。
       定位须满足 right + width ≤ 该间距 - 16px，否则会压住正文。 */
    --toc-w: 140px;
    position: fixed; top: 50%;
    right: clamp(8px, calc((100vw - 1080px) / 2 - var(--toc-w) - 16px), 32px);
    transform: translateY(-50%); width: var(--toc-w); max-height: 76vh; overflow-y: auto;
    background: rgba(255,255,255,0.96); border: 1px solid rgba(0,0,0,0.09);
    border-radius: 10px; padding: 0.7rem 0.5rem; z-index: 60;
    box-shadow: 0 4px 22px rgba(0,0,0,0.09); font-size: 0.78rem;
    scrollbar-width: thin;
  }
  @media (min-width: 1600px) { .toc-nav { --toc-w: 168px; font-size: 0.8rem; } }
  .toc-nav::-webkit-scrollbar { width: 4px; }
  .toc-nav::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.16); border-radius: 2px; }
  .toc-head {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em; color: var(--muted, #6c757d);
    padding: 0 0.55rem 0.45rem; border-bottom: 1px solid rgba(0,0,0,0.08); margin-bottom: 0.35rem;
  }
  .toc-list { list-style: none; margin: 0; padding: 0; }
  .toc-nav a {
    display: block; padding: 0.32rem 0.55rem; color: var(--muted, #6c757d); text-decoration: none;
    border-left: 2px solid transparent; border-radius: 0 4px 4px 0; line-height: 1.42;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; transition: none;
  }
  .toc-nav a:hover { color: var(--ink, #1a1a2e); background: rgba(0,0,0,0.045); }
  .toc-nav a.lv3 { padding-left: 1.05rem; font-size: 0.72rem; opacity: 0.9; }
  .toc-nav a.active {
    color: var(--accent, #e63946); border-left-color: var(--accent, #e63946);
    background: rgba(230,57,70,0.08); font-weight: 600;
  }
  .toc-toggle {
    position: fixed; right: 14px; bottom: 22px; width: 46px; height: 46px; border-radius: 50%;
    border: none; background: var(--accent, #e63946); color: #fff; font-size: 1.15rem;
    cursor: pointer; z-index: 61; box-shadow: 0 4px 14px rgba(230,57,70,0.36);
    display: flex; align-items: center; justify-content: center;
  }
  .toc-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.28); z-index: 59; }
  @media (min-width: 1400px) { .toc-toggle { display: none; } }
  @media (max-width: 1399px) {
    .toc-nav {
      --toc-w: 210px; right: 12px;
      transform: translateY(-50%) translateX(calc(100% + 26px));
      transition: transform 0.24s ease; max-height: 70vh; font-size: 0.82rem;
    }
    .toc-nav.open { transform: translateY(-50%) translateX(0); }
  }
</style>
<nav id="tocNav" class="toc-nav" aria-label="章节导航">
  <div class="toc-head">目录</div>
  <ul class="toc-list" id="tocList"></ul>
</nav>
<button id="tocToggle" class="toc-toggle" type="button" aria-label="打开章节目录" aria-expanded="false">&#9776;</button>
<script>
(function () {
  var nav = document.getElementById('tocNav');
  var list = document.getElementById('tocList');
  var btn = document.getElementById('tocToggle');
  if (!nav || !list) return;
  var scope = document.querySelector('body > .container') || document.body;
  var heads = [].filter.call(scope.querySelectorAll('h2, h3'), function (h) {
    return (h.textContent || '').trim().length > 0;
  });
  if (!heads.length) { nav.style.display = 'none'; if (btn) btn.style.display = 'none'; return; }

  var seq = 0;
  heads.forEach(function (h) {
    var txt = (h.textContent || '').trim().replace(/\\s+/g, ' ');
    if (!h.id) h.id = 'sec-' + (++seq);
    var a = document.createElement('a');
    a.href = '#' + h.id;
    a.textContent = txt;
    a.title = txt;
    if (h.tagName.toLowerCase() === 'h3') a.className = 'lv3';
    a.addEventListener('click', closeNav);
    var li = document.createElement('li');
    li.appendChild(a);
    list.appendChild(li);
  });

  var links = [].slice.call(list.querySelectorAll('a'));
  var mask = null;

  function closeNav() {
    nav.classList.remove('open');
    if (btn) btn.setAttribute('aria-expanded', 'false');
    if (mask) { mask.remove(); mask = null; }
  }
  if (btn) btn.addEventListener('click', function () {
    var open = nav.classList.toggle('open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      mask = document.createElement('div');
      mask.className = 'toc-mask';
      mask.addEventListener('click', closeNav);
      document.body.appendChild(mask);
    } else if (mask) { mask.remove(); mask = null; }
  });

  var current = heads[0];
  function spy() {
    var atBottom = (window.innerHeight + window.scrollY) >= (document.documentElement.scrollHeight - 4);
    var pick = heads[0];
    if (atBottom) {
      pick = heads[heads.length - 1];
    } else {
      for (var i = 0; i < heads.length; i++) {
        if (heads[i].getBoundingClientRect().top <= 140) pick = heads[i];
      }
    }
    if (pick === current) return;
    current = pick;
    var activeId = '#' + pick.id;
    links.forEach(function (a) { a.classList.toggle('active', a.getAttribute('href') === activeId); });
    var act = list.querySelector('a.active');
    if (act && nav.classList.contains('open') === false) {
      var nr = nav.getBoundingClientRect(), ar = act.getBoundingClientRect();
      if (ar.top < nr.top + 30 || ar.bottom > nr.bottom - 8) {
        nav.scrollTop += (ar.top - nr.top) - (nav.clientHeight / 2) + (ar.height / 2);
      }
    }
  }
  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { spy(); ticking = false; });
  }, { passive: true });
  window.addEventListener('resize', spy, { passive: true });
  spy();
})();
</script>'''

page = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>2026-{TODAY[5:]} 竞彩足球深度分析报告</title>
{CSS}
</head>
<body>

<!-- Hero区域 -->
<div class="hero">
  <div class="container">
    <h1>{TODAY} 竞彩足球深度分析报告</h1>
    <div class="subtitle">AI泊松模型V3.3 · 市场概率混合(总量守恒) · 比分矩阵对齐发布三率 · 让球盘联合校准 · 冷门风险分层 · 大比分(6+/7+)观察 · H2H方向性再分配 · 主客场分拆λ · {len(MATCHES)}场比赛全面覆盖</div>
    <div class="subtitle">数据更新时间: {now} (北京时间)</div>
    <div class="disclaimer">⚠️ 本报告仅供数据分析参考，不构成投注建议。理性购彩，量力而行。</div>
  </div>
</div>

<div class="container">

{picks_sec}
{bold_sec}
{overview_sec}
{chart_sec}
{deep_sec}
{summary4_sec}
{strategy_sec}
{league_sec}
{calib_sec}

</div>

<div class="footer">
  <div class="container">
    <p><strong>数据来源：</strong>P0级（官方赔率数据，网易彩票） | P1级（联赛积分榜、H2H 历史数据，积分榜与赛程来源 7m.com.cn / data.7m.com.cn） | P2级（伤病新闻、赛前预测分析，公开媒体报道）</p>
    <p style="margin-top:0.5rem;">AI泊松模型V3.3 · 指数衰减加权 · 主客场分拆λ · xG融合 · H2H总量因子+方向性再分配 · 市场概率混合(80%,总量守恒) · Platt校准 · 比分矩阵对齐发布三率 · 让球盘联合校准 · 冷门风险分层 · 大比分(6+/7+)观察 · 动态校准 · 零封修正</p>
    <p style="margin-top:0.5rem;">报告生成时间: {TODAY} | 仅供数据分析参考，不构成投注建议</p>
  </div>
</div>
{TOC_BLOCK}
</body>
</html>'''

out = f'predictions/{TODAY}/index.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(page)
print(f'已生成 {out}: {len(page)} 字符, {len(MATCHES)} 场卡片, 串关 {len(parlays)} 组')
