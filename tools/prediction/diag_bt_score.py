# -*- coding: utf-8 -*-
"""基于 2478 场 walk-forward 回测档的比分口径 A/B（读 tools/prediction/bt_dump.json，只读）。"""
import json, math, os, collections, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(HERE, 'tools', 'prediction', 'bt_dump.json')


def parse(s):
    try:
        h, a = str(s).split(':')
        return int(h), int(a)
    except Exception:
        return None


def pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def make_grid(lh, la, gh=9, ga=9):
    return [[pois(h, lh) * pois(a, la) for a in range(ga + 1)] for h in range(gh + 1)]


def align(g, p):
    q = [0.0, 0.0, 0.0]
    for h in range(len(g)):
        for a in range(len(g[0])):
            q[0 if h > a else (1 if h == a else 2)] += g[h][a]
    s = [p[i] / q[i] if q[i] > 1e-12 else 0.0 for i in range(3)]
    return [[g[h][a] * s[0 if h > a else (1 if h == a else 2)] for a in range(len(g[0]))]
            for h in range(len(g))]


def mode(g, lim=9, allow=None):
    best, bs = -1, None
    for h in range(min(lim, len(g) - 1) + 1):
        for a in range(min(lim, len(g[0]) - 1) + 1):
            if allow and not allow(h, a):
                continue
            if g[h][a] > best:
                best, bs = g[h][a], (h, a)
    return bs


def main():
    d = json.load(open(DUMP, encoding='utf-8'))
    print(f'回测档 {len(d)} 场\n')

    # ---------- 1) 现状校准 ----------
    c = collections.Counter()
    for r in d:
        act = (r['hg'], r['ag'])
        top = r['top']
        if not top:
            continue
        c['n'] += 1
        c['claim1'] += r['top_p'][0] / 100
        if len(r['top_p']) > 2:
            c['claim23'] += (r['top_p'][1] + r['top_p'][2]) / 100
        c['h1'] += top[0] == f'{act[0]}:{act[1]}'
        c['h23'] += f'{act[0]}:{act[1]}' in top[1:3]
        c['h3'] += f'{act[0]}:{act[1]}' in top[:3]
        if len(top) >= 6:
            c['h6'] += f'{act[0]}:{act[1]}' in top[:6]
        t1 = parse(top[0])
        if t1:
            c['near1'] += (abs(t1[0] - act[0]) <= 1 and abs(t1[1] - act[1]) <= 1)
        c['draw_head'] += top[0].split(':')[0] == top[0].split(':')[1]
    n = c['n']
    print('=== 现状（引擎头条口径）===')
    print(f"头条 自称 {c['claim1'] / n * 100:.1f}%  实际 {c['h1'] / n * 100:.1f}%   ({c['h1']}/{n})")
    print(f"双档 自称 {c['claim23'] / n * 100:.1f}%  实际 {c['h23'] / n * 100:.1f}%   ({c['h23']}/{n})")
    print(f"头条+双档 实际 {(c['h1'] + c['h23']) / n * 100:.1f}%   前三累计 {c['h3'] / n * 100:.1f}%   前六累计 {c['h6'] / n * 100:.1f}%")
    print(f"头条 ±1 球邻域 {c['near1'] / n * 100:.1f}%")
    print(f"头条为平局比分的比例 {c['draw_head'] / n * 100:.1f}%\n")

    # ---------- 2) 候选规则 ----------
    def ev(fn, name):
        h1 = h23 = near = 0
        for r in d:
            act = (r['hg'], r['ag'])
            pick = fn(r)
            if not pick:
                continue
            if pick[0] == act:
                h1 += 1
            if act in pick[1:3]:
                h23 += 1
            if abs(pick[0][0] - act[0]) <= 1 and abs(pick[0][1] - act[1]) <= 1:
                near += 1
        print(f'{name:<30} 头条 {h1 / n * 100:5.2f}%   双档 {h23 / n * 100:5.2f}%   ±1球 {near / n * 100:5.1f}%')

    def r_engine(r):
        return [parse(x) for x in r['top']]

    def r_pois(r, up=1.0, dw=1.0, quad=False):
        lh, la = r['lam_h'] * up, r['lam_a'] * up
        ph, pd, pa = r['probs']
        s = ph + pd * dw + pa
        g = align(make_grid(lh, la), (ph / s, pd * dw / s, pa / s))
        okey = 0 if ph >= pd and ph >= pa else (1 if pd >= pa else 2)
        allow = None
        if quad:
            allow = (lambda h, a: h > a) if okey == 0 else ((lambda h, a: h == a) if okey == 1 else (lambda h, a: a > h))
        if dw != 1.0 or up != 1.0:
            pass
        return [mode(g, allow=allow)]

    print('=== 候选规则（2478 场）===')
    ev(r_engine, 'R0 引擎头条(现状)')
    ev(lambda r: r_pois(r, dw=1.0), 'R1 泊松对齐1X2·众数')
    ev(lambda r: r_pois(r, dw=0.9), 'R1b 同上·平局权重x0.90')
    ev(lambda r: r_pois(r, dw=0.8), 'R1c 同上·平局权重x0.80')
    ev(lambda r: r_pois(r, dw=1.0, quad=True), 'R1d 同上·限制在预测象限内')
    ev(lambda r: r_pois(r, up=1.05), 'R1e 同上·λ +5%')
    ev(lambda r: r_pois(r, up=1.10), 'R1f 同上·λ +10%')
    ev(lambda r: r_pois(r, up=0.95), 'R1g 同上·λ -5%')
    # 直接取引擎列出的候选，但优先非平局
    def r_nodraw(r):
        t = [parse(x) for x in r['top']]
        if not t:
            return []
        for x in t:
            if x[0] != x[1]:
                return [x]
        return [t[0]]
    ev(r_nodraw, 'R2 引擎候选·首个非平局')


if __name__ == '__main__':
    main()
