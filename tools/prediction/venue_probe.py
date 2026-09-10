# -*- coding: utf-8 -*-
"""
主场/客场维度的基础λ可行性探测（纯 python，无第三方依赖）

背景（用户提议）：H2H 除历史对战进球外，还应区分「作为主队/客队」时的进球与失球能力。
本脚本回答两件事：
  A. 数据可行性：各队分主客的历史场次有多少？「同一主客方向」的 H2H 有多少样本？
  B. 收益验证：把基础λ从「不分主客的近25场 gf/ga + 固定主客系数」
     改为「分主客场观测 + 向现行估计量收缩」，泊松对数似然是否改善？

现行（baseline）：
    λ_home = (h_gf_all*0.75 + a_ga_all*0.25) * 1.15
    λ_away = (a_gf_all*0.75 + h_ga_all*0.25) * 0.90
候选（venue，λ 层经验贝叶斯收缩）：
    λ_home_venue = h_gf_HOME*0.75 + a_ga_AWAY*0.25      # 观测已含主客效应，不再乘系数
    λ_home = (n_eff*λ_home_venue + K*λ_home_base) / (n_eff + K)
"""
import json
import math
import collections
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# 兼容两种位置：仓库根 或 tools/prediction/（向上查找 results_data.json）
ROOT = HERE
for _ in range(3):
    if os.path.exists(os.path.join(ROOT, 'results_data.json')):
        break
    ROOT = os.path.dirname(ROOT)
RES = os.path.join(ROOT, 'results_data.json')
MIN_HIST = 5
HOME_BOOST, AWAY_DISCOUNT = 1.15, 0.90
DECAY = 0.96
N_WIN = 25


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
    if lh <= 0.02 or la <= 0.02:
        return -50.0
    return (-lh + hg * math.log(lh) - logfact(hg)
            - la + ag * math.log(la) - logfact(ag))


def wavg(vals, decay=DECAY):
    if not vals:
        return None
    w = [decay ** i for i in range(len(vals))]
    return sum(v * wi for v, wi in zip(vals, w)) / sum(w)


def eff_n(n, decay=DECAY):
    """指数衰减下的有效样本量 = Σ decay^i"""
    return sum(decay ** i for i in range(n))


def availability(rows):
    """A. 数据可行性统计"""
    gf_all = collections.defaultdict(list)
    ga_all = collections.defaultdict(list)
    gf_H = collections.defaultdict(list)   # 该队作为主队时的进球
    ga_H = collections.defaultdict(list)
    gf_A = collections.defaultdict(list)   # 该队作为客队时的进球
    ga_A = collections.defaultdict(list)
    pair_hist = collections.defaultdict(list)  # frozenset -> [(date, host, hg, ag)]

    h2h_any, h2h_same = [], []
    home_n, away_n = [], []

    for date, h, a, hg, ag in rows:
        if len(gf_all[h]) >= MIN_HIST and len(gf_all[a]) >= MIN_HIST:
            pn = frozenset((h, a))
            hist = pair_hist[pn]
            h2h_any.append(len(hist))
            same = sum(1 for d, host, x, y in hist if host == h)
            h2h_same.append(same)
            home_n.append(len(gf_H[h]))
            away_n.append(len(gf_A[a]))

        pair_hist[frozenset((h, a))].append((date, h, hg, ag))
        gf_all[h].insert(0, hg); ga_all[h].insert(0, ag)
        gf_all[a].insert(0, ag); ga_all[a].insert(0, hg)
        gf_H[h].insert(0, hg); ga_H[h].insert(0, ag)
        gf_A[a].insert(0, ag); ga_A[a].insert(0, hg)

    def dist(vals, thresholds):
        n = len(vals)
        return {f'≥{t}': sum(1 for v in vals if v >= t) / n for t in thresholds}

    print('=' * 62)
    print('A. 数据可行性（样本 = 满足双方均有≥5场历史后的每场比赛）')
    print('=' * 62)
    print(f'可评估场次: {len(h2h_any)}')
    print(f'各队「作为主队」历史场次: 均值 {sum(home_n)/len(home_n):.1f} '
          f'中位 {sorted(home_n)[len(home_n)//2]}')
    print(f'各队「作为客队」历史场次: 均值 {sum(away_n)/len(away_n):.1f} '
          f'中位 {sorted(away_n)[len(away_n)//2]}')
    print()
    print('H2H 样本量分布（占比）:')
    print('  任意主客方向 (现行门槛≥3):', dist(h2h_any, (1, 2, 3, 5)))
    print('  同一主客方向 (新提议)   :', dist(h2h_same, (1, 2, 3, 5)))
    return h2h_any, h2h_same


def evaluate(rows, K=None):
    """
    K=None → 现行 baseline；K=数值 → venue 版本，λ 层收缩强度 K（有效样本量口径）
    """
    gf_all = collections.defaultdict(list)
    ga_all = collections.defaultdict(list)
    gf_H = collections.defaultdict(list)
    ga_H = collections.defaultdict(list)
    gf_A = collections.defaultdict(list)
    ga_A = collections.defaultdict(list)

    ll = sq = 0.0
    n = 0
    tot_goals = pred_goals = 0.0

    for date, h, a, hg, ag in rows:
        if len(gf_all[h]) >= MIN_HIST and len(gf_all[a]) >= MIN_HIST:
            h_gf = wavg(gf_all[h][:N_WIN])
            h_ga = wavg(ga_all[h][:N_WIN])
            a_gf = wavg(gf_all[a][:N_WIN])
            a_ga = wavg(ga_all[a][:N_WIN])
            lh = (h_gf * 0.75 + a_ga * 0.25) * HOME_BOOST
            la = (a_gf * 0.75 + h_ga * 0.25) * AWAY_DISCOUNT

            if K is not None:
                h_gf_H = wavg(gf_H[h][:N_WIN])
                a_ga_A = wavg(ga_A[a][:N_WIN])
                a_gf_A = wavg(gf_A[a][:N_WIN])
                h_ga_H = wavg(ga_H[h][:N_WIN])
                if h_gf_H is not None and a_ga_A is not None:
                    lh_v = h_gf_H * 0.75 + a_ga_A * 0.25
                    ne = min(eff_n(len(gf_H[h][:N_WIN])), eff_n(len(ga_A[a][:N_WIN])))
                    lh = (ne * lh_v + K * lh) / (ne + K)
                if a_gf_A is not None and h_ga_H is not None:
                    la_v = a_gf_A * 0.75 + h_ga_H * 0.25
                    ne = min(eff_n(len(gf_A[a][:N_WIN])), eff_n(len(ga_H[h][:N_WIN])))
                    la = (ne * la_v + K * la) / (ne + K)

            ll += poisson_loglik(hg, ag, lh, la)
            sq += (hg - lh) ** 2 + (ag - la) ** 2
            n += 1
            tot_goals += hg + ag
            pred_goals += lh + la

        gf_all[h].insert(0, hg); ga_all[h].insert(0, ag)
        gf_all[a].insert(0, ag); ga_all[a].insert(0, hg)
        gf_H[h].insert(0, hg); ga_H[h].insert(0, ag)
        gf_A[a].insert(0, ag); ga_A[a].insert(0, hg)

    return ll / n, sq / (2 * n), n, pred_goals / tot_goals


def evaluate_scaled(rows, K=None):
    """
    公平对照：先拟合一个「全局缩放因子」把 λ 总量校准到无偏，再比 logL。
    目的：排除「venue 版本只是顺带修正了 baseline 2.3% 的高估」这一替代解释
         （引擎后续本就有 EWMA 动态校准，若增益全部来自偏差修正则会被重复计算）。
    """
    _, _, n, ratio = evaluate(rows, K=K)
    s = 1.0 / ratio
    gf_all = collections.defaultdict(list)
    ga_all = collections.defaultdict(list)
    gf_H = collections.defaultdict(list)
    ga_H = collections.defaultdict(list)
    gf_A = collections.defaultdict(list)
    ga_A = collections.defaultdict(list)
    ll = 0.0
    n = 0
    for date, h, a, hg, ag in rows:
        if len(gf_all[h]) >= MIN_HIST and len(gf_all[a]) >= MIN_HIST:
            h_gf = wavg(gf_all[h][:N_WIN]); h_ga = wavg(ga_all[h][:N_WIN])
            a_gf = wavg(gf_all[a][:N_WIN]); a_ga = wavg(ga_all[a][:N_WIN])
            lh = (h_gf * 0.75 + a_ga * 0.25) * HOME_BOOST
            la = (a_gf * 0.75 + h_ga * 0.25) * AWAY_DISCOUNT
            if K is not None:
                h_gf_H = wavg(gf_H[h][:N_WIN]); a_ga_A = wavg(ga_A[a][:N_WIN])
                a_gf_A = wavg(gf_A[a][:N_WIN]); h_ga_H = wavg(ga_H[h][:N_WIN])
                if h_gf_H is not None and a_ga_A is not None:
                    lh_v = h_gf_H * 0.75 + a_ga_A * 0.25
                    ne = min(eff_n(len(gf_H[h][:N_WIN])), eff_n(len(ga_A[a][:N_WIN])))
                    lh = (ne * lh_v + K * lh) / (ne + K)
                if a_gf_A is not None and h_ga_H is not None:
                    la_v = a_gf_A * 0.75 + h_ga_H * 0.25
                    ne = min(eff_n(len(gf_A[a][:N_WIN])), eff_n(len(ga_H[h][:N_WIN])))
                    la = (ne * la_v + K * la) / (ne + K)
            ll += poisson_loglik(hg, ag, lh * s, la * s)
            n += 1
        gf_all[h].insert(0, hg); ga_all[h].insert(0, ag)
        gf_all[a].insert(0, ag); ga_all[a].insert(0, hg)
        gf_H[h].insert(0, hg); ga_H[h].insert(0, ag)
        gf_A[a].insert(0, ag); ga_A[a].insert(0, hg)
    return ll / n, s


def main():
    rows = load_rows()
    print(f'载入 {len(rows)} 场赛果\n')
    availability(rows)

    print()
    print('=' * 62)
    print('B. 基础λ：主场/客场分拆 + 经验贝叶斯收缩（walk-forward）')
    print('=' * 62)
    print(f'{"方案":<28}{"场均logL":<12}{"进球MSE":<12}{"λ/实际"}')
    base = evaluate(rows, K=None)
    print(f'{"现行 baseline":<28}{base[0]:<12.4f}{base[1]:<12.4f}{base[3]:.4f}  (n={base[2]})')

    results = []
    for K in (2, 4, 6, 8, 12, 16, 25, 40, 100):
        per, mse, n, ratio = evaluate(rows, K=K)
        results.append((per, K, mse, ratio, n))
        print(f'{"venue 收缩 K=" + str(K):<28}{per:<12.4f}{mse:<12.4f}{ratio:.4f}')

    results.sort(reverse=True)
    best = results[0]
    print()
    print(f'最优 K={best[1]}: 场均logL={best[0]:.4f} (baseline {base[0]:.4f}, '
          f'Δ={best[0]-base[0]:+.4f}/场, {(best[0]-base[0])/abs(base[0])*100:+.2f}%)')
    print(f'        进球MSE {base[1]:.4f} → {best[2]:.4f} ({best[2]-base[1]:+.4f})')

    # 时序稳健性：前后半段分开看
    half = len(rows) // 2
    print()
    print('=== 时序稳健性（前50% / 后50%）===')
    for name, sub in (('前半段', rows[:half]), ('后半段', rows[half:])):
        b = evaluate(sub, K=None)
        v = evaluate(sub, K=best[1])
        print(f'  {name}: baseline {b[0]:.4f} → venue {v[0]:.4f}  Δ={v[0]-b[0]:+.4f}')

    print()
    print('=== 公平对照：先做全局无偏校准，再比 logL ===')
    print('（排除「增益只来自修正 baseline 高估」的替代解释）')
    for K in (2, 4, 6, 8, 12):
        b_s = evaluate_scaled(rows, K=None)
        v_s = evaluate_scaled(rows, K=K)
        print(f'  K={K:<3} baseline {b_s[0]:.4f}(s={b_s[1]:.4f}) → '
              f'venue {v_s[0]:.4f}(s={v_s[1]:.4f})  Δ={v_s[0]-b_s[0]:+.4f}')


if __name__ == '__main__':
    main()
