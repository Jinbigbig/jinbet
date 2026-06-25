import re
import os

# 路径自动定位：脚本位于 tools/，目标文件在上级目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(BASE_DIR, 'index.html')

with open(INDEX_HTML, encoding='utf-8') as f:
    content = f.read()

# Find all 胜/平/负其他 in the injected data section (after line ~10900)
lines = content.split('\n')
in_section = False
in_bf = False
bf_counts = {'胜其他': 0, '平其他': 0, '负其他': 0}
for i, line in enumerate(lines):
    if '"其他": {' in line:
        in_section = True
    if in_section and ('"比分":' in line or '"胜其他"' in line or '"平其他"' in line or '"负其他"' in line):
        if '"比分":' in line:
            in_bf = True
        if '"胜其他"' in line: bf_counts['胜其他'] += 1
        if '"平其他"' in line: bf_counts['平其他'] += 1
        if '"负其他"' in line: bf_counts['负其他'] += 1
    if in_section and '"半全场":' in line:
        in_bf = False
    if in_section and '"总进球":' in line:
        in_bf = False

print(f"比分 section stats: 胜其他={bf_counts['胜其他']}, 平其他={bf_counts['平其他']}, 负其他={bf_counts['负其他']}")

# Check if '其他' block still exists
if '"其他": {' in content[50000:]:
    print("WARNING: '其他' block still exists!")
else:
    print("OK: '其他' block removed")
