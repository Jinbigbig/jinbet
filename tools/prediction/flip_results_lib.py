# -*- coding: utf-8 -*-
"""
赛果库主客方向翻转修复工具

背景（已证）：results_data.json 全部条目的 home/away 相对官方源（网易竞彩 / 体彩）
系统性颠倒 —— 532/532 场、比分完全镜像。SCHEDULE / ODDS 方向是正确的，只有赛果库颠倒。

本脚本把单条赛果条目做「主客镜像」变换，得到一个语义等价的正确方向条目。

用法：
  python flip_results_lib.py --in results_data.json --out /tmp/flipped.json     # 生成翻转副本（不改原文件）
  python flip_results_lib.py --selftest                                        # 自检：翻转两次应回到原状
"""
import json, os, sys, copy

_BQC = {'胜胜': '负负', '胜平': '负平', '胜负': '负胜',
        '平胜': '平负', '平平': '平平', '平负': '平胜',
        '负胜': '胜负', '负平': '胜平', '负负': '胜胜'}
_BF_OTHER = {'胜其他': '负其他', '负其他': '胜其他', '平其他': '平其他'}


def _mirror_score(s):
    if not isinstance(s, str) or ':' not in s:
        return s
    parts = s.split(':')
    if len(parts) != 2:
        return s
    return f'{parts[1]}:{parts[0]}'


def _flip_handicap(h):
    if h is None:
        return h
    s = str(h).strip()
    if s in ('', '0'):
        return s
    try:
        v = int(s)
    except Exception:
        return h
    if v > 0:
        return f'-{v}'
    if v < 0:
        return f'+{-v}'
    return '0'


def _swap(a, b):
    return (b, a)


def flip_entry(key, e):
    """把一条赛果条目翻转为相反的主客方向。返回 (new_key, new_entry)。"""
    if not isinstance(e, dict):
        return key, e
    n = dict(e)
    # --- key ---
    p = key.split('_', 2)
    if len(p) == 3:
        new_key = f'{p[0]}_{p[2]}_{p[1]}'
    else:
        new_key = key
    # --- 队名 ---
    if 'home' in n or 'away' in n:
        n['home'], n['away'] = _swap(n.get('home'), n.get('away'))
    # --- 比分 ---
    for f in ('score', 'fullScore', 'halfScore'):
        if f in n:
            n[f] = _mirror_score(n[f])
    # --- 胜负标志 ---
    wf = n.get('winFlag')
    if wf in ('H', 'A'):
        n['winFlag'] = 'A' if wf == 'H' else 'H'
    # --- 胜平负赔率（胜=主胜，负=客胜）---
    for hk, ak in (('胜', '负'), ('hda胜', 'hda负'), ('hhda胜', 'hhda负')):
        if hk in n or ak in n:
            n[hk], n[ak] = _swap(n.get(hk), n.get(ak))
    # --- 让球盘 ---
    if 'handicap' in n:
        n['handicap'] = _flip_handicap(n['handicap'])
    if isinstance(n.get('让球'), list):
        rl = []
        for it in n['让球']:
            if not isinstance(it, dict):
                rl.append(it)
                continue
            j = dict(it)
            j['handicap'] = _flip_handicap(j.get('handicap'))
            j['胜'], j['负'] = _swap(j.get('胜'), j.get('负'))
            rl.append(j)
        n['让球'] = rl
    # --- 比分盘 ---
    if isinstance(n.get('比分'), dict):
        nb = {}
        for k, v in n['比分'].items():
            if k in _BF_OTHER:
                nk = _BF_OTHER[k]
            elif ':' in k:
                nk = _mirror_score(k)
            else:
                nk = k
            nb[nk] = v
        n['比分'] = nb
    # --- 半全场 ---
    if isinstance(n.get('半全场'), dict):
        n['半全场'] = {_BQC.get(k, k): v for k, v in n['半全场'].items()}
    # --- 总进球：主客无关 ---
    return new_key, n


def flip_all(lib):
    out = {}
    for k, v in lib.items():
        nk, nv = flip_entry(k, v)
        if nk in out:
            # 冲突：保留信息更全的一条
            cur = out[nk]
            rich_new = sum(1 for f in ('胜', '让球', '比分', '总进球', '半全场') if nv.get(f))
            rich_cur = sum(1 for f in ('胜', '让球', '比分', '总进球', '半全场') if cur.get(f))
            if rich_new <= rich_cur:
                continue
        out[nk] = nv
    return out


def main():
    args = sys.argv[1:]
    if '--selftest' in args:
        sample = {
            '2026-09-09_费耶诺德_巴萨': {
                'home': '费耶诺德', 'away': '巴萨', 'score': '1:5', 'fullScore': '1:5',
                'halfScore': '0:2', 'winFlag': 'A', 'handicap': '+1',
                '胜': '6.5', '平': '5.0', '负': '1.35',
                '让球': [{'handicap': '+1', '胜': '2.5', '平': '3.6', '负': '2.2'}],
                '比分': {'1:0': '13', '0:1': '9', '胜其他': '80', '负其他': '40'},
                '总进球': {'0': '16', '1': '6'},
                '半全场': {'胜胜': '8.25', '负负': '30', '平平': '8.1'},
            }
        }
        once = flip_all(sample)
        twice = flip_all(once)
        k0 = list(sample.keys())[0]
        print('一次翻转:', json.dumps(once, ensure_ascii=False, indent=2))
        print('二次翻转与原始相同:', json.dumps(twice, ensure_ascii=False, sort_keys=True)
              == json.dumps(sample, ensure_ascii=False, sort_keys=True))
        return
    src = dst = None
    for i, a in enumerate(args):
        if a == '--in':
            src = args[i + 1]
        if a == '--out':
            dst = args[i + 1]
    if not src or not dst:
        print(__doc__)
        return
    lib = json.load(open(src, encoding='utf-8'))
    out = flip_all(lib)
    json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'✅ {len(lib)} 条 → 翻转 {len(out)} 条，写出 {dst}')


if __name__ == '__main__':
    main()
