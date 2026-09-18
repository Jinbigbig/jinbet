# -*- coding: utf-8 -*-
"""头条「条件大胆」：只在「众数总进球明显低于 λ 总量」的场次把头条换成期望格。

触发条件： (λ主+λ客) - sum(众数格) >= T
在触发子集内比较 众数 vs 期望 的 Top1 命中率：若期望 ≥ 众数 → 零损失大胆化成立。
"""
import json, math, collections

rows = json.load(open('_grid_cache.json', encoding='utf-8'))
rows.sort(key=lambda r: r['d'])
N = len(rows)
cut = rows[int(N * 0.6)]['d']


def listed(h, a):
    if h > a:
        return h <= 5 and a <= 2
    if h == a:
        return h <= 3
    return a <= 5 and h <= 2


LISTED = {(h, a) for h in range(6) for a in range(6) if listed(h, a)}


def pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def mode_of(r):
    d = {}
    for s, p in r['top']:
        h, a = (int(x) for x in s.split(':'))
        d[(h, a)] = p
    for h in range(7):
        for a in range(7):
            if (h, a) not in d:
                d[(h, a)] = pois(r['lh'], h) * pois(r['la'], a) * 0.15
    return next(k for k, v in sorted(d.items(), key=lambda x: -x[1]) if k in LISTED)


for split, sub in (('全样本', rows), (f'时间外(≥{cut})', [r for r in rows if r['d'] >= cut])):
    print(f'\n######## {split} ########')
    for T in (0.0, 1.0, 1.5, 2.0):
        trig = [r for r in sub if (r['lh'] + r['la']) - sum(mode_of(r)) >= T]
        if len(trig) < 60:
            print(f'T={T}: 触发 {len(trig)} 场（样本不足）')
            continue
        hm = he = 0
        tm = te = 0
        for r in trig:
            act = (r['hg'], r['ag'])
            m = mode_of(r)
            e = (int(round(r['lh'])), int(round(r['la'])))
            hm += (act == m); he += (act == e)
            tm += sum(m); te += sum(e)
        n = len(trig)
        all_hm = sum(1 for r in sub if (r['hg'], r['ag']) == mode_of(r)) / len(sub)
        # 混合策略：触发子集用期望，其余用众数
        mix = sum(1 for r in sub
                  if (r['hg'], r['ag']) == ((int(round(r['lh'])), int(round(r['la'])))
                                            if (r['lh'] + r['la']) - sum(mode_of(r)) >= T
                                            else mode_of(r))) / len(sub)
        print(f'T≥{T}: 触发 {n} 场 ({n/len(sub)*100:.0f}%) | 子集内 众数 {hm/n*100:.1f}% vs 期望 {he/n*100:.1f}%'
              f' (差 {(he-hm)/n*100:+.1f}pp) | 进球 {tm/n:.2f}→{te/n:.2f}'
              f' | 混合策略全局 Top1 {mix*100:.1f}% (纯众数 {all_hm*100:.1f}%)')
