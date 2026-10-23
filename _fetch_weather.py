#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""赛前天气（Open-Meteo，免费无需 Key）→ weather.json

用途：逐场显示比赛当地比赛时段的天气，判断雨战/大风对进球数的影响。

数据链路：
  主队中文简称 → 主场城市（TEAM_CITY）→ 经纬度（stadium_geo.json 缓存，
  缺失时调 Open-Meteo Geocoding 现查并写回）→ 比赛日当地 18:00~23:00 逐时
  气温/降雨概率/降水量/风速 → 汇总成一行结论。

口径说明：
  · 中国竞彩不含开球时刻，故取当地晚间 18:00-23:00 作为比赛时段窗口
    （欧洲联赛主流开球区间；跨零点场次取 18:00-23:00 仍覆盖绝大部分）。
  · 只有 1 个免费源（Open-Meteo）可用；World Weather Online 需付费 Key，
    Transfermarkt/PL 官方等伤停源详见 _fetch_injuries.py 的说明。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

GEO_CACHE = 'stadium_geo.json'
OUT = 'weather.json'

# 球队中文简称（竞彩官方简称）→ 主场所在城市（英文，供 Geocoding 使用）
TEAM_CITY = {
    # 2026-10-23 补充：欧战缺失映射
    '格风暴': 'Graz', '波兹南': 'Poznan', '萨迪纳摩': 'Zagreb', '尤文图斯': 'Turin',
    '克里特': 'Heraklion', '贝西克塔': 'Istanbul', '利勒斯特': 'Lillestrom',
    '尤文': 'Turin', '博德闪耀': 'Bodo', '布拉加': 'Braga', '费伦茨瓦': 'Budapest',
    # 日本
    '东京FC': 'Tokyo', '柏太阳神': 'Kashiwa', '川崎前锋': 'Kawasaki', '神户胜利': 'Kobe',
    '横滨水手': 'Yokohama', '浦和红钻': 'Saitama', '鹿岛鹿角': 'Kashima', '名古屋鲸': 'Nagoya',
    '大阪钢巴': 'Osaka', '大阪樱花': 'Osaka', '广岛三箭': 'Hiroshima', '福冈黄蜂': 'Fukuoka',
    '大宫松鼠': 'Saitama', '富山胜利': 'Toyama', '町田泽维': 'Machida', '京都': 'Kyoto',
    # 英格兰
    '曼联': 'Manchester', '曼城': 'Manchester', '阿森纳': 'London', '切尔西': 'London',
    '热刺': 'London', '西汉姆': 'London', '水晶宫': 'London', '富勒姆': 'London',
    '布伦特福德': 'London', '维拉': 'Birmingham', '利物浦': 'Liverpool', '埃弗顿': 'Liverpool',
    '纽卡斯尔': 'Newcastle upon Tyne', '布莱顿': 'Brighton', '狼队': 'Wolverhampton',
    '诺丁汉森林': 'Nottingham', '伯恩茅斯': 'Bournemouth', '伯恩利': 'Burnley',
    '利兹联': 'Leeds', '桑德兰': 'Sunderland', '莱切斯特': 'Leicester', '南安普敦': 'Southampton',
    # 西班牙
    '皇马': 'Madrid', '马竞': 'Madrid', '赫塔菲': 'Madrid', '巴列卡诺': 'Madrid',
    '巴萨': 'Barcelona', '西班牙人': 'Barcelona', '贝蒂斯': 'Seville', '塞维利亚': 'Seville',
    '莱万特': 'Valencia', '瓦伦西亚': 'Valencia', '毕尔巴鄂': 'Bilbao',
    '比利亚雷亚尔': 'Villarreal', '皇家社会': 'San Sebastian', '塞尔塔': 'Vigo',
    '奥萨苏纳': 'Pamplona', '马洛卡': 'Palma', '阿拉维斯': 'Vitoria-Gasteiz',
    '赫罗纳': 'Girona', '埃尔切': 'Elche', '奥维耶多': 'Oviedo',
    # 意大利
    '科莫': 'Como', '国米': 'Milan', 'AC米兰': 'Milan', '尤文': 'Turin', '都灵': 'Turin',
    '那不勒斯': 'Naples', '罗马': 'Rome', '拉齐奥': 'Rome', '亚特兰大': 'Bergamo',
    '佛罗伦萨': 'Florence', '博洛尼亚': 'Bologna', '热那亚': 'Genoa', '乌迪内斯': 'Udine',
    '莱切': 'Lecce', '卡利亚里': 'Cagliari', '萨索洛': 'Reggio Emilia', '比萨': 'Pisa',
    '维罗纳': 'Verona', '帕尔马': 'Parma', '克雷莫纳': 'Cremona',
    # 德国
    '拜仁': 'Munich', '多特': 'Dortmund', '莱红牛': 'Leipzig', '勒沃库森': 'Leverkusen',
    '斯图加特': 'Stuttgart', '法兰克福': 'Frankfurt', '云达不来梅': 'Bremen',
    '弗莱堡': 'Freiburg', '门兴': 'Monchengladbach', '沃夫斯堡': 'Wolfsburg',
    '霍芬海姆': 'Sinsheim', '美因茨': 'Mainz', '奥格斯堡': 'Augsburg',
    '柏林联合': 'Berlin', '汉堡': 'Hamburg', '科隆': 'Cologne', '海登海姆': 'Heidenheim',
    '圣保利': 'Hamburg',
    # 法国
    '里尔': 'Lille', '朗斯': 'Lens', '巴黎圣曼': 'Paris', '巴黎FC': 'Paris',
    '马赛': 'Marseille', '摩纳哥': 'Monaco', '里昂': 'Lyon', '尼斯': 'Nice',
    '雷恩': 'Rennes', '南特': 'Nantes', '斯特拉斯堡': 'Strasbourg', '图卢兹': 'Toulouse',
    '蒙彼利埃': 'Montpellier', '布雷斯特': 'Brest', '兰斯': 'Reims', '欧塞尔': 'Auxerre',
    '勒阿弗尔': 'Le Havre', '昂热': 'Angers', '梅斯': 'Metz', '洛里昂': 'Lorient',
    # 荷兰 / 葡萄牙 / 比利时
    '费耶诺德': 'Rotterdam', '阿贾克斯': 'Amsterdam', '埃因霍温': 'Eindhoven',
    '特温特': 'Enschede', '乌德勒支': 'Utrecht', '阿尔克马': 'Alkmaar',
    '里斯本': 'Lisbon', '本菲卡': 'Lisbon', '波尔图': 'Porto', '布拉加': 'Braga',
    '布鲁日': 'Bruges', '安德莱赫特': 'Brussels', '根特': 'Ghent',
    # 土耳其 / 奥地利 / 瑞士 / 苏格兰
    '加拉塔萨': 'Istanbul', '费内巴切': 'Istanbul', '贝西克塔斯': 'Istanbul',
    'LASK林茨': 'Linz', '萨尔茨堡': 'Salzburg', '格拉茨': 'Graz', '维也纳快速': 'Vienna',
    '巴塞尔': 'Basel', '年轻人': 'Bern', '凯尔特人': 'Glasgow', '流浪者': 'Glasgow',
    # 北欧 / 东欧
    '维京': 'Stavanger', '博德闪耀': 'Bodo', '罗森博格': 'Trondheim', '莫尔德': 'Molde',
    '布兰': 'Bergen', '哥本哈根': 'Copenhagen', '中日德兰': 'Herning',
    '马尔默': 'Malmo', '赫尔辛基': 'Helsinki',
    # 巴西 / 南美
    '帕梅拉斯': 'Sao Paulo', '科林蒂安': 'Sao Paulo', '圣保罗': 'Sao Paulo',
    '弗鲁米嫩': 'Rio de Janeiro', '弗拉门戈': 'Rio de Janeiro', '博塔弗戈': 'Rio de Janeiro',
    '达伽马': 'Rio de Janeiro', '克鲁塞罗': 'Belo Horizonte', '米内罗竞技': 'Belo Horizonte',
    '格雷米奥': 'Porto Alegre', '国际': 'Porto Alegre', '巴伊亚': 'Salvador',
    '福塔雷萨': 'Fortaleza', '桑托斯': 'Santos', '布拉干蒂诺': 'Braganca Paulista',
}

# 英文城市 → 中文（缺失则保留英文，不影响出报告）
CITY_ZH = {
    'Tokyo': '东京', 'Kashiwa': '柏市', 'Kawasaki': '川崎', 'Kobe': '神户',
    'Yokohama': '横滨', 'Saitama': '埼玉', 'Kashima': '鹿岛', 'Nagoya': '名古屋',
    'Osaka': '大阪', 'Hiroshima': '广岛', 'Fukuoka': '福冈', 'Toyama': '富山',
    'Machida': '町田', 'Kyoto': '京都',
    'Manchester': '曼彻斯特', 'London': '伦敦', 'Birmingham': '伯明翰',
    'Liverpool': '利物浦', 'Newcastle upon Tyne': '纽卡斯尔', 'Brighton': '布莱顿',
    'Wolverhampton': '伍尔弗汉普顿', 'Nottingham': '诺丁汉', 'Bournemouth': '伯恩茅斯',
    'Burnley': '伯恩利', 'Leeds': '利兹', 'Sunderland': '桑德兰',
    'Leicester': '莱斯特', 'Southampton': '南安普敦',
    'Madrid': '马德里', 'Barcelona': '巴塞罗那', 'Seville': '塞维利亚',
    'Valencia': '瓦伦西亚', 'Bilbao': '毕尔巴鄂', 'Villarreal': '比利亚雷亚尔',
    'San Sebastian': '圣塞瓦斯蒂安', 'Vigo': '维戈', 'Pamplona': '潘普洛纳',
    'Palma': '帕尔马', 'Vitoria-Gasteiz': '维多利亚', 'Girona': '赫罗纳',
    'Elche': '埃尔切', 'Oviedo': '奥维耶多',
    'Como': '科莫', 'Milan': '米兰', 'Turin': '都灵', 'Naples': '那不勒斯',
    'Rome': '罗马', 'Bergamo': '贝加莫', 'Florence': '佛罗伦萨', 'Bologna': '博洛尼亚',
    'Genoa': '热那亚', 'Udine': '乌迪内', 'Lecce': '莱切', 'Cagliari': '卡利亚里',
    'Reggio Emilia': '雷焦艾米利亚', 'Pisa': '比萨', 'Verona': '维罗纳',
    'Parma': '帕尔马', 'Cremona': '克雷莫纳',
    'Munich': '慕尼黑', 'Dortmund': '多特蒙德', 'Leipzig': '莱比锡',
    'Leverkusen': '勒沃库森', 'Stuttgart': '斯图加特', 'Frankfurt': '法兰克福',
    'Bremen': '不来梅', 'Freiburg': '弗莱堡', 'Monchengladbach': '门兴格拉德巴赫',
    'Wolfsburg': '沃尔夫斯堡', 'Sinsheim': '辛斯海姆', 'Mainz': '美因茨',
    'Augsburg': '奥格斯堡', 'Berlin': '柏林', 'Hamburg': '汉堡', 'Cologne': '科隆',
    'Heidenheim': '海登海姆',
    'Lille': '里尔', 'Lens': '朗斯', 'Paris': '巴黎', 'Marseille': '马赛',
    'Monaco': '摩纳哥', 'Lyon': '里昂', 'Nice': '尼斯', 'Rennes': '雷恩',
    'Nantes': '南特', 'Strasbourg': '斯特拉斯堡', 'Toulouse': '图卢兹',
    'Montpellier': '蒙彼利埃', 'Brest': '布雷斯特', 'Reims': '兰斯',
    'Auxerre': '欧塞尔', 'Le Havre': '勒阿弗尔', 'Angers': '昂热',
    'Metz': '梅斯', 'Lorient': '洛里昂',
    'Rotterdam': '鹿特丹', 'Amsterdam': '阿姆斯特丹', 'Eindhoven': '埃因霍温',
    'Enschede': '恩斯赫德', 'Utrecht': '乌得勒支', 'Alkmaar': '阿尔克马尔',
    'Lisbon': '里斯本', 'Porto': '波尔图', 'Braga': '布拉加',
    'Bruges': '布鲁日', 'Brussels': '布鲁塞尔', 'Ghent': '根特',
    'Istanbul': '伊斯坦布尔', 'Linz': '林茨', 'Salzburg': '萨尔茨堡',
    'Graz': '格拉茨', 'Vienna': '维也纳', 'Basel': '巴塞尔', 'Bern': '伯尔尼',
    'Glasgow': '格拉斯哥', 'Stavanger': '斯塔万格', 'Bodo': '博德',
    'Trondheim': '特隆赫姆', 'Molde': '莫尔德', 'Bergen': '卑尔根',
    'Copenhagen': '哥本哈根', 'Herning': '海宁', 'Malmo': '马尔默', 'Helsinki': '赫尔辛基',
    'Sao Paulo': '圣保罗', 'Rio de Janeiro': '里约热内卢',
    'Belo Horizonte': '贝洛奥里藏特', 'Porto Alegre': '阿雷格里港',
    'Salvador': '萨尔瓦多', 'Fortaleza': '福塔莱萨', 'Santos': '桑托斯',
    'Braganca Paulista': '布拉干萨保利斯塔',
}

GRADE_TXT = {
    'bad': '恶劣',
    'warn': '需留意',
    'ok': '正常',
}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/131.0 Safari/537.36',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def load_geo():
    try:
        return json.load(open(GEO_CACHE, encoding='utf-8'))
    except Exception:
        return {}


def geocode(city, cache):
    """按城市名查经纬度，命中缓存直接返回。"""
    key = city.strip().lower()
    for k, v in cache.items():
        if k.strip().lower() == key:
            return v
    url = ('https://geocoding-api.open-meteo.com/v1/search?name=%s&count=1&language=en&format=json'
           % urllib.parse.quote(city))
    try:
        js = _get(url)
        res = (js.get('results') or [None])[0]
        if not res:
            return None
        v = {'lat': res['latitude'], 'lon': res['longitude'],
             'name': res.get('name'), 'country': res.get('country')}
        cache[city] = v
        return v
    except Exception as e:
        print(f'  [geo] {city} 查询失败: {e}')
        return None


def fetch_one(lat, lon, date):
    url = ('https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f'
           '&hourly=temperature_2m,precipitation_probability,precipitation,wind_speed_10m'
           '&wind_speed_unit=kmh'
           '&start_date=%s&end_date=%s&timezone=auto' % (lat, lon, date, date))
    js = _get(url)
    h = js.get('hourly') or {}
    times = h.get('time') or []
    pick = [i for i, t in enumerate(times) if 18 <= int(t[11:13]) <= 23]
    if not pick:
        return None

    def col(name):
        arr = h.get(name) or []
        return [arr[i] for i in pick if i < len(arr) and arr[i] is not None]

    temps, pops, rains, winds = col('temperature_2m'), col('precipitation_probability'), \
        col('precipitation'), col('wind_speed_10m')
    if not temps:
        return None
    d = {
        't_min': round(min(temps), 1), 't_max': round(max(temps), 1),
        'pop': int(max(pops) if pops else 0),
        'rain': round(max(rains) if rains else 0.0, 1),
        'wind': round(max(winds) if winds else 0.0, 1),
    }
    # 风速单位 km/h：35 km/h ≈ 5 级风（明显影响长传与射门），25 km/h ≈ 4 级
    if d['pop'] >= 70 or d['rain'] >= 5 or d['wind'] >= 35:
        d['grade'] = 'bad'
    elif d['pop'] >= 40 or d['rain'] >= 1 or d['wind'] >= 25:
        d['grade'] = 'warn'
    else:
        d['grade'] = 'ok'
    return d


def main():
    calc = json.load(open('_calc_result.json', encoding='utf-8'))
    today = calc['today']
    matches = calc.get('matches') or []
    cache = load_geo()
    out = {'date': today, 'updated': time.strftime('%Y-%m-%d %H:%M'), 'matches': {}}
    miss = []
    for m in matches:
        home = m.get('home') or ''
        city = TEAM_CITY.get(home)
        if not city:
            miss.append(home)
            continue
        geo = geocode(city, cache)
        if not geo:
            miss.append(home)
            continue
        try:
            w = fetch_one(geo['lat'], geo['lon'], today)
        except Exception as e:
            print(f'  [weather] {m.get("matchNumStr")} {home} 失败: {e}')
            continue
        if not w:
            continue
        w['city'] = CITY_ZH.get(city) or CITY_ZH.get(geo.get('name') or '') or (geo.get('name') or city)
        w['country'] = geo.get('country') or ''
        out['matches'][m.get('matchNumStr') or f'{home}vs{m.get("away")}'] = w
        time.sleep(0.35)  # 免费 API 限流友好
    json.dump(cache, open(GEO_CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'[天气] {today}：{len(out["matches"])}/{len(matches)} 场已取到')
    if miss:
        print(f'[天气] 缺城市映射 {len(miss)} 队：' + '、'.join(dict.fromkeys(miss)))
    bad = [k for k, v in out['matches'].items() if v['grade'] != 'ok']
    if bad:
        print('[天气] 需留意场次：' + '、'.join(
            f'{k}({GRADE_TXT[out["matches"][k]["grade"]]})' for k in bad))
    return 0


if __name__ == '__main__':
    sys.exit(main())
