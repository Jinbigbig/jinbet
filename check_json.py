"""读取并打印odds_data.json的更新时间、比赛数量和前5场赔率数据，用于快速验证数据是否正常。"""
import json, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
with open('odds_data.json','r',encoding='utf-8') as f:
    d = json.load(f)
print('updated:', d['updated'])
print('count:', d['count'])
for k in list(d['data'].keys())[:5]:
    v = d['data'][k]
    print(repr(k), '| 胜:', repr(v.get('胜')), '| 平:', repr(v.get('平')), '| 负:', repr(v.get('负')))
