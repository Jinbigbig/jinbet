"""比分精选榜头条口径 A/B：复用生产回放（selection_algo.pk_dist + 历史快照 + 实际赛果）。

比较：
  raw   本板块自身分布 argmax（现状 → 均衡场次恒 1:1）
  rule  同一份分布，但套用「倾向象限内优选」头条口径（与报告 4.2 / 卡片同规则）

指标：头条命中 / 双档命中 / 头条 1:1 占比 / 头条与象限矛盾占比。
用法：python pk_head_probe.py
"""
import collections

try:                       # 工作盘用下划线前缀，master 正本去前缀
    import _optimize_selection as O
except ImportError:
    import optimize_selection as O
import selection_algo as SA

TODAY = '2026-09-19'
DAYS = O._collect_days(TODAY)


def rule_pick(cells, okey, gap=5.0):
    """cells = [(score, prob%)...] 概率降序；套用倾向象限内优选。"""
    def q(s):
        h, a = (int(x) for x in s.split(':'))
        return 'home' if h > a else ('away' if a > h else 'draw')

    if len(cells) < 2:
        return cells[0]
    s0, p0 = cells[0]
    if q(s0) != 'draw':
        return cells[0]
    if okey == 'draw':
        return cells[0]
    want = okey if okey in ('home', 'away') else None
    cands = [c for c in cells[1:] if (q(c[0]) == want if want else q(c[0]) != 'draw')]
    if not cands:
        return cells[0]
    b = max(cands, key=lambda c: c[1])
    return b if (p0 - b[1]) < gap else cells[0]


stat = collections.Counter()
stat_band = collections.Counter()
contra = collections.Counter()
one_one = collections.Counter()
tot = collections.Counter()
n_days = 0
for rows in DAYS:
    n_days += 1
    for m, act in rows:
        cells = sorted(((s, round(p * 100, 1)) for s, p in SA.pk_dist(m).items()), key=lambda x: -x[1])
        if not cells:
            continue
        dk = SA.direction_key(m)
        pick_raw = cells[0][0]
        pick_rule = rule_pick(cells, dk)[0]
        band_raw = [s for s, _ in cells[1:3]]
        band_rule = [s for s, _ in cells if s != pick_rule][:2]
        tot['n'] += 1
        for name, pick, band in (('raw', pick_raw, band_raw), ('rule', pick_rule, band_rule)):
            if act == pick:
                stat[name] += 1
            elif act in band:
                stat_band[name] += 1
            if pick == '1:1':
                one_one[name] += 1
        if pick_rule != pick_raw:
            contra['changed'] += 1

n = tot['n']
print(f'回放天数={n_days}  场次={n}')
for name in ('raw', 'rule'):
    print(f'  {name:4s} 头条命中 {stat[name] / n * 100:.2f}%  双档命中 {stat_band[name] / n * 100:.2f}%  '
          f'合计 {(stat[name] + stat_band[name]) / n * 100:.2f}%  头条1:1占比 {one_one[name] / n * 100:.0f}%')
print(f'  口径改动场次 {contra["changed"]}/{n} = {contra["changed"] / n * 100:.0f}%')
