# -*- coding: utf-8 -*-
"""把 index.html 的 RESULTS 块按 results_data.json 重写（用于方向修复后的同步）"""
import json, os, sys, importlib.util

ROOT = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('uon', os.path.join(ROOT, 'update_odds_net.py'))
uon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uon)

HTML = os.path.join(ROOT, 'index.html')
html = open(HTML, encoding='utf-8').read()
data = json.load(open(os.path.join(ROOT, 'results_data.json'), encoding='utf-8'))
new = uon.update_html_results(html, data)
assert new != html, 'RESULTS 块未发生变化'
open(HTML, 'w', encoding='utf-8').write(new)
print(f'✅ index.html RESULTS 已按 results_data.json 重写（{len(data)} 条）')
