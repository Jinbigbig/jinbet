# -*- coding: utf-8 -*-
"""探针2：比分精选「自建管线」= 本身泊松网格 + 自己对齐到引擎已发布 1X2，自己取 argmax/2/3。
对比引擎矩阵口径（现生产）。"""
import json, glob, os, math, importlib
import selection_algo as SA
import _pk_ref_probe as P   # 复用数据加载

MAXG = 8
def pois(k, lam): return math.exp(-lam) * lam ** k / math.factorial(k)

def self_grid(m):
    lh = float(m.get('lam_home', 0) or 0); la = float(m.get('lam_away', 0) or 0)
    d = {}
    for h in range(MAXG + 1):
        for a in range(MAXG + 1):
            if f'{h}:{a}' in SA.LISTED_LABELS:
                d[f'{h}:{a}'] = pois(h, lh) * pois(a, la)
    return d

def align(d, probs):
    """自建对齐：三象限分别缩放到引擎已发布 1X2 概率。"""
    out = dict(d)
    for key, lab in (('home', lambda h, a: h > a), ('draw', lambda h, a: h == a), ('away', lambda h, a: a > h)):
        tgt = float(probs.get(key, 0) or 0) / 100.0
        cur = 0.0
        for s in out:
            h, a = (int(x) for x in s.split(':'))
            if lab(h, a): cur += out[s]
        if cur > 1e-12 and tgt > 0:
            k = tgt / cur
            for s in out:
                h, a = (int(x) for x in s.split(':'))
                if lab(h, a): out[s] *= k
    tot = sum(out.values())
    if tot > 0:
        for s in out: out[s] /= tot
    return out

def pk_rank(m, aligned=True, n=3):
    d = self_grid(m)
    if aligned: d = align(d, SA.prob1x2(m))
    cells = sorted(d.items(), key=lambda x: -x[1])
    return [(s, round(p * 100, 1)) for s, p in cells[:n]]

D = P.days
t = SA.load_tuning()
for mode in ('engine(现生产)', 'self-未对齐', 'self-已对齐1X2'):
    allh = allb = selh = selb = n = sn = 0
    for date, rows in D:
        ms = [m for m, _ in rows]
        for m, a in rows:
            n += 1
            if mode.startswith('engine'):
                hd = SA.hit_pick(m)[0]; bd = [s for s, _ in SA.band_scores(m, 2)]
            else:
                r = pk_rank(m, aligned=(mode == 'self-已对齐1X2'))
                hd = r[0][0]; bd = [s for s, _ in r[1:3]]
            if a == hd: allh += 1
            if a in bd: allb += 1
        tiers, flat, _ = SA.rank_pk(ms, t, SA.TIER_PK)
        for xt in (tiers[0] if tiers else []):
            m = xt[1]
            a = next(ac for mm, ac in rows if mm is m)
            sn += 1
            if mode.startswith('engine'):
                hd = SA.hit_pick(m)[0]; bd = [s for s, _ in SA.band_scores(m, 2)]
            else:
                r = pk_rank(m, aligned=(mode == 'self-已对齐1X2'))
                hd = r[0][0]; bd = [s for s, _ in r[1:3]]
            if a == hd: selh += 1
            if a in bd: selb += 1
    print(f'{mode:<16} 全样本 头条 {allh}/{n}={allh/n*100:.1f}%  双档 {allb}/{n}={allb/n*100:.1f}%  |'
          f'  第一档 头条 {selh}/{sn}  双档 {selb}/{sn}')
