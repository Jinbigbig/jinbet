with open(r'C:\Users\Jin\Desktop\jinbet_update\jinbet_update\update_163_odds.py', encoding='utf-8') as f:
    content = f.read()

# 1. Remove '其他': {} from initialization
content = content.replace(
    "            '其他': {},\n",
    ""
)

# 2. Remove the "同时提取其他" block
content = content.replace(
    '            # 同时提取"其他"\n            if \'胜其他\' in name: entry[\'其他\'][\'胜其他\'] = odds\n            elif \'平其他\' in name: entry[\'其他\'][\'平其他\'] = odds\n            elif \'负其他\' in name: entry[\'其他\'][\'负其他\'] = odds\n',
    ''
)

# 3. Update the hardcoded example data comment (瑞士 vs 加拿大 game)
content = content.replace(
    "          '其他': {'胜其他':'100', '平其他':'300', '负其他':'200'},\n          ",
    ""
)

with open(r'C:\Users\Jin\Desktop\jinbet_update\jinbet_update\update_163_odds.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
