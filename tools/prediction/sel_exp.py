# -*- coding: utf-8 -*-
"""实验：大胆档 / 比分精选 的候选排序口径对比（仅回放历史，不改生产）。

用法：python sel_exp.py
"""
import json, os, glob, datetime, collections
import selection_algo as SA

today = datetime.datetime.now().strftime('%Y-%m-%d')

recs = {}
for f in sorted(glob.glob(os.path.join('.', 'results_history', '*.json'))):
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
    rd = json.load(open('results_data.json', encoding='utf-8'))
    for k, v in (rd.items() if isinstance(rd, dict) else []):
        if isinstance(v, dict):
            recs[k] = v
except Exception:
    pass


def actual(y, h, a):
    for key in (f'{y}_{h}_{a}', f'{y}_{a}_{h}'):
        r = recs.get(key)
        if r:
            s = r.get('score') or r.get('fullScore') or ''
            if isinstance(s, str) and ':' in s:
                return s
    return None


tuning = SA.load_tuning()

days = []
for sp in sorted(glob.glob(os.path.join('.', 'predictions', '*', 'pred_snapshot.json'))):
    date = os.path.basename(os.path.dirname(sp))
    if date >= today:
        continue
    try:
        snap = json.load(open(sp, encoding='utf-8'))
    except Exception:
        continue
    rows = []
    for m in (snap.get('matches') or []):
        a = actual(date, m.get('home'), m.get('away'))
        if not a:
            continue
        nm = dict(m)
        nm.setdefault('prob', {'home': m.get('prob_home', 0), 'draw': m.get('prob_draw', 0),
                               'away': m.get('prob_away', 0)})
        nm.setdefault('cold', False)
        nm.setdefault('data_n', {})
        rows.append((nm, a))
    if len(rows) >= SA.TIER_PK:
        days.append((date, rows))


def m_of(x):
    return x[1] if isinstance(x, tuple) else x


# ---------- 生产口径的选中集合 ----------
def prod_pk(matches, t):
    return [m_of(x) for x in SA.rank_pk(matches, t, SA.TIER_PK)[1]]


def prod_bd(matches, t):
    return [m_of(x) for x in SA.rank_bold(matches, t, SA.TIER_BD)[1]]


# ---------- 候选排序键 ----------
def k_pk_cap_lt(m, t):
    """比分精选：质量相同，但 λ 大的排后面（把好场次提前）。"""
    return (SA.pk_quality(m, t), -SA.lam_total(m))


# 大胆档候选
def bd_cur(m, t):
    return SA.bold_quality(m, t)


def bd_extreme_only(m, t):
    """只看极限档概率（总进球再上一档，真·进攻型）。"""
    _, xp = SA.extreme_pick(m)
    return xp or 0.0


def bd_ok_extreme(m, t):
    """极限档概率，但要求极限档 != 头条（否则等于重复稳档）。"""
    _, xp = SA.extreme_pick(m)
    hs, _ = SA.hit_pick(m)
    x, _ = SA.extreme_pick(m)
    if x == hs:
        return -1.0
    return xp or 0.0


def bd_ok_scale(m, t):
    """量级档概率，但要求量级档 != 头条（避免把稳档当大胆档）。"""
    e, ep, is_mode = SA.expect_score(m)
    if is_mode:
        return -1.0
    return ep or 0.0


def bd_hi_lam(m, t):
    """要求 λ 总量 >= 2.4（进攻环境好的场次）后按当前口径排。"""
    if SA.lam_total(m) < 2.4:
        return -1.0
    return SA.bold_quality(m, t)


def bd_novel(m, t):
    """量级档 != 头条 时用量级档概率；否则退回极限档概率（保证总有候选）。"""
    e, ep, is_mode = SA.expect_score(m)
    if not is_mode:
        return ep or 0.0
    _, xp = SA.extreme_pick(m)
    return xp or 0.0


CAND_BD = [
    ('当前 max(极限,量级)', bd_cur),
    ('仅极限档', bd_extreme_only),
    ('极限档且≠头条', bd_ok_extreme),
    ('量级档且≠头条', bd_ok_scale),
    ('λ≥2.4 后当前口径', bd_hi_lam),
    ('量级≠头条否则极限', bd_novel),
]


def eval_bd(keyfn):
    rate, cov, tot, hit, logs = 0.0, 0, 0, 0, []
    n = 0
    for date, rows in days:
        nc = [m for m, _ in rows if not SA.is_cold(m)]
        ranked = sorted([(m, a) for m, a in rows if not SA.is_cold(m)],
                        key=lambda r: -keyfn(r[0], tuning))
        sel = ranked[:SA.TIER_BD]
        s = sum(1 for m, a in sel if SA.bd_result(m, a) in ('scale', 'extreme'))
        n += 1
        rate += s / max(1, len(sel))
        cov += 1 if s >= 1 else 0
        tot += len(sel)
        hit += s
        logs.append(f'{date[-5:]}:{s}/{len(sel)}')
    if n == 0:
        return 0, 0, 0, 0, []
    obj = 0.6 * (rate / n) * 100 + 0.4 * (cov / n) * 100
    return obj, hit / max(1, tot) * 100, hit, tot, logs


print('=== 大胆档候选口径（12 天回放，冷启动已排除）===')
print(f"{'口径':<22}{'目标':>7}{'命中率':>8}{'命中/腿':>10}   逐日")
for name, fn in CAND_BD:
    obj, hr, hit, tot, logs = eval_bd(fn)
    print(f'{name:<22}{obj:>7.2f}{hr:>7.1f}%{hit:>6}/{tot:<4}   {" ".join(logs)}')

print()
print('=== 比分精选候选口径 ===')
for name, fn in [('当前 质量分', lambda m, t: SA.pk_quality(m, t)),
                 ('质量分+λ升序', k_pk_cap_lt)]:
    rate, cov, tot, hit, logs = 0.0, 0, 0, 0, []
    n = 0
    for date, rows in days:
        ranked = sorted([(m, a) for m, a in rows if not SA.is_cold(m)],
                        key=lambda r: (-fn(r[0], tuning)[0] if isinstance(fn(r[0], tuning), tuple)
                                       else -fn(r[0], tuning)))
        sel = ranked[:SA.TIER_PK]
        s = sum(1 for m, a in sel if SA.pk_result(m, a) in ('hit', 'band'))
        n += 1
        rate += s / max(1, len(sel))
        cov += 1 if s >= 1 else 0
        tot += len(sel)
        hit += s
        logs.append(f'{date[-5:]}:{s}/{len(sel)}')
    obj = 0.6 * (rate / n) * 100 + 0.4 * (cov / n) * 100
    print(f'{name:<22}{obj:>7.2f}{hit/max(1,tot)*100:>7.1f}%{hit:>6}/{tot:<4}   {" ".join(logs)}')

print()
print('=== 大胆档「量级档 == 头条」退化比例 ===')
same = tot2 = 0
for date, rows in days:
    for m, a in rows:
        if SA.is_cold(m):
            continue
        e, _, is_mode = SA.expect_score(m)
        _, xp = SA.extreme_pick(m)
        hs, _ = SA.hit_pick(m)
        tot2 += 1
        if is_mode:
            same += 1
print(f'全历史 {tot2} 场非冷启动中，量级档 == 头条 的有 {same} 场 = {same/max(1,tot2)*100:.1f}%')
