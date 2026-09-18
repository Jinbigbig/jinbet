# -*- coding: utf-8 -*-
"""诊断：比分精选/大胆档 回放口径是否与生产一致 + 历史真实命中率。

对比两套选取：
  A) 生产口径：走 SA.rank_pk / SA.rank_bd（排除冷启动、按 num_tiers 分档）
  B) 优化器口径：_optimize_selection 里的 _pk_day_score / _bd_day_score（不排除冷启动）
若 A/B 选取结果不同 → 优化器在评估另一个算法，调参无效。
"""
import json, os, glob, datetime, collections
import selection_algo as SA

today = datetime.datetime.now().strftime('%Y-%m-%d')

# ---- 赛果缓存（与优化器一致）----
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


tuning = SA.load_tuning()

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
        act = actual(date, m.get('home'), m.get('away'))
        if not act:
            continue
        nm = dict(m)
        nm.setdefault('prob', {'home': m.get('prob_home', 0), 'draw': m.get('prob_draw', 0),
                               'away': m.get('prob_away', 0)})
        nm.setdefault('cold', False)
        nm.setdefault('data_n', {})
        rows.append((nm, act))
    if rows:
        days.append((date, rows))

print(f'有赛果的历史日: {len(days)}')
print()

pk_all = collections.Counter()
bd_all = collections.Counter()
hdr = f"{'日期':<12}{'场':>3} | {'生产pk前6命中':>12} {'优化器pk前6':>12} | {'生产bd前4命中':>12} {'优化器bd前4':>12} | 差异"
print(hdr)
print('-' * len(hdr))

diff_days = 0
cold_in_prod = 0
for date, rows in days:
    colds = [m for m, _ in rows if SA.is_cold(m)]

    # A) 生产口径（rank_* 返回 [(排序键, match)]，需取 [1]）
    amap = {id(m): a for m, a in rows}
    tiers_pk, flat_pk, _ = SA.rank_pk([m for m, _ in rows], tuning, SA.TIER_PK)
    selA = [x[1] for x in flat_pk]
    succA = sum(1 for m in selA if SA.pk_result(m, amap[id(m)]) in ('hit', 'band'))
    bdA = [x[1] for x in SA.rank_bold([m for m, _ in rows], tuning, SA.TIER_BD)[1]]
    bsuccA = sum(1 for m in bdA if SA.bd_result(m, amap[id(m)]) in ('scale', 'extreme'))

    # B) 优化器口径（不排冷启动）
    rankedB = sorted(rows, key=lambda r: -SA.pk_quality(r[0], tuning))
    selB = [m for m, _ in rankedB[:SA.TIER_PK]]
    succB = sum(1 for m, a in rankedB[:SA.TIER_PK] if SA.pk_result(m, a) in ('hit', 'band'))
    rankedBB = sorted(rows, key=lambda r: -SA.bold_quality(r[0], tuning))
    bdB = [m for m, _ in rankedBB[:SA.TIER_BD]]
    bsuccB = sum(1 for m, a in rankedBB[:SA.TIER_BD] if SA.bd_result(m, a) in ('scale', 'extreme'))

    same = (set(map(id, selA)) == set(map(id, selB))) and (set(map(id, bdA)) == set(map(id, bdB)))
    if not same:
        diff_days += 1
    for m in selA:
        if SA.is_cold(m):
            cold_in_prod += 1

    nA, nB = min(SA.TIER_PK, len(selA)), min(SA.TIER_PK, len(selB))
    for m in selA:
        pk_all[SA.pk_result(m, amap[id(m)])] += 1
    for m in bdA:
        bd_all[SA.bd_result(m, amap[id(m)])] += 1

    print(f"{date:<12}{len(rows):>3} | {succA}/{nA:<9} {succB}/{nB:<11} | "
          f"{bsuccA}/{min(SA.TIER_BD,len(bdA)):<9} {bsuccB}/{min(SA.TIER_BD,len(bdB)):<11} | "
          f"{'' if same else '不同'}")

print()
tot_pk = sum(pk_all.values()); tot_bd = sum(bd_all.values())
hitpk = pk_all['hit'] + pk_all['band']
print(f'生产口径 比分精选：{tot_pk} 腿 命中(含双档) {hitpk} = {hitpk/max(1,tot_pk)*100:.1f}%  '
      f'[单点 {pk_all["hit"]} / 双档 {pk_all["band"]} / 未中 {pk_all["miss"]}]')
hitbd = bd_all['scale'] + bd_all['extreme']
print(f'生产口径 大胆档  ：{tot_bd} 腿 命中 {hitbd} = {hitbd/max(1,tot_bd)*100:.1f}%  '
      f'[量级 {bd_all["scale"]} / 极限 {bd_all["extreme"]} / 未中 {bd_all["miss"]}]')
print()
print(f'两套口径选取不同的天数: {diff_days}/{len(days)}')
print(f'生产口径里出现的冷启动场次腿数: {cold_in_prod}（应为 0）')
