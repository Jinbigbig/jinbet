# -*- coding: utf-8 -*-
"""大胆档新模型的大样本验证（离线探针，不入库）。

样本：_calib_backup_20260916/backtest_after.json（2462 场，2026-01-30 ~ 2026-09-09，
含 1X2 概率与实际比分，但无 λ）→ 先从 1X2 概率反解 (λh, λa)，再直接调用
生产实现 selection_algo.bd_ref 评估各参数口径的命中率。

说明：本表无「比分精选占位」信息，故只验证参考口径与质量排序（不含互斥），
互斥的效果另由 12 天快照回放验证。
"""
import json, math, os
import selection_algo as SA

SRC = '_calib_backup_20260916/backtest_after.json'
TIER_BD = SA.TIER_BD

# 真实 λ 口径来自引擎的期望值，量级 1.6~4.2（保险丝）→ 反解也在该区间内找
STEPS = [round(0.10 * i, 2) for i in range(1, 41)]  # 0.10 ~ 4.00


def _pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def build_grid(steps):
    """(λh, λa) 网格 → 1X2 三元组（纯泊松，7×7 截断）。"""
    out = []
    for lh in steps:
        for la in steps:
            t = lh + la
            if t < 1.5 or t > 4.3:
                continue
            ph = pd = pa = 0.0
            for h in range(7):
                fh = _pmf(h, lh)
                for a in range(7):
                    p = fh * _pmf(a, la)
                    if h > a:
                        ph += p
                    elif h == a:
                        pd += p
                    else:
                        pa += p
            s = ph + pd + pa
            out.append((lh, la, ph / s, pd / s, pa / s))
    return out


def invert(probs, grid):
    """按 1X2 三元组的最小平方误差反解 (λh, λa)。"""
    ph, pd, pa = probs['H'], probs['D'], probs['A']
    best, bd = None, 1e9
    for lh, la, x, y, z in grid:
        d = (x - ph) ** 2 + (y - pd) ** 2 + (z - pa) ** 2
        if d < bd:
            bd, best = d, (lh, la)
    return best


def refs(lh, la, tuning):
    return SA.bd_ref({'lam_home': lh, 'lam_away': la}, tuning)


def old_ref(lh, la, probs):
    """旧口径：倾向 = 引擎 1X2 argmax；量级 = 该象限内总球数 = round(λ总) 的最高概率格。"""
    d, _, _ = SA.bd_grid({'lam_home': lh, 'lam_away': la})
    lean = max((('home', probs['H']), ('draw', probs['D']), ('away', probs['A'])),
               key=lambda x: x[1])[0]
    base = int(round(lh + la))
    s, ps = SA._bd_pick(d, lean, base)
    x, px = SA._bd_pick(d, lean, base + 1)
    return s, ps, x, px


def main():
    rows = json.load(open(SRC, encoding='utf-8'))['results']
    grid = build_grid(STEPS)
    print(f'样本 {len(rows)} 场，λ 网格 {len(grid)} 组')

    matches = []
    for r in rows:
        act = r.get('actual_score')
        pr = r.get('probs') or {}
        if not act or ':' not in act or len(pr) < 3:
            continue
        lh, la = invert(pr, grid)
        matches.append({'date': r['date'], 'act': act, 'lh': lh, 'la': la, 'probs': pr,
                        'lam_home': lh, 'lam_away': la})
    print(f'可用 {len(matches)} 场')

    byday = {}
    for m in matches:
        byday.setdefault(m['date'], []).append(m)
    days = [byday[d] for d in sorted(byday) if len(byday[d]) >= 4]
    print(f'可用天数 {len(days)}（≥4 场）\n')

    def evaluate(quality_fn, ref_fn, tag):
        rates, covs, hits, legs = [], [], 0, 0
        for day in days:
            scored = sorted(((quality_fn(m), m) for m in day), key=lambda x: -x[0])[:TIER_BD]
            h = 0
            for _, m in scored:
                s, _, x, _ = ref_fn(m)
                if m['act'] == s or (x and m['act'] == x):
                    h += 1
            hits += h
            legs += len(scored)
            rates.append(h / max(1, len(scored)))
            covs.append(1 if h >= 1 else 0)
        n = len(days)
        obj = 0.6 * (sum(rates) / n) * 100 + 0.4 * (sum(covs) / n) * 100
        print(f'{tag:<22} 目标={obj:6.2f}  命中={hits}/{legs} = {hits/max(1,legs)*100:5.1f}%  '
              f'命中日={sum(covs)}/{n}')
        return obj


    print('—— 旧口径 ——')
    evaluate(lambda m: max((old_ref(m['lh'], m['la'], m['probs'])[1] or 0),
                           (old_ref(m['lh'], m['la'], m['probs'])[3] or 0)),
             lambda m: old_ref(m['lh'], m['la'], m['probs']), '旧口径(引擎象限/取整)')

    print('\n—— 新模型（自带 λ 泊松）——')
    best = []
    for sh in (-1, 0, 1, 2):
        for mt in (2, 3):
            for gap in (1, 2):
                t = dict(SA.DEFAULT_TUNING, bd_total_shift=sh, bd_min_total=mt, bd_gap=gap)
                q = lambda m, t=t: SA.bd_ref(m, t)[1] + (SA.bd_ref(m, t)[3] or 0)
                o = evaluate(q, lambda m, t=t: SA.bd_ref(m, t),
                             f'shift={sh} minT={mt} gap={gap}')
                best.append((o, sh, mt, gap))
    best.sort(reverse=True)
    print('\n排名前 5:', [(f'{o:.2f}', s, m, g) for o, s, m, g in best[:5]])

    print('\n—— 前 70% / 后 30% 天分段（只看前 4 名与旧口径）——')
    n = len(days)
    cut = int(n * 0.7)
    half1, half2 = days[:cut], days[cut:]
    def ev(tag, quality_fn, ref_fn, subset):
        save = days[:]; days[:] = subset
        o = evaluate(quality_fn, ref_fn, tag)
        days[:] = save
        return o
    for o, sh, mt, gap in best[:4]:
        t = dict(SA.DEFAULT_TUNING, bd_total_shift=sh, bd_min_total=mt, bd_gap=gap)
        q = lambda m, t=t: SA.bd_ref(m, t)[1] + (SA.bd_ref(m, t)[3] or 0)
        r = lambda m, t=t: SA.bd_ref(m, t)
        ev(f'  [前70%] shift={sh} minT={mt} gap={gap}', q, r, half1)
        ev(f'  [后30%] shift={sh} minT={mt} gap={gap}', q, r, half2)
    qo = lambda m: max(old_ref(m['lh'], m['la'], m['probs'])[1] or 0,
                       old_ref(m['lh'], m['la'], m['probs'])[3] or 0)
    ro = lambda m: old_ref(m['lh'], m['la'], m['probs'])
    ev('  [前70%] 旧口径', qo, ro, half1)
    ev('  [后30%] 旧口径', qo, ro, half2)


if __name__ == '__main__':
    main()


def sweep_lean():
    """对比两种倾向来源：自身泊松 vs 引擎 1X2（两者都不读引擎比分矩阵）。"""
    rows = json.load(open(SRC, encoding='utf-8'))['results']
    grid = build_grid(STEPS)
    ms = []
    for r in rows:
        act, pr = r.get('actual_score'), r.get('probs') or {}
        if not act or ':' not in act or len(pr) < 3:
            continue
        lh, la = invert(pr, grid)
        ms.append({'date': r['date'], 'act': act, 'lh': lh, 'la': la, 'probs': pr,
                   'lam_home': lh, 'lam_away': la})
    byday = {}
    for m in ms:
        byday.setdefault(m['date'], []).append(m)
    days = [byday[d] for d in sorted(byday) if len(byday[d]) >= 4]

    def eng_ref(m, sh, mt, gap):
        d, _, _ = SA.bd_grid(m)
        lean = max((('home', m['probs']['H']), ('draw', m['probs']['D']),
                    ('away', m['probs']['A'])), key=lambda x: x[1])[0]
        base = max(mt, int(round(m['lam_home'] + m['lam_away'])) + sh)
        s, ps = SA._bd_pick(d, lean, base)
        x, px = SA._bd_pick(d, lean, base + gap)
        return s, ps, x, px

    print('\n=== 倾向来源对比（minT=2 / gap=1）===')
    print(f'{"shift":>6}{"自身泊松":>12}{"引擎1X2":>12}')
    for sh in (-2, -1, 0, 1, 2):
        line = f'{sh:>6}'
        for mode in ('self', 'engine'):
            rates, covs, hits, legs = [], [], 0, 0
            for day in days:
                def q(m):
                    r = SA.bd_ref(m, dict(SA.DEFAULT_TUNING, bd_total_shift=sh,
                                          bd_min_total=2, bd_gap=1)) if mode == 'self' \
                        else eng_ref(m, sh, 2, 1)
                    return (r[1] or 0) + (r[3] or 0)
                scored = sorted(((q(m), m) for m in day), key=lambda x: -x[0])[:TIER_BD]
                h = 0
                for _, m in scored:
                    r = SA.bd_ref(m, dict(SA.DEFAULT_TUNING, bd_total_shift=sh,
                                          bd_min_total=2, bd_gap=1)) if mode == 'self' \
                        else eng_ref(m, sh, 2, 1)
                    if m['act'] == r[0] or (r[2] and m['act'] == r[2]):
                        h += 1
                hits += h; legs += len(scored)
                rates.append(h / max(1, len(scored)))
                covs.append(1 if h >= 1 else 0)
            o = 0.6 * (sum(rates) / len(days)) * 100 + 0.4 * (sum(covs) / len(days)) * 100
            line += f'{o:7.2f}({hits/legs*100:4.1f}%)'
        print(line)


if __name__ == '__main__':
    pass

sweep_lean()
