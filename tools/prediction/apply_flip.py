# -*- coding: utf-8 -*-
"""一次性修复：翻转 results_data.json 与 results_history/*.json 的主客方向。
原文件备份到 _flip_backup/。"""
import json, os, glob, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flip_results_lib import flip_all

ROOT = os.path.dirname(os.path.abspath(__file__))
BK = os.path.join(ROOT, '_flip_backup')
os.makedirs(os.path.join(BK, 'results_history'), exist_ok=True)

APPLY = '--apply' in sys.argv

# 1) results_data.json
p = os.path.join(ROOT, 'results_data.json')
shutil.copy2(p, os.path.join(BK, 'results_data.json'))
lib = json.load(open(p, encoding='utf-8'))
out = flip_all(lib)
print(f'results_data.json: {len(lib)} → {len(out)} 条')
if APPLY:
    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

# 2) results_history/*.json
tot_in = tot_out = 0
for fp in sorted(glob.glob(os.path.join(ROOT, 'results_history', '*.json'))):
    base = os.path.basename(fp)
    if base == 'index.json':
        continue
    shutil.copy2(fp, os.path.join(BK, 'results_history', base))
    d = json.load(open(fp, encoding='utf-8'))
    if not isinstance(d, dict):
        continue
    f = flip_all(d)
    tot_in += len(d); tot_out += len(f)
    if APPLY:
        json.dump(f, open(fp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'results_history/: {tot_in} → {tot_out} 条')
print('已应用' if APPLY else '（试算，未写盘；加 --apply 生效）')
