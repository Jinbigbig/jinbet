# -*- coding: utf-8 -*-
"""读取投注记录JSON文件（默认从Downloads找最新的投注记录_*.json），重算统计字段后注入到index.html的_injectedBets数组，然后git push到gh-pages。"""
import sys, os, json, glob, io, re, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from itertools import combinations, product

# ---------- 路径配置 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, 'index.html')
BETS_TMP = os.path.join(BASE_DIR, '_injected_bets.json')
DOWNLOADS = os.path.join(os.path.expanduser('~'), 'Downloads')

EXCLUSIVE_TYPES = {'总进球', '比分', '半全场'}  # 兼容：保留定义但不再使用（所有玩法统一走赛果枚举算法）


# ================================================================
#  Step 1: 定位投注记录 JSON
# ================================================================
def find_bets_file():
    if len(sys.argv) >= 2:
        p = sys.argv[1].strip().strip('"')
        if os.path.isfile(p):
            return p
        print(f'[错误] 文件不存在: {p}')
        sys.exit(1)
    # 自动找 Downloads 下最新的 投注记录_*.json
    pattern = os.path.join(DOWNLOADS, '投注记录_*.json')
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        print(f'[错误] 未在 {DOWNLOADS} 下找到 投注记录_*.json，请手动指定路径:')
        print(f'  python push_bets.py "C:\\path\\to\\bets.json"')
        sys.exit(1)
    return files[0]


# ================================================================
#  Step 2: 重算逻辑（等价前端 recalcBetStats + computeExclusiveSpRange）
# ================================================================
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
    for outcome in cartesian(game_options):
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
    min_sp = min(all_sp) if all_sp else 0.0
    max_sp = max(all_sp) if all_sp else 0.0
    bet['spRange'] = {'min': min_sp, 'max': max_sp}

    # 所有玩法统一按「每场最多1个结果命中」的开奖逻辑计算
    odds_arr = [[float(o.get('odds') or 0) for o in g.get('options', [])] for g in games]
    bet['totalSpRange'] = compute_exclusive_sp_range(odds_arr, combos, n)
    bet['totalSp'] = max_sp
    bet['hasExclusiveOptions'] = True
    return bet


# ================================================================
#  Step 3: 注入到 index.html _injectedBets 数组
# ================================================================
def inject_into_html(bets_json_str):
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    marker = 'var _injectedBets = '
    start = content.find(marker)
    if start == -1:
        raise RuntimeError('index.html 中找不到 var _injectedBets = 标记')

    # 找到数组结束位置
    brk_start = content.find('[', start + len(marker))
    stack = 1
    i = brk_start + 1
    in_str = None
    esc = False
    brk_end = -1
    while i < len(content) and stack > 0:
        c = content[i]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == in_str:
                in_str = None
        else:
            if c == '"' or c == "'":
                in_str = c
            elif c == '[':
                stack += 1
            elif c == ']':
                stack -= 1
                if stack == 0:
                    brk_end = i
                    break
        i += 1

    if brk_end == -1:
        raise RuntimeError('未找到 _injectedBets 数组的结束 ]')

    semi = content.find(';', brk_end)
    if semi == -1:
        raise RuntimeError('未找到 _injectedBets 数组后的分号')

    new_section = marker + bets_json_str.rstrip() + ';'
    new_content = content[:start] + new_section + content[semi + 1:]

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)


# ================================================================
#  Step 4: Git 提交推送
# ================================================================
def run_git(*args):
    cmd = ['git', '--no-pager'] + list(args)
    print(f'\n> git {" ".join(args)}')
    res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, encoding='utf-8', errors='replace')
    if res.stdout.strip():
        print(res.stdout.rstrip())
    if res.stderr.strip():
        print(res.stderr.rstrip(), file=sys.stderr)
    return res

def git_commit_push(bet_count, src_name):
    # fetch first 保证 force-with-lease 成功
    run_git('fetch', 'origin', 'gh-pages')

    # add 变更文件
    run_git('add', 'index.html')
    if os.path.exists(BETS_TMP):
        run_git('add', '_injected_bets.json')
    run_git('add', os.path.basename(__file__))
    bat_file = os.path.splitext(os.path.basename(__file__))[0] + '.bat'
    if os.path.exists(os.path.join(BASE_DIR, bat_file)):
        run_git('add', bat_file)
    if os.path.exists(os.path.join(BASE_DIR, '_rebuild_bets.py')):
        run_git('add', '_rebuild_bets.py')

    status = run_git('status', '--short')
    if not status.stdout.strip():
        print('\n[提示] 没有任何变更，跳过提交')
        return True

    msg = f'推送{bet_count}条投注记录（来自 {src_name}）'
    res = run_git('commit', '-m', msg)
    if res.returncode != 0:
        print('[错误] git commit 失败')
        return False

    res = run_git('push', '--force-with-lease', 'origin', 'gh-pages')
    if res.returncode != 0:
        print('[错误] git push 失败，尝试 --force 推送：')
        res = run_git('push', '--force', 'origin', 'gh-pages')
        if res.returncode != 0:
            print('[错误] push 仍然失败，请手动处理')
            return False
    return True


# ================================================================
#  Main
# ================================================================
def main():
    print('=' * 60)
    print('  🚀 投注记录一键推送')
    print('=' * 60)

    # Step 1
    src_file = find_bets_file()
    src_name = os.path.basename(src_file)
    print(f'\n[1/4] 读取投注记录: {src_file}')
    with open(src_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    bets = data.get('bets', data) if isinstance(data, dict) else data
    if not isinstance(bets, list):
        print('[错误] JSON 格式不正确，需要 {bets: [...]} 或直接是数组')
        sys.exit(1)
    print(f'      ✓ 共 {len(bets)} 条记录')

    # Step 2
    print(f'\n[2/4] 重算统计字段...')
    recalc = []
    for idx, b in enumerate(bets):
        new_b = dict(b)
        recalc.append(recalc_bet_stats(new_b))
        n = len(new_b.get('games', []))
        cmb = new_b.get('passCombos', [])
        pts = sorted(set(g.get('playType') for g in new_b.get('games', [])))
        sr = new_b['spRange']
        tsr = new_b.get('totalSpRange')
        tsr_str = f" totalSp=[{tsr['min']:.2f}~{tsr['max']:.2f}]" if tsr else ''
        print(f'      {idx+1:>2}. {n}场{cmb}关 {",".join(pts)}  sp=[{sr["min"]:.2f}~{sr["max"]:.2f}]{tsr_str}')
    print(f'      ✓ 完成。{len(recalc)} 条 totalSpRange 已按赛果枚举算法重新计算')

    # 写临时 JSON（可选入库）
    bets_json_str = json.dumps(recalc, ensure_ascii=False, indent=2)
    with open(BETS_TMP, 'w', encoding='utf-8') as f:
        f.write(bets_json_str)

    # Step 3
    print(f'\n[3/4] 注入 index.html _injectedBets 数组...')
    inject_into_html(bets_json_str)
    print(f'      ✓ 注入成功')

    # 校验拼写
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()
    if 'comboWinAmountst' in html:
        print('      ⚠ 警告: HTML 中检测到 comboWinAmountst 拼写错误')
    bad_count = html.count('comboWinAmountst')
    good_count = html.count('"comboWinAmounts": {}')
    print(f'      ✓ comboWinAmounts 校验: 错误{bad_count}处，正确{good_count}处')

    # Step 4
    print(f'\n[4/4] Git 提交 & 推送到 gh-pages...')
    ok = git_commit_push(len(recalc), src_name)
    if not ok:
        sys.exit(1)

    print('\n' + '=' * 60)
    print(f'  ✅ 全部完成！{len(recalc)} 条已推送')
    print(f'     等待 GitHub Pages 部署 1-2 分钟后 Ctrl+F5 刷新页面')
    print('=' * 60)


if __name__ == '__main__':
    main()
