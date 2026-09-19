# -*- coding: utf-8 -*-
"""JinBet 每日健康诊断（一条命令回答「最近预测准不准、是不是模型坏了」）。

用法：python daily_diag.py [--days 10] [--date 2026-09-18]

输出三件事：
  1) 逐日命中表（方向 / 单点 / 双档 / 两档）—— 与长期基准并列，判断是「样本波动」还是「模型漂移」
  2) 1X2 校准表（模型自称 vs 实际）—— 概率有没有系统性偏差
  3) 模型 vs 纯市场去水（1X2）—— 模型是否还有增量

判读口径（长期 walk-forward 基准，2478 场）：
  1X2 准确率 51.2%（市场去水 51.9%）· 比分单点 15.1% · 双档 24.0% · 前三累计 39.1% · 头条±1球 67.2%
  单日 11~16 场时，比分单点的合理波动区间是 0~4 场，连续两三天的 1/11 不代表模型失效。
"""
import os, sys, glob, json, argparse, collections, datetime, math

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import selection_algo as SA

LONG_RUN = {'acc': 51.2, 'single': 15.1, 'band': 24.0, 'top3': 39.1, 'near': 67.2,
            'mkt_acc': 51.9, 'n': 2478}


def parse(s):
    try:
        h, a = str(s).split(':')
        return int(h), int(a)
    except Exception:
        return None


def load_results():
    recs = {}
    for f in sorted(glob.glob(os.path.join(HERE, 'results_history', '*.json'))):
        if os.path.basename(f) == 'index.json':
            continue
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict):
                    recs.setdefault(k, v)
    try:
        rd = json.load(open(os.path.join(HERE, 'results_data.json'), encoding='utf-8'))
        for k, v in (rd or {}).items():
            if isinstance(v, dict):
                recs[k] = v
    except Exception:
        pass
    return recs


def lookup(recs, y, home, away):
    for key in (f'{y}_{home}_{away}', f'{y}_{away}_{home}'):
        rec = recs.get(key)
        if rec:
            s = rec.get('score') or rec.get('fullScore') or ''
            if isinstance(s, str) and ':' in s:
                return s
    return None


def load_days(today, days):
    recs = load_results()
    out = []
    for sp in sorted(glob.glob(os.path.join(HERE, 'predictions', '*', 'pred_snapshot.json'))):
        date = os.path.basename(os.path.dirname(sp))
        if date >= today:
            continue
        try:
            snap = json.load(open(sp, encoding='utf-8'))
        except Exception:
            continue
        rows = []
        for m in (snap.get('matches') or []):
            act = lookup(recs, date, m.get('home'), m.get('away'))
            if act and parse(act):
                nm = dict(m)
                nm.setdefault('cold', False)
                nm.setdefault('data_n', {})
                nm.setdefault('prob', {'home': m.get('prob_home', 0), 'draw': m.get('prob_draw', 0),
                                       'away': m.get('prob_away', 0)})
                rows.append((nm, act))
        if rows:
            out.append((date, rows))
    return out[-days:] if days else out


def section_daily(days):
    t = SA.load_tuning()
    print('=== 逐日命中 ===')
    print(f"{'日期':<12}{'场次':>4}{'方向':>9}{'单点':>9}{'双档':>9}{'精选档':>9}{'大胆档':>9}")
    agg = collections.Counter()
    for date, rows in days:
        n = len(rows)
        d_hit = s_hit = b_hit = 0
        scored = False
        for m, act in rows:
            a = parse(act)
            rk = 'home' if a[0] > a[1] else ('away' if a[1] > a[0] else 'draw')
            d_hit += SA.direction_key(m) == rk
            ts = [x['score'] for x in (m.get('top_scores') or []) if x.get('score')]
            if ts:
                scored = True
                s_hit += ts[0] == act
                b_hit += act in set(ts[1:3])
        amap = {}
        for m, a in rows:
            amap['%s|%s' % (m.get('home'), m.get('away'))] = a
        pk_t, _, bd_t, _, _ = SA.split_boards([m for m, _ in rows], t, SA.TIER_PK, SA.TIER_BD)
        pk = [x[1] for x in (pk_t[0] if pk_t else [])]
        bd = [x[1] for x in (bd_t[0] if bd_t else [])]
        pkh = sum(1 for m in pk if SA.pk_result(m, amap['%s|%s' % (m.get('home'), m.get('away'))], t) in ('hit', 'band'))
        bdh = sum(1 for m in bd if SA.bd_result(m, amap['%s|%s' % (m.get('home'), m.get('away'))], t) in ('scale', 'extreme'))
        flag = '' if scored else '  ← 快照无候选比分，单点/双档不可比'
        print(f"{date:<12}{n:>4}{d_hit:>5}/{n:<3}{s_hit:>5}/{n:<3}{b_hit:>5}/{n:<3}"
              f"{pkh:>5}/{len(pk):<3}{bdh:>5}/{len(bd):<3}{flag}")
        agg['n'] += n
        agg['d'] += d_hit
        if scored:
            agg['sn'] += n
            agg['s'] += s_hit
            agg['b'] += b_hit
        agg['pk'] += pkh
        agg['pkn'] += len(pk)
        agg['bd'] += bdh
        agg['bdn'] += len(bd)
    print()
    print(f"方向   {agg['d']}/{agg['n']} = {agg['d'] / agg['n'] * 100:.1f}%   "
          f"（长期 {LONG_RUN['acc']}% / 市场去水 {LONG_RUN['mkt_acc']}%）")
    if agg['sn']:
        print(f"单点   {agg['s']}/{agg['sn']} = {agg['s'] / agg['sn'] * 100:.1f}%   （长期 {LONG_RUN['single']}%）")
        print(f"双档   {agg['b']}/{agg['sn']} = {agg['b'] / agg['sn'] * 100:.1f}%   （长期 {LONG_RUN['band']}%）")
    print(f"比分精选第一档 {agg['pk']}/{agg['pkn']} = {agg['pk'] / max(1, agg['pkn']) * 100:.1f}%   "
          f"（等同「前三档累计」口径，长期 {LONG_RUN['top3']}%）")
    print(f"大胆档第一档   {agg['bd']}/{agg['bdn']} = {agg['bd'] / max(1, agg['bdn']) * 100:.1f}%")
    return agg


def section_calib(days):
    rows = [(m, a) for _, rs in days for m, a in rs]
    n = len(rows)
    print('\n=== 1X2 校准（模型自称 vs 实际）===')
    ap = [0, 0, 0]
    fp = [0.0, 0.0, 0.0]
    near = 0
    for m, a in rows:
        h, d = parse(a)
        rk = 0 if h > d else (2 if d > h else 1)
        ap[rk] += 1
        fp[0] += float(m.get('prob_home', 0)) / 100
        fp[1] += float(m.get('prob_draw', 0)) / 100
        fp[2] += float(m.get('prob_away', 0)) / 100
        ts = [x['score'] for x in (m.get('top_scores') or []) if x.get('score')]
        if ts:
            th, ta = parse(ts[0])
            near += (abs(th - h) <= 1 and abs(ta - d) <= 1)
    for i, name in enumerate(['主胜', '平局', '客胜']):
        print(f'  {name}  模型 {fp[i] / n * 100:5.1f}%   实际 {ap[i] / n * 100:5.1f}%   '
              f'差 {(fp[i] / n - ap[i] / n) * 100:+.1f}pp')
    print(f'  头条 ±1 球邻域命中 {near}/{n} = {near / n * 100:.1f}%（长期 {LONG_RUN["near"]}%）')


def section_market(days):
    rows = [(m, a) for _, rs in days for m, a in rs]
    c = collections.Counter()
    for m, a in rows:
        od = m.get('odds') or {}
        try:
            o = {'home': float(od['胜']), 'draw': float(od['平']), 'away': float(od['负'])}
        except Exception:
            continue
        h, aw = parse(a)
        rk = 'home' if h > aw else ('away' if aw > h else 'draw')
        pm = {'home': float(m.get('prob_home') or 0), 'draw': float(m.get('prob_draw') or 0),
              'away': float(m.get('prob_away') or 0)}
        raw = {k: 1 / v for k, v in o.items()}
        s = sum(raw.values())
        mp = {k: v / s for k, v in raw.items()}
        c['n'] += 1
        c['model'] += max(pm, key=pm.get) == rk
        c['market'] += max(mp, key=mp.get) == rk
        c['agree'] += max(pm, key=pm.get) == max(mp, key=mp.get)
    print('\n=== 模型 vs 纯市场去水（近 %d 场有赔率的快照）===' % c['n'])
    if not c['n']:
        print('  样本不足')
        return
    print(f"  模型 {c['model']}/{c['n']} = {c['model'] / c['n'] * 100:.1f}%   "
          f"纯市场 {c['market']}/{c['n']} = {c['market'] / c['n'] * 100:.1f}%   "
          f"两者同选 {c['agree'] / c['n'] * 100:.1f}%")
    if c['n'] < 200:
        print('  ⚠ 样本 < 200 场，只作参考（长期 2478 场：模型 51.2% / 市场 51.9%）')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=10)
    ap.add_argument('--date', default=datetime.datetime.now().strftime('%Y-%m-%d'))
    a = ap.parse_args()
    days = load_days(a.date, a.days)
    if not days:
        print('没有可用比赛日')
        return
    print(f'诊断窗口 {days[0][0]} → {days[-1][0]}（{len(days)} 天）\n')
    section_daily(days)
    section_calib(days)
    section_market(days)
    print('\n判读：方向长期 51~52%（市场同水平，已到天花板）；比分单点长期 15%、双档 24%、'
          '前三累计 39%。单日 15 场的比分单点合理波动 0~4 场，'
          '连续多日低于 10% 且 λ 偏差 >0.2 球/场才需要怀疑模型漂移。')


if __name__ == '__main__':
    main()
