# -*- coding: utf-8 -*-
"""扫描 bd_lambda_min（大胆档 λ 总量下限）与 pk λ 分界，看改善是否稳定（防过拟合）。"""
import json, os, glob, datetime
import selection_algo as SA

today = datetime.datetime.now().strftime('%Y-%m-%d')
recs = {}
for f in sorted(glob.glob(os.path.join('.', 'results_history', '*.json'))):
    if os.path.basename(f) == 'index.json':
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
    for k, v in (rd.items() if isinstance(rd, dict) else []):
        if isinstance(v, dict):
            recs[k] = v
except Exception:
    pass


def actual(y, h, a):
    for key in (f'{y}_{h}_{a}', f'{y}_{a}_{h}'):
        r = recs.get(key)
        if r:
            s = r.get('score') or r.get('fullScore') or ''
            if isinstance(s, str) and ':' in s:
                return s
    return None


days = []
for sp in sorted(glob.glob(os.path.join('.', 'predictions', '*', 'pred_snapshot.json'))):
    date = os.path.basename(os.path.dirname(sp))
    if date >= today:
        continue
    try:
        snap = json.load(open(sp, encoding='utf-8'))
    except Exception:
        continue
    rows = []
    for m in (snap.get('matches') or []):
        a = actual(date, m.get('home'), m.get('away'))
        if not a:
            continue
        nm = dict(m)
        nm.setdefault('prob', {'home': m.get('prob_home', 0), 'draw': m.get('prob_draw', 0),
                               'away': m.get('prob_away', 0)})
        nm.setdefault('cold', False)
        nm.setdefault('data_n', {})
        rows.append((nm, a))
    if len(rows) >= SA.TIER_PK:
        days.append((date, rows))

print(f'可用天数 {len(days)}（{days[0][0]} ~ {days[-1][0]}）\n')

print('=== 大胆档 bd_lambda_min 扫描（生产口径：排冷启动，取第一档 4 场）===')
print(f"{'λ下限':>6}{'目标':>8}{'命中率':>8}{'命中/腿':>9}{'命中日':>7}   逐日命中")
for lm in (0.0, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.2):
    t = dict(SA.DEFAULT_TUNING, bd_lambda_min=lm)
    rate = cov = tot = hit = 0
    logs = []
    for date, rows in days:
        noncold = [(m, a) for m, a in rows if not SA.is_cold(m)]
        ranked = sorted(noncold, key=lambda r: (-SA.bold_quality(r[0], t), -SA.lam_total(r[0])))
        sel = ranked[:SA.TIER_BD]
        s = sum(1 for m, a in sel if SA.bd_result(m, a) in ('scale', 'extreme'))
        rate += s / max(1, len(sel))
        cov += 1 if s >= 1 else 0
        tot += len(sel)
        hit += s
        logs.append(f'{date[-5:]}:{s}')
    n = len(days)
    obj = 0.6 * (rate / n) * 100 + 0.4 * (cov / n) * 100
    print(f'{lm:>6.1f}{obj:>8.2f}{hit/max(1,tot)*100:>7.1f}%{hit:>6}/{tot:<3}{cov:>5}/{n:<2}   {" ".join(logs)}')

print()
print('=== 比分精选 pk_lambda_caps 第三档 + 退化降权扫描（生产口径，第一档 6 场）===')
print(f"{'cap3':>6}{'degen':>7}{'目标':>8}{'命中率':>8}{'命中/腿':>9}   逐日命中")
for cap in (3.0, 3.2, 3.4, 3.6, 3.8, 4.2):
    for dg in (1.0, 0.9, 0.85, 0.8):
        t = dict(SA.DEFAULT_TUNING, pk_lambda_caps=[2.6, 3.0, cap], pk_degen_down=dg)
        rate = cov = tot = hit = 0
        logs = []
        for date, rows in days:
            noncold = [(m, a) for m, a in rows if not SA.is_cold(m)]
            ranked = sorted(noncold, key=lambda r: -SA.pk_quality(r[0], t))
            sel = ranked[:SA.TIER_PK]
            s = sum(1 for m, a in sel if SA.pk_result(m, a) in ('hit', 'band'))
            rate += s / max(1, len(sel))
            cov += 1 if s >= 1 else 0
            tot += len(sel)
            hit += s
            logs.append(f'{date[-5:]}:{s}')
        n = len(days)
        obj = 0.6 * (rate / n) * 100 + 0.4 * (cov / n) * 100
        flag = '  <<< 默认' if (cap == 3.4 and dg == 0.85) else ''
        if dg in (1.0, 0.85):
            print(f'{cap:>6.1f}{dg:>7.2f}{obj:>8.2f}{hit/max(1,tot)*100:>7.1f}%{hit:>6}/{tot:<3}{flag}')
