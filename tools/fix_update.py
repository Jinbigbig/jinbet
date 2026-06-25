import os

# 路径自动定位：脚本位于 tools/，目标文件在上级目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(BASE_DIR, 'update_163_odds.py')

with open(TARGET, encoding='utf-8') as f:
    content = f.read()

# Show lines around 234-270
lines = content.split('\n')
for i in range(230, min(275, len(lines))):
    print(f'{i+1}: {repr(lines[i])}')
