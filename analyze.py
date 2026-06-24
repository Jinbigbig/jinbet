import re

with open(r'C:\Users\Jin\Desktop\jinbet_update\jinbet_update\index.html', encoding='utf-8') as f:
    content = f.read()

# Find the first game's data (瑞士 vs 加拿大)
idx = content.find('瑞士 vs 加拿大')
chunk = content[idx:idx+3000]
others = re.findall(r'"(胜其他|平其他|负其他)": "([^"]+)"', chunk)
print('First game occurrences:', others)

# Check the whole injected data section
idx2 = content.find("localStorage.setItem('worldcup_odds_v737'")
injected = content[idx2:]
all_game_blocks = re.findall(r'"(胜其他|平其他|负其他)": "([^"]+)"', injected)
from collections import Counter
c = Counter(k for k,v in all_game_blocks)
print('\nIn injected data:', dict(c))
print('Total occurrences in injected:', len(all_game_blocks))

# Check if '其他' block still exists in injected data
if '"其他": {' in injected:
    count = injected.count('"其他": {')
    print(f'\nWARNING: Still {count} "其他" blocks in injected data!')
else:
    print('\nOK: No standalone "其他" blocks in injected data')

# Check SCHEDULE section
idx3 = content.find('const SCHEDULE = {')
schedule_chunk = content[idx3:idx3+5000]
schedule_others = re.findall(r'"(胜其他|平其他|负其他)": "([^"]+)"', schedule_chunk)
print('\nIn SCHEDULE:', schedule_others)
