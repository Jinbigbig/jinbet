#!/usr/bin/env python3
"""
网易竞彩足球赔率自动更新 - 完整版
==========================================
功能:
  1. 抓取网易页面所有玩法赔率（胜平负/让球/比分/总进球/半全场）
  2. 转换为本地 oddsData 格式
  3. 注入到本地 HTML 文件（写入 localStorage，打开页面自动生效）
  4. 按网易页面顺序重排比赛
  5. 支持 cron 每小时自动执行
==========================================

用法:
  python3 update_163_odds.py           # 立即执行一次
  python3 update_163_odds.py --test  # 仅测试解析，不写入文件
  python3 update_163_odds.py --cron  # 显示定时任务配置说明
"""

import re, json, html, sys, os, argparse, datetime, urllib.request, urllib.error
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 配置 ──────────────────────────────────
LOCAL_HTML   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v7.28.html')
BACKUP_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'odds_backup')
LOG_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'odds_update.log')
STORAGE_KEY  = 'worldcup_odds_v738'        # 与 HTML 内的一致
# ────────────────────────────────────────────

def log(msg):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

# ── 网易数据解析 ──────────────────────────

def nparse(val):
    """递归解析网易 [tag, data] 格式"""
    if isinstance(val, list) and len(val) == 2:
        tag, data = val
        if tag == 0:
            return data
        if tag == 1 and isinstance(data, list):
            return [nparse(i) for i in data]
    if isinstance(val, dict):
        return {k: nparse(v) for k, v in val.items()}
    if isinstance(val, list):
        return [nparse(i) for i in val]
    return val

def nget(obj, key):
    if not isinstance(obj, dict):
        return None
    raw = obj.get(key)
    return nparse(raw) if raw is not None else None

def parse_play_items(play_item_list):
    items = {}
    parsed = nparse(play_item_list)
    if not isinstance(parsed, list):
        return items
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = nget(item, 'playItemName')
        odds = nget(item, 'odds')
        if name and odds is not None:
            items[name] = str(odds)
    return items

def fetch_163():
    url = "https://sports.163.com/caipiao/bet/football"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://sports.163.com/',
    }
    log(f"抓取: {url}")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8')

def extract_matches(html_content):
    """从网易页面 HTML 提取所有比赛数据"""
    m = re.search(
        r'<astro-island[^>]+component-url="[^"]*PageSports[^"]*"[^>]*props="([^"]*)"',
        html_content, re.DOTALL)
    if not m:
        raise ValueError("未找到 PageSports props 数据")

    props_str = html.unescape(m.group(1))
    log(f"props 数据长度: {len(props_str)} 字符")
    props = json.loads(props_str)

    init_list = nparse(nget(props, 'initList'))
    if not isinstance(init_list, list):
        raise ValueError("initList 格式异常")

    matches = []
    for group in init_list:
        if not isinstance(group, dict):
            continue
        match_list = nparse(nget(group, 'matchList'))
        if not isinstance(match_list, list):
            continue
        for raw in match_list:
            if not isinstance(raw, dict):
                continue
            home  = nget(raw, 'homeTeam')
            guest = nget(raw, 'guestTeam')
            if not home or not guest:
                continue

            plays = {}
            play_map = nget(raw, 'playMap')
            if isinstance(play_map, dict):
                for code, pval in play_map.items():
                    if not isinstance(pval, dict):
                        continue
                    plays[code] = {
                        'play_name': nget(pval, 'playName'),
                        'concede':   nget(pval, 'concede'),
                        'items':     parse_play_items(nget(pval, 'playItemList')),
                    }

            matches.append({
                'jc_num':    nget(raw, 'jcNum'),
                'home':      nget(home, 'teamName'),
                'guest':     nget(guest, 'teamName'),
                'match_time': nget(raw, 'matchTime'),
                'plays':     plays,
            })
    return matches

# ── 转换为本地 oddsData 格式 ──────────────


# ── 赛程表（需与 v7.28.html 同步）──────────────
SCHEDULE = {
    '2026-06-24': [
        { 'home': '葡萄牙', 'away': '乌兹别克斯坦' },
        { 'home': '英格兰', 'away': '加纳' },
        { 'home': '巴拿马', 'away': '克罗地亚' },
        { 'home': '哥伦比亚', 'away': '刚果（金）' },
    ],
    '2026-06-25': [
        { 'home': '瑞士', 'away': '加拿大' },
        { 'home': '波黑', 'away': '卡塔尔' },
        { 'home': '苏格兰', 'away': '巴西' },
        { 'home': '摩洛哥', 'away': '海地' },
        { 'home': '南非', 'away': '韩国' },
        { 'home': '捷克', 'away': '墨西哥' },
    ],
    '2026-06-26': [
        { 'home': '库拉索', 'away': '科特迪瓦' },
        { 'home': '厄瓜多尔', 'away': '德国' },
        { 'home': '突尼斯', 'away': '荷兰' },
        { 'home': '日本', 'away': '瑞典' },
        { 'home': '新西兰', 'away': '比利时' },
        { 'home': '埃及', 'away': '伊朗' },
    ],
    '2026-06-27': [
        { 'home': '佛得角', 'away': '乌拉圭' },
        { 'home': '沙特阿拉伯', 'away': '西班牙' },
        { 'home': '挪威', 'away': '法国' },
        { 'home': '塞内加尔', 'away': '伊拉克' },
        { 'home': '阿尔及利亚', 'away': '奥地利' },
        { 'home': '约旦', 'away': '阿根廷' },
        { 'home': '哥伦比亚', 'away': '葡萄牙' },
        { 'home': '刚果（金）', 'away': '乌兹别克斯坦' },
        { 'home': '克罗地亚', 'away': '加纳' },
        { 'home': '巴拿马', 'away': '英格兰' },
        { 'home': '巴拉圭', 'away': '澳大利亚' },
        { 'home': '土耳其', 'away': '美国' },
        { 'home': '佛得角', 'away': '沙特' },
        { 'home': '乌拉圭', 'away': '西班牙' },
    ],
}

EXTRA_VS_TO_DATE = {
    '巴拉圭 vs 澳大利亚': '2026-06-27',
    '土耳其 vs 美国': '2026-06-27',
    '佛得角 vs 沙特': '2026-06-27',
    '乌拉圭 vs 西班牙': '2026-06-27',
}

def vs_to_date_key(vs_key):
    for date, games in SCHEDULE.items():
        for g in games:
            if g['home'] + ' vs ' + g['away'] == vs_key:
                return date + '_' + g['home'] + '_' + g['away']
    if vs_key in EXTRA_VS_TO_DATE:
        d = EXTRA_VS_TO_DATE[vs_key]
        return d + '_' + vs_key.replace(' vs ', '_')
    return None

def convert_to_odds_data(matches_163):
    """
    网易数据 → 本地 oddsData 格式

    本地格式:
      oddsData = {
        "瑞士 vs 加拿大": {
          '胜': '2.21', '平': '2.71', '负': '3.25',
          '让球': [{handicap:'-1', '胜':'4.7', '平':'3.86', '负':'1.52'}],
          '比分': {'1:0':'8.25', '2:0':'10.5', ...},
          '总进球': {'0':'8', '1':'4.8', ...},
'半全场': {'胜胜':'3.85', ...}
        },
        ...
      }
    """
    odds_data = {}
    match_order = []

    for m in matches_163:
        h = m['home']
        g = m['guest']
        if not h or not g:
            continue
        key = f"{h} vs {g}"
        match_order.append(key)
        plays = m['plays']

        entry = {
            '胜': '', '平': '', '负': '',
            '让球': [],
            '比分': {},
            '总进球': {},
            '半全场': {},
        }

        # 胜平负（HDA，concede=0 为标准胜平负）
        hda = plays.get('HDA', {})
        if hda.get('concede') == '0':
            for name, odds in hda.get('items', {}).items():
                if name == '主胜': entry['胜'] = odds
                elif name == '平':   entry['平'] = odds
                elif name == '客胜': entry['负'] = odds

        # 让球（HHDA，concede≠0）
        hhda = plays.get('HHDA', {})
        if hhda:
            c = hhda.get('concede', '0')
            item_map = {}
            for name, odds in hhda.get('items', {}).items():
                if name == '主胜': item_map['胜'] = odds
                elif name == '平':   item_map['平'] = odds
                elif name == '客胜': item_map['负'] = odds
            if item_map:
                entry['让球'] = [{'handicap': c, **item_map}]

        # 比分（FBF）
        fbf = plays.get('FBF', {})
        score_items = fbf.get('items', {})
        for name, odds in score_items.items():
            entry['比分'][name] = odds

        # 总进球（FJQ）
        fjq = plays.get('FJQ', {})
        for name, odds in fjq.get('items', {}).items():
            entry['总进球'][name] = odds

        # 半全场（FBQC）
        fbqc = plays.get('FBQC', {})
        for name, odds in fbqc.get('items', {}).items():
            entry['半全场'][name] = odds

        odds_data[key] = entry

    return odds_data, match_order

# ── 注入 HTML 文件 ─────────────────────────

def inject_into_html(odds_data, match_order):
    """
    把赔率数据注入 HTML 文件：
    在 </script> 前插入 JS，直接给 oddsData 赋值并写入 localStorage
    这样 init() → loadFromStorage() 会自动读到最新数据
    """
    if not os.path.exists(LOCAL_HTML):
        log(f"❌ 文件不存在: {LOCAL_HTML}")
        return False

    with open(LOCAL_HTML, 'r', encoding='utf-8') as f:
        content = f.read()

    # 备份
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f"v7.28_backup_{ts}.html")
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    log(f"✅ 备份: {backup_path}")

    # 把数据序列化为 JS 字面量（JSON 是合法 JS）
    # 转换 key 格式：主队 vs 客队 → 日期_主队_客队
    odds_date_fmt = {}
    for k, v in odds_data.items():
        new_key = vs_to_date_key(k)
        if new_key:
            odds_date_fmt[new_key] = v
        else:
            log("  ⚠️  无法匹配日期: " + k)
    log(f"  日期格式转换: {len(odds_data)}场 → {len(odds_date_fmt)}场")
    odds_json   = json.dumps(odds_date_fmt, ensure_ascii=False, indent=2)
    order_json  = json.dumps(match_order, ensure_ascii=False)
    now_str     = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    # 构造注入 JS（直接赋值，不用 JSON.parse）
    # 注意：必须在 init() 调用之前执行，这样 loadFromStorage 才能读到新数据
    # 最佳位置：在 <script> 标签内、init() 定义之后、init() 调用之前
    inject_js = (
        "\n// === 网易赔率自动注入（" + now_str + "）===\n"
        "(function(){\n"
        "  try {\n"
        "    var data = " + odds_json + ";\n"
        "    var order = " + order_json + ";\n"
        "    localStorage.setItem('" + STORAGE_KEY + "', JSON.stringify(data));\n"
        "    localStorage.setItem('" + STORAGE_KEY + "_order', JSON.stringify(order));\n"
        "    console.log('[网易赔率] 已写入 localStorage，共' + Object.keys(data).length + '场');\n"
        "  } catch(e) {\n"
        "    console.error('[网易赔率] 注入失败', e);\n"
        "  }\n"
        "})();\n"
        "// === 结束注入 ===\n"
    )

    # 注入位置：在 init(); 调用前插入（init 在文件末尾）
    # 找 "init();" 这一行，在它前面插入
    init_call_pos = content.rfind('\ninit();\n')
    if init_call_pos == -1:
        # 备选：找 </script> 前插入（页面加载后执行，下次刷新生效）
        init_call_pos = content.rfind('</script>')
        if init_call_pos == -1:
            log("❌ 未找到注入位置（init() 或 </script>）")
            return False
        log("⚠️  未找到 init() 调用，将注入到 </script> 前（下次刷新生效）")

    new_content = content[:init_call_pos] + inject_js + content[init_call_pos:]

    with open(LOCAL_HTML, 'w', encoding='utf-8') as f:
        f.write(new_content)

    log(f"✅ 已注入: {LOCAL_HTML}")
    log(f"  赔率数据: {len(odds_data)} 场")
    log(f"  比赛顺序: {len(match_order)} 场")
    log(f"  ⚠️  请刷新浏览器页面（F5）使数据生效")
    return True

# ── 定时任务配置 ─────────────────────────

def setup_cron():
    script_path = os.path.abspath(__file__)
    python_path = sys.executable or '/usr/bin/python3'

    log("=" * 50)
    log("定时任务配置说明")
    log("=" * 50)
    log("")
    log("【方案A】crontab（每分钟执行一次）:")
    log(f"  (1) 运行: crontab -e")
    log(f"  (2) 添加一行:")
    log(f"      0 * * * * {python_path} {script_path} >> {LOG_FILE} 2>&1")
    log("")
    log("【方案B】直接运行以下命令配置 cron（需要 sudo）:")
    log(f"  echo '0 * * * * {python_path} {script_path} >> {LOG_FILE} 2>&1' | crontab -")
    log("")
    log(f"日志文件: {LOG_FILE}")
    log(f"查看日志: tail -f {LOG_FILE}")

# ── Main ──────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='网易竞彩足球赔率自动更新')
    parser.add_argument('--cron', action='store_true', help='显示定时任务配置说明')
    parser.add_argument('--test', action='store_true', help='仅测试解析，不写入文件')
    args = parser.parse_args()

    if args.cron:
        setup_cron()
        return

    log("=" * 50)
    log("网易竞彩足球赔率自动更新 - 开始执行")
    log("=" * 50)

    try:
        # ① 抓取网易页面
        log("① 抓取网易页面...")
        html_content = fetch_163()
        log(f"  ✅ 页面大小: {len(html_content)} bytes")

        # ② 解析比赛数据
        log("② 解析比赛数据...")
        matches = extract_matches(html_content)
        log(f"  ✅ 解析到 {len(matches)} 场比赛")

        if args.test:
            log("【测试模式】仅解析，不写入文件")
            for m in matches[:5]:
                plays = list(m['plays'].keys())
                log(f"  {m['jc_num']} {m['home']} vs {m['guest']} 玩法:{plays}")
            log(f"  ... 共 {len(matches)} 场")
            return

        # ③ 转换为本地格式
        log("③ 转换为本地 oddsData 格式...")
        odds_data, match_order = convert_to_odds_data(matches)
        log(f"  ✅ 转换完成: {len(odds_data)} 场")

        # ④ 注入 HTML 文件
        log("④ 注入 HTML 文件...")
        ok = inject_into_html(odds_data, match_order)

        if ok:
            log("✅ 全部完成!")
            log(f"  请刷新浏览器页面（F5）")
            log(f"  日志: tail -f {LOG_FILE}")
        else:
            log("❌ 注入失败")

    except Exception as e:
        log(f"❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
