# -*- coding: utf-8 -*-
"""
赛果库主客标签真实性验证（无需用户人工核对）
思路：
 A. 结构层：检出「反向孪生键」(A_B 与 B_A 同时存在)，判断是否人为双写
 B. 权威锚：SCHEDULE / ODDS 来自体彩官方 API 的 homeTeamAllName / guestTeamAllName
    （官方竞彩字段，语义不可疑），用它做判决基准
 C. 判决：results_data 里 key=日期_主_客 的条目，其 'home' 字段是否 == 官方主队
 D. 影响面：统计有多少条目的方向与官方一致
"""
import json, os, sys
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(os.path.join(ROOT, 'results_data.json')):
    ROOT = os.path.dirname(ROOT)

def load(name):
    for base in (ROOT, os.path.join(ROOT, 'tools', 'prediction')):
        p = os.path.join(base, name)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
    raise FileNotFoundError(name)

res = load('results_data.json')
odds = load('odds_data.json')

# ---- 从 index.html 读 SCHEDULE（官方权威主客）----
sched = {}
for base in (ROOT, os.path.join(ROOT, 'tools', 'prediction')):
    p = os.path.join(base, 'index.html')
    if os.path.exists(p):
        html = open(p, 'r', encoding='utf-8').read()
        import re
        m = re.search(r'const SCHEDULE = \{([\s\S]*?)\n\};', html)
        if m:
            js = m.group(0).replace('const SCHEDULE = ', '').rstrip(';').rstrip()
            # 宽松解析：{ '2026-09-10': [ {...}, ... ], ... }
            import re as _re
            for dm in _re.finditer(r"'(\d{4}-\d{2}-\d{2})'\s*:\s*\[([\s\S]*?)\]\s*,?\s*(?='\d{4}|\}$)", js):
                d = dm.group(1)
                body = dm.group(2)
                lst = []
                for gm in _re.finditer(r"\{[^{}]*\}", body):
                    g = gm.group(0)
                    h = _re.search(r"home\s*:\s*'([^']*)'", g)
                    a = _re.search(r"away\s*:\s*'([^']*)'", g)
                    if h and a:
                        lst.append((h.group(1), a.group(1)))
                sched[d] = lst
        break

print('=' * 78)
print('A. 结构层：results_data.json 规模与孪生结构')
print('=' * 78)
print(f'  总条目数            : {len(res)}')

pairs = defaultdict(list)   # (date, frozenset) -> [keys]
for k in res:
    p = k.split('_', 2)
    if len(p) == 3:
        pairs[(p[0], frozenset(p[1:]))].append(k)
uniq = len(pairs)
twins = sum(1 for v in pairs.values() if len(v) > 1)
print(f'  去重后唯一对阵      : {uniq}')
print(f'  存在反向孪生的对阵  : {twins}  ({twins/max(uniq,1)*100:.1f}%)')
multi = Counter(len(v) for v in pairs.values())
print(f'  每对阵条目数分布    : {dict(sorted(multi.items()))}')

# ---- 孪生对是否比分镜像 ----
mirror_ok = mirror_bad = 0
samples = []
for (d, fs), keys in pairs.items():
    if len(keys) != 2:
        continue
    k1, k2 = sorted(keys)
    s1 = str(res[k1].get('score', '') or '')
    s2 = str(res[k2].get('score', '') or '')
    if ':' not in s1 or ':' not in s2:
        continue
    a, b = s1.split(':')[:2]
    c, e = s2.split(':')[:2]
    if (a, b) == (e, c):
        mirror_ok += 1
        if len(samples) < 5:
            samples.append((k1, s1, k2, s2))
    else:
        mirror_bad += 1
        if mirror_bad <= 5 and len(samples) < 8:
            samples.append(('MISMATCH', k1, s1, k2, s2))
print(f'  孪生对比分镜像      : 是 {mirror_ok} / 否 {mirror_bad}')
for s in samples[:6]:
    print(f'      {s}')

print()
print('=' * 78)
print('B. 权威锚：用 SCHEDULE（体彩官方 homeTeamAllName）判决 results 的 home 字段')
print('=' * 78)


def dir_of(entry):
    """返回该条目自身宣称的 (home, away)"""
    return entry.get('home', ''), entry.get('away', '')


# 建立 日期+无序队对 -> 官方(home,away)
official = {}
for d, lst in sched.items():
    for h, a in lst:
        official[(d, frozenset((h, a)))] = (h, a)

print(f'  SCHEDULE 覆盖日期数: {len(sched)}，场次: {sum(len(v) for v in sched.values())}')

agree = disagree = noanchor = 0
dis_list = []
for k, v in res.items():
    p = k.split('_', 2)
    if len(p) != 3:
        continue
    d = p[0]
    off = official.get((d, frozenset(p[1:])))
    if not off:
        noanchor += 1
        continue
    h, a = dir_of(v)
    if (h, a) == off:
        agree += 1
    elif (h, a) == (off[1], off[0]):
        disagree += 1
        if len(dis_list) < 8:
            dis_list.append((k, v.get('home'), v.get('away'), off, str(v.get('score'))))
    else:
        agree += 1  # 队名不同源，跳过

tot_anch = agree + disagree
print(f'  可判决条目: {tot_anch}  (无官方锚: {noanchor})')
if tot_anch:
    print(f'    与官方方向【一致】: {agree}  ({agree/tot_anch*100:.1f}%)')
    print(f'    与官方方向【颠倒】: {disagree}  ({disagree/tot_anch*100:.1f}%)')
print('  颠倒样例（results认为的主队 vs 官方主队）:')
for x in dis_list:
    print(f'    key={x[0]}\n        results home/away = {x[1]} / {x[2]}\n        官方 home/away    = {x[3][0]} / {x[3][1]}   比分={x[4]}')

print()
print('=' * 78)
print('C. 统计口径：主客胜分布（分层看孪生污染影响）')
print('=' * 78)


def stat(entries, label):
    h = d = a = 0
    hg = ag = 0
    n = 0
    for k, v in entries:
        s = str(v.get('score', '') or '')
        if ':' not in s:
            continue
        try:
            x, y = s.split(':')[:2]
            x, y = int(x), int(y)
        except Exception:
            continue
        n += 1
        hg += x; ag += y
        if x > y:
            h += 1
        elif x < y:
            a += 1
        else:
            d += 1
    if not n:
        print(f'  {label}: 无比分样本')
        return
    print(f'  {label:<28} n={n:<5} 主胜{h/n*100:5.2f}%  平{d/n*100:5.2f}%  客胜{a/n*100:5.2f}%  场均 {hg/n:.3f} / {ag/n:.3f}')


all_items = list(res.items())
stat(all_items, '全库（含孪生）')
single = [it for it in all_items
          if len(pairs.get((it[0].split('_', 2)[0], frozenset(it[0].split('_', 2)[1:])), [])) == 1]
twin = [it for it in all_items
        if len(pairs.get((it[0].split('_', 2)[0], frozenset(it[0].split('_', 2)[1:])), [])) == 2]
stat(single, '仅单条对阵（无孪生）')
stat(twin, '仅孪生对阵（双向全在）')

# 只保留与官方方向一致的条目
anchored = []
for k, v in res.items():
    p = k.split('_', 2)
    if len(p) != 3:
        continue
    off = official.get((p[0], frozenset(p[1:])))
    if off and (v.get('home'), v.get('away')) == off:
        anchored.append((k, v))
stat(anchored, '★与官方同向的条目')

# ODDS 权威口径（体彩 API h/d/a）
print()
oh = od = oa = 0
for k, v in odds.items():
    try:
        hh = float(v.get('胜') or 0); dd = float(v.get('平') or 0); aa = float(v.get('负') or 0)
    except Exception:
        continue
    if hh > 1 and dd > 1 and aa > 1:
        s = 1/hh + 1/dd + 1/aa
        hh, dd, aa = (1/hh)/s, (1/dd)/s, (1/aa)/s
        oh += hh; od += dd; oa += aa
        globals()['_o_n'] = globals().get('_o_n', 0) + 1
n_odds = globals().get('_o_n', 0)
if n_odds:
    print(f'  ODDS 去水后隐含（体彩官方 home/draw/away 字段） n={n_odds}')
    print(f'    主胜 {oh/n_odds*100:.2f}%  平 {od/n_odds*100:.2f}%  客胜 {oa/n_odds*100:.2f}%')

print()
print('=' * 78)
print('D. 逐场抽样：当日/近期比赛在 results 与 SCHEDULE 中的主客方向对照')
print('=' * 78)
shown = 0
for d in sorted(sched.keys(), reverse=True):
    for h, a in sched[d]:
        for kk, vv in res.items():
            if kk.split('_', 2)[:1] != [d]:
                continue
            if set(kk.split('_', 2)[1:]) == {h, a}:
                print(f'  {d}  官方: {h} vs {a}   |  results[{kk}] home={vv.get("home")} away={vv.get("away")} score={vv.get("score")}')
                shown += 1
                break
    if shown >= 10:
        break
