with open(r'C:\Users\Jin\Desktop\jinbet_update\jinbet_update\update_163_odds.py', encoding='utf-8') as f:
    content = f.read()

# Show lines around 234-270
lines = content.split('\n')
for i in range(230, min(275, len(lines))):
    print(f'{i+1}: {repr(lines[i])}')
