"""读取index.html，提取并打印所有比赛的基本信息，检查数据完整性。"""
import re
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(BASE_DIR, 'index.html')

with open(INDEX_HTML, encoding='utf-8') as f:
    content = f.read()

# Find injected data section
idx = content.find("localStorage.setItem('worldcup_odds_v737'")
injected = content[idx:]

# Extract all games' 比分 sections
# Pattern: "比分": { ... }
# We need to count how many games have 胜/平/负其他 in their 比分 sections

games_with_scores = re.findall(r'"比分": \{([^}]+(?:\{[^}]*\}[^}]*)*)\}', injected)
print(f"Found {len(games_with_scores)} 比分 sections")

# Count occurrences of 胜/平/负其他 in injected data
cnt = {
    '胜其他': injected.count('"胜其他"'),
    '平其他': injected.count('"平其他"'),
    '负其他': injected.count('"负其他"'),
}
print(f"In injected data: 胜其他={cnt['胜其他']}, 平其他={cnt['平其他']}, 负其他={cnt['负其他']}")
print(f"Expected: 18 each (one per game)")

# Check if standalone 其他 block exists
if '"其他": {' in injected:
    print("WARNING: 独立其他区块仍然存在!")
else:
    print("OK: 无独立其他区块")
