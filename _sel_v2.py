# -*- coding: utf-8 -*-
"""对比大胆档两种落地方式：
  V1 硬门槛：λ < 门槛 的场次直接出局（档内可能不足 4 场）
  V2 软偏好：λ ≥ 门槛 的优先，不足 TIER_BD 时用剩余场次补满（档位不缩水）
并输出今日实际生效情况。
"""
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


def pick(noncold, t, mode, thr):
    """返回选中的 (m, a) 列表。"""
    if mode == 'V1':
        ranked = sorted([r for r in noncold if SA.lam_total(r[0]) >= thr],
                        key=lambda r: (-SA.bold_quality(r[0], t), -SA.lam_total(r[0])))
        return ranked[:SA.TIER_BD]
    hi = sorted([r for r in noncold if SA.lam_total(r[0]) >= thr],
                key=lambda r: (-SA.bold_quality(r[0], t), -SA.lam_total(r[0])))
    if len(hi) >= SA.TIER_BD:
        return hi[:SA.TIER_BD]
    rest = sorted([r for r in noncold if SA.lam_total(r[0]) < thr],
                  key=lambda r: (-SA.bold_quality(r[0], t), -SA.lam_total(r[0])))
    return hi + rest[:SA.TIER_BD - len(hi)]


print(f'历史天数 {len(days)}\n')
print(f"{'方式':<6}{'门槛':>6}{'目标':>8}{'命中率':>8}{'命中/腿':>9}{'命中日':>7}   逐日(命中/腿)")
for mode in ('V1', 'V2'):
    for thr in (0.0, 2.4, 2.6, 2.8, 3.0, 3.2):
        t = dict(SA.DEFAULT_TUNING)
        rate = cov = tot = hit = 0
        logs = []
        for date, rows in days:
            noncold = [(m, a) for m, a in rows if not SA.is_cold(m)]
            sel = pick(noncold, t, mode, thr)
            s = sum(1 for m, a in sel if SA.bd_result(m, a) in ('scale', 'extreme'))
            rate += s / max(1, len(sel))
            cov += 1 if s >= 1 else 0
            tot += len(sel)
            hit += s
            logs.append(f'{date[-5:]}:{s}/{len(sel)}')
        n = len(days)
        obj = 0.6 * (rate / n) * 100 + 0.4 * (cov / n) * 100
        mark = ''
        if thr == 0.0 and mode == 'V1':
            mark = '  <<< 当前生产'
        print(f'{mode:<6}{thr:>6.1f}{obj:>8.2f}{hit/max(1,tot)*100:>7.1f}%{hit:>6}/{tot:<3}{cov:>5}/{n:<2}{mark}')
    print()

# ---- 今日实际 ----
print('=== 今日（2026-09-17）各门槛下的大胆档候选 ===')
snap = json.load(open(os.path.join('predictions', today, 'pred_snapshot.json'), encoding='utf-8'))
ms = snap.get('matches') or []
noncold = [m for m in ms if not SA.is_cold(m)]
print(f'共 {len(ms)} 场，非冷启动 {len(noncold)} 场')
for m in sorted(noncold, key=lambda x: -SA.lam_total(x)):
    e, ep, is_mode = SA.expect_score(m)
    print(f"  {m.get('matchNumStr')} {m.get('home')} vs {m.get('away')}  λ总={SA.lam_total(m):.2f}  "
          f"量级={e}({ep}) {'==头条' if is_mode else ''}")
print()
for thr in (0.0, 2.6, 2.8, 3.0):
    for mode in ('V1', 'V2'):
        sel = pick([(m, None) for m in noncold], dict(SA.DEFAULT_TUNING), mode, thr)
        print(f'  门槛{thr:>4.1f} {mode} → {len(sel)} 场: ' +
              ', '.join(x[0].get('matchNumStr', '') for x in sel))
    print()
