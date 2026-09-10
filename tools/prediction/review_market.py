"""市场 vs 模型 vs 实际赛果 —— 三方对照分析工具。

回答的问题：
  1) 市场（去水后）到底有多准？系统性偏差在哪？
  2) 「按市场买」真的能挣钱么？（含抽水/返还率测算）
  3) 我们的模型相对市场有没有增量？在哪些场次有？
  4) 指定日期的逐场对照明细。

数据源：
  - 市场：index.html 的 ODDS 块（`YYYY-MM-DD_主_客`，含 胜/平/负/让球/比分/总进球/半全场）
  - 赛果：results_data.json + results_history/*.json（已修正主客方向）
  - 模型：predictions/<date>/pred_snapshot.json（09-05 起）

用法:
  python review_market.py                 # 全量市场体检 + 逐日模型对照
  python review_market.py --date 2026-09-09   # 单日明细
  python review_market.py --dates 2026-09-05 2026-09-10  # 区间模型对照
"""
import argparse
import glob
import json
import math
import os
import re
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = BASE
for _ in range(3):
    if os.path.isdir(os.path.join(ROOT, 'results_history')):
        break
    ROOT = os.path.dirname(ROOT)
EPS = 1e-9


# ---------------------------------------------------------------- 数据加载
def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_odds_block():
    """从 index.html 读 ODDS 块（JS 对象字面量 → dict）。"""
    html = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    m = re.search(r'const ODDS = (\{[\s\S]*?\n\});', html)
    if not m:
        return {}
    x = m.group(1)
    x = re.sub(r"'", '"', x)
    x = re.sub(r',\s*\]', ']', x)
    x = re.sub(r',\s*\}', '}', x)
    x = re.sub(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', x)
    return json.loads(x)


def load_results_all():
    """合并 results_data.json 与 results_history/*.json（键 = 日期_主_客）。"""
    recs = {}
    for f in sorted(glob.glob(os.path.join(ROOT, 'results_history', '*.json'))):
        if os.path.basename(f) == 'index.json':
            continue
        try:
            d = load_json(f)
        except Exception:
            continue
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict):
                    recs.setdefault(k, v)
    rd = os.path.join(ROOT, 'results_data.json')
    if os.path.exists(rd):
        d = load_json(rd)
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict):
                    # results_data 更新，优先覆盖；但若新条目缺赔率而旧的有一点，保留赔率
                    old = recs.get(k)
                    if old and not (v.get('胜') or v.get('hda胜')):
                        merged = dict(v)
                        for fld in ('胜', '平', '负', 'hda胜', 'hda平', 'hda负',
                                    '比分', '总进球', '半全场', '让球'):
                            if not merged.get(fld) and old.get(fld):
                                merged[fld] = old[fld]
                        recs[k] = merged
                    else:
                        recs[k] = v
    return recs


def _num(v):
    try:
        f = float(v)
        return f if f > 1.0 else None
    except Exception:
        return None


def parse_score(rec):
    s = rec.get('score') or rec.get('fullScore') or ''
    if not isinstance(s, str) or ':' not in s:
        return None
    a, b = s.split(':', 1)
    try:
        return int(a), int(b)
    except Exception:
        return None


def outcome_of(h, a):
    return 'H' if h > a else ('A' if h < a else 'D')


def devig3(oh, od, ol):
    raw = [1.0 / oh, 1.0 / od, 1.0 / ol]
    s = sum(raw)
    return [r / s for r in raw], s


# ---------------------------------------------------------------- 指标
def brier(probs, idx):
    return sum((p - (1.0 if i == idx else 0.0)) ** 2 for i, p in enumerate(probs))


def logloss(probs, idx):
    return -math.log(max(probs[idx], EPS))


def acc(probs, idx):
    return 1 if max(range(3), key=lambda i: probs[i]) == idx else 0


def wilson_z(n1, s1, n2, s2):
    """两个比例的 Z 值（样本均值检验）。"""
    if n1 == 0 or n2 == 0:
        return 0.0
    p1, p2 = s1 / n1, s2 / n2
    p = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return (p1 - p2) / se if se > 0 else 0.0


# ---------------------------------------------------------------- 市场体检
def market_audit(recs, odds_block, min_year=2026):
    print('=' * 78)
    print('【一】市场（赔率）体检：全量历史')
    print('=' * 78)

    rows = []
    for k, rec in recs.items():
        sc = parse_score(rec)
        if not sc:
            continue
        date = k.split('_', 1)[0]
        if date < f'{min_year}-01-01':
            continue
        oh = _num(rec.get('胜')) or _num(rec.get('hda胜'))
        od = _num(rec.get('平')) or _num(rec.get('hda平'))
        ol = _num(rec.get('负')) or _num(rec.get('hda负'))
        if not (oh and od and ol):
            ob = odds_block.get(k) or {}
            oh = oh or _num(ob.get('胜'))
            od = od or _num(ob.get('平'))
            ol = ol or _num(ob.get('负'))
            if not (oh and od and ol):
                continue
        probs, book = devig3(oh, od, ol)
        rows.append({
            'key': k, 'date': date, 'league': rec.get('leagueAbbr') or rec.get('league') or '?',
            'oh': oh, 'od': od, 'ol': ol, 'raw': [1 / oh, 1 / od, 1 / ol],
            'p': probs, 'book': book, 'idx': 'HDA'.index(outcome_of(*sc)),
            'hg': sc[0], 'ag': sc[1],
        })

    n = len(rows)
    print(f'样本: {n} 场（含完整胜平负赔率与比分）')
    if not n:
        return rows
    books = [r['book'] for r in rows]
    print(f'平均返还率(1/抽水): {1 / (sum(books) / n) * 100:.2f}%   平均抽水: {(sum(books) / n - 1) * 100:.2f}%')
    print(f'理论：每注 1 元无脑申购期望回报 = 返还率 = {1 / (sum(books) / n) * 100:.2f}%')

    # 1X2 频率 vs 隐含
    act = Counter(r['idx'] for r in rows)
    imp_dv = [sum(r['p'][i] for r in rows) / n for i in range(3)]
    imp_raw = [sum(r['raw'][i] for r in rows) / n for i in range(3)]
    print()
    print('  结果     实际频率   去水隐含   原始隐含    差(实际-去水)')
    for i, lab in enumerate(['主胜', '平局', '客胜']):
        f = act[i] / n
        print(f'  {lab}    {f * 100:7.2f}%   {imp_dv[i] * 100:7.2f}%   {imp_raw[i] * 100:7.2f}%   '
              f'{(f - imp_dv[i]) * 100:+6.2f}pp')

    # 校准曲线（按被看好的概率分档）
    print()
    print('  市场去水概率校准（分档 × 实现频率）：')
    print('    概率档         样本   预测均值   实际频率    差')
    bands = [(0.0, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5),
             (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]
    for lo, hi in bands:
        sel = []
        for r in rows:
            for i in range(3):
                if lo <= r['p'][i] < hi:
                    sel.append((r['p'][i], 1 if r['idx'] == i else 0))
        if len(sel) < 20:
            continue
        pm = sum(s[0] for s in sel) / len(sel)
        fm = sum(s[1] for s in sel) / len(sel)
        print(f'    [{lo:.2f},{hi:.2f})   {len(sel):6d}   {pm * 100:7.2f}%   {fm * 100:7.2f}%   '
              f'{(fm - pm) * 100:+6.2f}pp')

    # 策略 ROI（按挂牌赔率实投）
    print()
    print('  无脑策略 ROI（按挂牌赔率，1 单位平注）：')
    def roi(sel_idx, label, picker):
        tot = cnt = 0.0
        for r in rows:
            i = picker(r)
            if i is None:
                continue
            cnt += 1
            o = (r['oh'], r['od'], r['ol'])[i]
            tot += (o if r['idx'] == i else 0) - 1
        if cnt:
            print(f'    {label:<22} 注数 {int(cnt):5d}  命中 {sum(1 for r in rows if picker(r) is not None and r["idx"] == picker(r)) / cnt * 100:5.1f}%  ROI {tot / cnt * 100:+6.2f}%')

    roi(None, '买主胜(每场)', lambda r: 0)
    roi(None, '买平局(每场)', lambda r: 1)
    roi(None, '买客胜(每场)', lambda r: 2)
    roi(None, '买低赔方(热门)', lambda r: min(range(3), key=lambda i: (r['oh'], r['od'], r['ol'])[i]))
    roi(None, '买高赔方(冷门)', lambda r: max(range(3), key=lambda i: (r['oh'], r['od'], r['ol'])[i]))

    # 热门档位细看
    print()
    print('  按低赔方赔率分档（买热门）：')
    for lo, hi in [(1.0, 1.3), (1.3, 1.6), (1.6, 2.0), (2.0, 2.5), (2.5, 3.5), (3.5, 99)]:
        sel = [r for r in rows if lo <= min(r['oh'], r['od'], r['ol']) < hi]
        if len(sel) < 20:
            continue
        tot = 0.0
        for r in sel:
            i = min(range(3), key=lambda j: (r['oh'], r['od'], r['ol'])[j])
            o = (r['oh'], r['od'], r['ol'])[i]
            tot += (o if r['idx'] == i else 0) - 1
        print(f'    赔率 [{lo},{hi})  注数 {len(sel):5d}  ROI {tot / len(sel) * 100:+6.2f}%')

    # 平局专项
    print()
    print('  平局专项（市场是否低估平局）：')
    tot = 0.0
    for r in rows:
        tot += (r['od'] if r['idx'] == 1 else 0) - 1
    print(f'    全量买平：ROI {tot / n * 100:+6.2f}%   实际平局率 {act[1] / n * 100:.2f}%  '
          f'去水隐含 {imp_dv[1] * 100:.2f}%')
    for lo, hi in [(0.18, 0.24), (0.24, 0.28), (0.28, 0.34)]:
        sel = [r for r in rows if lo <= r['p'][1] < hi]
        if len(sel) < 20:
            continue
        t = sum((r['od'] if r['idx'] == 1 else 0) - 1 for r in sel)
        print(f'    隐含平概率 [{lo},{hi})  {len(sel):5d} 场  实际平局率 {sum(1 for r in sel if r["idx"] == 1) / len(sel) * 100:5.2f}%  '
              f'ROI {t / len(sel) * 100:+6.2f}%')

    # 比分盘/总进球盘（子集）
    bfs = [(k, recs[k]) for k in recs if isinstance(recs[k].get('比分'), dict) and parse_score(recs[k])]
    zjs = [(k, recs[k]) for k in recs if isinstance(recs[k].get('总进球'), dict) and parse_score(recs[k])]
    print()
    print(f'  比分盘样本 {len(bfs)} 场，总进球盘样本 {len(zjs)} 场（近期才有全盘口）')
    if zjs:
        hit3 = hit1 = 0
        bias = 0.0
        for k, rec in zjs:
            hg, ag = parse_score(rec)
            tot_goals = hg + ag
            raw = {kk: 1.0 / float(vv) for kk, vv in rec['总进球'].items() if _num(vv)}
            s = sum(raw.values()) or 1.0
            p = {kk: vv / s for kk, vv in raw.items()}
            exp = 0.0
            for kk, pp in p.items():
                kk2 = str(kk).replace('球', '')
                if '+' in kk2 or '七' in str(kk) or kk2.startswith('7'):
                    v = 7.0
                else:
                    try:
                        v = float(kk2)
                    except Exception:
                        continue
                exp += v * pp
            bias += (tot_goals - exp)
            top = max(p.items(), key=lambda x: x[1])[0]
            t2 = str(top).replace('球', '')
            if t2 == str(tot_goals):
                hit1 += 1
            cand = {'0', '1', '2', '3', '4', '5', '6', '7+'}
            top3 = [kk for kk, _ in sorted(p.items(), key=lambda x: -x[1])[:3]]
            top3 = {str(x).replace('球', '') for x in top3}
            if str(tot_goals) in top3 or (str(tot_goals) == '7' and '7+' in top3):
                hit3 += 1
        m = len(zjs)
        print(f'    总进球盘：期望均值偏差 {bias / m:+.3f} 球/场   Top1 命中 {hit1 / m * 100:.1f}%   Top3 覆盖 {hit3 / m * 100:.1f}%')
        act_tg = sum(sum(parse_score(recs[k])) for k, _ in zjs) / m
        print(f'    实际场均总进球 {act_tg:.3f}')
    if bfs:
        hit1 = 0
        cov3 = cov5 = 0
        for k, rec in bfs:
            hg, ag = parse_score(rec)
            real = f'{hg}:{ag}'
            raw = {kk: 1.0 / float(vv) for kk, vv in rec['比分'].items() if _num(vv)}
            s = sum(raw.values()) or 1.0
            ranked = [kk for kk, _ in sorted(((kk, vv / s) for kk, vv in raw.items()), key=lambda x: -x[1])]
            if ranked[:1] == [real]:
                hit1 += 1
            if real in ranked[:3]:
                cov3 += 1
            if real in ranked[:5]:
                cov5 += 1
        m = len(bfs)
        print(f'    比分盘：Top1 命中 {hit1 / m * 100:.1f}%   Top3 覆盖 {cov3 / m * 100:.1f}%   Top5 覆盖 {cov5 / m * 100:.1f}%')
    return rows


# ---------------------------------------------------------------- 模型对照
def load_snapshots():
    out = {}
    for f in sorted(glob.glob(os.path.join(ROOT, 'predictions', '*', 'pred_snapshot.json'))):
        date = os.path.basename(os.path.dirname(f))
        try:
            d = load_json(f)
        except Exception:
            continue
        if isinstance(d, dict) and d.get('matches'):
            out[date] = d
    return out


def model_compare(snaps, recs, odds_block, d1=None, d2=None):
    print()
    print('=' * 78)
    print('【二】模型 vs 市场：逐日对照')
    print('=' * 78)
    dates = sorted(snaps)
    if d1:
        dates = [d for d in dates if d >= d1]
    if d2:
        dates = [d for d in dates if d <= d2]
    allm = []
    per_day = []
    for date in dates:
        snap = snaps[date]
        day = []
        for m in snap.get('matches') or []:
            home, away = m.get('home'), m.get('away')
            key = f'{date}_{home}_{away}'
            rec = recs.get(key)
            if not rec:
                continue
            sc = parse_score(rec)
            if not sc:
                continue
            oh = _num(rec.get('胜')) or _num(rec.get('hda胜'))
            od = _num(rec.get('平')) or _num(rec.get('hda平'))
            ol = _num(rec.get('负')) or _num(rec.get('hda负'))
            ob = odds_block.get(key) or {}
            oh = oh or _num(ob.get('胜'))
            od = od or _num(ob.get('平'))
            ol = ol or _num(ob.get('负'))
            if not (oh and od and ol):
                continue
            mp, book = devig3(oh, od, ol)
            mdl = [float(m.get('prob_home', 0)) / 100, float(m.get('prob_draw', 0)) / 100,
                   float(m.get('prob_away', 0)) / 100]
            s = sum(mdl) or 1.0
            mdl = [x / s for x in mdl]
            idx = 'HDA'.index(outcome_of(*sc))
            row = {'date': date, 'id': m.get('id'), 'home': home, 'away': away,
                   'league': m.get('league', ''), 'score': f'{sc[0]}:{sc[1]}', 'idx': idx,
                   'mdl': mdl, 'mkt': mp, 'raw': [1 / oh, 1 / od, 1 / ol],
                   'oh': oh, 'od': od, 'ol': ol, 'book': book,
                   'lam_t': float(m.get('lam_total') or 0), 'tg': sc[0] + sc[1]}
            day.append(row)
            allm.append(row)
        if day:
            per_day.append((date, day))

    if not allm:
        print('无可用对照样本')
        return []
    n = len(allm)
    bm = sum(brier(r['mdl'], r['idx']) for r in allm) / n
    bk = sum(brier(r['mkt'], r['idx']) for r in allm) / n
    am = sum(acc(r['mdl'], r['idx']) for r in allm) / n
    ak = sum(acc(r['mkt'], r['idx']) for r in allm) / n
    lm = sum(logloss(r['mdl'], r['idx']) for r in allm) / n
    lk = sum(logloss(r['mkt'], r['idx']) for r in allm) / n
    print(f'样本: {n} 场（{dates[0]} ~ {dates[-1]}，{len(per_day)} 天）')
    print()
    print('  口径         Brier     LogLoss   方向Top1')
    print(f'  我们的模型   {bm:.4f}   {lm:.4f}   {am * 100:5.1f}%')
    print(f'  市场(去水)   {bk:.4f}   {lk:.4f}   {ak * 100:5.1f}%')
    print(f'  差值(模型-市场) {bm - bk:+.4f}   {lm - lk:+.4f}   {(am - ak) * 100:+.1f}pp')

    # 逐年逐日明细
    print()
    print('  逐日明细（场次 | 模型Brier | 市场Brier | 模型方向 | 市场方向）：')
    for date, day in per_day:
        m = len(day)
        b1 = sum(brier(r['mdl'], r['idx']) for r in day) / m
        b2 = sum(brier(r['mkt'], r['idx']) for r in day) / m
        a1 = sum(acc(r['mdl'], r['idx']) for r in day) / m
        a2 = sum(acc(r['mkt'], r['idx']) for r in day) / m
        flag = '← 模型更好' if b1 < b2 else ''
        print(f'    {date}  {m:3d}场  {b1:.4f}  {b2:.4f}  {a1 * 100:5.1f}%  {a2 * 100:5.1f}%  {flag}')

    # 分歧分档
    print()
    print('  模型与市场的分歧分档（分歧 = 被看好方向上的概率差最大者）：')
    buckets = defaultdict(list)
    for r in allm:
        i_m = max(range(3), key=lambda i: r['mdl'][i])
        i_k = max(range(3), key=lambda i: r['mkt'][i])
        div = max(abs(r['mdl'][i] - r['mkt'][i]) for i in range(3))
        same = (i_m == i_k)
        b = 0 if div < 0.03 else (1 if div < 0.06 else (2 if div < 0.10 else 3))
        buckets[b].append((r, same, i_m, i_k))
    labels = ['分歧<3pp', '3~6pp', '6~10pp', '>10pp']
    print('    档位        场次  方向一致  模型对  市场对   双方都错  模型Brier  市场Brier')
    for b in sorted(buckets):
        grp = buckets[b]
        m = len(grp)
        cons = sum(1 for g in grp if g[1])
        mw = sum(1 for g in grp if g[0]['idx'] == g[2])
        kw = sum(1 for g in grp if g[0]['idx'] == g[3])
        both = sum(1 for g in grp if g[0]['idx'] != g[2] and g[0]['idx'] != g[3])
        b1 = sum(brier(g[0]['mdl'], g[0]['idx']) for g in grp) / m
        b2 = sum(brier(g[0]['mkt'], g[0]['idx']) for g in grp) / m
        print(f'    {labels[b]:<12}{m:5d}   {cons / m * 100:6.1f}%  {mw / m * 100:5.1f}%  {kw / m * 100:5.1f}%   '
              f'{both / m * 100:6.1f}%   {b1:.4f}    {b2:.4f}')

    # 只看双方方向不一致的场次
    dis = [(g[0], g[2], g[3]) for g in sum(buckets.values(), []) if not g[1]]
    if dis:
        mw = sum(1 for r, im, ik in dis if r['idx'] == im)
        kw = sum(1 for r, im, ik in dis if r['idx'] == ik)
        print()
        print(f'  ★ 方向不一致的 {len(dis)} 场：模型对 {mw} ({mw / len(dis) * 100:.1f}%)，市场对 {kw} ({kw / len(dis) * 100:.1f}%)，'
              f'Z={wilson_z(len(dis), mw, len(dis), kw):+.2f}')

    # 投注视角：模型挑出的「相对市场有价值」的注
    print()
    print('  价值投注视角（模型概率 > 去水市场概率 + 阈值，按挂牌赔率实投）：')
    for thr in (0.0, 0.03, 0.05, 0.08):
        tot = cnt = hit = 0.0
        for r in allm:
            for i in range(3):
                if r['mdl'][i] - r['mkt'][i] > thr:
                    cnt += 1
                    o = (r['oh'], r['od'], r['ol'])[i]
                    win = 1 if r['idx'] == i else 0
                    hit += win
                    tot += (o if win else 0) - 1
        if cnt:
            print(f'    阈值 +{thr * 100:.0f}pp  注数 {int(cnt):4d}  命中 {hit / cnt * 100:5.1f}%  ROI {tot / cnt * 100:+6.2f}%')

    # 总进球 / 比分对照
    print()
    print('  总进球预测对照：')
    dev_m = sum(r['lam_t'] - r['tg'] for r in allm) / n
    print(f'    模型 λ合计 平均偏差 {dev_m:+.3f} 球/场')
    tk = [r for r in allm if isinstance(recs.get(f"{r['date']}_{r['home']}_{r['away']}", {}).get('总进球'), dict)]
    if tk:
        d2v = 0.0
        for r in tk:
            rec = recs[f"{r['date']}_{r['home']}_{r['away']}"]
            raw = {k2: 1.0 / float(v2) for k2, v2 in rec['总进球'].items() if _num(v2)}
            s = sum(raw.values()) or 1.0
            exp = 0.0
            for k2, p2 in raw.items():
                kk2 = str(k2).replace('球', '')
                try:
                    v = 7.0 if ('+' in kk2 or kk2 == '7') else float(kk2)
                except Exception:
                    continue
                exp += v * (p2 / s)
            d2v += r['tg'] - exp
        print(f'    市场总进球盘 平均偏差 {d2v / len(tk):+.3f} 球/场（{len(tk)} 场）')
    return allm


def day_detail(rows, date):
    print()
    print('=' * 78)
    print(f'【三】{date} 逐场三方对照')
    print('=' * 78)
    sel = [r for r in rows if r['date'] == date]
    if not sel:
        print('该日无对照样本')
        return
    print(f'{"编号":<8}{"对阵":<26}{"比分":<7}{"实际":<5}{"模型 主/平/客":<22}{"市场 主/平/客":<22}{"模型":<6}{"市场":<6}')
    hit_m = hit_k = 0
    for r in sel:
        va = '主胜' if r['idx'] == 0 else ('平' if r['idx'] == 1 else '客胜')
        im = max(range(3), key=lambda i: r['mdl'][i])
        ik = max(range(3), key=lambda i: r['mkt'][i])
        sm = '✓' if im == r['idx'] else '✗'
        sk = '✓' if ik == r['idx'] else '✗'
        hit_m += im == r['idx']
        hit_k += ik == r['idx']
        vs = f"{r['home']} vs {r['away']}"
        pad = 26 - sum(2 if ord(c) > 127 else 1 for c in vs)
        print(f"{r['id']:<8}{vs}{' ' * max(pad, 1)}"
              f"{r['score']:<7}{va:<5}"
              f"{r['mdl'][0] * 100:5.1f}/{r['mdl'][1] * 100:4.1f}/{r['mdl'][2] * 100:4.1f}    "
              f"{r['mkt'][0] * 100:5.1f}/{r['mkt'][1] * 100:4.1f}/{r['mkt'][2] * 100:4.1f}    "
              f"{sm}    {sk}")
    n = len(sel)
    print()
    print(f'  当日方向命中：模型 {hit_m}/{n} ({hit_m / n * 100:.0f}%)   市场 {hit_k}/{n} ({hit_k / n * 100:.0f}%)')
    b1 = sum(brier(r['mdl'], r['idx']) for r in sel) / n
    b2 = sum(brier(r['mkt'], r['idx']) for r in sel) / n
    print(f'  当日 Brier：模型 {b1:.4f}   市场 {b2:.4f}')
    tg = sum(r['tg'] for r in sel)
    lk = sum(r['lam_t'] for r in sel)
    print(f'  当日进球：实际 {tg} 球（场均 {tg / n:.2f}）  模型 λ合计 {lk:.1f}（场均 {lk / n:.2f}）')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=None)
    ap.add_argument('--dates', nargs=2, default=None, metavar=('FROM', 'TO'))
    ap.add_argument('--skip-audit', action='store_true')
    a = ap.parse_args()

    recs = load_results_all()
    ob = load_odds_block()
    print(f'载入：赛果 {len(recs)} 条，ODDS {len(ob)} 条')
    snaps = load_snapshots()
    print(f'预测快照：{", ".join(sorted(snaps))}')

    if not a.skip_audit:
        market_audit(recs, ob)
    d1, d2 = (a.dates if a.dates else (None, None))
    if a.date:
        d1 = d2 = a.date
    allm = model_compare(snaps, recs, ob, d1, d2)
    if a.date:
        day_detail(allm, a.date)


if __name__ == '__main__':
    main()
