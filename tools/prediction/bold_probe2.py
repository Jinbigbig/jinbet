# -*- coding: utf-8 -*-
"""大胆化口径：分 λ 档 + 时间外检验集对比。

关键问题：众数的命中优势在各 λ 档是否一致？失真（偏差）是否集中在高 λ 段？
若高 λ 段众数优势消失 → 可「低 λ 保守、高 λ 大胆」分层，代价最小。
"""
import json, math, collections

rows = json.load(open('_grid_cache.json', encoding='utf-8'))
rows.sort(key=lambda r: r['d'])
N = len(rows)


def listed(h, a):
    if h > a:
        return h <= 5 and a <= 2
    if h == a:
        return h <= 3
    return a <= 5 and h <= 2


LISTED = {(h, a) for h in range(6) for a in range(6) if listed(h, a)}


def pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def dist(r):
    d = {}
    for s, p in r['top']:
        h, a = (int(x) for x in s.split(':'))
        d[(h, a)] = p
    for h in range(7):
        for a in range(7):
            if (h, a) not in d:
                d[(h, a)] = pois(r['lh'], h) * pois(r['la'], a) * 0.15
    return d


def cands(r):
    lh, la = r['lh'], r['la']
    d = dist(r)
    lr = [(k, v) for k, v in sorted(d.items(), key=lambda x: -x[1]) if k in LISTED]
    o = {}
    o['众数'] = [lr[0][0]] + [x[0] for x in lr[1:3]]
    o['round(λ)'] = [(int(round(lh)), int(round(la)))] + [x[0] for x in lr[:3]]
    o['round(λ-0.25)'] = [(int(round(lh - .25)), int(round(la - .25)))] + [x[0] for x in lr[:3]]
    o['逐轴取大'] = [(max(lr[0][0][0], int(round(lh))), max(lr[0][0][1], int(round(la))))] + [x[0] for x in lr[:3]]
    return o


def evaluate(subset, title):
    n = len(subset)
    if n < 50:
        return
    act = sum(r['hg'] + r['ag'] for r in subset) / n
    agg = collections.defaultdict(lambda: {'h1': 0, 'h2': 0, 'h3': 0, 'tot': 0.0, 'big': 0})
    for r in subset:
        actual = (r['hg'], r['ag'])
        for name, keys in cands(r).items():
            a = agg[name]
            if actual == keys[0]:
                a['h1'] += 1
            if actual in keys[:2]:
                a['h2'] += 1
            if actual in keys[:3]:
                a['h3'] += 1
            a['tot'] += sum(keys[0])
            if sum(keys[0]) >= 3:
                a['big'] += 1
    print(f'\n### {title}  (n={n}, 实际平均 {act:.2f} 球)')
    print(f'{"口径":<14}{"Top1":>8}{"Top2":>8}{"Top3":>8}{"预测进球":>10}{"偏差":>8}{"≥3球":>8}')
    print('-' * 62)
    for name, a in agg.items():
        print(f'{name:<14}{a["h1"]/n*100:>7.1f}%{a["h2"]/n*100:>7.1f}%{a["h3"]/n*100:>7.1f}%'
              f'{a["tot"]/n:>10.2f}{a["tot"]/n-act:>+8.2f}{a["big"]/n*100:>7.1f}%')


# 全样本
evaluate(rows, '全样本')
# 分 λ 档
for lo, hi, tag in [(0, 2.6, 'λ≤2.6'), (2.6, 3.5, '2.6<λ≤3.5'), (3.5, 99, 'λ>3.5')]:
    sub = [r for r in rows if lo < r['lh'] + r['la'] <= hi] if lo else [r for r in rows if r['lh'] + r['la'] <= hi]
    evaluate(sub, tag)
# 时间外：后 40%
cut = rows[int(N * 0.6)]['d']
evaluate([r for r in rows if r['d'] >= cut], f'时间外检验集(后40%, ≥{cut})')
