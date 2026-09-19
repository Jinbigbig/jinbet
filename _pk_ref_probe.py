# -*- coding: utf-8 -*-
"""探针：比分精选若改为「自带模型」(纯 λ 泊松) 出头条/双档，与引擎比分矩阵口径相比如何。
数据：predictions/*/pred_snapshot.json（含 top_scores + lam_* 与实际赛果）。"""
import json, glob, os, math
import selection_algo as SA

LISTED = SA.LISTED_LABELS
MAXG = 8

def pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)

def own_grid(m):
    lh = float(m.get('lam_home', 0) or 0); la = float(m.get('lam_away', 0) or 0)
    return [[pois(h, lh) * pois(a, la) for a in range(MAXG + 1)] for h in range(MAXG + 1)]

def own_rank(m, lean=None, n=3):
    """自身泊松网格内，按概率降序的前 n 个列出比分（不受象限约束，全列出格）。"""
    d = own_grid(m)
    cells = sorted(((d[h][a], f'{h}:{a}') for h in range(MAXG + 1) for a in range(MAXG + 1)
                    if f'{h}:{a}' in LISTED), key=lambda x: -x[0])
    return [(s, round(p * 100, 1)) for p, s in cells[:n]]

def load_actuals():
    recs = {}
    try:
        rd = json.load(open('results_data.json', encoding='utf-8'))
        for k, v in rd.items():
            if isinstance(v, dict):
                recs[k] = v
    except Exception:
        pass
    for f in sorted(glob.glob('results_history/*.json')):
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
    return recs

def actual(recs, y, h, a):
    for key in (f'{y}_{h}_{a}', f'{y}_{a}_{h}'):
        r = recs.get(key)
        if r:
            s = r.get('score') or r.get('fullScore') or ''
            if isinstance(s, str) and ':' in s:
                return s
    return None

recs = load_actuals()
days = []
for sp in sorted(glob.glob('predictions/*/pred_snapshot.json')):
    date = os.path.basename(os.path.dirname(sp))
    if date >= '2026-09-17':
        continue
    snap = json.load(open(sp, encoding='utf-8'))
    rows = []
    for m in snap.get('matches') or []:
        a = actual(recs, date, m.get('home'), m.get('away'))
        if not a:
            continue
        nm = dict(m)
        nm.setdefault('prob', {'home': m.get('prob_home', 0), 'draw': m.get('prob_draw', 0),
                               'away': m.get('prob_away', 0)})
        nm.setdefault('cold', False); nm.setdefault('data_n', {})
        rows.append((nm, a))
    if len(rows) >= SA.TIER_PK:
        days.append((date, rows))

t = SA.load_tuning()
print(f'可用天数 {len(days)}')
tot = {'eng_hit': 0, 'own_hit': 0, 'eng_or_own_diff': 0, 'n': 0,
       'eng_band': 0, 'own_band': 0}
sel_eng = {'hit': 0, 'band': 0, 'n': 0}
sel_own = {'hit': 0, 'band': 0, 'n': 0}
diff_list = []
for date, rows in days:
    ms = [m for m, _ in rows]
    for m, a in rows:
        e, _ = SA.hit_pick(m)
        o = own_rank(m, n=3)
        tot['n'] += 1
        if a == e: tot['eng_hit'] += 1
        if a == o[0][0]: tot['own_hit'] += 1
        if a in [x[0] for x in SA.band_scores(m, 2)]: tot['eng_band'] += 1
        if a in [x[0] for x in o[1:3]]: tot['own_band'] += 1
        if e != o[0][0]:
            tot['eng_or_own_diff'] += 1
            diff_list.append((date, m.get('home'), m.get('away'), e, o[0][0], a))
    tiers, flat, _ = SA.rank_pk(ms, t, SA.TIER_PK)
    for xt in (tiers[0] if tiers else []):
        m = xt[1]
        a = dict(rows)[m] if False else next(ac for mm, ac in rows if mm is m)
        e, _ = SA.hit_pick(m); o = own_rank(m, n=3)
        sel_eng['n'] += 1; sel_own['n'] += 1
        if a == e: sel_eng['hit'] += 1
        if a in [x[0] for x in SA.band_scores(m, 2)]: sel_eng['band'] += 1
        if a == o[0][0]: sel_own['hit'] += 1
        if a in [x[0] for x in o[1:3]]: sel_own['band'] += 1

n = tot['n']
print(f'\n=== 全部已出赛果场次 n={n} ===')
print(f'  引擎矩阵头条(top_scores[0]) 命中 : {tot["eng_hit"]}/{n} = {tot["eng_hit"]/n*100:.1f}%')
print(f'  自带泊松 argmax 命中            : {tot["own_hit"]}/{n} = {tot["own_hit"]/n*100:.1f}%')
print(f'  引擎双档命中                    : {tot["eng_band"]}/{n} = {tot["eng_band"]/n*100:.1f}%')
print(f'  自带双档命中                    : {tot["own_band"]}/{n} = {tot["own_band"]/n*100:.1f}%')
print(f'  两种口径头条不同的场次           : {tot["eng_or_own_diff"]}/{n} = {tot["eng_or_own_diff"]/n*100:.1f}%')
print(f'\n=== 仅比分精选第一档（生产选取相同）n={sel_eng["n"]} ===')
print(f'  引擎口径 头条+双档: {sel_eng["hit"]}/{sel_eng["n"]}, 双档 {sel_eng["band"]}/{sel_eng["n"]}')
print(f'  自带口径 头条+双档: {sel_own["hit"]}/{sel_own["n"]}, 双档 {sel_own["band"]}/{sel_own["n"]}')
print('\n差异样例（前 8）:')
for x in diff_list[:8]:
    print('  ', x)
