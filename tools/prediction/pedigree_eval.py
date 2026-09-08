# -*- coding: utf-8 -*-
"""
历史战绩窗口评估：长期战绩 vs 近 10 场状态，谁更有预测力？

背景：用户要求预测要"结合历史战绩"（如欧冠历史战绩）。
本脚本用 results_data.json 做 walk-forward 检验，回答两个问题：
  Q1: 长期历史战绩（全部历史场均净胜球）相对近 10 场状态，是否有增量信息？
  Q2: 两者最优混合权重是多少？（用于决定引擎的"战绩窗口"参数）

方法（纯 python，无第三方依赖）：
  逐场推进（按日期），对每场用该场之前的球队历史计算：
    d10  = 近 10 场场均净胜球差（主 - 客）
    dall = 全部历史场均净胜球差（主 - 客）
  评估目标：该场主队实际净胜球 gd = hg - ag
  指标：Pearson 相关、MSE、方向（胜/平/负）命中率、分层效应表

用法: python pedigree_eval.py
"""
import json
import math
import collections
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, 'results_data.json')
MIN_HIST = 5  # 球队至少需要的历史场次


def load_rows():
    res = json.load(open(RES, encoding='utf-8'))
    rows = []
    for k, v in res.items():
        date = k.split('_')[0]
        fs = v.get('fullScore') or ''
        if ':' not in fs:
            continue
        try:
            hg, ag = [int(x) for x in fs.split(':')]
        except ValueError:
            continue
        rows.append((date, v.get('home', ''), v.get('away', ''), hg, ag, v.get('league', '')))
    rows.sort(key=lambda r: r[0])
    return rows


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def main():
    rows = load_rows()
    print(f'载入 {len(rows)} 场（含比分）')

    hist = collections.defaultdict(list)
    samples = []  # (d10, dall, gd, n_h, n_a)
    for date, h, a, hg, ag, lg in rows:
        nh, na = len(hist[h]), len(hist[a])
        if nh >= MIN_HIST and na >= MIN_HIST:
            g10 = lambda t: sum(hist[t][-10:]) / len(hist[t][-10:])
            gall = lambda t: sum(hist[t]) / len(hist[t])
            samples.append((g10(h) - g10(a), gall(h) - gall(a), hg - ag, min(nh, na)))
        hist[h].append(hg - ag)
        hist[a].append(ag - hg)

    n = len(samples)
    print(f'可评估样本: {n} 场（两队历史均 ≥{MIN_HIST} 场）')
    if n < 100:
        print('样本不足，结论不可靠')
        return

    d10 = [s[0] for s in samples]
    dall = [s[1] for s in samples]
    gd = [s[2] for s in samples]

    print('\n=== Q1 单变量预测力（目标 = 主队实际净胜球）===')
    print(f'  近10场状态差 d10 : Pearson r = {pearson(d10, gd):+.4f}')
    print(f'  长期战绩差 dall  : Pearson r = {pearson(dall, gd):+.4f}')
    print(f'  d10 与 dall 共线性: r = {pearson(d10, dall):+.4f}  (越接近 1 → 长期信息越冗余)')

    # 网格搜索混合权重: Δ = α·d10 + (1-α)·dall
    print('\n=== Q2 混合权重网格搜索 Δ = α·d10 + (1-α)·dall ===')
    best = None
    for i in range(0, 21):
        alpha = i / 20
        mix = [alpha * a + (1 - alpha) * b for a, b in zip(d10, dall)]
        # 用最小二乘拟合 gd = k·Δ 后的 MSE（缩放不影响 r，用 r 与 MSE 双指标）
        r = pearson(mix, gd)
        # 方向命中率（胜/平/负三分类）
        hit = sum(1 for m, g in zip(mix, gd)
                  if (m > 0.15 and g > 0) or (abs(m) <= 0.15 and g == 0) or (m < -0.15 and g < 0))
        acc = hit / n
        mse = sum((g - m) ** 2 for m, g in zip(mix, gd)) / n  # 未校准的 MSE
        if best is None or r > best[1]:
            best = (alpha, r, acc, mse)
        if i % 4 == 0 or alpha in (0.0, 1.0):
            print(f'  α={alpha:.2f}  r={r:+.4f}  方向命中={acc*100:.2f}%  rawMSE={mse:.3f}')
    print(f'\n  最优 α = {best[0]:.2f} (r={best[1]:+.4f}, 方向命中 {best[2]*100:.2f}%)')

    # Q1 核心：分层检验 —— 在 d10 相近的桶内，dall 是否仍有单调效应
    print('\n=== Q1 分层检验：控制近期状态 d10 后，长期战绩 dall 是否仍有增量 ===')
    order = sorted(range(n), key=lambda i: d10[i])
    q = n // 5
    buckets = [order[i * q:(i + 1) * q] for i in range(4)] + [order[4 * q:]]
    tot_effect = []
    for bi, bk in enumerate(buckets):
        if len(bk) < 40:
            continue
        sub = sorted(bk, key=lambda i: dall[i])
        half = len(sub) // 2
        lo = sub[:half]          # 长期战绩较差的一半
        hi = sub[len(sub) - half:]  # 长期战绩较好的一半
        gd_lo = sum(gd[i] for i in lo) / len(lo)
        gd_hi = sum(gd[i] for i in hi) / len(hi)
        win_lo = sum(1 for i in lo if gd[i] > 0) / len(lo)
        win_hi = sum(1 for i in hi if gd[i] > 0) / len(hi)
        d10_avg = sum(d10[i] for i in bk) / len(bk)
        tot_effect.append((gd_hi - gd_lo, len(bk)))
        print(f'  桶{bi+1} (n={len(bk):4d}, d10均值={d10_avg:+.2f}): '
              f'长期强 主净胜球 {gd_hi:+.3f} / 主胜率 {win_hi*100:.1f}%  vs  '
              f'长期弱 {gd_lo:+.3f} / {win_lo*100:.1f}%   差 = {gd_hi-gd_lo:+.3f} 球')
    if tot_effect:
        avg = sum(e * w for e, w in tot_effect) / sum(w for _, w in tot_effect)
        print(f'\n  加权平均增量效应: {avg:+.3f} 球/场')
        if abs(avg) < 0.05:
            print('  → 结论：控制近期状态后，长期战绩几乎无增量（|效应| < 0.05 球）')
        else:
            print('  → 结论：控制近期状态后，长期战绩仍有可测增量')

    # 窗口扫描：找到最优历史窗口 / 时间衰减
    print('\n=== Q3 历史窗口扫描（强度差 → 主队净胜球）===')
    print(f'  {"窗口":<12}{"n":<7}{"r":<10}{"方向命中":<10}{"rawMSE"}')
    for N in (5, 10, 15, 20, 30, 50, 10 ** 9):
        hist3 = collections.defaultdict(list)
        S = []
        for date, h, a, hg, ag, lg in rows:
            if len(hist3[h]) >= MIN_HIST and len(hist3[a]) >= MIN_HIST:
                g = lambda t, N=N: sum(hist3[t][-N:]) / len(hist3[t][-N:])
                S.append((g(h) - g(a), hg - ag))
            hist3[h].append(hg - ag)
            hist3[a].append(ag - hg)
        xs = [s[0] for s in S]
        ys = [s[1] for s in S]
        hit = sum(1 for m, g in zip(xs, ys)
                  if (m > 0.15 and g > 0) or (abs(m) <= 0.15 and g == 0) or (m < -0.15 and g < 0))
        label = '全部历史' if N > 1000 else f'近{N}场'
        print(f'  {label:<12}{len(S):<7}{pearson(xs, ys):<+10.4f}{hit/len(S)*100:<10.2f}'
              f'{sum((g-m)**2 for m, g in zip(xs, ys))/len(S):.3f}')

    print('\n=== Q4 时间衰减 EWMA 扫描（α 越大越看重近期）===')
    print(f'  {"α":<8}{"≈半衰期(场)":<14}{"r":<10}{"方向命中":<10}{"rawMSE"}')
    for alpha in (0.03, 0.05, 0.08, 0.12, 0.20, 0.35):
        hist4 = collections.defaultdict(list)
        S = []

        def ewma(seq, a=alpha):
            tot, w = 0.0, 0.0
            for i in range(len(seq) - 1, -1, -1):
                tot += seq[i] * w if i < len(seq) - 1 else seq[i]
                w = w * (1 - a) + a if i < len(seq) - 1 else a
                if i < len(seq) - 1:
                    pass
            # 标准 EWMA：从最近往旧走
            s, ww = 0.0, 0.0
            for v in reversed(seq):
                s += v * ww
                ww = ww * (1 - a) + a if ww > 0 else a * 0  # placeholder
            return s

        def ewma_ok(seq, a=alpha):
            # s_t = a*x_t + (1-a)*s_{t-1}，从旧到新
            s = 0.0
            first = True
            for v in seq:
                s = v if first else a * v + (1 - a) * s
                first = False
            return s

        for date, h, a, hg, ag, lg in rows:
            if len(hist4[h]) >= MIN_HIST and len(hist4[a]) >= MIN_HIST:
                S.append((ewma_ok(hist4[h], alpha) - ewma_ok(hist4[a], alpha), hg - ag))
            hist4[h].append(hg - ag)
            hist4[a].append(ag - hg)
        xs = [s[0] for s in S]
        ys = [s[1] for s in S]
        hit = sum(1 for m, g in zip(xs, ys)
                  if (m > 0.15 and g > 0) or (abs(m) <= 0.15 and g == 0) or (m < -0.15 and g < 0))
        half = round(math.log(0.5) / math.log(1 - alpha), 1)
        print(f'  {alpha:<8}{half:<14}{pearson(xs, ys):<+10.4f}{hit/len(S)*100:<10.2f}'
              f'{sum((g-m)**2 for m, g in zip(xs, ys))/len(S):.3f}')

    # 分赛事（重点看欧冠）
    print('\n=== 分赛事：欧冠/欧罗巴 子样本 ===')
    hist2 = collections.defaultdict(list)
    sub_by_lg = collections.defaultdict(list)
    rows2 = load_rows()
    for date, h, a, hg, ag, lg in rows2:
        if len(hist2[h]) >= MIN_HIST and len(hist2[a]) >= MIN_HIST:
            g10 = lambda t: sum(hist2[t][-10:]) / len(hist2[t][-10:])
            gall = lambda t: sum(hist2[t]) / len(hist2[t])
            sub_by_lg[lg].append((g10(h) - g10(a), gall(h) - gall(a), hg - ag))
        hist2[h].append(hg - ag)
        hist2[a].append(ag - hg)
    for lg in ('欧冠', '欧罗巴', '英超', '西甲'):
        s = sub_by_lg.get(lg) or []
        if len(s) < 30:
            print(f'  {lg:<6} n={len(s):<4} 样本不足')
            continue
        a10 = [x[0] for x in s]
        aall = [x[1] for x in s]
        agd = [x[2] for x in s]
        print(f'  {lg:<6} n={len(s):<4} r(d10)={pearson(a10, agd):+.3f}  r(dall)={pearson(aall, agd):+.3f}')


if __name__ == '__main__':
    main()
