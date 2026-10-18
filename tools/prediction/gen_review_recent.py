"""生成「近期复盘」汇总页：把最近 N 天已发布预测逐场对照实际赛果。

数据来源：
  - 预测：predictions/<date>/pred_snapshot.json
  - 赛果：results_data.json（键 = 日期_主_客，主客方向已由 update_odds_net 对齐）

口径（与 gen_review.py / daily_diag.py 保持一致）：
  - 方向 = max(prob_home, prob_draw, prob_away) 对应赛果
  - 单点 = headline（快照内已落盘的「命中比分」）
  - 双档 = top_scores 第 2、第 3 比分
  - ±1 球 = 主客两侧各自误差 ≤1 球
  - λ 偏差 = lam_total − 实际总进球

用法：
  python gen_review_recent.py                # 最近 14 天，输出到 predictions/<今天>/review_recent.html
  python gen_review_recent.py --days 30
  python gen_review_recent.py --out predictions/2026-10-18/review_recent.html
"""
import argparse
import datetime as dt
import glob
import html
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))

DIR_CN = {'home': '主胜', 'draw': '平局', 'away': '客胜'}
DIR_MARK = {'home': '胜', 'draw': '平', 'away': '负'}


def norm(s):
    return str(s or '').replace(' ', '').strip()


def load_results():
    data = json.load(open(os.path.join(ROOT, 'results_data.json'), encoding='utf-8'))
    idx, rev = {}, {}
    for k, v in data.items():
        day = k.split('_', 1)[0]
        idx[(day, norm(v.get('home')), norm(v.get('away')))] = v
        rev[(day, norm(v.get('away')), norm(v.get('home')))] = v
    return idx, rev


def parse_score(s):
    try:
        h, a = str(s).replace('-', ':').split(':')
        return int(h), int(a)
    except Exception:
        return None


def collect(days):
    idx, rev = load_results()
    rows = []
    for day in days:
        p = os.path.join(ROOT, 'predictions', day, 'pred_snapshot.json')
        if not os.path.exists(p):
            continue
        snap = json.load(open(p, encoding='utf-8'))
        ms = snap['matches'] if isinstance(snap.get('matches'), list) else list(snap.get('matches', {}).values())
        for m in ms:
            h, a = norm(m.get('home')), norm(m.get('away'))
            v = idx.get((day, h, a))
            flipped = False
            if not v:
                v = rev.get((day, h, a))
                flipped = bool(v)
            if not v:
                continue
            sc = parse_score(v.get('score') or v.get('fullScore'))
            if not sc:
                continue
            gh, ga = sc
            if flipped:
                gh, ga = ga, gh
            ph, pd, pa = (m.get('prob_home') or 0), (m.get('prob_draw') or 0), (m.get('prob_away') or 0)
            pick = 'home' if ph >= max(pd, pa) else ('draw' if pd >= pa else 'away')
            act = 'home' if gh > ga else ('away' if gh < ga else 'draw')
            head = ((m.get('headline') or {}).get('score') or m.get('top_score') or '').replace('-', ':')
            hs, as_ = parse_score(head) or (None, None)
            tops = [x.get('score') for x in (m.get('top_scores') or []) if isinstance(x, dict)]
            band = [s.replace('-', ':') for s in tops[1:3]]
            rows.append({
                'day': day,
                'no': m.get('id') or m.get('matchNumStr') or '',
                'league': m.get('league') or '',
                'home': m.get('home') or '',
                'away': m.get('away') or '',
                'pick': pick,
                'pick_p': max(ph, pd, pa),
                'head': head,
                'band': band,
                'actual': '%d:%d' % (gh, ga),
                'dir_ok': pick == act,
                'score_ok': head == '%d:%d' % (gh, ga),
                'band_ok': '%d:%d' % (gh, ga) in band,
                'near_ok': bool(hs is not None and abs(hs - gh) <= 1 and abs(as_ - ga) <= 1),
                'stars': int(m.get('stars') or 0),
                'lam': float(m.get('lam_total') or 0),
                'act_total': gh + ga,
            })
    return rows


def pct(a, b):
    return 0.0 if not b else a / b * 100


def esc(s):
    return html.escape(str(s), quote=True)


def build(rows, days, title_range):
    byday = defaultdict(list)
    for r in rows:
        byday[r['day']].append(r)
    days_has = sorted(byday)
    n = len(rows)
    kpi = {
        'dir': sum(r['dir_ok'] for r in rows),
        'score': sum(r['score_ok'] for r in rows),
        'band': sum(r['band_ok'] for r in rows),
        'near': sum(r['near_ok'] for r in rows),
    }
    bias = [r['lam'] - r['act_total'] for r in rows if r['lam']]
    mae = sum(abs(b) for b in bias) / len(bias) if bias else 0
    mean_bias = sum(bias) / len(bias) if bias else 0

    hits = sorted([r for r in rows if r['score_ok']], key=lambda r: (-r['stars'], -r['pick_p']))[:8]
    burns = sorted([r for r in rows if not r['dir_ok']], key=lambda r: (-r['stars'], -r['pick_p']))[:8]
    near_miss = sorted([r for r in rows if not r['score_ok'] and r['near_ok']],
                       key=lambda r: (-r['stars'], -r['pick_p']))[:6]

    lg = defaultdict(list)
    for r in rows:
        lg[r['league']].append(r)
    lg_rows = sorted([(k, v) for k, v in lg.items() if len(v) >= 8], key=lambda x: -len(x[1]))

    st = defaultdict(list)
    for r in rows:
        st[r['stars']].append(r)

    # 每日方向条形（宽度按命中率）
    bars = []
    for d in days_has:
        rs = byday[d]
        dh = pct(sum(x['dir_ok'] for x in rs), len(rs))
        sh = pct(sum(x['score_ok'] for x in rs), len(rs))
        bars.append((d, len(rs), dh, sh))

    css = """
    :root{--bg:#f6f8fb;--card:#fff;--ink:#12202f;--muted:#6b7c90;--line:#e3e9f2;--blue:#2f6fe0;--green:#128a4b;--red:#d33f3f;--amber:#c98a10;--soft:#eef3fb;}
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}
    .wrap{max-width:1120px;margin:0 auto;padding:28px 18px 60px}
    h1{font-size:1.6rem;margin:0 0 6px}
    .sub{color:var(--muted);font-size:.88rem;margin-bottom:22px}
    .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:26px}
    .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
    .kpi .lab{font-size:.78rem;color:var(--muted)}
    .kpi .val{font-size:1.5rem;font-weight:700;letter-spacing:.3px}
    .kpi .note{font-size:.74rem;color:var(--muted)}
    .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:22px}
    h2{font-size:1.05rem;margin:0 0 12px;display:flex;align-items:center;gap:8px}
    h2 span.dot{width:8px;height:8px;border-radius:50%;background:var(--blue);display:inline-block}
    table{width:100%;border-collapse:collapse;font-size:.85rem}
    th,td{padding:8px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
    th{color:var(--muted);font-weight:600;font-size:.76rem;text-transform:uppercase;letter-spacing:.4px;background:#fbfcfe}
    tbody tr:hover{background:#fafcff}
    .num{font-variant-numeric:tabular-nums}
    .ok{color:var(--green);font-weight:600}
    .no{color:var(--red);font-weight:600}
    .warn{color:var(--amber);font-weight:600}
    .tag{display:inline-block;padding:1px 7px;border-radius:20px;font-size:.72rem;border:1px solid transparent}
    .t-green{background:#e8f7ee;color:#128a4b;border-color:#c7ebd5}
    .t-red{background:#fdecec;color:#c53434;border-color:#f6d2d2}
    .t-amber{background:#fdf5e4;color:#a8760c;border-color:#f2e3bf}
    .t-blue{background:#eaf1fd;color:#2f6fe0;border-color:#d3e2fb}
    .t-grey{background:#f1f4f8;color:#5e7186;border-color:#e2e8f1}
    .bar{height:8px;background:var(--soft);border-radius:20px;overflow:hidden;min-width:70px}
    .bar i{display:block;height:100%;background:linear-gradient(90deg,#4b8bf0,#2f6fe0)}
    details{border:1px solid var(--line);border-radius:10px;padding:0 14px;margin-bottom:10px;background:#fff}
    details[open]{box-shadow:0 2px 10px rgba(20,40,80,.05)}
    summary{cursor:pointer;padding:12px 0;font-weight:600;font-size:.9rem;list-style:none;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    summary::-webkit-details-marker{display:none}
    summary .sm{font-weight:400;color:var(--muted);font-size:.8rem}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
    @media(max-width:820px){.grid2{grid-template-columns:1fr}}
    .list{font-size:.85rem;margin:0;padding-left:18px}
    .list li{margin:6px 0}
    .foot{color:var(--muted);font-size:.78rem;margin-top:26px;text-align:center}
    .legend{font-size:.78rem;color:var(--muted);margin-top:10px}
    """

    def bar_html(v):
        w = max(2, min(100, v))
        return '<div class="bar"><i style="width:%.0f%%"></i></div>' % w

    parts = []
    parts.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append('<title>近期复盘 · %s</title><style>%s</style></head><body><div class="wrap">' % (esc(title_range), css))
    parts.append('<h1>近期预测复盘</h1>')
    parts.append('<div class="sub">%s ｜ 覆盖 %d 天 %d 场已完赛场次 ｜ 判定口径：方向 / 单点(头条比分) / 双档(第2+第3) / ±1球</div>'
                 % (esc(title_range), len(days_has), n))

    parts.append('<div class="kpis">')
    for lab, val, note, cls in [
        ('方向', '%.1f%%' % pct(kpi['dir'], n), '%d / %d' % (kpi['dir'], n), ''),
        ('单点(头条)', '%.1f%%' % pct(kpi['score'], n), '%d / %d' % (kpi['score'], n), ''),
        ('双档', '%.1f%%' % pct(kpi['band'], n), '%d / %d' % (kpi['band'], n), ''),
        ('±1 球邻域', '%.1f%%' % pct(kpi['near'], n), '%d / %d' % (kpi['near'], n), ''),
        ('λ 总进球偏差', '%+.2f' % mean_bias, 'MAE %.2f 球/场' % mae, ''),
    ]:
        parts.append('<div class="kpi"><div class="lab">%s</div><div class="val %s">%s</div><div class="note">%s</div></div>' % (lab, cls, val, note))
    parts.append('</div>')

    # 逐日
    parts.append('<div class="card"><h2><span class="dot"></span>逐日战绩</h2><table><thead><tr>'
                 '<th>日期</th><th class="num">场次</th><th>方向</th><th class="num">方向%</th>'
                 '<th>单点</th><th>双档</th><th>±1</th><th>当日最佳</th><th>当日最痛</th></tr></thead><tbody>')
    for d in days_has:
        rs = byday[d]
        dh = sum(x['dir_ok'] for x in rs)
        sh = sum(x['score_ok'] for x in rs)
        bh = sum(x['band_ok'] for x in rs)
        nh = sum(x['near_ok'] for x in rs)
        ok_rows = [x for x in rs if x['dir_ok']]
        best_pool = ok_rows or rs
        best = sorted(best_pool, key=lambda x: (x['score_ok'], x['band_ok'], x['stars'], x['pick_p']), reverse=True)[0]
        worst = sorted([x for x in rs if not x['dir_ok']], key=lambda x: (-x['stars'], -x['pick_p']))
        best_txt = '%s %s %s' % (best['no'], esc(best['home'] + ' vs ' + best['away']), esc(best['actual']))
        if worst:
            w = worst[0]
            worst_txt = '%s %s %s（预 %s）' % (w['no'], esc(w['home'] + ' vs ' + w['away']), esc(w['actual']), esc(w['head']))
        else:
            worst_txt = '—'
        parts.append('<tr><td><b>%s</b> %s</td><td class="num">%d</td><td>%s %d/%d</td><td class="num">%.0f%%</td>'
                     '<td>%d</td><td>%d</td><td>%d</td><td>%s</td><td>%s</td></tr>'
                     % (d[5:], ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][dt.date(*map(int, d.split('-'))).weekday()],
                        len(rs), bar_html(pct(dh, len(rs))), dh, len(rs), pct(dh, len(rs)), sh, bh, nh, best_txt, worst_txt))
    parts.append('</tbody></table><div class="legend">方向% 条越满越好；单点/双档/±1 为场次数。</div></div>')

    # 亮点/失手
    parts.append('<div class="grid2">')
    parts.append('<div class="card"><h2><span class="dot" style="background:#128a4b"></span>押中的比分</h2><ul class="list">')
    if hits:
        for r in hits:
            parts.append('<li>%s <b>%s vs %s</b> → <b>%s</b> <span class="tag t-green">%d★</span> <span class="tag t-blue">%s</span></li>'
                         % (esc(r['no']), esc(r['home']), esc(r['away']), esc(r['actual']), r['stars'], esc(r['league'])))
    else:
        parts.append('<li>本窗口无单点命中</li>')
    parts.append('</ul></div>')
    parts.append('<div class="card"><h2><span class="dot" style="background:#d33f3f"></span>方向翻车（按星级）</h2><ul class="list">')
    if burns:
        for r in burns:
            parts.append('<li>%s <b>%s vs %s</b> 预 <b>%s</b> → 实 <b>%s</b> <span class="tag t-amber">%d★</span></li>'
                         % (esc(r['no']), esc(r['home']), esc(r['away']), esc(r['head']), esc(r['actual']), r['stars']))
    else:
        parts.append('<li>无</li>')
    parts.append('</ul></div></div>')

    if near_miss:
        parts.append('<div class="card"><h2><span class="dot" style="background:#c98a10"></span>差一球（±1 命中但比分未中）</h2><ul class="list">')
        for r in near_miss:
            parts.append('<li>%s %s vs %s 预 <b>%s</b> → 实 <b>%s</b> <span class="tag t-blue">%d★</span></li>'
                         % (esc(r['no']), esc(r['home']), esc(r['away']), esc(r['head']), esc(r['actual']), r['stars']))
        parts.append('</ul></div>')

    # 分组
    parts.append('<div class="grid2">')
    parts.append('<div class="card"><h2><span class="dot"></span>分联赛（≥8 场）</h2><table><thead><tr><th>联赛</th><th class="num">n</th><th class="num">方向</th><th class="num">单点</th><th class="num">±1</th></tr></thead><tbody>')
    for k, v in lg_rows:
        parts.append('<tr><td>%s</td><td class="num">%d</td><td class="num">%.0f%%</td><td class="num">%.0f%%</td><td class="num">%.0f%%</td></tr>'
                     % (esc(k), len(v), pct(sum(x['dir_ok'] for x in v), len(v)),
                        pct(sum(x['score_ok'] for x in v), len(v)), pct(sum(x['near_ok'] for x in v), len(v))))
    parts.append('</tbody></table></div>')
    parts.append('<div class="card"><h2><span class="dot"></span>分星级（信心标定）</h2><table><thead><tr><th>星级</th><th class="num">n</th><th class="num">方向</th><th class="num">单点</th></tr></thead><tbody>')
    for k in sorted(st):
        v = st[k]
        parts.append('<tr><td>%d★</td><td class="num">%d</td><td class="num">%.0f%%</td><td class="num">%.0f%%</td></tr>'
                     % (k, len(v), pct(sum(x['dir_ok'] for x in v), len(v)), pct(sum(x['score_ok'] for x in v), len(v))))
    parts.append('</tbody></table></div></div>')

    # 逐场明细
    parts.append('<div class="card"><h2><span class="dot"></span>逐场明细</h2>')
    for d in sorted(days_has, reverse=True):
        rs = byday[d]
        dh = sum(x['dir_ok'] for x in rs)
        sh = sum(x['score_ok'] for x in rs)
        parts.append('<details><summary>%s <span class="sm">%d 场 ｜ 方向 %d ｜ 单点 %d</span></summary>'
                     '<table><thead><tr><th>编号</th><th>联赛</th><th>对阵</th><th>预测方向</th><th>预测比分</th>'
                     '<th>双档</th><th>实际</th><th>判定</th></tr></thead><tbody>'
                     % (d, len(rs), dh, sh))
        for r in sorted(rs, key=lambda x: x['no']):
            judge = []
            judge.append('<span class="tag t-green">方向✓</span>' if r['dir_ok'] else '<span class="tag t-red">方向✗</span>')
            if r['score_ok']:
                judge.append('<span class="tag t-green">单点✓</span>')
            elif r['band_ok']:
                judge.append('<span class="tag t-blue">双档✓</span>')
            elif r['near_ok']:
                judge.append('<span class="tag t-amber">±1</span>')
            parts.append('<tr><td>%s</td><td>%s</td><td>%s vs %s</td><td>%s <span class="tag t-grey">%d★</span></td>'
                         '<td><b>%s</b></td><td>%s</td><td><b>%s</b></td><td>%s</td></tr>'
                         % (esc(r['no']), esc(r['league']), esc(r['home']), esc(r['away']),
                            DIR_CN[r['pick']], r['stars'], esc(r['head']),
                            ' / '.join(esc(b) for b in r['band']) or '—', esc(r['actual']), ''.join(judge)))
        parts.append('</tbody></table></details>')
    parts.append('</div>')

    parts.append('<div class="foot">本页由预测快照与实际赛果自动对照生成，仅供数据分析参考，不构成投注建议。</div>')
    parts.append('</div></body></html>')
    return ''.join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=14)
    ap.add_argument('--end', default=None, help='窗口结束日 YYYY-MM-DD，默认今天')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    end = dt.date.fromisoformat(a.end) if a.end else dt.date.today()
    start = end - dt.timedelta(days=a.days - 1)
    all_days = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(ROOT, 'predictions', '*', 'pred_snapshot.json')))
    days = [d for d in all_days if start.isoformat() <= d <= end.isoformat()]

    rows = collect(days)
    if not rows:
        print('窗口内无已完赛场次')
        return
    used = sorted({r['day'] for r in rows})
    title = '%s → %s' % (used[0], used[-1])
    out = a.out or os.path.join(ROOT, 'predictions', end.isoformat(), 'review_recent.html')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'w', encoding='utf-8').write(build(rows, used, title))

    n = len(rows)
    print('复盘窗口 %s ｜ %d 天 %d 场' % (title, len(used), n))
    print('  方向 %.1f%% (%d)  单点 %.1f%% (%d)  双档 %.1f%% (%d)  ±1 %.1f%% (%d)'
          % (pct(sum(r['dir_ok'] for r in rows), n), sum(r['dir_ok'] for r in rows),
             pct(sum(r['score_ok'] for r in rows), n), sum(r['score_ok'] for r in rows),
             pct(sum(r['band_ok'] for r in rows), n), sum(r['band_ok'] for r in rows),
             pct(sum(r['near_ok'] for r in rows), n), sum(r['near_ok'] for r in rows)))
    b = [r['lam'] - r['act_total'] for r in rows if r['lam']]
    print('  λ 偏差 %+.2f  MAE %.2f' % (sum(b) / len(b), sum(abs(x) for x in b) / len(b)))
    print('输出 → %s' % out)


if __name__ == '__main__':
    main()
