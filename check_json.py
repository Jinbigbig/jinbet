import json, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
with open('odds_data.json','r',encoding='utf-8') as f:
    d = json.load(f)
print('updated:', d['updated'])
print('count:', d['count'])
for k in list(d['data'].keys())[:5]:
    v = d['data'][k]
    print(repr(k), '| 胜:', repr(v.get('胜')), '| 平:', repr(v.get('平')), '| 负:', repr(v.get('负')))
