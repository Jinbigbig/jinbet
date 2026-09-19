# -*- coding: utf-8 -*-
"""A/B：比分精选「引擎矩阵口径」(旧=git HEAD) vs「选场用引擎、展示用本板块自算」(新)。
12 天回放，第一档命中率 / 命中日。"""
import json, glob, os
import importlib
import selection_algo as NEW
import _sa_old as OLD

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


def act(y, h, a):
    for key in (f'{y}_{h}_{a}', f'{y}_{a}_{h}'):
        r = recs.get(key)
        if r:
            s = r.get('score') or r.get('fullScore') or ''
            if isinstance(s, str) and ':' in s:
                return s
    return None


DAYS = []
for sp in sorted(glob.glob('predictions/*/pred_snapshot.json')):
    date = os.path.basename(os.path.dirname(sp))
    if date >= '2026-09-17':
        continue
    snap = json.load(open(sp, encoding='utf-8'))
    rows = []
    for m in snap.get('matches') or []:
        a = act(date, m.get('home'), m.get('away'))
        if not a:
            continue
        nm = dict(m)
        nm.setdefault('prob', {'home': m.get('prob_home', 0), 'draw': m.get('prob_draw', 0),
                               'away': m.get('prob_away', 0)})
        nm.setdefault('cold', False)
        nm.setdefault('data_n', {})
        rows.append((nm, a))
    if len(rows) >= 6:
        DAYS.append((date, rows))


def _key(mod, m):
    return mod.match_key(m) if hasattr(mod, 'match_key') else id(m)


def _pk_hit(mod, m, a, t):
    """兼容旧模块签名 pk_result(m, actual)。"""
    try:
        return mod.pk_result(m, a, t)
    except TypeError:
        return mod.pk_result(m, a)


def run(mod, rows, tag, tune=None):
    t = dict(mod.DEFAULT_TUNING)
    if tune:
        t.update(tune)
    ms = [m for m, _ in rows]
    amap = {_key(mod, m): a for m, a in rows}
    pk_t, pk_f, _ = mod.rank_pk(ms, t, mod.TIER_PK)
    if tag == 'pk':
        sel = [x[1] for x in (pk_t[0] if pk_t else [])]
        hit = sum(1 for m in sel if _pk_hit(mod, m, amap[_key(mod, m)], t) in ('hit', 'band'))
    else:
        ex = {_key(mod, m[1]) for m in pk_f}
        tiers, _ = mod.rank_bold(ms, t, mod.TIER_BD, exclude=ex)
        sel = [x[1] for x in (tiers[0] if tiers else [])]
        hit = sum(1 for m in sel
                  if mod.bd_result(m, amap[_key(mod, m)], t) in ('scale', 'extreme'))
    return hit, len(sel)


def main():
    for tag, name in (('pk', '比分精选'), ('bd', '大胆档')):
        oh = on = nh = nn = od = nd = 0
        for date, rows in DAYS:
            h1, n1 = run(OLD, rows, tag)
            h2, n2 = run(NEW, rows, tag)
            oh += h1; on += n1; nh += h2; nn += n2
            od += 1 if h1 >= 1 else 0
            nd += 1 if h2 >= 1 else 0
        print(f'{name}: 旧 {oh}/{on}={oh/max(1,on)*100:.1f}% 命中日 {od}/{len(DAYS)}'
              f'   →   新 {nh}/{nn}={nh/max(1,nn)*100:.1f}% 命中日 {nd}/{len(DAYS)}')


if __name__ == '__main__':
    main()
