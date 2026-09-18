# -*- coding: utf-8 -*-
"""扫描 7M 联赛 id，定位「英冠」等尚未收录联赛的 id（一次性探针）。"""
import json, re, sys
from concurrent.futures import ThreadPoolExecutor
import urllib.request

TARGETS = ['英格蘭冠軍', '英冠', '冠軍聯賽', '英格蘭聯賽錦標', '英格蘭足總']
URL = 'https://data.7m.com.cn/matches_data/{}/big/standing.js'


def probe(i):
    try:
        req = urllib.request.Request(URL.format(i), headers={'User-Agent': 'Mozilla/5.0'})
        raw = urllib.request.urlopen(req, timeout=6).read().decode('utf-8', 'ignore')
    except Exception:
        return None
    if 'f_sds_tn' not in raw:
        return None
    m = re.search(r'f_sds_ln\s*=\s*\[(.*?)\]', raw, re.S)
    name = ''
    if m:
        parts = re.findall(r"'([^']*)'", m.group(1))
        name = ' / '.join(parts[:3])
    if not name:
        m2 = re.search(r'f_sds_tn\s*=\s*\[(.*?)\]', raw, re.S)
        name = (m2.group(1)[:80] if m2 else '?')
    hit = any(t in name for t in TARGETS)
    return (i, name, hit)


ids = list(range(1, 261)) + list(range(600, 1001))
found = []
with ThreadPoolExecutor(max_workers=24) as ex:
    for r in ex.map(probe, ids):
        if r and r[2]:
            found.append(r)
            print('HIT', r[0], r[1], flush=True)
json.dump(found, open('_7m_scan_hits.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('done, hits =', len(found))
