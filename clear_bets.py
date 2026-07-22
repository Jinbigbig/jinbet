# -*- coding: utf-8 -*-
"""将index.html中的_injectedBets数组置为空数组，删除线上已推送的所有投注记录。运行时需输入YES确认。"""
import sys, os, io, re, subprocess, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, 'index.html')
INJECTED_PATH = os.path.join(BASE_DIR, '_injected_bets.json')

SEPARATOR = '=' * 60


def current_bet_count():
    """先尝试统计 index.html 中当前 _injectedBets 有几条记录"""
    try:
        with open(HTML_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        marker = 'var _injectedBets = '
        start = content.find(marker)
        if start == -1:
            return -1
        # 找到数组起止并解析
        arr_start = content.find('[', start + len(marker))
        stack = 1
        i = arr_start + 1
        in_str = None
        esc = False
        arr_end = -1
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
                if c in ('"', "'"):
                    in_str = c
                elif c == '[':
                    stack += 1
                elif c == ']':
                    stack -= 1
                    if stack == 0:
                        arr_end = i
                        break
            i += 1
        if arr_end == -1:
            return -1
        arr_json = content[arr_start:arr_end + 1]
        data = json.loads(arr_json)
        return len(data) if isinstance(data, list) else -1
    except Exception:
        return -1


def clear_injected_bets_html():
    """把 index.html 中的 var _injectedBets = [...] 替换为 []"""
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    marker = 'var _injectedBets = '
    start = content.find(marker)
    if start == -1:
        raise RuntimeError('index.html 中找不到 var _injectedBets = 标记')

    arr_start = content.find('[', start + len(marker))
    stack = 1
    i = arr_start + 1
    in_str = None
    esc = False
    arr_end = -1
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
            if c in ('"', "'"):
                in_str = c
            elif c == '[':
                stack += 1
            elif c == ']':
                stack -= 1
                if stack == 0:
                    arr_end = i
                    break
        i += 1
    if arr_end == -1:
        raise RuntimeError('未找到 _injectedBets 数组的结束 ]')

    semi = content.find(';', arr_end)
    if semi == -1:
        raise RuntimeError('未找到 _injectedBets 数组后的分号')

    new_section = marker + '[];'
    new_content = content[:start] + new_section + content[semi + 1:]

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)


def clear_injected_json():
    """同步清空 _injected_bets.json（保持为 []）"""
    with open(INJECTED_PATH, 'w', encoding='utf-8') as f:
        f.write('[]\n')


def run_git(*args):
    cmd = ['git', '--no-pager'] + list(args)
    print(f'\n> git {" ".join(args)}')
    res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, encoding='utf-8', errors='replace')
    if res.stdout.strip():
        print(res.stdout.rstrip())
    if res.stderr.strip():
        print(res.stderr.rstrip(), file=sys.stderr)
    return res


def main():
    print(SEPARATOR)
    print('  ⚠️   清空线上投注记录  ⚠️')
    print(SEPARATOR)
    print()
    n = current_bet_count()
    if n >= 0:
        print(f'  当前 _injectedBets 中有  {n}  条投注记录。')
    else:
        print('  [警告] 无法读取当前 _injectedBets 中的记录数。')
    print()
    print('  执行后，线上所有已推送的投注记录将被清空且不可恢复！')
    print('  （浏览器 localStorage 中的本地数据不受影响）')
    print()

    # ------ 二次确认 ------
    print('请输入大写 YES 继续执行，其他任意输入将取消：', flush=True)
    try:
        confirm = input('> ').strip()
    except EOFError:
        confirm = ''
    if confirm != 'YES':
        print()
        print('[取消] 未输入 YES，已安全终止。')
        sys.exit(0)

    print()
    print('✓ 确认通过，开始清空...')
    print()

    # ------ Step 1: 清空 index.html _injectedBets ------
    print('[1/3] 清空 index.html _injectedBets ...')
    clear_injected_bets_html()
    print('      ✓ 已替换为 var _injectedBets = [];')

    # ------ Step 2: 同步清空本地 _injected_bets.json ------
    print('[2/3] 清空 _injected_bets.json ...')
    clear_injected_json()
    print('      ✓ 已保存为 []')

    # ------ Step 3: Git 提交 & 推送 ------
    print('[3/3] Git 提交 & 推送到 gh-pages ...')
    r = run_git('fetch', 'origin', 'gh-pages')
    if r.returncode != 0:
        print('      [警告] git fetch 失败（可能网络波动），继续尝试推送...')

    run_git('add', 'index.html')
    run_git('add', '_injected_bets.json')
    print()
    run_git('status', '--short')
    print()
    r = run_git('commit', '-m', '清空线上投注记录（_injectedBets 重置为 []）')
    if r.returncode != 0:
        print()
        print('[提示] git commit 无新变更（index.html 可能原本已是空数组）。')
    else:
        print()
        # 推送：先 force-with-lease，再退化为 force
        r = run_git('push', '--force-with-lease', 'origin', 'gh-pages')
        if r.returncode != 0:
            print('\n[警告] --force-with-lease 失败，尝试 --force 推送：')
            r = run_git('push', '--force', 'origin', 'gh-pages')
            if r.returncode != 0:
                print('\n[错误] 推送仍然失败（可能是网络问题），请稍后重试或手动 git push。')
                sys.exit(1)

    print()
    print(SEPARATOR)
    print('  ✓ 线上投注记录已清空')
    print('    等待 GitHub Pages 部署 1-2 分钟后 Ctrl+F5 刷新页面')
    print(SEPARATOR)


if __name__ == '__main__':
    main()
