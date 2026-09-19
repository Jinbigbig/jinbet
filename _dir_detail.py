# -*- coding: utf-8 -*-
"""逐场方向（1X2）命中明细：近 N 天每场预测 vs 实际。"""
import os, sys, glob, json, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import selection_algo as SA
from daily_diag import load_days, parse

CN = {'home': '主胜', 'draw': '平局', 'away': '客胜'}


def main():
    days = load_days('2026-09-18', 10)
    allrows = []
    for date, rows in days:
        for m, act in rows:
            h, a = parse(act)
            rk = 'home' if h > a else ('away' if a > h else 'draw')
            pk = SA.direction_key(m)
            pr = SA.prob1x2(m)
            od = m.get('odds') or {}
            allrows.append(dict(date=date, lg=m.get('league', ''), home=m.get('home'), away=m.get('away'),
                                pick=pk, actual=rk, score=act, hit=pk == rk,
                                mg=max(pr, key=pr.get), marg=round(pr.get(max(pr, key=pr.get), 0), 1),
                                ph=round(pr.get('home', 0), 1), pd=round(pr.get('draw', 0), 1), pa=round(pr.get('away', 0), 1),
                                o_h=od.get('胜'), o_d=od.get('平'), o_a=od.get('负'),
                                stars=m.get('stars')))
    n = len(allrows)
    hit = sum(r['hit'] for r in allrows)
    print('窗口 %s → %s  %d 天  %d 场' % (days[0][0], days[-1][0], len(days), n))
    print('方向命中 %d/%d = %.1f%%' % (hit, n, hit / n * 100))
    print()
    print('=== 逐日 ===')
    for date, rows in days:
        sub = [r for r in allrows if r['date'] == date]
        h = sum(r['hit'] for r in sub)
        print('%s  %2d/%2d = %5.1f%%' % (date, h, len(sub), h / len(sub) * 100))
    print()
    print('=== 按预测方向拆解 ===')
    for k in ('home', 'draw', 'away'):
        sub = [r for r in allrows if r['pick'] == k]
        if not sub:
            continue
        h = sum(r['hit'] for r in sub)
        print('  预测%-3s %2d 场，命中 %2d = %5.1f%%' % (CN[k], len(sub), h, h / len(sub) * 100))
    print()
    print('=== 按实际结果拆解（模型抓到了吗）===')
    for k in ('home', 'draw', 'away'):
        sub = [r for r in allrows if r['actual'] == k]
        if not sub:
            continue
        h = sum(r['hit'] for r in sub)
        print('  实际%-3s %2d 场，预测中 %2d = %5.1f%%' % (CN[k], len(sub), h, h / len(sub) * 100))
    print()
    print('=== 按把握度（最大概率）分档 ===')
    for lo, hi in ((0, 40), (40, 50), (50, 60), (60, 100)):
        sub = [r for r in allrows if lo <= r['marg'] < hi]
        if not sub:
            continue
        h = sum(r['hit'] for r in sub)
        print('  %2d%%~%2d%%  %2d 场，命中 %2d = %5.1f%%' % (lo, hi, len(sub), h, h / len(sub) * 100))
    print()
    print('=== 错判明细（%d 场）===' % (n - hit))
    for r in allrows:
        if r['hit']:
            continue
        print('  %s %-8s %s vs %s  预测%s(%.0f%%)  实际%s %s' %
              (r['date'][5:], r['lg'][:8], r['home'], r['away'], CN[r['pick']], r['marg'], CN[r['actual']], r['score']))
    json.dump(allrows, open(os.path.join(HERE, '_dir_rows.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print()
    print('已写出 _dir_rows.json')


if __name__ == '__main__':
    main()
