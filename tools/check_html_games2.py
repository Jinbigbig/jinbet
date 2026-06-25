import re
import os

# 路径自动定位：脚本位于 tools/，目标文件在上级目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(BASE_DIR, 'index.html')

with open(INDEX_HTML, encoding='utf-8') as f:
    content = f.read()

# Find injected data section
idx = content.find("localStorage.setItem('worldcup_odds_v737'")
end_idx = content.find("});", idx)
injected = content[idx:end_idx+3]

# The injected data structure has 18 games. Each game has a 比分 object.
# Count games by looking for pattern: "DATE_HOME_GUEST": {
game_count = injected.count('": {')
print(f"Game objects in injected data: {game_count}")

# Count occurrences of 胜/平/负其他 in injected data
cnt = {
    '胜其他': injected.count('"胜其他"'),
    '平其他': injected.count('"平其他"'),
    '负其他': injected.count('"负其他"'),
}
print(f"Total: 胜其他={cnt['胜其他']}, 平其他={cnt['平其他']}, 负其他={cnt['负其他']}")
print(f"Per game: ~{cnt['胜其他']/game_count:.1f} each")
