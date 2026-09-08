# -*- coding: utf-8 -*-
"""
引擎「第一步基础λ」的窗口/衰减参数扫描（纯 python，无第三方依赖）

背景：pedigree_eval.py 发现长期战绩窗口（20~30 场）优于近 10 场。
本脚本直接优化引擎真实的损失函数：泊松对数似然
    logL = log P(hg | λ_home) + log P(ag | λ_away)
其中 λ 完全按引擎第一步公式计算：
    λ_home = (h_gf*0.75 + a_ga*0.25) * 1.15
    λ_away = (a_gf*0.75 + h_ga*0.25) * 0.90
扫描：历史窗口 N × 指数衰减 DECAY

用法: python window_sweep.py
"""
import json
import math
import collections
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, 'results_data.json')
MIN_HIST = 5
HOME_BOOST, AWAY_DISCOUNT = 1.15, 0.90


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
        rows.append((date, v.get('home', ''), v.get('away', ''), hg, ag))
    rows.sort(key=lambda r: r[0])
    return rows


def logfact(n):
    return math.lgamma(n + 1)


def poisson_loglik(hg, ag, lh, la):
    """泊松对数似然（忽略与参数无关的常数项 -log(hg!)-log(ag!) 也计入，便于比较）"""
    if lh <= 0.02 or la <= 0.02:
        return -50.0
    return (-lh + hg * math.log(lh) - logfact(hg)
            - la + ag * math.log(la) - logfact(ag))


def wavg(vals, decay):
    """引擎同款：vals[0] 为最近一场，权重 decay^i"""
    w = [decay ** i for i in range(len(vals))]
    return sum(v * wi for v, wi in zip(vals, w)) / sum(w)


def evaluate(rows, N, decay):
    gf = collections.defaultdict(list)  # team -> [进球, ...] 由新到旧
    ga = collections.defaultdict(list)
    ll = 0.0
    sq = 0.0
    n = 0
    for date, h, a, hg, ag in rows:
        if len(gf[h]) >= MIN_HIST and len(gf[a]) >= MIN_HIST:
            h_gf = wavg(gf[h][:N], decay)
            h_ga = wavg(ga[h][:N], decay)
            a_gf = wavg(gf[a][:N], decay)
            a_ga = wavg(ga[a][:N], decay)
            lh = (h_gf * 0.75 + a_ga * 0.25) * HOME_BOOST
            la = (a_gf * 0.75 + h_ga * 0.25) * AWAY_DISCOUNT
            ll += poisson_loglik(hg, ag, lh, la)
            sq += (hg - lh) ** 2 + (ag - la) ** 2
            n += 1
        gf[h].insert(0, hg)
        ga[h].insert(0, ag)
        gf[a].insert(0, ag)
        ga[a].insert(0, hg)
    return ll, ll / n, sq / (2 * n), n


def main():
    rows = load_rows()
    print(f'载入 {len(rows)} 场')
    print('\n扫描 历史窗口 N × 衰减 DECAY（目标：泊松对数似然，越大越好）')
    print(f'{"N":<6}{"DECAY":<8}{"总logL":<14}{"场均logL":<12}{"进球MSE"}')
    results = []
    for N in (5, 8, 10, 15, 20, 25, 30, 40, 60):
        for decay in (0.80, 0.85, 0.90, 0.95, 1.00):
            tot, per, mse, n = evaluate(rows, N, decay)
            results.append((per, N, decay, tot, mse, n))
            print(f'{N:<6}{decay:<8.2f}{tot:<14.1f}{per:<12.4f}{mse:.4f}')
    results.sort(reverse=True)
    print('\n=== TOP 5 组合 ===')
    for per, N, decay, tot, mse, n in results[:5]:
        eff = sum(decay ** i for i in range(200))  # 有效样本量
        print(f'  N={N:<3} DECAY={decay:<5.2f} 场均logL={per:.4f}  MSE={mse:.4f}  有效样本≈{eff:.1f}场')
    # 现行参数基线
    base = [r for r in results if r[1] == 10 and abs(r[2] - 0.85) < 1e-9][0]
    best = results[0]
    print(f'\n现行 (N=10, DECAY=0.85): 场均logL={base[0]:.4f}  MSE={base[4]:.4f}')
    print(f'最优 (N={best[1]}, DECAY={best[2]:.2f}): 场均logL={best[0]:.4f}  MSE={best[4]:.4f}')
    print(f'改进: ΔlogL={best[0]-base[0]:+.4f}/场 ({(best[0]-base[0])/abs(base[0])*100:+.2f}%), '
          f'ΔMSE={best[4]-base[4]:+.4f}')


if __name__ == '__main__':
    main()
