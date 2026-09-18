# -*- coding: utf-8 -*-
"""大胆档「独立建模 + 互斥分池」回放对照（离线探针，不入库）。

对照三组：
  A 旧口径   ：引擎象限众数/λ取整口径（expect_score+extreme_pick），全池、不互斥
  B 新模型   ：自带泊松模型（bd_ref），可开关互斥
逐档网格：bd_total_shift / bd_min_total / bd_gap / bd_exclusive
"""
import json, os, glob
import selection_algo as SA

TODAY = '2026-09-17'
TIER_PK, TIER_BD = SA.TIER_PK, SA.TIER_BD


def _cache():
    recs = {}
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
    rd = json.load(open('results_data.json', encoding='utf-8'))
    for k, v in rd.items():
        if isinstance(v, dict):
            recs[k] = v
    return recs


RECS = _cache()


def actual(y, h, a):
    for key in (f'{y}_{h}_{a}', f'{y}_{a}_{h}'):
        r = RECS.get(key)
        if r:
            s = r.get('score') or r.get('fullScore') or ''
            if isinstance(s, str) and ':' in s:
                return s
    return None


def days():
    out = []
    for sp in sorted(glob.glob('predictions/*/pred_snapshot.json')):
        d = os.path.basename(os.path.dirname(sp))
        if d >= TODAY:
            continue
        snap = json.load(open(sp, encoding='utf-8'))
        rows = []
        for m in snap.get('matches') or []:
            a = actual(d, m.get('home'), m.get('away'))
            if not a:
                continue
            nm = dict(m)
            nm.setdefault('prob', {'home': m.get('prob_home', 0),
                                   'draw': m.get('prob_draw', 0),
                                   'away': m.get('prob_away', 0)})
            nm.setdefault('cold', False)
            nm.setdefault('data_n', {})
            rows.append((nm, a))
        if len(rows) >= TIER_PK:
            out.append((d, rows))
    return out


def _first(tiers):
    return [x[1] for x in (tiers[0] if tiers else [])]


# ---------- A 旧口径 ----------
def old_day(rows):
    amap = {id(m): a for m, a in rows}
    ms = [m for m, _ in rows]
    keyed = []
    for m in ms:
        if SA.is_cold(m):
            continue
        _, ep, _ = SA.expect_score(m)
        _, xp = SA.extreme_pick(m)
        keyed.append((max(xp or 0.0, ep or 0.0), SA.lam_total(m), m))
    keyed.sort(key=lambda x: (-x[0], -x[1]))
    sel = [x[2] for x in keyed[:TIER_BD]]
    hit = 0
    for m in sel:
        e, _, _ = SA.expect_score(m)
        x, _ = SA.extreme_pick(m)
        a = amap[id(m)]
        if a == e or (x and a == x):
            hit += 1
    return hit, len(sel)


# ---------- B 新模型 ----------
def new_day(rows, tuning):
    amap = {id(m): a for m, a in rows}
    _, _, bd_t, _, _ = SA.split_boards([m for m, _ in rows], tuning)
    sel = _first(bd_t)
    hit = sum(1 for m in sel if SA.bd_result(m, amap[id(m)], tuning) in ('scale', 'extreme'))
    return hit, len(sel)


def obj(res):
    n = len(res)
    rate = sum(h / max(1, t) for h, t in res) / n
    cov = sum(1 for h, t in res if h >= 1) / n
    return 0.6 * rate * 100 + 0.4 * cov * 100, sum(h for h, _ in res), sum(t for _, t in res), sum(1 for h, _ in res if h >= 1)


D = days()
print(f'可用天数 {len(D)}\n')

resA = [old_day(r) for _, r in D]
oa, ha, ta, ca = obj(resA)
print(f'A 旧口径（引擎象限/λ取整，全池不互斥）: 目标={oa:.2f} 命中={ha}/{ta} 命中日={ca}/{len(D)}')

print('\nB 新模型网格（互斥=1 时 bold 池 = 全部 - 冷启动 - 比分精选占位）：')
rows_out = []
for exc in (1, 0):
    for sh in (-1, 0, 1, 2):
        for mt in (2, 3):
            for gap in (1, 2):
                t = dict(SA.DEFAULT_TUNING, bd_total_shift=sh, bd_min_total=mt,
                         bd_gap=gap, bd_exclusive=exc)
                res = [new_day(r, t) for _, r in D]
                o, h, n, c = obj(res)
                rows_out.append((o, exc, sh, mt, gap, h, n, c))
rows_out.sort(key=lambda x: -x[0])
print(f'{"目标":>6} {"互斥":>4} {"shift":>5} {"minT":>5} {"gap":>4} {"命中":>7} {"命中日":>6}')
for o, exc, sh, mt, gap, h, n, c in rows_out[:12]:
    print(f'{o:6.2f} {exc:>4} {sh:>5} {mt:>5} {gap:>4} {h:>3}/{n:<3} {c:>4}/{len(D)}')
print('...')
for o, exc, sh, mt, gap, h, n, c in rows_out[-4:]:
    print(f'{o:6.2f} {exc:>4} {sh:>5} {mt:>5} {gap:>4} {h:>3}/{n:<3} {c:>4}/{len(D)}')
