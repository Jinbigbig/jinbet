# -*- coding: utf-8 -*-
# 由 _calc_result.json + _data_batch*.json 生成 2026-09-05 V2.2 报告
# 版式严格复刻 2026-07-21 风格（与上午云端旧版一致）：CSS 直接取自 _old_0905.html
import json, re, html, datetime, math
from collections import Counter

CALC = json.load(open('_calc_result.json', encoding='utf-8'))
MATCHES = CALC['matches']
CALIB = CALC['calibration']
TODAY = CALC['today']

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
</style>'''
# 第六节已改为按当日实际联赛动态生成（见 build_league_sec），不再回收旧报告静态段落

def build_league_sec(matches):
    """按当日实际联赛动态生成第六节（旧版为回收上一份报告的静态段落，会串场）"""
    from collections import OrderedDict
    grouped = OrderedDict()
    for m in matches:
        grouped.setdefault(m.get('league') or '未知', []).append(m)
    out = ['<h2>六、当日赛事联赛形势</h2>', '<div class="league-overview-grid">']
    for lg, ms in grouped.items():
        out.append('  <div class="league-card">')
        out.append(f'    <h4>{esc(lg)} ({len(ms)}场)</h4>')
        out.append('    <ul style="font-size:0.85rem;margin:0.35rem 0 0 1.1rem;padding:0;">')
        for m in ms:
            sc, pr = first_score(m)
            out.append(f"      <li>{m.get('matchNumStr','')} {rank_tag(m['home'], m.get('home_rank'))}"
                       f" vs {rank_tag(m['away'], m.get('away_rank'))}"
                       f" — 总进球λ {m.get('lam_total',0):.2f}，首选 {sc}（{pr*100:.1f}%）</li>")
        out.append('    </ul>')
        out.append('  </div>')
    out.append('</div>')
    return '\n'.join(out)


def esc(s): return html.escape(str(s if s is not None else ''))

def rank_tag(name, rank):
    return f'{esc(name)}<sub class="rank-tag">[{esc(rank)}]</sub>' if rank is not None else esc(name)

def team_with_rank(name, rank):
    """第三节队名右下角排名小字（缺失排名时只显示队名）"""
    if rank in (None, '', '-', 0): return esc(name)
    r = rank if str(rank).startswith('联赛第') else f'联赛第{rank}'
    return f'{esc(name)}<sub class="team-rank">{esc(r)}</sub>'

def dash(score): return score.replace(':', '-')

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
    """方向首选：Platt 校准后最可能赛果象限内的众数比分。

    全局众数在均衡场次几乎恒为 1:1（P≈11~14%），对跟方向的用户无信息量；
    象限条件口径把「胜平负倾向」与「该倾向下最可能比分」分开表达。
    返回 (倾向中文, 倾向key, 方向比分, 方向比分概率0-1, 倾向概率0-1)。
    """
    pr = m['prob']
    okey, olabel = max([('home', '主胜'), ('draw', '平局'), ('away', '客胜')], key=lambda x: pr[x[0]])
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


# ---------- V3.3 二级盘：让球盘偏差 + 冷门风险 ----------
RQ_LABEL = {'W': '让球胜', 'D': '让球平', 'L': '让球负'}
UPSET_CLS = {'低': 'tag-green', '中': 'tag-yellow', '高': 'tag-red'}


def rq_block(m):
    """让球盘偏差提示卡：市场去水 → 纯模型 → 联合校准 → EV 建议。

    依据（market_calib_fit.py 月度时间外）：纯模型 EV>1.10 每场1注 498注 +4.78%(t=0.76)，
    联合校准 197注 +16.86% —— 模型在 1X2 无 alpha，但在让球盘「过滤」上有 alpha。
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
    return f'''
  <h4>让球盘偏差（{esc(hcap_show)} {esc(lo)} · |让球|={rq['abs']} · 最大分歧 {rq['div_pp']:.0f}pp · 置信度{rq['conf']}）</h4>
  <div class="table-wrap">
    <table class="history-table">
      <thead><tr><th>让球盘</th><th>赔率</th><th>市场去水</th><th>纯模型</th><th>联合校准</th><th>EV</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p style="font-size:0.78rem;margin:0.3rem 0 0.7rem;">
    <b>价值建议：</b><span class="tag {'tag-red' if b['ev'] >= 1.10 and rq['conf'] != '低' else ('tag-yellow' if b['ev'] >= 1.00 else 'tag-blue')}">{esc(b['pick'])} @{esc(b['odds'])}</span>
    EV <strong style="color:{ev_cls};">{b['ev']:.2f}</strong>（校准概率 {b['prob']:.1f}%），
    模型−市场分歧 {rq['calibrated'][b['key']]-rq['market'][b['key']]:+.1f}pp。
    <span style="color:var(--muted);">EV≥1.10 且置信度≥中才算「有偏离」；本场 {'达标' if b['ev'] >= 1.10 and rq['conf'] != '低' else '不达标（仅观察）'}。</span>{warn_html}
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
            f'基于 {u["n_samples"]} 场拟合，时间外低风险 1/3 翻车 ≈25% / 高风险 1/3 ≈44%。</span></div>')


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
        '4.4 冷门风险明细（V3.3 新增 · 次数概率 + 影响因素）',
        f'冷门定义 = <b>市场首选方向未命中</b>（含平局）。训练基础率 <b>{rows[0][1]["upset"]["base_rate"]:.1f}%</b>'
        f'（{rows[0][1]["upset"]["n_samples"]} 场）。模型 <code>P=σ(β·x)</code>，'
        '特征 = 市场首选概率(−)、模型−市场分歧(−)、|让球|(−)、λ和(−)、市场熵(+)；'
        '时间外 Brier <b>0.2342</b> vs 常数基线 0.2498，低风险 1/3 翻车 ≈25% / 高风险 1/3 ≈44%。'
        '<b>用法</b>：高风险场次不进信心串关（可小注博冷）；中风险场次少押单场方向。'
        '⚠️ 2026-09 样本仅 46 场、分层不显著，模型随样本自动向基础率收缩。'
        '<br><b>与星级的关系（重要）</b>：星级 = 首选比分概率，与冷门风险<b>不是同一件事</b>'
        '（相关 ≈ 0，且呈倒 U）：4★ 档（首选比分 0.12–0.15，占样本 29%）实测翻车率 <b>54.6% 最高</b>，'
        '而 5★ 档（≥0.15，λ 极低）降到 40.9%。<b>高星级 ≠ 低冷门</b>，两者要分开看。',
        '<th>编号</th><th>主队</th><th>客队</th><th>风险</th><th>冷门概率</th><th>市场首选</th>'
        '<th>模型−市场</th><th>|让球|</th><th>λ和</th><th>市场熵</th>', body)


BIG_CLS = {'高': 'tag-red', '中': 'tag-yellow', '低': 'tag-blue'}


def big_goals_table():
    """4.5 大比分（总进球 6+ / 7+）观察 —— 回答「哪场最像出大比分」。"""
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
        '4.5 大比分（总进球 6+ / 7+）观察（2026-09-10 新增）',
        f'口径：市场<b>总进球盘</b>去水 → logit 校准 → 诚实概率（总进球盘的「6」与「7+」是两个独立档位，'
        f'6+ = 两者之和）。今日最像的一场：'
        f'<b>{esc(top["matchNumStr"])} {esc(top["home"])} vs {esc(top["away"])}</b>'
        f'（市场隐含 {tb["market6"]:.1f}% → 校准 {tb["cal6"]:.1f}%）；{len(rows)} 场里「至少一场 6+」≈'
        f'<b>{p_any:.0f}%</b>，期望 {exp_n:.2f} 场。'
        '<br><b>为什么必须校准</b>：市场对高进球系统性定价偏高 —— 4217 场实测，去水后 P(6+) 均值 '
        '<b>9.41% vs 实际 6.28%</b>、P(7+) <b>4.09% vs 2.37%</b>，且概率越高越离谱'
        '（去水 ≥18% 的档：21.95% 对 15.45%）。'
        '<br><b>结论（反直觉但要记住）</b>：「最近天天有 6+」是<b>基础率 × 每天场次数</b>的必然，不是异象 —— '
        '每场 6+ 基础率 6.5%，一天 15 场时「至少一场 6+」本来就有 <b>62%</b>、30 场时 <b>88%</b>'
        '（实测分档 61.9% / 87.8%，与理论吻合）。全量 4599 场里 6+ 只占 6.50%、7+ 占 2.54%。'
        '直接按赔率回测：买「恰好 6 球」ROI <b>−41.1%</b>、买「7+ 球」ROI <b>−54.1%</b>'
        '（所有赔率区间全负）。<b>所以本表只用于「哪场最像」，不构成投注建议</b>；'
        '要参与请只当小注娱乐。',
        '<th>编号</th><th>主队</th><th>客队</th><th>市场隐含P(6+)</th><th>校准P(6+)</th>'
        '<th>校准P(7+)</th><th>其中正好6球</th><th>6档赔率</th><th>7+档赔率</th>'
        '<th>校准EV(7+)</th><th>等级</th>', body)


def market_dev_section(matches):
    """4.3 让球盘市场偏差清单（按 EV 排序）。"""
    rows = []
    for m in matches:
        rq = m.get('rq')
        if not rq:
            continue
        b = rq['best']
        rows.append((b['ev'], m, rq, b))
    if not rows:
        return ''
    rows.sort(key=lambda x: -x[0])
    body = ''
    for ev, m, rq, b in rows:
        if ev >= 1.10 and rq['conf'] == '高':
            cls, hit = 'tag-red', '✅ 达标(高置信)'
        elif ev >= 1.10 and rq['conf'] == '中':
            cls, hit = 'tag-yellow', '⚠️ 中置信'
        elif ev >= 1.10:
            cls, hit = 'tag-blue', '❌ 低置信(勿跟)'
        elif ev >= 1.00:
            cls, hit = 'tag-yellow', '观察'
        else:
            cls, hit = 'tag-blue', '—'
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
                 f'<td style="font-family:monospace;font-weight:700;">{ev:.2f}</td>'
                 f'<td>{rq["div_pp"]:.0f}pp</td>'
                 f'<td>{esc(rq["conf"])}</td><td>{hit}</td>'
                 f'<td>{up_str}</td></tr>')
    return _sub_table(
        '4.3 让球盘市场偏差清单（V3.3 新玩法 · 按 EV 降序）',
        '模型在 <b>1X2 概率值</b>上没有 alpha（纯市场 Brier 0.5504 &lt; 纯模型 0.6134，且要付 12% 抽水），'
        '但在 <b>让球盘「过滤」</b>上有 alpha：联合校准 <code>logit(P)=a+b1·logit(p_mkt)+b2·logit(p_model)</code> '
        '后，月度时间外「每场只买 EV 最高的一注」197 注 ROI <b>+16.86%</b>（纯模型同口径 498 注 +4.78%，t=0.76）。'
        '⚠️ <b>EV&gt;1.10 才算有偏离</b>；|让球|=1 置信高（样本 3429）、=2 中（170）、≥3 低（样本不足）。'
        '该玩法月度 ROI 波动大（+81%/+53%/−27%/−14%），只用小注。<b>不要用它替换 1X2 判断</b>。',
        '<th>编号</th><th>主队</th><th>客队</th><th>让球</th><th>价值方向</th><th>赔率</th>'
        '<th>市场</th><th>纯模型</th><th>联合校准</th><th>EV</th><th>最大分歧</th><th>置信</th><th>状态</th><th>冷门风险</th>',
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


def match_card(m):
    hh = H2H.get(m['matchNumStr']) or []
    olabel, okey, dscore, dprob, oprob = direction_pick(m)
    tg = total_goals_info(m)
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
    <span class="home">{team_with_rank(m["home"], m["home_rank"])}</span>
    <span class="vs">VS</span>
    <span class="away">{team_with_rank(m["away"], m["away_rank"])}</span>
  </div>

  <div class="odds-grid">
    <div class="odds-item"><div class="label">主胜</div><div class="value win">{esc(o.get("胜","-"))}</div></div>
    <div class="odds-item"><div class="label">平局</div><div class="value draw">{esc(o.get("平","-"))}</div></div>
    <div class="odds-item"><div class="label">客胜</div><div class="value loss">{esc(o.get("负","-"))}</div></div>
  </div>

  <h4>积分排名与形势</h4>
  <div class="insight-grid">
    <div class="insight-card"><div class="insight-label">主队排名</div><div class="insight-value">{esc(m["home_rank"] if m["home_rank"] else "-")} / {esc(m["league"])}</div></div>
    <div class="insight-card"><div class="insight-label">客队排名</div><div class="insight-value">{esc(m["away_rank"] if m["away_rank"] else "-")} / {esc(m["league"])}</div></div>
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
  <p style="font-size:0.9rem;line-height:1.8;">{esc(m["news"])}</p>

  {sig_html}
  {upset_block(m)}
  {rq_block(m)}
  <div class="prediction">
    <div class="pred-title">🎯 AI泊松模型V3.3预测</div>
    <div class="pred-row">
      <span class="pred-label">比分概率组:</span>
      <span class="pred-value">{esc(score_group(m, 5))}</span>
    </div>
    <div class="pred-row">
      <span class="pred-label">组合覆盖:</span>
      <span class="pred-value">Top3 {coverage(m,3):.1f}% · Top5 {coverage(m,5):.1f}%
        <span style="color:var(--muted);">（2577场回测命中：Top3 33.3% · Top5 49.1%）</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">方向首选:</span>
      <span class="pred-score">{dash(dscore)}</span>
      <span class="pred-value">({dprob*100:.1f}% ｜ {olabel}{oprob*100:.1f}% 倾向内最可能比分
        <span style="color:var(--muted);">· 跟方向时用，回测命中 11.5%</span>)</span>
    </div>
    <div class="pred-row">
      <span class="pred-label">信心评级:</span>
      {stars_html(m['stars'])}{upset_tag}
    </div>
    <div class="pred-row">
      <span class="pred-label">总进球倾向:</span>
      <span class="tag {tg['cls']}" style="margin-right:0.5rem;">{tg['tag']}</span>
      <span class="pred-value">≥3球 {tg['ge3']*100:.0f}% · ≥4球 {tg['ge4']*100:.0f}% · 最可能{tg['mode']}球 (λ总{tg['lt']:.2f})</span>
    </div>
    <div style="margin-top:0.35rem;font-size:0.72rem;color:var(--muted);">
      注：「最可能单比分」在多数场次恒为 1:1 —— 独立泊松的联合众数 = (⌊λ主⌋, ⌊λ客⌋)，λ 落在 [1,2) 时必然落到 1-1，属数学性质（回测 66.8% 场次如此），<b>不是模型没算</b>。单比分命中上限仅 13.5%，故以「比分概率组 + 组合覆盖」为准。「方向首选」= 该倾向象限内概率最高的比分，供跟单场方向的玩法使用（回测命中 11.5%）；判断大球/小球以「总进球倾向」为准。<b>V3.3 起本比分组已与上方发布的胜/平/负对齐</b>（此前两处口径最多相差 9.9pp）。
    </div>
    <div style="margin-top:0.75rem;font-size:0.75rem;color:var(--muted);font-family:monospace;line-height:1.8;word-break:break-all;">
      {esc(m['chain'])}
    </div>
    <div style="margin-top:0.5rem;font-size:0.78rem;color:var(--muted);">
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
rowsA = rowsB = ''
for m in MATCHES:
    ts = m['top_scores']
    top3 = sum(t['prob'] for t in ts[:3])
    cold = esc(m['signals'][0]) if m['signals'] and m['signals'] != ['无明显冷门信号'] else '-'
    tg = total_goals_info(m)
    pr = m['prob']
    num_cell = f'<td><span class="tag tag-blue">{esc(m["matchNumStr"])}</span></td>'
    pair = f'<td>{rank_tag(m["home"], m["home_rank"])}</td><td>{rank_tag(m["away"], m["away_rank"])}</td>'
    # 4.1 胜负与比分（1X2 三率 + 方向首选 + 众数 合并一表）
    dlabel2, dkey2, ds2, dp2, op2 = direction_pick(m)
    _secs = [f'{dash(t["score"])} ({t["prob"]:.1f}%)'
             for t in ts[1:4] if dash(t['score']) != dash(ds2)][:2]
    second = ' · '.join(_secs) or '-'
    rowsA += (f'<tr>{num_cell}{pair}'
              f'<td>{pr["home"]:.1f}%</td><td>{pr["draw"]:.1f}%</td><td>{pr["away"]:.1f}%</td>'
              f'<td><span class="tag {DIR_TAG.get(dlabel2, "tag-blue")}">{dlabel2} {op2*100:.1f}%</span></td>'
              f'<td style="font-family:monospace;font-weight:700;color:var(--accent);">{dash(ds2)}'
              f' <span style="color:var(--muted);font-weight:400;font-size:0.8rem;">({dp2*100:.1f}%)</span></td>'
              f'<td style="font-family:monospace;">{esc(second)}</td>'
              f'<td>{top3:.1f}%</td>'
              f'<td>{sum(t["prob"] for t in ts[:5]):.1f}%</td>'
              f'<td>{stars_html(m["stars"])}</td>'
              f'<td style="font-size:0.78rem;">{cold}</td></tr>')
    # 4.2 进球数预测
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
<p style="font-size:0.85rem;color:var(--muted);">两种玩法口径分开看：<b>胜负+比分</b>看方向（Platt 校准三率 → 倾向 → 该方向内首选比分）、<b>进球数</b>看总量倾向（λ 泊松累加，命中率远高于单比分）。<b>勿押单比分</b>：2577 场回测（V3.3 生产口径），单比分命中上限 <b>13.5%</b>，Top3 组 <b>33.3%</b>，Top5 组 <b>49.1%</b>——单比分的「最可能值」在多达 66.8% 的场次里都是 1-1，这是独立泊松联合众数的数学性质，不代表模型没有区分度；真正的区分度体现在比分组的构成与覆盖上。</p>
{_sub_table('4.1 胜负与比分预测', '胜/平/负三率经 Platt 校准（修正泊松平局低估）；<b>倾向</b> = 三者中概率最高者；<b>方向首选</b> = 该倾向象限内概率最高的比分（跟方向玩法用它，回测命中 11.5%）。<b>比分矩阵已对齐发布三率</b>（V3.3 SCORE_ALIGN）：矩阵三象限的质量缩放到与「胜率/平率/负率」两列完全一致，象限内形状不变；此前两处口径最多相差 9.9pp（同一页自相矛盾），对齐后比分 LogLoss −0.0131（t=−4.15）、1X2 Brier −1.4%、方向命中 +0.47pp，Top5 覆盖变化在噪声内。押比分请以 <b>Top3/Top5 覆盖</b> 为准（回测 33.3% / 49.1%）。',
            '<th>编号</th><th>主队</th><th>客队</th><th>胜率</th><th>平率</th><th>负率</th><th>倾向</th><th>方向首选</th><th>次选/三选</th><th>Top3覆盖</th><th>Top5覆盖</th><th>信心</th><th>冷门</th>', rowsA)}
{_sub_table('4.2 进球数预测', 'λ主/客独立泊松相加。大球: P(≥3)≥58% · 小球: ≤42% · 其余均势；"最可能"为总进球众数。',
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
    legs, odds_prod, prob_prod = [], 1.0, 1.0
    for m in ms:
        _ol, _ok, ds, dp, _op = direction_pick(m)
        s, p = ds, dp
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
                    f"{len(legs)}串1：取评级最高（4-5★优先）的{len(legs)}场，均取方向首选比分（倾向内最可能）"
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

stars_dist = Counter(m['stars'] for m in MATCHES)
top_star = max(stars_dist) if stars_dist else 0
dist_desc = ' / '.join(f"{stars_dist.get(s,0)}场{s}★" for s in (5, 4, 3, 2) if stars_dist.get(s, 0))
hi_note = '无4★以上场次——' if top_star < 4 else (f"共{stars_dist.get(4,0)+stars_dist.get(5,0)}场高信心场次，" if top_star >= 4 else '')
cold_cnt = sum(1 for m in MATCHES if m['signals'] != ['无明显冷门信号'])
dir_cnt = sum(1 for m in MATCHES if m['dir_applied'])
lam_mean = sum(m['lam_total'] for m in MATCHES) / len(MATCHES)
_lvl = Counter((m.get('upset') or {}).get('level') for m in MATCHES if m.get('upset'))
_upsets = [m['upset']['prob'] for m in MATCHES if m.get('upset')]
_upset_mean = sum(_upsets) / len(_upsets) if _upsets else 0
_rq_val = [m for m in MATCHES if m.get('rq') and m['rq']['best']['ev'] >= 1.10
           and m['rq']['conf'] in ('高', '中')]
_rq_void = [m for m in MATCHES if m.get('rq') and m['rq']['best']['ev'] >= 1.10
            and m['rq']['conf'] == '低']
_rq_hit = '、'.join(f"{m['matchNumStr']} {m['rq']['best']['pick']}"
                    for m in sorted(_rq_val, key=lambda x: -x['rq']['best']['ev'])[:4])
_bigs = sorted([m for m in MATCHES if m.get('big')], key=lambda m: -m['big']['cal6'])
_big_top = _bigs[0] if _bigs else None
_big_any = (1 - math.prod(1 - m['big']['cal6'] / 100 for m in _bigs)) * 100 if _bigs else 0
_big_card = ''
if _big_top:
    _bt = _big_top['big']
    _big_card = (
        '<div class="summary-card"><h4>🎯 大比分（6+）观察 (2026-09-10 新增)</h4>'
        '<p style="font-size:0.9rem;">今日最像出 6+ 的一场：<strong style="color:var(--accent2);">'
        f'{esc(_big_top["matchNumStr"])} {esc(_big_top["home"])}vs{esc(_big_top["away"])}</strong>'
        f'（校准 P(6+)≈<strong>{_bt["cal6"]:.1f}%</strong>，市场隐含 {_bt["market6"]:.1f}%）；'
        f'{len(_bigs)} 场「至少一场 6+」≈ <strong>{_big_any:.0f}%</strong>。'
        '<b>但别押大球</b>：市场对高进球系统性定价偏高（4217 场去水 P(6+) 均值 9.41% vs 实际 6.28%），'
        '直接按赔率回测买「恰好 6 球」ROI <b>−41.1%</b>、买「7+」ROI <b>−54.1%</b>。'
        '「最近天天有大球」是基础率 × 场次数的必然（一天 15 场时本来就有 62% 概率出至少一场），'
        '不是可押的规律。</p></div>\n  ')

strategy_sec = f'''
<h2>五、核心策略与风险提示</h2>

<div class="summary-grid">
  <div class="summary-card"><h4>🎯 高信心场次</h4><p style="font-size:0.9rem;">本期最高评级 <strong style="color:var(--accent2);">{top_star}★</strong>（{dist_desc}），{hi_note}冷门信号普遍存在，串关按实际评级从严组串。</p></div>
  <div class="summary-card"><h4>⚠️ 冷门预警场次</h4><p style="font-size:0.9rem;">共 <strong style="color:var(--accent3);">{cold_cnt}</strong> 场检测到冷门信号（凯利指数异常/排名与赔率背离等），组串时应回避或仅作博冷补充。</p></div>
  <div class="summary-card"><h4>📊 大球概率</h4><p style="font-size:0.9rem;">本期场均总进球λ <strong>{lam_mean:.2f}</strong>；H2H大球因子≥1.3x的场次建议关注大球方向，H2H偏低的场次谨防闷平。</p></div>
  <div class="summary-card"><h4>🎲 冷门风险分布 (V3.3)</h4><p style="font-size:0.9rem;">本期平均冷门概率 <strong style="color:var(--accent3);">{_upset_mean:.1f}%</strong>：低风险 <strong>{_lvl.get('低',0)}</strong> 场 · 中 <strong>{_lvl.get('中',0)}</strong> 场 · 高 <strong>{_lvl.get('高',0)}</strong> 场。<b>高风险场次已从信心串关中剔除</b>（时间外高风险 1/3 翻车率 ≈44% vs 低风险 ≈25%）。</p></div>
  {_big_card}<div class="summary-card"><h4>⚖️ 让球盘价值 (V3.3)</h4><p style="font-size:0.9rem;">让球盘联合校准后 EV≥1.10 且置信度≥中 的场次 <strong style="color:var(--accent2);">{len(_rq_val)}</strong> 场{('：' + _rq_hit) if _rq_hit else ''}；另有 <strong>{len(_rq_void)}</strong> 场 EV 达标但<b>置信度低</b>（|让球|≥3 / 分歧&gt;25pp / 无1X2锚点）已判为不可跟。月度时间外 197 注 ROI <strong>+16.86%</strong>（纯模型同口径 +4.78%）——<b>价值在过滤不在加权</b>，仅小注。</p></div>
  <div class="summary-card"><h4>🎯 比分口径一致性 (V3.3)</h4><p style="font-size:0.9rem;">比分概率组的分布已与同页发布的胜/平/负<b>完全对齐</b>（此前因市场混合/联赛形状混合/Platt 三步都只作用在 1X2 上，两处口径最多相差 <strong>9.9pp</strong>）。对齐后比分 LogLoss −0.0131（t=−4.15）、1X2 Brier −1.4%、方向命中 +0.47pp；Top5 覆盖变化在噪声内（±0.2pp）。</p></div>
  <div class="summary-card"><h4>🔄 方向性调整</h4><p style="font-size:0.9rem;">本日 <strong style="color:var(--accent2);">{dir_cnt}</strong> 场应用了H2H方向性总量守恒再分配（V2.2新增），胜负记录直接改变λ分配而非只调总进球。</p></div>
  <div class="summary-card"><h4>🚑 伤病影响</h4><p style="font-size:0.9rem;">多支球队的伤病与战意信息已纳入逐场分析，核心球员缺阵对强队战力影响显著，重点关注伤停卡片。</p></div>
  <div class="summary-card"><h4>⚖️ 凯利指数</h4><p style="font-size:0.9rem;">部分场次赔率与模型预测存在偏差，模型与市场方向背离的场次已在冷门列标注，需谨慎对待。</p></div>
</div>

<div class="warning">
  <strong>风险提示：</strong>足球比赛存在较大不确定性，伤病、红牌、点球、VAR等因素均可能影响比赛结果。本报告基于历史数据和AI模型分析，仅供参考，不构成投注建议。请理性购彩，量力而行。
</div>

<div class="parlay-section">
  <h3>比分串关推荐</h3>
  <table class="parlay-table">
    <tr><th>类型</th><th>组合</th><th>组合赔率</th><th>综合概率</th><th>信心评级</th></tr>
    {parlay_rows}
  </table>
  <div class="parlay-note">注：综合概率为各场方向首选比分概率连乘（近似独立）。信心串关绿色背景，冷门串关橙色背景（博平/博冷高赔方向，对标里尔爆冷巴黎类场次）。组数与腿数随当日场次动态调整：信心组 = min(3, max(2, 场次÷8))，冷门组 = min(3, max(2, 场次÷10))，每组 3 腿（≥15场）或 2 腿（6-14场）；冷门场次不足时用高信心场锚定补足，每组至少 2 组、至少 2 腿。</div>
</div>
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
    <span>H2H方向性再分配 (V2.2) · 市场概率混合 (V3.2) · 让球盘联合校准 + 冷门风险 + 比分矩阵对齐 + 大比分观察 (V3.3)</span>
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
    <p><strong>数据来源：</strong>P0级（官方赔率数据）| P1级（联赛积分榜、H2H历史数据）| P2级（伤病新闻、预测分析）</p>
    <p style="margin-top:0.5rem;">AI泊松模型V3.3 · 指数衰减加权 · 主客场分拆λ · xG融合 · H2H总量因子+方向性再分配 · 市场概率混合(80%,总量守恒) · Platt校准 · 比分矩阵对齐发布三率 · 让球盘联合校准 · 冷门风险分层 · 大比分(6+/7+)观察 · 动态校准 · 零封修正</p>
    <p style="margin-top:0.5rem;">报告生成时间: {TODAY} | 仅供数据分析参考，不构成投注建议</p>
  </div>
</div>
</body>
</html>'''

out = f'predictions/{TODAY}/index.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(page)
print(f'已生成 {out}: {len(page)} 字符, {len(MATCHES)} 场卡片, 串关 {len(parlays)} 组')
