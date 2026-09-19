# -*- coding: utf-8 -*-
"""比分口径「大胆化」候选对比（4036 场生产口径缓存）。

目标：在保持/略降命中率的前提下，让头条比分不再系统性偏小。
评估三个维度：
  hit1  = Top1 单点命中率
  hit2  = Top2 命中率
  bias  = 平均预测总进球 − 平均实际总进球（负值=偏保守）
  big%  = 预测总进球 ≥3 的场次占比（大胆度）
"""
import json, math, collections

rows = json.load(open('_grid_cache.json', encoding='utf-8'))
N = len(rows)
act_tot = sum(r['hg'] + r['ag'] for r in rows) / N
print(f'样本 {N} 场 | 实际平均总进球 {act_tot:.3f}\n')


def pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def listed(s):
    h, a = s
    if h > a:
        return h <= 5 and a <= 2
    if h == a:
        return h <= 3
    return a <= 5 and h <= 2


# ---------- 候选口径：每个返回 [(score, prob), ...] 排序 ----------
LISTED = {(h, a) for h in range(6) for a in range(6) if listed((h, a))}
# 用缓存的 top6 近似完整分布（只覆盖前 6 格），并补 λ 泊松作为后备
def dist(r):
    d = {}
    for s, p in r['top']:
        h, a = (int(x) for x in s.split(':'))
        d[(h, a)] = p
    for h in range(7):
        for a in range(7):
            k = (h, a)
            if k not in d:
                d[k] = pois(r['lh'], h) * pois(r['la'], a) * 0.15  # 尾部近似（仅用于排序）
    return d


def cands(r):
    lh, la = r['lh'], r['la']
    d = dist(r)
    ranked = sorted(d.items(), key=lambda x: -x[1])
    listed_ranked = [(k, v) for k, v in ranked if k in LISTED]
    out = {}

    # 1 现状：联合众数
    out['①众数(现状)'] = listed_ranked[:2]

    # 2 期望取整 round(λ)
    c = (int(round(lh)), int(round(la)))
    out['②round(λ)'] = [(c, d.get(c, 0))] + [x for x in listed_ranked if x[0] != c][:1]

    # 3 ceil(λ) 向上取整
    c = (math.ceil(lh - 0.15), math.ceil(la - 0.15))
    out['③ceil(λ)'] = [(c, d.get(c, 0))] + [x for x in listed_ranked if x[0] != c][:1]

    # 4 众数 + 大胆档（同倾向内、总进球更大的最高概率格）
    if listed_ranked:
        mk = listed_ranked[0][0]
        okey = 'home' if mk[0] > mk[1] else ('draw' if mk[0] == mk[1] else 'away')
        q = (lambda k: k[0] > k[1]) if okey == 'home' else (
            (lambda k: k[0] == k[1]) if okey == 'draw' else (lambda k: k[0] < k[1]))
        bolder = [(k, v) for k, v in listed_ranked
                  if q(k) and (k[0] + k[1]) > (mk[0] + mk[1])]
        out['④众数+大胆档'] = [listed_ranked[0]] + (bolder[:1] or listed_ranked[1:2])

    # 5 倾向象限条件期望（落在象限内的 λ 条件期望，四舍五入）
    lt = lh + la
    # 条件期望：以泊松近似算 H>A / H=A / H<A 下的期望进球
    ph = pd_ = pa = 0.0
    eh = ea = 0.0
    eh_d = 0.0
    eh_a = 0.0
    for h in range(9):
        for a in range(9):
            p = pois(lh, h) * pois(la, a)
            if h > a:
                ph += p; eh += p * h; ea += p * a
            elif h == a:
                pd_ += p; eh_d += p * h
            else:
                pa += p; eh_a += p * a
    okey = max([('home', ph), ('draw', pd_), ('away', pa)], key=lambda x: x[1])[0]
    if okey == 'home':
        c = (int(round(eh / ph)) if ph > 0 else int(round(lh)),
             int(round(ea / ph)) if ph > 0 else int(round(la)))
    elif okey == 'draw':
        v = int(round(eh_d / pd_)) if pd_ > 0 else int(round(lh))
        c = (v, v)
    else:
        c = (int(round(lh * 0.9)), int(round(eh_a / pa)) if pa > 0 else int(round(la)))
    if c == (0, 0):
        c = (1, 1)
    if c[0] == c[1] and okey != 'draw':
        c = (c[0], c[1]) if okey == 'home' else (c[0], c[1])
    if okey == 'home' and c[0] <= c[1]:
        c = (c[1] + 1, c[1])
    if okey == 'away' and c[1] <= c[0]:
        c = (c[0], c[0] + 1)
    out['⑤象限条件期望'] = [(c, d.get(c, 0))] + [x for x in listed_ranked if x[0] != c][:1]

    # 6 众数上抬一档（主客各 +0.5 后取整，倾向保持不变）
    mk = listed_ranked[0][0]
    c = (mk[0] + 1, mk[1]) if mk[0] >= mk[1] else (mk[0], mk[1] + 1)
    if mk[0] == mk[1]:
        c = (mk[0] + 1, mk[1] + 1)
    out['⑥众数+1档'] = [listed_ranked[0], (c, d.get(c, 0))]

    return out


agg = collections.defaultdict(lambda: {'h1': 0, 'h2': 0, 'tot': 0.0, 'big': 0})
for r in rows:
    actual = (r['hg'], r['ag'])
    for name, picks in cands(r).items():
        a = agg[name]
        keys = [p[0] for p in picks[:2]]
        if actual in keys[:1]:
            a['h1'] += 1
        if actual in keys:
            a['h2'] += 1
        a['tot'] += keys[0][0] + keys[0][1]
        if keys[0][0] + keys[0][1] >= 3:
            a['big'] += 1

print(f'{"口径":<16}{"Top1":>8}{"Top2":>8}{"平均预测进球":>13}{"进球偏差":>10}{"≥3球场次":>11}')
print('-' * 68)
for name, a in agg.items():
    bias = a['tot'] / N - act_tot
    print(f'{name:<16}{a["h1"]/N*100:>7.1f}%{a["h2"]/N*100:>7.1f}%'
          f'{a["tot"]/N:>13.2f}{bias:>+10.2f}{a["big"]/N*100:>10.1f}%')
