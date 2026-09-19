# -*- coding: utf-8 -*-
"""自适应胆档：只在「众数偏小」的场次启用大胆档，众数已够大时退回次高众数。

规则：
  稳档 = 联合众数（数学最优，头条不变）
  胆档 = round(λ)（量级无偏）
  若 sum(胆档) > sum(稳档) → 第二档用胆档（这场众数确实偏小）
  否则 → 第二档用次高众数（现状，众数已够大，改了反而掉命中）
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
    second = lr[1][0]
    o = {}
    o['A 现状:众数+次高'] = [mode, second, lr[2][0]]
    o['B 全量胆档'] = [mode, exp, second]
    # 自适应
    if sum(exp) > sum(mode):
        o['C 自适应胆档'] = [mode, exp, second]
    else:
        o['C 自适应胆档'] = [mode, second, exp]
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
    agg = collections.defaultdict(lambda: {'h1': 0, 'h2': 0, 'h3': 0, 'tot': 0.0, 'big': 0})
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
    print(f'\n### {title} (n={n}, 实际平均 {act:.2f} 球)')
    print(f'{"组合":<18}{"Top1":>8}{"Top2":>8}{"Top3":>8}{"档均进球":>10}{"含≥3球档":>11}')
    print('-' * 66)
    for name, a in agg.items():
        print(f'{name:<18}{a["h1"]/n*100:>7.1f}%{a["h2"]/n*100:>7.1f}%{a["h3"]/n*100:>7.1f}%'
              f'{a["tot"]/n/2:>10.2f}{a["big"]/n*100:>10.1f}%')


evaluate(rows, '全样本')
cut = rows[int(N * 0.6)]['d']
evaluate([r for r in rows if r['d'] >= cut], f'时间外检验集(≥{cut})')
for lo, hi, tag in [(0, 2.6, 'λ≤2.6'), (2.6, 3.5, '2.6<λ≤3.5'), (3.5, 99, 'λ>3.5')]:
    sub = [r for r in rows if lo < r['lh'] + r['la'] <= hi] if lo else [r for r in rows if r['lh'] + r['la'] <= hi]
    sub = [r for r in sub if r['d'] >= cut]
    if len(sub) >= 80:
        evaluate(sub, f'{tag} · 时间外')

# 自适应触发率
trig = sum(1 for r in rows if sum((int(round(r['lh'])), int(round(r['la'])))) >
           sum(next(k for k, v in sorted(dist(r).items(), key=lambda x: -x[1]) if k in LISTED)))
print(f'\n自适应胆档触发率: {trig/N*100:.1f}% 场次（这些场次众数偏小，会被换上大胆档）')
