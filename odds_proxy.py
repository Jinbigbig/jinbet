#!/usr/bin/env python3
"""本地HTTP代理服务（127.0.0.1:51888），帮浏览器从网易/百度抓取赔率和赛果数据，绕过浏览器CORS限制。"""
import http.server, json, re, urllib.request, html, threading, time

HOST, PORT = '127.0.0.1', 51888

# ── 解析百度体育赛果 ────────────────────────────────────────────────────
def fetch_baidu_results():
    url = "https://tiyu.baidu.com/al/match?match=%E4%B8%96%E7%95%8C%E6%9D%AF&tab=%E8%B5%9B%E7%A8%8B"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://tiyu.baidu.com/',
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')

def parse_baidu_results(html_content):
    results = []
    
    team_pattern = re.compile(r'team-row-name_3JDB3[^>]*>\s*<span[^>]*>\s*([^<]+?)\s*<')
    score_pattern = re.compile(r'team-row-score_3XZ7d[^>]*>\s*<span[^>]*>(\d+)</span>')
    
    team_matches = team_pattern.findall(html_content)
    score_matches = score_pattern.findall(html_content)
    
    match_count = min(len(team_matches) // 2, len(score_matches) // 2)
    for i in range(match_count):
        home_idx = i * 2
        away_idx = i * 2 + 1
        home = team_matches[home_idx].strip()
        away = team_matches[away_idx].strip()
        home_score = score_matches[home_idx] if home_idx < len(score_matches) else ''
        away_score = score_matches[away_idx] if away_idx < len(score_matches) else ''
        if home and away and home_score.isdigit() and away_score.isdigit():
            results.append({
                'home': home,
                'away': away,
                'score': f"{home_score}:{away_score}"
            })
    
    return results

# ── 解析163 ──────────────────────────────────────────────────────────────
def nparse(val):
    if isinstance(val, list) and len(val) == 2:
        tag, data = val
        if tag == 0: return data
        if tag == 1 and isinstance(data, list): return [nparse(i) for i in data]
    if isinstance(val, dict): return {k: nparse(v) for k, v in val.items()}
    if isinstance(val, list): return [nparse(i) for i in val]
    return val

def nget(obj, key):
    if not isinstance(obj, dict): return None
    raw = obj.get(key)
    return nparse(raw) if raw is not None else None

def parse_items(lst):
    r = {}
    for it in (nparse(lst) or []):
        if not isinstance(it, dict): continue
        n = nget(it, 'playItemName')
        o = nget(it, 'odds')
        if n and o is not None: r[str(n)] = str(o)
    return r

def fetch_odds():
    url = "https://sports.163.com/caipiao/bet/football"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://sports.163.com/',
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode('utf-8')
    m = re.search(r'<astro-island[^>]+component-url="[^"]*PageSports[^"]*"[^>]*props="([^"]*)"', raw, re.DOTALL)
    if not m: raise ValueError("未找到赔率数据")
    props = json.loads(html.unescape(m.group(1)))
    matches = []
    for grp in (nparse(nget(props, 'initList')) or []):
        if not isinstance(grp, dict): continue
        for rm in (nparse(nget(grp, 'matchList')) or []):
            h = nget(rm, 'homeTeam')
            g = nget(rm, 'guestTeam')
            if not h or not g: continue
            plays = {}
            for code, pval in (nget(rm, 'playMap') or {}).items():
                if isinstance(pval, dict):
                    plays[code] = {
                        'items': parse_items(nget(pval, 'playItemList')),
                        'concede': nget(pval, 'concede')
                    }
            matches.append({'home': nget(h, 'teamName'), 'guest': nget(g, 'teamName'), 'plays': plays})
    return matches

def convert(matches):
    result, order = {}, []
    for m in matches:
        h, g = m['home'], m['guest']
        if not h or not g: continue
        key = f"{h} vs {g}"
        order.append(key)
        e = {'胜': '', '平': '', '负': '', '让球': [], '比分': {}, '总进球': {}, '其他': {}, '半全场': {}}
        p = m['plays']
        hda = p.get('HDA', {})
        if hda.get('concede') == '0':
            for n, o in hda.get('items', {}).items():
                if n == '主胜': e['胜'] = o
                elif n == '平': e['平'] = o
                elif n == '客胜': e['负'] = o
        hhda = p.get('HHDA', {})
        if hhda:
            im = {n: o for n, o in hhda.get('items', {}).items()}
            if im: e['让球'] = [{'concede': hhda.get('concede', '0'), '胜': im.get('主胜', ''), '平': im.get('平', ''), '负': im.get('客胜', '')}]
        for n, o in p.get('FBF', {}).get('items', {}).items(): e['比分'][n] = o
        for n, o in p.get('FJQ', {}).get('items', {}).items(): e['总进球'][n] = o
        for n, o in p.get('FBQC', {}).get('items', {}).items(): e['半全场'][n] = o
        result[key] = e
    return result, order

# ── HTTP服务 ─────────────────────────────────────────────────────────────
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        try:
            if self.path == '/odds':
                matches = fetch_odds()
                odds_vs, order = convert(matches)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'data': odds_vs, 'order': order, 'count': len(odds_vs)}).encode())
                return
            if self.path == '/cron-update':
                matches = fetch_odds()
                odds_vs, order = convert(matches)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'count': len(odds_vs)}).encode())
                print(f"[{time.strftime('%H:%M:%S')}] cron更新成功: {len(odds_vs)}场", flush=True)
                return
            if self.path == '/port':
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'51888')
                return
            if self.path == '/results':
                html_content = fetch_baidu_results()
                results = parse_baidu_results(html_content)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'data': results, 'count': len(results)}).encode())
                print(f"[{time.strftime('%H:%M:%S')}] 赛果抓取成功: {len(results)}场", flush=True)
                return
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode())
            except: pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.end_headers()

srv = http.server.HTTPServer((HOST, PORT), H)
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()
print(f"代理已启动，监听 http://127.0.0.1:{PORT}", flush=True)
print(f"赔率接口: curl http://127.0.0.1:{PORT}/odds", flush=True)
print(f"Cron触发: curl http://127.0.0.1:{PORT}/cron-update", flush=True)
print(f"按 Ctrl+C 停止", flush=True)

# 保持运行（主线程不能退出）
while True:
    time.sleep(86400)
