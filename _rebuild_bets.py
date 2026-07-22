# -*- coding: utf-8 -*-
"""读取投注记录JSON，按实际开奖逻辑（每场最多1个结果命中）重新计算命中结果。"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from itertools import combinations, product

SRC = r'C:\Users\Jin\Downloads\投注记录_2026-06-27 (1).json'
OUT = r'c:\Users\Jin\Desktop\jinbet_update\jinbet_update\_injected_bets.json'

# ---------- 等价前端实现 ----------
def get_combinations(arr, k):
    return [list(c) for c in combinations(arr, k)]

def cartesian(arrays):
    return [list(p) for p in product(*arrays)]

def compute_exclusive_sp_range(game_options, combos, n):
    if any((not opts) for opts in game_options):
        return {'min': 0.0, 'max': 0.0}
    k_to_idx_arrs = {}
    for k in combos:
        if 0 < k <= n:
            k_to_idx_arrs[k] = get_combinations(list(range(n)), k)
    min_total = float('inf')
    max_total = -float('inf')
    outcomes = cartesian(game_options)
    for outcome in outcomes:
        total = 0.0
        for k in combos:
            idx_arrs = k_to_idx_arrs.get(k)
            if not idx_arrs:
                continue
            for idx_arr in idx_arrs:
                prod = 1.0
                ok = True
                for i in idx_arr:
                    odd = outcome[i]
                    if odd is None or odd <= 0:
                        ok = False
                        break
                    prod *= odd
                if ok:
                    total += prod
        if total < min_total:
            min_total = total
        if total > max_total:
            max_total = total
    if min_total == float('inf'):
        min_total = 0.0
    if max_total == -float('inf'):
        max_total = 0.0
    return {'min': min_total, 'max': max_total}

def recalc_bet_stats(bet):
    games = bet.get('games', [])
    combos = bet.get('passCombos', [])
    all_sp = []
    n = len(games)
    game_options = [[dict(o) for o in g.get('options', [])] for g in games]
    for k in combos:
        if k <= n:
            idx_arrs = get_combinations(list(range(n)), k)
            for idx_arr in idx_arrs:
                opt_combos = cartesian([game_options[i] for i in idx_arr])
                for opt_combo in opt_combos:
                    sp = 1.0
                    for opt in opt_combo:
                        sp *= float(opt.get('odds') or 0)
                    all_sp.append(sp)
    if all_sp:
        min_sp = min(all_sp)
        max_sp = max(all_sp)
    else:
        min_sp = 0.0
        max_sp = 0.0
    bet['spRange'] = {'min': min_sp, 'max': max_sp}

    # 所有玩法统一按「每场最多1个结果命中」的开奖逻辑计算
    odds_arr = [[float(o.get('odds') or 0) for o in g.get('options', [])] for g in games]
    bet['totalSpRange'] = compute_exclusive_sp_range(odds_arr, combos, n)
    bet['totalSp'] = max_sp
    bet['hasExclusiveOptions'] = True
    return bet

# ---------- 执行 ----------
with open(SRC, 'r', encoding='utf-8') as f:
    data = json.load(f)
bets = data.get('bets', [])
print(f'读取到 {len(bets)} 条投注记录')

recalc = []
for idx, b in enumerate(bets):
    new_b = dict(b)
    # 保留所有原始字段，仅重算统计字段
    recalc.append(recalc_bet_stats(new_b))

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(recalc, f, ensure_ascii=False, indent=2)

# 打印统计
print(f'重算完成：')
for i, b in enumerate(recalc):
    n = len(b.get('games', []))
    cmb = b.get('passCombos', [])
    pt_list = sorted(set(g.get('playType') for g in b.get('games', [])))
    has_ex = b.get('hasExclusiveOptions')
    sp = b.get('spRange', {})
    tsp = b.get('totalSpRange')
    tsp_str = ''
    if tsp:
        tsp_str = f" totalSp=[{tsp['min']:.4f}~{tsp['max']:.4f}]"
    print(f"  {i+1:>2}. id={b['id'][:8]}… {n}场 {cmb}关 玩法:{','.join(pt_list)} exclusive={has_ex} sp=[{sp['min']:.4f}~{sp['max']:.4f}]{tsp_str}")

print(f'\n已写入 {OUT}')
