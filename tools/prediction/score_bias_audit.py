#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
score_bias_audit.py — 预测比分/λ 与实际赛果的全量对账审计

用途：回答「模型总进球是否系统性偏差、比分预测是否信息量过低」。
数据源：predictions/<date>/pred_snapshot.json（真实 λ 与比分）+ results_data.json（赛果）
输出：逐日偏差表、月度汇总、比分选择模式对照（top1 / 象限首选 / 全局众数 / argmax）

用法：
    python score_bias_audit.py                # 全量汇总
    python score_bias_audit.py --detail       # 追加逐日明细
"""
import json
import os
import sys
import glob
import collections

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_results():
    with open(os.path.join(ROOT, 'results_data.json'), encoding='utf-8') as f:
        return json.load(f)


def parse_score(s):
    try:
        a, b = str(s).split(':')
        return int(a), int(b)
    except Exception:
        return None


def load_days():
    days = {}
    for d in sorted(glob.glob(os.path.join(ROOT, 'predictions', '20*'))):
        snap = os.path.join(d, 'pred_snapshot.json')
        if not os.path.exists(snap):
            continue
        date = os.path.basename(d)
        try:
            with open(snap, encoding='utf-8') as f:
                days[date] = json.load(f)['matches']
        except Exception as e:
            print(f'  [跳过] {date}: {e}')
    return days


def best_score_in_quadrant(m):
    """象限内最可能比分（报告头条 = 方向首选）"""
    ph, pd, pa = m['prob_home'], m['prob_draw'], m['prob_away']
    if ph >= pd and ph >= pa:
        q = 'home'
    elif pa >= pd:
        q = 'away'
    else:
        q = 'draw'
    return m.get('quad_top', {}).get(q, {}).get('score'), q


def main():
    detail = '--detail' in sys.argv
    results = load_results()
    days = load_days()

    print(f'快照天数: {len(days)}  ({min(days)} ~ {max(days)})')
    print('=' * 96)

    rows = []
    for date in sorted(days):
        n = n_match = 0
        lam_sum = act_sum = 0.0
        hit_dir = hit_top1 = hit_quad = hit_top3 = hit_top5 = 0
        pick_counter = collections.Counter()
        miss_detail = []
        for m in days[date]:
            n += 1
            key = f"{date}_{m['home']}_{m['away']}"
            res = results.get(key)
            if not res:
                continue
            sc = parse_score(res.get('fullScore'))
            if not sc:
                continue
            n_match += 1
            h, a = sc
            actual_total = h + a
            lam_sum += m.get('lam_total', 0)
            act_sum += actual_total

            # 方向
            if h > a:
                act_dir = 'home'
            elif h < a:
                act_dir = 'away'
            else:
                act_dir = 'draw'
            ph, pd, pa = m['prob_home'], m['prob_draw'], m['prob_away']
            if ph >= pd and ph >= pa:
                mod_dir = 'home'
            elif pa >= pd:
                mod_dir = 'away'
            else:
                mod_dir = 'draw'
            if mod_dir == act_dir:
                hit_dir += 1

            top1 = m.get('top_score')
            quad, _ = best_score_in_quadrant(m)
            tops = [t['score'] for t in m.get('top_scores', [])]
            actual_s = f'{h}:{a}'
            if top1 == actual_s:
                hit_top1 += 1
            if quad == actual_s:
                hit_quad += 1
            if actual_s in tops[:3]:
                hit_top3 += 1
            if actual_s in tops[:5]:
                hit_top5 += 1
            pick_counter[f'{top1}|{quad}'] += 1
            miss_detail.append((m['id'], m['home'], m['away'], top1, quad, actual_s,
                                round(m.get('lam_total', 0), 2), actual_total))

        if n_match == 0:
            rows.append((date, n, 0, None, None, None, None, None, None, None, []))
            continue
        rows.append((
            date, n, n_match,
            lam_sum / n_match, act_sum / n_match, (lam_sum - act_sum) / n_match,
            hit_dir / n_match, hit_top1 / n_match, hit_quad / n_match,
            (hit_top3 / n_match, hit_top5 / n_match),
            miss_detail,
        ))

    # 表头
    print(f"{'日期':<12}{'场':>4}{'命中':>5}{'预测λ和':>9}{'实际和':>8}{'偏差':>8}"
          f"{'方向':>7}{'top1':>7}{'象限':>7}{'top3':>7}{'top5':>7}")
    print('-' * 96)
    tot = collections.defaultdict(float)
    totn = 0
    for r in rows:
        date, n, nm, lp, ap, bias, d1, t1, q1, t35, misses = r
        if nm == 0:
            print(f'{date:<12}{n:>4}{0:>5}   (无赛果)')
            continue
        t3, t5 = t35
        print(f'{date:<12}{n:>4}{nm:>5}{lp:>9.2f}{ap:>8.2f}{bias:>+8.2f}'
              f'{d1*100:>6.0f}%{t1*100:>6.0f}%{q1*100:>6.0f}%{t3*100:>6.0f}%{t5*100:>6.0f}%')
        tot['lam'] += lp * nm
        tot['act'] += ap * nm
        tot['dir'] += d1 * nm
        tot['t1'] += t1 * nm
        tot['q'] += q1 * nm
        tot['t3'] += t3 * nm
        tot['t5'] += t5 * nm
        totn += nm

    if totn:
        print('-' * 96)
        print(f"{'合计/均值':<12}{totn:>4}{totn:>5}{tot['lam']/totn:>9.2f}{tot['act']/totn:>8.2f}"
              f"{(tot['lam']-tot['act'])/totn:>+8.2f}{tot['dir']/totn*100:>6.0f}%"
              f"{tot['t1']/totn*100:>6.0f}%{tot['q']/totn*100:>6.0f}%"
              f"{tot['t3']/totn*100:>6.0f}%{tot['t5']/totn*100:>6.0f}%")

    # 月度
    print()
    print('=== 按月汇总 ===')
    mon = collections.defaultdict(lambda: collections.defaultdict(float))
    monn = collections.Counter()
    for r in rows:
        date, n, nm, lp, ap, bias, d1, t1, q1, t35, misses = r
        if nm == 0:
            continue
        mk = date[:7]
        monn[mk] += nm
        mon[mk]['lam'] += lp * nm
        mon[mk]['act'] += ap * nm
        mon[mk]['dir'] += d1 * nm
        mon[mk]['q'] += q1 * nm
        mon[mk]['t1'] += t1 * nm
    for mk in sorted(mon):
        nn = monn[mk]
        print(f"{mk}  {nn:>4}场  λ和 {mon[mk]['lam']/nn:.2f} vs 实际 {mon[mk]['act']/nn:.2f} "
              f"偏差 {(mon[mk]['lam']-mon[mk]['act'])/nn:+.2f}  方向 {mon[mk]['dir']/nn*100:.0f}%  "
              f"象限比分 {mon[mk]['q']/nn*100:.0f}%  top1 {mon[mk]['t1']/nn*100:.0f}%")

    # 比分选择模式分布
    print()
    print('=== 当日报告头条比分选择分布（top_score|象限首选）===')
    for date in sorted(days)[-8:]:
        picks = []
        for m in days[date]:
            quad, _ = best_score_in_quadrant(m)
            picks.append(f"{m.get('top_score')}|{quad}")
        cnt = collections.Counter(picks)
        top = '  '.join(f'{k}×{v}' for k, v in cnt.most_common(6))
        print(f'{date}: {top}')
        one_one = sum(1 for p in picks if p.startswith('1:1'))
        print(f'          1:1 占比 {one_one}/{len(picks)} = {one_one/len(picks)*100:.0f}%')

    if detail:
        print()
        print('=== 逐日失手明细（最近5日）===')
        for r in rows[-5:]:
            date, n, nm, lp, ap, bias, d1, t1, q1, t35, misses = r
            if nm == 0:
                continue
            print(f'\n[{date}] 偏差 {bias:+.2f}')
            for (mid, h, a, top1, quad, actual, lam, atot) in misses:
                flag = '✅' if quad == actual else ('△' if top1 == actual else '✗')
                print(f'  {flag} {mid} {h}vs{a}: 头条 {quad} / 众数 {top1} → 实际 {actual} (λ和{lam} vs {atot})')


if __name__ == '__main__':
    main()
