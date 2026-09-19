# -*- coding: utf-8 -*-
"""决定性实验：头条「胆」档 + 二档「稳」档 的组合能否既大胆又不掉命中？

原理：众数格偏小（1-0/1-1），期望格偏大（2-1/2-2），两者在 31 格矩阵上
落点不同 ⇒ 组合的 Top2 覆盖可能优于「众数 + 次高众数」（现状 27.6%）。
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


def combos(r):
    lh, la = r['lh'], r['la']
    d = dist(r)
    lr = [(k, v) for k, v in sorted(d.items(), key=lambda x: -x[1]) if k in LISTED]
    mode = lr[0][0]
    exp = (int(round(lh)), int(round(la)))
    if exp not in LISTED:
        exp = mode
    o = {}
    o['A 现状:众数+次高'] = [mode, lr[1][0], lr[2][0]]
    o['B 稳+胆:众数+期望'] = [mode, exp, lr[1][0]]
    o['C 胆+稳:期望+众数'] = [exp, mode, lr[1][0]]
    o['D 期望+次高'] = [exp, lr[0][0], lr[1][0]]
    # 去重（若两档同格，补第三候选）
    out = {}
    for k, v in o.items():
        seen, uniq = set(), []
        for s in v:
            if s not in seen:
                seen.add(s); uniq.append(s)
        for s, _ in lr:
            if len(uniq) >= 3:
                break
            if s not in seen:
                seen.add(s); uniq.append(s)
        out[k] = uniq
    return out


def evaluate(subset, title):
    n = len(subset)
    act = sum(r['hg'] + r['ag'] for r in subset) / n
    agg = collections.defaultdict(lambda: {'h1': 0, 'h2': 0, 'h3': 0, 'tot': 0.0, 'big': 0, 'ovl': 0})
    for r in subset:
        actual = (r['hg'], r['ag'])
        for name, keys in combos(r).items():
            a = agg[name]
            if actual == keys[0]:
                a['h1'] += 1
            if actual in keys[:2]:
                a['h2'] += 1
            if actual in keys[:3]:
                a['h3'] += 1
            a['tot'] += sum(keys[0]) + sum(keys[1])
            if max(sum(keys[0]), sum(keys[1])) >= 3:
                a['big'] += 1
            if keys[0] != keys[1]:
                a['ovl'] += 1
    print(f'\n### {title} (n={n}, 实际平均 {act:.2f} 球)')
    print(f'{"组合":<20}{"Top1":>8}{"Top2":>8}{"Top3":>8}{"档均进球":>10}{"含≥3球档":>11}{"两档不同":>10}')
    print('-' * 76)
    for name, a in agg.items():
        print(f'{name:<20}{a["h1"]/n*100:>7.1f}%{a["h2"]/n*100:>7.1f}%{a["h3"]/n*100:>7.1f}%'
              f'{a["tot"]/n/2:>10.2f}{a["big"]/n*100:>10.1f}%{a["ovl"]/n*100:>9.1f}%')


evaluate(rows, '全样本')
cut = rows[int(N * 0.6)]['d']
evaluate([r for r in rows if r['d'] >= cut], f'时间外检验集(≥{cut})')
for lo, hi, tag in [(0, 2.6, 'λ≤2.6'), (2.6, 3.5, '2.6<λ≤3.5'), (3.5, 99, 'λ>3.5')]:
    sub = [r for r in rows if lo < r['lh'] + r['la'] <= hi] if lo else [r for r in rows if r['lh'] + r['la'] <= hi]
    if r'd' in rows[0]:
        sub = [r for r in sub if r['d'] >= cut]
    evaluate(sub, f'{tag} · 时间外')
