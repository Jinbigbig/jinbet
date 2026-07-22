"""修复update_163_odds.py中的特定问题（查看第234-270行代码）。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(BASE_DIR, 'update_163_odds.py')

with open(TARGET, encoding='utf-8') as f:
    content = f.read()

# Show lines around 234-270
lines = content.split('\n')
for i in range(230, min(275, len(lines))):
    print(f'{i+1}: {repr(lines[i])}')
