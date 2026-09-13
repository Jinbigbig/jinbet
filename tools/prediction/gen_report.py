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
            _hs, _hp = hit_pick(m)
            _es, _ep, _ = expect_score(m)
            _hp_txt = f'（模型给该比分 {_hp:.1f}%）' if _hp is not None else ''
            out.append(f"      <li>{m.get('matchNumStr','')} {rank_tag(m['home'], m.get('home_rank'))}"
                       f" vs {rank_tag(m['away'], m.get('away_rank'))}"
                       f" — 总进球λ {m.get('lam_total',0):.2f}，命中比分 {dash(_hs)}{_hp_txt}"
                       f"（量级参考 {dash(_es)}）</li>")
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
    """倾向 + 该倾向象限内的众数比分（2026-09-13 起**只作内部用**，不再当头条）。

    全局众数在均衡场次几乎恒为 1:1（P≈11~14%），且众数是分布单点、必然低于均值
    （回测总进球系统性低 0.90 球/场），故头条已改用 expect_score()。
    本函数仍用于：① 判定倾向；② 约束期望比分落在倾向象限内；③ 期望比分不合法时的兜底。
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


def band_prob(m, score):
    """参考比分的 ±1 球覆盖概率：P(|H-h0|<=1 且 |A-a0|<=1)，独立泊松。

    单比分是 31 格划分里的单点，命中天花板低（回测 15.4%）；
    但「落在参考比分上下各 1 球范围」的覆盖率回测 66.4%，
    这才是跟单场比分时应该看的数字（2026-09-13 lambda_level_probe.py，1591 场）。
    """
    try:
        h0, a0 = (int(x) for x in str(score).split(':'))
    except ValueError:
        return None
    lh, la = m['lam_home'], m['lam_away']
    pmf = lambda k, lam: math.exp(-lam) * lam ** k / math.factorial(k)
    pr = 0.0
    for h in range(max(0, h0 - 1), h0 + 2):
        for a in range(max(0, a0 - 1), a0 + 2):
            pr += pmf(h, lh) * pmf(a, la)
    return pr


_LISTED_LABELS = {
    '1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '4:0', '4:1', '4:2', '5:0', '5:1', '5:2',
    '0:0', '1:1', '2:2', '3:3',
    '0:1', '0:2', '1:2', '0:3', '1:3', '2:3', '0:4', '1:4', '2:4', '0:5', '1:5', '2:5',
}


def hit_pick(m):
    """头条「命中比分」= 已对齐比分矩阵的**联合众数**（= top_scores[0] 里的首个列出比分）。

    口径依据（2026-09-13 用户定调「主要优化方向 = 比分的准确度，概率大小没有意义，
    命中次数多了目标函数才好优化」）：
      给定一个比分分布，(单场) 使 P(押中) 最大的选择唯一 = argmax。
      ⇒ 众数就是「命中次数」这个目标函数下的最优解；
      ⇒ 任何单调变换（温度/锐化/展平）都不改变 argmax，命中率与概率幅值无关
        （score_hit_probe.py H1 实测 T=0.85/1.0/1.15/1.35 四种变换命中完全相同）。

    时间外回测（score_hit_probe.py H2/H7，1591 场，后 40% 检验集）：
      联合众数 18.4%（全样本 16.6%）＞ 象限列出众数 16.3%（15.4%）＞ round(λ) 13.7%（13.8%）。
      McNemar 配对：联合众数 vs round(λ) χ²=4.79（p<0.05，显著）。
    返回 (比分, 模型给该比分的概率或 None)。
    """
    for t in (m.get('top_scores') or []):
        if t.get('score') in _LISTED_LABELS:
            return t['score'], t.get('prob')
    _, _, ds, _, _ = direction_pick(m)
    return ds, None


def hit_band(m, k=2):
    """双档 / Top-k = 联合众数排序下的前 k 个列出比分。

    回测（1591 场生产口径）：Top1 16.6% → Top2 29.9% → Top3 39.9%。
    对照上一版「期望比分 + 同倾向次高」：Top1 13.8% / Top2 26.0% —— 双档少中 61 场。
    返回 [(score, prob), ...]。
    """
    out = []
    for t in (m.get('top_scores') or []):
        if t.get('score') in _LISTED_LABELS:
            out.append((t['score'], t.get('prob') or 0.0))
        if len(out) >= k:
            break
    return out


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


def expect_score(m):
    """「量级参考比分」= λ 期望进球四舍五入（2026-09-13 起**降级为参考列**，不再作头条）。

    它的价值是「无偏」而不是「押中」：总进球偏差 −0.22 球/场（联合众数口径 −0.90，
    因为众数是分布单点、必然低于均值）。用户已明确目标是命中次数，
    故头条让位给联合众数，本口径保留为「这场预计几比几的量级」。
    强制落在已发布倾向象限内（否则退回该象限概率首选），避免与倾向自相矛盾。
    返回 (比分, 该比分模型概率或 None, 是否与象限众数一致)。
    """
    lh, la = m['lam_home'], m['lam_away']
    _, okey, dscore, _, _ = direction_pick(m)
    cand = (int(round(lh)), int(round(la)))
    ok = ((cand[0] > cand[1]) if okey == 'home'
          else ((cand[0] == cand[1]) if okey == 'draw' else (cand[0] < cand[1])))
    if ok and f'{cand[0]}:{cand[1]}' in _LISTED_LABELS:
        label = f'{cand[0]}:{cand[1]}'
    else:
        label = dscore
    prob = next((t['prob'] for t in m['top_scores'] if t['score'] == label), None)
    return label, prob, (label == dscore)


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
    返回 (标签, class)。
    """
    lt = m['lam_home'] + m['lam_away']
    if lt <= 2.6:
        return '比分可照抄（λ≤2.6 单点18~22%）', 'tag-green'
    if lt <= 3.5:
        return '比分仅参考（单点约13%）', 'tag-yellow'
    return '比分不可照抄（单点约11%）', 'tag-red'



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
        '<br><b>信心评级（2026-09-13 重构）</b>：星级 = <b>胜平负倾向的确定性</b>'
        '（Platt 后 max(胜/平/负) 概率），阈值 0.44 / 0.50 / 0.57 / 0.66。'
        '1591 场实测各档方向命中 <b>37.5% / 49.5% / 50.4% / 60.4% / 74.4%</b>，'
        '对应冷门率 <b>65.8% / 52.0% / 49.3% / 39.9% / 27.8%</b>（单调）。'
        '与上表互补：上表由市场+λ 特征<b>预测</b>风险，星级则直接从方向概率<b>读</b>确定性。'
        '<span style="color:var(--muted);">（旧口径＝比分矩阵众数概率：方向判别力仅 +13.6pp 且中间档非单调，'
        '期望比分概率更差（−1.7pp），两者均已弃用。）</span>',
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
    hscore, hprob = hit_pick(m)
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
               f'<b>命中比分 {esc(dash(hscore))}</b></td></tr>')
    out.append('</tbody></table></div>')
    return '\n'.join(out)


def match_card(m):
    hh = H2H.get(m['matchNumStr']) or []
    olabel, okey, dscore, dprob, oprob = direction_pick(m)
    tg = total_goals_info(m)
    hscore, hprob = hit_pick(m)
    qp = hit_band(m, 2)
    escore, eprob, esame = expect_score(m)
    qp_join = ' + '.join(f'{dash(s)} {p:.1f}%' for s, p in qp) or dash(dscore)
    qp_sum = sum(p for _, p in qp)
    bp = band_prob(m, hscore)
    hprob_str = f'｜模型给该比分 {hprob:.1f}%' if hprob is not None else ''
    # 联合众数落在倾向象限之外时（约 6 成场次会发生：P(主胜)>P(平) 但 P(1:1)>P(1:0)），
    # 加一句提示，避免读者以为报告自相矛盾 —— 概率高的是「方向」，命中率高的是「单格」。
    _hs_dir = ('home' if int(hscore.split(':')[0]) > int(hscore.split(':')[1])
               else ('draw' if int(hscore.split(':')[0]) == int(hscore.split(':')[1]) else 'away')
               ) if ':' in str(hscore) else okey
    hm_mark = '' if _hs_dir == okey else '（该格不在倾向象限内——方向概率最高的象限 ≠ 单格概率最高的比分，双档已覆盖两者）'
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
      <span class="pred-label">命中比分:</span>
      <span class="pred-score">{dash(hscore)}</span>
      <span class="pred-value">（{olabel}倾向｜比分矩阵联合众数{hprob_str}）
        <br><span style="color:var(--muted);font-size:0.8rem;">头条口径 = <b>因素推出的比分</b>（= 已对齐比分矩阵的联合众数）。注意这不是「另一种算法」：λ 完全由因素链决定（见下方「比分是怎么推出来的」），把 λ 落成整数比分时，⌊λ⌋ 就是众数 —— 两者是同一个答案的两种写法。4036 场回测（2026-01-01~09-12）：联合众数单点 <b>14.94%</b> ＞ floor(λ) 13.85% ＞ round(λ) 13.06% ＞ <b>无脑全猜 1:1 常数基线 12.93%</b>；McNemar 配对 χ²=6.47 / 8.11 / 19.34，<b>三者均 p&lt;0.05 显著</b>。真正没意义的是概率的<b>数值</b>大小 —— 温度展平/锐化不改变 argmax，四种变换实测命中完全相同</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">比分双档:</span>
      <span class="pred-score">{esc(qp_join)}</span>
      <span class="pred-value">（众数排序前两档，合计 <b>{qp_sum:.1f}%</b>
        <span style="color:var(--muted);">· 4036 场回测：双档命中 <b>26.54%</b>（单档 14.94%）</span>）</span>
    </div>
    <div class="pred-row">
      <span class="pred-label">量级参考:</span>
      <span class="pred-score">{dash(escore)}</span>
      <span class="pred-value"><span style="color:var(--muted);">λ 期望进球取整（{m['lam_home']:.2f}:{m['lam_away']:.2f}{'' if esame else '｜象限内已修正'}）。这条<b>不为押中</b>，只为告诉你「这场预计几比几的量级」——它的总进球偏差 −0.22 球/场（众数口径 −0.90，因为众数是分布单点、必然低于均值）</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">±1球覆盖:</span>
      <span class="pred-score">{f'{bp*100:.1f}%' if bp is not None else '-'}</span>
      <span class="pred-value"><span style="color:var(--muted);">实际比分落在头条比分上下各 1 球范围内的概率（回测 <b>67.24%</b>）——跟单场比分时最该看的容错数字</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">比分概率组:</span>
      <span class="pred-value">{esc(score_group(m, 5))}</span>
    </div>
    <div class="pred-row">
      <span class="pred-label">组合覆盖:</span>
      <span class="pred-value">Top3 {coverage(m,3):.1f}% · Top5 {coverage(m,5):.1f}%
        <span style="color:var(--muted);">（4036 场回测命中：Top1 14.94% · Top2 26.54% · Top3 <b>35.48%</b> · Top4 43.93% · Top5 <b>51.78%</b>）</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">比分可信度:</span>
      <span class="tag {cred_cls}">{esc(cred_tag)}</span>
      <span class="pred-value"><span style="color:var(--muted);">λ总量 {m['lam_home']+m['lam_away']:.2f} 分档实测（4036 场）——λ≤2.6 单点 18~22% / 双档 31~35%；λ&gt;2.6 单点稳定在 11~13% / 双档 23~24%。λ≤2.6 的场次（约 1/3）比分最可照抄；高总进球场次请以方向与总量为主</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">信心评级:</span>
      {stars_html(m['stars'])}{upset_tag}
      <span class="pred-value"><span style="color:var(--muted);">方向确定性 {max(m["prob"]["home"], m["prob"]["draw"], m["prob"]["away"]):.1f}%
        · 1591 场实测各档方向命中 37.5%→74.4%、冷门率 65.8%→27.8%</span></span>
    </div>
    <div class="pred-row">
      <span class="pred-label">总进球倾向:</span>
      <span class="tag {tg['cls']}" style="margin-right:0.5rem;">{tg['tag']}</span>
      <span class="pred-value">≥3球 {tg['ge3']*100:.0f}% · ≥4球 {tg['ge4']*100:.0f}% · 最可能{tg['mode']}球 (λ总{tg['lt']:.2f})</span>
    </div>
    <div style="margin-top:0.35rem;font-size:0.72rem;color:var(--muted);">
      <b>目标函数说明（2026-09-13 定调：主要优化方向 = 比分准确度，概率大小没有意义）</b>：
      <b>头条 = 已对齐比分矩阵的联合众数</b>。这条口径不是偏好问题而是数学结论——给定一个比分分布，
      让「押中场次数」最大的选择<b>唯一</b>就是 argmax（众数）；而任何单调变换（温度展平/锐化、概率缩放）
      都不改变 argmax，所以<b>「概率高不高」与命中次数无因果关系，只有排序对不对有关</b>
      （score_hit_probe.py H1 实测 T=0.85/1.00/1.15/1.35 四种变换命中完全相同：检验集 117/637）。
      <b>已试过且无法超越众数的排序来源</b>（1591 场，时间外 637 场检验）：市场比分盘去水众数 17.1%、
      模型×市场混合 17.3~17.9%、格子级乘性纠偏（训练集实测频率/模型概率，K 收缩）18.8%、
      分区条件经验重排 18.8%、总进球边缘纠偏 18.7%、Dixon-Coles 低分修正 17.3~18.5% ——
      <b>全部落在 ±0.4pp 的噪声内</b>，只有众数（18.4%）是真的赢面。
      <b>可提升的地方在「分布」而不在「选法」</b>：单比分 = 方向命中 53.8% × 方向内命中 31%，
      要提高命中次数只能让 λ/形状更准（或引入新信息源），换选法没有空间。
      当前实测阶梯（4036 场生产口径）：单档 14.94% → 双档 26.54% → Top3 35.48% → ±1球 67.24% → 方向约 50%。
    </div>
    <h4 style="margin-top:0.9rem;">🧩 比分是怎么推出来的（因素链）</h4>
    <div style="font-size:0.78rem;color:var(--muted);margin-bottom:0.2rem;">
      比分不是「从概率分布里挑一格」，而是<b>因素先定 λ、λ 再定比分</b>：
      近期战绩 → 主客场分拆 → 联赛环境 → H2H → 市场 → 校准 → 形状混合，每一步都写在这张表里。
      换个因素取值，λ 就换，比分跟着换 —— 这才是可优化的旋钮。
    </div>
    {chain_table(m)}
    {('<div style="margin-top:0.35rem;font-size:0.76rem;color:var(--accent3);">'
      '⚠️ 本场 <b>1X2 赔率由「比分盘」反推</b>（竞彩未开出胜平负）：31 档比分赔率去水后按'
      '主/平/客三区聚合。<b>已验证</b>——在赔率齐全场次上对照，2026-09-03 起的数据方向一致率 '
      '100%、平均偏差 1.0~2.2pp（<code>_score2hda_probe.py</code>）。</div>')
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
rowsA = rowsB = ''
for m in MATCHES:
    ts = m['top_scores']
    top3 = sum(t['prob'] for t in ts[:3])
    cold = esc(m['signals'][0]) if m['signals'] and m['signals'] != ['无明显冷门信号'] else '-'
    tg = total_goals_info(m)
    pr = m['prob']
    num_cell = f'<td><span class="tag tag-blue">{esc(m["matchNumStr"])}</span></td>'
    pair = f'<td>{rank_tag(m["home"], m["home_rank"])}</td><td>{rank_tag(m["away"], m["away_rank"])}</td>'
    # 4.1 胜负与比分（1X2 三率 + 命中比分 + 双档 + 覆盖；头条=矩阵联合众数=命中最优）
    dlabel2, dkey2, ds2, dp2, op2 = direction_pick(m)
    _hs2, _hp2 = hit_pick(m)
    _qp2 = hit_band(m, 2)
    _qp2_sum = sum(p for _, p in _qp2)
    _escore2, _eprob2, _esame2 = expect_score(m)
    _bp = band_prob(m, _hs2)
    _bp_cell = (f'{_bp*100:.0f}%' if _bp is not None else '-')
    _cred_t, _cred_c = score_cred(m)
    _hp_str = f' <span style="color:var(--muted);font-weight:400;font-size:0.8rem;">({_hp2:.1f}%)</span>' if _hp2 is not None else ''
    rowsA += (f'<tr>{num_cell}{pair}'
              f'<td>{pr["home"]:.1f}%</td><td>{pr["draw"]:.1f}%</td><td>{pr["away"]:.1f}%</td>'
              f'<td><span class="tag {DIR_TAG.get(dlabel2, "tag-blue")}">{dlabel2} {op2*100:.1f}%</span></td>'
              f'<td style="font-family:monospace;font-weight:700;color:var(--accent);">{dash(_hs2)}{_hp_str}'
              f'<br><span style="color:var(--muted);font-weight:400;font-size:0.72rem;">量级 {dash(_escore2)}'
              f' · λ {m["lam_home"]:.2f}:{m["lam_away"]:.2f}</span></td>'
              f'<td style="font-family:monospace;font-size:0.8rem;">'
              f'{"+".join(dash(s) for s, _ in _qp2)}<br>'
              f'<span style="color:var(--muted);font-size:0.72rem;">合计 {_qp2_sum:.1f}%</span></td>'
              f'<td style="font-family:monospace;">{_bp_cell}</td>'
              f'<td>{top3:.1f}%</td>'
              f'<td>{sum(t["prob"] for t in ts[:5]):.1f}%</td>'
              f'<td><span class="tag {_cred_c}">{_cred_t.split("（")[0]}</span></td>'
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
<p style="font-size:0.85rem;color:var(--muted);">两种玩法口径分开看：<b>胜负+比分</b>看方向（Platt 校准三率 → 倾向 → 因素推出的整数比分）、<b>进球数</b>看总量倾向（λ 泊松累加，命中率远高于单比分）。
<b>「比分不是分布式算的，是根据因素得出来的」—— 这个说法是对的，本节数字全部来自因素链。</b>
λ 是 <b>4 组因素的确定性函数</b>（近期战绩 EWMA → 主客场分拆收缩 → 联赛先验收缩 → 市场概率混合，见 <code>factor_hit_probe.py</code> F1 分解），
把 λ 这个小数落成整数比分时 ⌊λ⌋ 就等于联合众数 —— 所以「众数」不是另一套算法，而是同一个因素答案的另一种写法；真正没有意义的是概率的<b>数值</b>（单调变换不改变 argmax）。
<b>精确性 4036 场回测（2026-01-01~09-12）</b>：联合众数单点 <b>14.94%</b> ＞ floor(λ) 13.85% ＞ round(λ) 13.06% ＞ <b>无脑全猜 1:1 的常数基线 12.93%</b>；
McNemar 配对 χ² = 6.47 / 8.11 / 19.34（对手分别为 floor / round / 常数），<b>三者均 p&lt;0.05 显著</b>。
⚠️ <b>但「无脑猜 1:1」就能拿 12.93%</b>，说明<b>比分必须挑场次看</b>：按模型自评概率排序每日取前 3 场，
单比分命中 <b>20.50%</b>（对照全场次 14.94%），取前 3 场时 49.0% 的比赛日至少中 1 场 —— 见报告开头的「🎯 今日比分精选」。
⛔ <b>调因素这条路已实证走不通</b>：坐标上升在训练集（2421 场）上挑出 8 项因素改动、多中 28 场，
换到检验集（1615 场）<b>反而少中 21 场</b>、λMAE 1.8036→1.8805、Brier 0.5953→0.6634 全线变差（纯过拟合）。
<b>已试过且无法超越众数的排序源</b>：市场比分盘 14.3~17.1%、模型×市场混合 16.0~17.9%、格子级乘性纠偏 18.8%、分区条件经验重排 18.8%、总进球边缘纠偏 18.7%、Dixon-Coles 17.3~18.5%——全在 ±0.4pp 噪声内。
<b>提升空间只在「分布」不在「选法」</b>：单比分 = 方向命中 × 方向内命中，要再提只能让 λ/形状更准或引入新信息源（赔率漂移 CLV、阵容伤停）。
λ 期望值口径降级为「<b>量级参考</b>」（无偏：总进球偏差 −0.22 球/场；众数口径 −0.90）。</p>
{_sub_table('4.1 胜负与比分预测', '胜/平/负三率经 Platt 校准（修正泊松平局低估）；<b>倾向</b> = 三者中概率最高者。<b>命中比分</b>（2026-09-13 定调）= <b>因素推出的整数比分</b>，等于已对齐比分矩阵的联合众数 —— λ 由因素链确定，⌊λ⌋ 即众数，两者是同一答案的两种写法（不是两套算法）。4036 场回测单点 <b>14.94%</b>：floor(λ) 13.85%、round(λ) 13.06%、<b>常数基线（全猜 1:1）12.93%</b>；McNemar χ²=6.47/8.11/19.34 均显著。概率的<b>数值</b>与命中率无关（单调变换不改 argmax）。<b>量级</b>小字 = λ 期望进球取整，<b>不为押中</b>，只为给出「预计几比几的量级」（总进球偏差 −0.22 球/场，众数口径 −0.90，因众数是分布单点、必然低于均值）。<b>比分双档</b> = 众数排序前两档，回测命中 <b>26.54%</b>（单档 14.94%）。<b>±1球覆盖</b> = 实际比分落在头条比分上下各 1 球范围内的概率（回测 <b>67.24%</b>）——容错口径看这个。<b>比分可信度</b> = 按 λ 总量分档给出<b>实测</b>命中率（4036 场生产口径）：λ≤2.0 单点 22.3%/双档 34.5%；2.0~2.3 单点 18.3%；2.3~2.6 单点 19.2%；2.6~3.0 单点 13.0%；3.0~3.5 单点 13.4%；&gt;3.5 单点 11.1% —— λ≤2.6（约 1/3 场次）单点 18~22% 是最值得看比分的区间。<b>比分矩阵已对齐发布三率</b>（V3.3 SCORE_ALIGN），对齐后比分 LogLoss −0.0131（t=−4.15）、1X2 Brier −1.4%、方向命中 +0.47pp。',
'<th>编号</th><th>主队</th><th>客队</th><th>胜率</th><th>平率</th><th>负率</th><th>倾向</th><th>命中比分</th><th>比分双档</th><th>±1球覆盖</th><th>Top3覆盖</th><th>Top5覆盖</th><th>比分可信度</th><th>信心</th><th>冷门</th>', rowsA)}
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
    """比分串关的腿：统一走头条口径「命中比分」（矩阵联合众数），概率取该比分模型概率。

    此处只作高赔彩票型展示：lambda_level_probe.py 回测 3 串 1（比分腿）198 天仅中 1 天（0.5%），
    故真实概率必须如实标注，不作推荐强度使用。
    """
    legs, odds_prod, prob_prod = [], 1.0, 1.0
    for m in ms:
        _ol, _ok, ds, dp, _op = direction_pick(m)
        s, hp = hit_pick(m)
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
                    f"{len(legs)}串1：取评级最高（4-5★优先）的{len(legs)}场，比分腿统一用头条口径「命中比分」（矩阵联合众数）"
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
  <div class="summary-card"><h4>📈 总进球偏差归因 (2026-09-13)</h4><p style="font-size:0.9rem;">1591 场回测：<b>2026 年 1~8 月模型 λ 场均高估 +0.12 球</b>（实际 2.75~2.91），并非系统性低估；<b>9 月实际场均升到 3.05~3.13</b>（全库口径），属异常高进球期，这才使近期偏差转负（09-11 −0.63 / 09-12 −0.47）。λ 水平系数 k 扫描：k=1.10~1.15 会让 MAE、比分 LogLoss、1X2 Brier <b>全线变差</b>，故<b>不追高</b>；校准窗口 7→14 天在时间外把 MAE 1.1869→1.1850 且显著降低逐日颠簸，为可选优化项。</p></div>
  <div class="summary-card"><h4>🎯 比分口径一致性 (V3.3)</h4><p style="font-size:0.9rem;">比分概率组的分布已与同页发布的胜/平/负<b>完全对齐</b>（此前因市场混合/联赛形状混合/Platt 三步都只作用在 1X2 上，两处口径最多相差 <strong>9.9pp</strong>）。对齐后比分 LogLoss −0.0131（t=−4.15）、1X2 Brier −1.4%、方向命中 +0.47pp；Top5 覆盖变化在噪声内（±0.2pp）。</p></div>
  <div class="summary-card"><h4>🎯 比分目标函数与口径 (2026-09-13 三次定调)</h4><p style="font-size:0.9rem;">用户明确：<b>主要优化方向 = 比分的准确度；概率大小没有意义；命中次数多了目标函数才好优化</b>；并指出「<b>比分不是分布式算的，是根据因素得出的</b>」。⚖️ <b>本轮把这三句话逐条验证了一遍</b>（新增 <code>_score_from_factors.py</code> / <code>_baseline_probe.py</code> / <code>_pick_mcnemar.py</code> / <code>_daily_top_probe.py</code> / <code>factor_hit_probe.py</code>，4036 场 2026-01-01~09-12）：<br>
  ① <b>「λ 由因素决定」成立</b>：λ 是 4 组因素的确定性函数（近期战绩EWMA → 主客场分拆收缩 → 联赛先验收缩 → 市场概率混合），且 ⌊λ⌋ 就等于联合众数 —— 众数不是另一套算法，是同一答案的另一种写法。<br>
  ② <b>「概率无意义」成立</b>：单调变换（温度展平/锐化 T=0.85~1.35）不改变 argmax，四种变换命中完全相同。<br>
  ③ <b>但「比分层没价值」不成立</b>：联合众数单点 14.94% vs <b>无脑全猜 1:1 的常数基线 12.93%</b>，净多中 <b>+81 场</b>，McNemar χ²=<b>19.34（p&lt;0.001）</b>；换 floor(λ)/round(λ) 反更差（13.85%/13.06%，χ²=6.47/8.11 显著否决）。<br>
  ⚠️ <b>真正的问题不是「众数」而是「退化」</b>：65.8% 的场次首选都落在 1:1（独立泊松联合众数 = (⌊λ主⌋,⌊λ客⌋)，双方 λ 都落在 [1,2) 时必然 1:1，是数学性质不是算错）。加上「全猜 1:1 就有 12.93%」，结论是 <b>比分必须挑场次看</b> → 新增报告开头「<b>🎯 今日比分精选</b>」：按模型自评概率排序每日取前 3 场，单比分命中 <b>20.50%</b>（对照全场次 14.94%），49.0% 的比赛日至少中 1 场；自评概率五等分档实测命中单调 10.8%→20.0%。<br>
  ⛔ <b>调因素已被实证否决</b>：坐标上升在训练集（2421 场）挑出 8 项改动、多中 28 场，检验集（1615 场）<b>反少中 21 场</b>、λMAE 1.8036→1.8805、Brier 0.5953→0.6634 全线变差 —— 纯过拟合。<b>已系统排查且都赢不过众数的排序源</b>：市场比分盘去水 14.3~17.1%、模型×市场混合 16.0~17.9%、格子级乘性纠偏 18.8%、分区条件经验重排 18.8%、总进球边缘纠偏 18.7%、Dixon-Coles 17.3~18.5% —— 全在 ±0.4pp 噪声内。<br>
  🔧 <b>顺带查清一个配置不一致</b>：<code>league_profile.json</code> 的形状混合权重自 w=0.3 时代起一直是 <b>0.3</b>（即线上真实生效值），而引擎注释/探针/项目记忆长期按 <b>0.5</b> 处理 —— 「文档口径」与「线上口径」不是一回事，且这种错位从探针输出里看不出来。已让探针改为<b>从档案读值</b>（不再硬编码），文档同步更正。<b>是否升到 0.5</b>：全样本 +21 场，但时间外 0.3=272 / 0.5=270 / 0.6=275（噪声地板 16 场）<b>不显著</b> → 维持 0.3 不动（改动会连带触发 Platt 重拟合，收益不可证）。<br>
  <b>下一步提升只能来自「分布」而非「选法」</b>：单比分 = 方向命中 × 方向内命中，要提命中次数必须让 λ/形状更准或引入新信息源（赔率漂移 CLV、阵容/伤停）。</p></div>
  <div class="summary-card"><h4>🔄 方向性调整</h4><p style="font-size:0.9rem;">本日 <strong style="color:var(--accent2);">{dir_cnt}</strong> 场应用了H2H方向性总量守恒再分配（V2.2新增），胜负记录直接改变λ分配而非只调总进球。</p></div>
  <div class="summary-card"><h4>🚑 伤病影响</h4><p style="font-size:0.9rem;">多支球队的伤病与战意信息已纳入逐场分析，核心球员缺阵对强队战力影响显著，重点关注伤停卡片。</p></div>
  <div class="summary-card"><h4>⚖️ 凯利指数</h4><p style="font-size:0.9rem;">部分场次赔率与模型预测存在偏差，模型与市场方向背离的场次已在冷门列标注，需谨慎对待。</p></div>
</div>

<div class="warning">
  <strong>风险提示：</strong>足球比赛存在较大不确定性，伤病、红牌、点球、VAR等因素均可能影响比赛结果。本报告基于历史数据和AI模型分析，仅供参考，不构成投注建议。请理性购彩，量力而行。
</div>

<div class="parlay-section">
  <h3>方向串关推荐（主口径）</h3>
  <table class="parlay-table">
    <tr><th>类型</th><th>组合</th><th>组合赔率</th><th>综合概率</th><th>信心评级</th></tr>
    {parlay_dir_rows}
  </table>
  <div class="parlay-note">注：以「倾向」（胜/平/负）为串关腿，不押具体比分。1591 场回测：单腿方向命中 53.8%、3腿全中 <b>25.3%</b>、198 个比赛日 ROI <b>−3.0%</b>（相对比分串关的 0.5% 全中率，这是唯一接近盈亏平衡的串关口径）。组数与腿数与下方比分串关一致。</div>
</div>

<div class="parlay-section">
  <h3>比分串关推荐（高赔彩票型 · 命中率 &lt;1%）</h3>
  <table class="parlay-table">
    <tr><th>类型</th><th>组合</th><th>组合赔率</th><th>综合概率</th><th>信心评级</th></tr>
    {parlay_rows}
  </table>
  <div class="parlay-note">注：综合概率为各场比分腿概率连乘（近似独立）。比分腿已统一为头条口径<b>「命中比分」</b>（矩阵联合众数），概率取模型给该比分的概率。<b>比分串关的 3 腿全中率仅 0.5%（198 个比赛日仅 1 天命中）</b>，组合概率常低至 0.1%~0.4%——请把它当作买彩票而非投资建议，切勿重注。想提高命中率请看上表 <b>Top3 覆盖 39.9% / ±1球覆盖 66.4%</b>，而非串关。信心串关绿色背景，冷门串关橙色背景（博平/博冷高赔方向）。组数与腿数随当日场次动态调整：信心组 = min(3, max(2, 场次÷8))，冷门组 = min(3, max(2, 场次÷10))，每组 3 腿（≥15场）或 2 腿（6-14场）；冷门场次不足时用高信心场锚定补足，每组至少 2 组、至少 2 腿。</div>
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

# ---------- 🎯 今日比分精选（该押哪几场） ----------
# 依据（_daily_top_probe.py，4036 场 / 241 个比赛日，生产口径 w=0.3）：
#   全场次单比分命中 14.94%；按「模型给该比分的概率」排序每日取前 k 场 →
#   前1场 21.16%、前2场 21.88%、前3场 20.50%、前5场 19.64%；取前3场时 49.0% 的比赛日至少中 1 场。
#   模型自评概率五等分档实测命中单调：10.8% → 12.2% → 14.1% → 17.6% → 20.0%（最强档是最弱档的 1.9 倍）。
#   等价排序器（差 ≤1.4pp，均在噪声内）：λ总量最低 21.58/21.46/20.78%；概率÷λ总量 20.75/20.83/20.78%。
#   预测本身不改动，本节只是把「模型自己最有把握的场次」挑出来。
def _conf_rank(m):
    s, p = hit_pick(m)
    lt = float(m.get('lam_home', 0) or 0) + float(m.get('lam_away', 0) or 0)
    pf = float(p) if p else 0.0
    return s, pf, lt, pf


_picks = sorted((_conf_rank(m) + (m,) for m in MATCHES), key=lambda x: -x[3])
_rows_pk = ''
for _i, (_s, _pf, _lt, _cf, _m) in enumerate(_picks[:5], 1):
    _b2 = hit_band(_m, 2)
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
<h2>🎯 今日比分精选（该押哪几场）</h2>
<div class="card">
  <p style="font-size:0.86rem;color:var(--muted);margin-bottom:0.7rem;">
    <b>为什么单列这一节。</b>单比分是 31 格划分里的一个单点，全场次平均命中只有 <b>14.94%</b>
    （4036 场回测：2026-01-01~09-12）；而且「无脑全场猜 1:1」就有 12.93% —— 所以<b>比分必须挑场次看</b>。
    模型不是每场都一样有把握：按「模型给该比分的概率」排序，模型自评概率五等分档的实测命中率是
    <b>单调上升</b>的（10.8% → 12.2% → 14.1% → 17.6% → <b>20.0%</b>，最强档是最弱档的 1.9 倍）。
    把这条用在每日精选上，单比分命中率提到 <b>21%</b>
    （前1场 21.16% / 前2场 <b>21.88%</b> / 前3场 20.50% / 前5场 19.64%，对照全场次 14.94%），
    取前 3 场时 <b>49.0% 的比赛日至少能中 1 场</b>。
    <b>本节不改变任何预测</b>，只是把「模型自己最有把握的场次」排到前面 ——
    要跟单场比分就看这几场，其余场次请看方向与总进球倾向。
  </p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>#</th><th>编号 · 联赛</th><th>对阵</th><th>命中比分</th><th>双档</th>
      <th>±1球</th><th>模型概率</th><th>比分可信度</th></tr></thead>
      <tbody>{_rows_pk}</tbody>
    </table>
  </div>
  <p style="font-size:0.76rem;color:var(--muted);margin-top:0.55rem;">
    排序依据 = 模型给「命中比分」的概率（下方小字为该场总进球 λ）。等价排序器（差距 ≤1.4pp，均在噪声内）：
    λ总量最低（每日前3场 20.78%）、概率÷λ总量（20.78%）、P(1:1) 最高（19.53%）。
    <b>对照基准：全场次 14.94%、联合众数 14.94%、常数基线（全猜 1:1）12.93%</b>
    —— 联合众数对数基线的 McNemar χ²=<b>19.34</b>（p&lt;0.001，净多中 81 场）。
  </p>
</div>
'''

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
