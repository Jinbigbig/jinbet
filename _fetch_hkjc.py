# -*- coding: utf-8 -*-
"""赛前简报抓取（香港赛马会 football.hkjc.com）-> hkjc.json

为什么需要它：lineupstoday 覆盖五大联赛+欧战，懂球帝覆盖葡超/德乙/英甲/巴甲/挪超/瑞超，
但**日职/日乙/韩职/沙特/澳超/墨超的伤停长期空白**，而 HKJC 的「赛前简报」逐场给：

    球队名
    受傷：球员（位置）、球员（位置）
    停賽：球员（位置）
    上陣成疑：球员（位置）

页面是 Next.js RSC，单个 3.4MB 页面内嵌 `allMatchPreview` 数组（近一个月约 900+ 条），
用 `self.__next_f.push([1,"..."])` 分片，拼接后是一段干净 JSON。

两个坑：
1. `path` 里的日期是**稿件发布日**，不是比赛日（欧洲夜场提前 1-2 天发稿）；
   所以按「窗口天数」取值，再按主客队名与当日对阵配对。
2. 全部繁体、港译队名；队名还原统一走 _league_match.to_simp()（内含 ALIAS_REV）。
   还原不出来的补在 HK_EXTRA 里。

用法：
    python _fetch_hkjc.py                 # 按 _calc_result.json 的 today
    python _fetch_hkjc.py --date 2026-10-22
    python _fetch_hkjc.py --audit         # 只报告窗口内未映射的港译队名
"""
import json
import os
import re
import sys
import urllib.request

BASE = 'https://football.hkjc.com/zh-hk/preview-summary'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
TIMEOUT = 90
WINDOW_DAYS = 3          # 稿件发布日落在 [TODAY-3, TODAY]
OUT = 'hkjc.json'

# 港译 -> 报告统一用名（ALIAS_REV 覆盖不到的，按需往下补；补一行就多覆盖一队）
HK_EXTRA = {
    # 欧战
    '加拉塔沙雷': '加拉塔萨', '寧斯': 'LASK林茨', '薩克達': '顿涅茨克矿工',
    '燕豪芬': '埃因霍温', 'FC辛辛那提': '辛辛那提FC', 'AEK雅典': 'AEK雅典',
    '費倫巴治': '费内巴切', '學生隊': '拉普拉塔大学生', '利昂': '莱昂',
    '索菲亞利夫斯基': '索菲亚列夫斯基', '奧摩尼亞': '奥莫尼亚', '克里特': 'OFI克里特',
    '艾拉華特阿美尼亞': '阿拉拉特亚美尼亚', '施捷': '采列', '薩爾斯堡': '萨尔茨堡',
    '奧沙卡': '大阪钢巴', '藍十字希達高': '蓝十字',
    # 日职
    '名古屋鯨魚': '名古屋八鲸', '千葉巿原': '千叶市原', '長崎成功丸': '长崎成功丸',
    # 韩职
    'FC首爾': '首尔FC', '蔚山HD': '蔚山现代', '全北汽車': '全北现代', '浦項制鐵': '浦项制铁',
    '大邱FC': '大邱FC', '仁川聯': '仁川联', '水原FC': '水原FC', '水原藍翼': '水原三星',
    '江原FC': '江原FC', '金泉尚武': '金泉尚武', '濟州聯': '济州联', 'FC大田': '大田FC',
    '光州FC': '光州FC', '安養': '安养', '富川1995': '富川1995',
    # 沙特
    '希拉爾': '利雅得新月', '艾納斯': '利雅得胜利', '伊蒂哈德': '吉达联合',
    '吉達艾阿里': '吉达国民', '艾塔亞文': '布赖代合作', '艾卡迪沙': '卡迪西亚',
    '伊蒂法克': '达曼协作', '艾利雅德': '利雅得青年', '艾法特': '哈萨法特',
    '卡赫利': '卡赫利', '尼奧姆SC': '新未来体育', '迪里耶會': '迪里耶',
    '艾沙比': '利雅得沙巴布', '艾費哈': '费哈', '艾拉德': '拉德',
    # 澳超
    '墨爾本城': '墨尔本城', '墨爾本勝仗': '墨尔本胜利', '悉尼FC': '悉尼FC',
    '西悉尼流浪者': '西悉尼漫步者', '阿德萊德聯': '阿德莱德联', '布里斯班獅吼': '布里斯班狮吼',
    '中岸水手': '中央海岸水手', '威靈頓鳳凰': '惠灵顿凤凰', '珀斯光輝': '珀斯光荣',
    '西部聯': '西部联', '馬卡瑟FC': '麦克阿瑟FC', '奧克蘭FC': '奥克兰FC',
    # 墨超
    '克雷塔羅': '克雷塔罗', '堤格雷斯': '老虎大学', '普馬斯': '美洲狮',
    '帕丘卡': '帕丘卡', '藍十字': '蓝十字', '托盧卡': '托卢卡', '迪祖亞拿': '蒂华纳',
    '阿特拿斯': '阿特拉斯', 'CF阿美利加': '墨西哥美洲', '普埃布拉': '普埃布拉',
    '蒙特雷': '蒙特雷', '祖亞雷斯': '华雷斯', '阿蘭特': '阿兰特', '瓜達拉哈拉': '瓜达拉哈拉',
    '尼卡沙': '内卡萨', '聖路易斯體育會': '圣路易斯竞技', '拿根亞': '桑托斯拉古纳',
    '利昂': '莱昂',
    # 巴甲 / 自由杯
    '小保加': '博卡青年', '蒙特維多城托基': '蒙得维的亚城托克', '隆德里納': '隆德里纳',
    '古亞巴': '库亚巴',
    # 英甲 / 英乙
    '樸茨茅夫': '朴茨茅斯', '基寧咸': '吉灵汉姆', '維爾港': '维尔港', '雷丁': '雷丁',
    '奧連特': '莱顿东方', '普雷斯頓雄獅': '普雷斯顿', '貝利': '贝里',
    # 其它欧洲
    '列治普斯納': '莱赫波兹南', '薩格勒布戴拿模': '萨格勒布迪纳摩', '奈梅亨': '奈梅亨',
    '費倫斯華路士': '费伦茨瓦罗斯', '杜連斯': '都灵', '積基朗尼亞': '比亚韦斯托克',
    '安德列治': '安德莱赫特', '些路迪': '凯尔特人', '柏辛域陀尼亞': '比尔森胜利',
    '般尼茅夫': '伯恩茅斯', '比錫達斯': '贝西克塔斯', '水晶宮': '水晶宫',
    '賓菲加': '本菲卡', '奧林比亞高斯': '奥林匹亚科斯', '布拉格斯巴達': '布拉格斯巴达',
    '利尼史特朗': '利勒斯特罗姆', '阿爾克馬爾': '阿尔克马尔', '聖基萊斯聯': '圣吉尔联',
    '比亞斯華夏普爾': '贝尔谢巴工人', '格拉茨': '格拉茨风暴', '馬賽': '马赛',
    '沙比阿爾阿里': '阿尔阿赫利', '艾阿恩': '艾因', '艾查捷拉': '半岛',
    '阿吉曼會': '阿吉曼', '艾華斯爾': '瓦斯尔', '卡爾巴FC': '卡尔巴联合',
    # 竞彩简称对齐（简报还原名与竞彩队名不同，缺这些整场配对失败）
    '艾夫斯堡': '埃夫斯堡', '馬模': '马尔默', '伊高斯': '前进之鹰',
    '泰斯達': '斯达', '甘馬雷斯': '吉马良斯', '馬里迪莫': '马里迪莫',
    '拖連奴': '都灵', '蒙沙': '蒙扎', '比斯特': '布雷斯特',
    '葉士域治': '伊普斯', '諾定咸森林': '诺丁汉',
}

_KW = ('受傷／缺陣', '上陣成疑', '受傷', '停賽', '缺陣')
_ERRS = ('內容完全由', '推介', '軍情', '近況', '往績')

# opencc 缺失时的降级字表（只收球员名/位置/伤因里高频出现的繁体字）
_T2S = {
    '傷': '伤', '衛': '卫', '將': '将', '後': '后', '門': '门', '腦': '脑', '盪': '荡',
    '腳': '脚', '斷': '断', '節': '节', '關': '关', '頭': '头', '頸': '颈', '側': '侧',
    '內': '内', '韌': '韧', '帶': '带', '賽': '赛', '陣': '阵', '場': '场', '員': '员',
    '復': '复', '發': '发', '熱': '热', '療': '疗', '癒': '愈', '體': '体', '髖': '髋',
    '臥': '卧', '舊': '旧', '術': '术', '見': '见', '詳': '详', '謝': '谢', '諾': '诺',
    '貝': '贝', '費': '费', '賀': '贺', '賓': '宾', '贊': '赞', '賴': '赖', '趙': '赵',
    '車': '车', '軍': '军', '軒': '轩', '輕': '轻', '輝': '辉', '農': '农', '連': '连',
    '進': '进', '運': '运', '達': '达', '遠': '远', '遜': '逊', '邁': '迈', '鄭': '郑',
    '酋': '酋', '郵': '邮', '鈴': '铃', '銀': '银', '鋒': '锋', '錫': '锡', '鍾': '钟',
    '鎖': '锁', '鐵': '铁', '鑽': '钻', '長': '长', '閃': '闪', '間': '间', '隊': '队',
    '際': '际', '雄': '雄', '雲': '云', '電': '电', '震': '震', '霍': '霍', '靈': '灵',
    '韋': '韦', '項': '项', '頓': '顿', '題': '题', '顎': '颚', '風': '风', '颶': '飓',
    '飛': '飞', '飯': '饭', '養': '养', '馬': '马', '駿': '骏', '骼': '骼', '魚': '鱼',
    '魯': '鲁', '鯊': '鲨', '鯨': '鲸', '鳥': '鸟', '鵝': '鹅', '鹽': '盐', '鹿': '鹿',
    '麥': '麦', '黃': '黄', '龍': '龙', '龐': '庞', '岡': '冈', '亞': '亚', '來': '来',
    '倉': '仓', '倫': '伦', '偉': '伟', '優': '优', '兩': '两', '凱': '凯', '別': '别',
    '剛': '刚', '勝': '胜', '勞': '劳', '勢': '势', '華': '华', '啟': '启', '國': '国',
    '圖': '图', '聖': '圣', '堅': '坚', '壯': '壮', '奧': '奥', '學': '学', '寧': '宁',
    '寶': '宝', '島': '岛', '巿': '市', '師': '师', '廣': '广', '彌': '弥', '復': '复',
    '愛': '爱', '態': '态', '慶': '庆', '應': '应', '懷': '怀', '戶': '户', '揚': '扬',
    '損': '损', '搶': '抢', '擊': '击', '斷': '断', '時': '时', '曉': '晓', '會': '会',
    '東': '东', '榮': '荣', '構': '构', '標': '标', '樣': '样', '樹': '树', '橋': '桥',
    '機': '机', '橫': '横', '櫻': '樱', '權': '权', '歐': '欧', '歷': '历', '畢': '毕',
    '漢': '汉', '滿': '满', '濟': '济', '灣': '湾', '為': '为', '烏': '乌', '無': '无',
    '煙': '烟', '熱': '热', '狀': '状', '獅': '狮', '獨': '独', '瑪': '玛', '璽': '玺',
    '畢': '毕', '當': '当', '發': '发', '盧': '卢', '確': '确', '礎': '础', '禮': '礼',
    '積': '积', '競': '竞', '簡': '简', '紀': '纪', '約': '约', '紅': '红', '納': '纳',
    '紐': '纽', '級': '级', '素': '素', '索': '索', '紹': '绍', '絲': '丝', '綠': '绿',
    '維': '维', '練': '练', '總': '总', '繩': '绳', '羅': '罗', '聯': '联', '聲': '声',
    '聽': '听', '腳': '脚', '脫': '脱', '腦': '脑', '膠': '胶', '臉': '脸', '臨': '临',
    '舉': '举', '艙': '舱', '藝': '艺', '蘇': '苏', '蘭': '兰', '處': '处', '號': '号',
    '蟲': '虫', '術': '术', '衝': '冲', '補': '补', '裝': '装', '見': '见', '親': '亲',
    '覺': '觉', '觀': '观', '計': '计', '訂': '订', '訓': '训', '記': '记', '評': '评',
    '試': '试', '話': '话', '認': '认', '誰': '谁', '課': '课', '調': '调', '談': '谈',
    '謂': '谓', '講': '讲', '證': '证', '識': '识', '護': '护', '變': '变', '讚': '赞',
    '豐': '丰', '豬': '猪', '貓': '猫', '賊': '贼', '質': '质', '賴': '赖', '賽': '赛',
    '贏': '赢', '趙': '赵', '趨': '趋', '跡': '迹', '踐': '践', '軌': '轨', '軒': '轩',
    '軟': '软', '較': '较', '載': '载', '輔': '辅', '輕': '轻', '輛': '辆', '輪': '轮',
    '輯': '辑', '輸': '输', '轉': '转', '轟': '轰', '農': '农', '這': '这', '連': '连',
    '週': '周', '遊': '游', '過': '过', '遞': '递', '遜': '逊', '遷': '迁', '選': '选',
    '遺': '遗', '鄰': '邻', '鄭': '郑', '釋': '释', '針': '针', '鈍': '钝', '鈴': '铃',
    '鉤': '钩', '銜': '衔', '銷': '销', '鋒': '锋', '錯': '错', '鍵': '键', '鍾': '钟',
    '鎊': '镑', '鏟': '铲', '鏡': '镜', '鐘': '钟', '鐵': '铁', '鑄': '铸', '鑑': '鉴',
    '閉': '闭', '開': '开', '閒': '闲', '閱': '阅', '闆': '板', '關': '关', '陣': '阵',
    '陰': '阴', '陳': '陈', '陸': '陆', '陽': '阳', '階': '阶', '隨': '随', '隱': '隐',
    '雙': '双', '雜': '杂', '雞': '鸡', '離': '离', '難': '难', '霧': '雾', '靈': '灵',
    '靜': '静', '頂': '顶', '順': '顺', '須': '须', '預': '预', '領': '领', '頒': '颁',
    '頌': '颂', '頭': '头', '顆': '颗', '顏': '颜', '願': '愿', '類': '类', '顧': '顾',
    '顯': '显', '風': '风', '飛': '飞', '餐': '餐', '餘': '余', '館': '馆', '駐': '驻',
    '駕': '驾', '騎': '骑', '驚': '惊', '骨': '骨', '髮': '发', '鬥': '斗', '魚': '鱼',
    '鮮': '鲜', '鳳': '凤', '鴨': '鸭', '鴻': '鸿', '鵬': '鹏', '鶴': '鹤', '鹹': '咸',
    '麗': '丽', '黨': '党', '齡': '龄', '龜': '龟',
}
# 球员姓名常用字（opencc 缺失时的降级补充）
_T2S.update(dict(zip('湯鄧韓醫鋼蹤齊喬傑劉張楊強語讀請說負責資趕辦違還邊雞豬鳳鴨鵝鹽麥黃點黨齡龜龍麗願類顧顯風飛養馬驗髮鬥魚鳥', '汤邓韩医钢踪齐乔杰刘张杨强语读请说负责资赶办违还边鸡猪凤鸭鹅盐麦黄点党龄龟龙丽愿类顾显风飞养马验发斗鱼鸟')))


# ---------------------------------------------------------------- 繁体 / 队名
def _t2s(s):
    """纯繁简转换（球员名 / 位置 / 伤因），不改译名。"""
    if not s:
        return s
    try:
        from opencc import OpenCC
        return OpenCC('t2s').convert(s)
    except Exception:
        pass
    return ''.join(_T2S.get(c, c) for c in s)


def _team_cn(hk):
    """港译繁体队名 -> 报告统一简体名（先查港译表，再走 ALIAS_REV，最后纯繁简）。"""
    if not hk:
        return hk
    if hk in HK_EXTRA:
        return HK_EXTRA[hk]
    try:
        import _league_match as LM
        r = LM.to_simp(hk)
        if r and r != hk:
            return r
    except Exception:
        pass
    return _t2s(hk)


def _norm(s):
    """比对用的弱归一：去空格/点，FC 挪位，巿→市。"""
    if not s:
        return ''
    s = s.replace('巿', '市').replace(' ', '').replace('·', '').replace('.', '')
    s = re.sub(r'(?i)\bFC\b', '', s)
    s = s.replace('FC', '')
    return s


def _hit(hk, cand):
    """港译名能否对应到候选中文名（cand 为当日对阵里的队名）。"""
    cn = _team_cn(hk)
    a, b = _norm(cn), _norm(cand)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(b) >= 2 and (b in a or a in b):
        return True
    return False


# ---------------------------------------------------------------- 抓取 / 解析
def fetch():
    req = urllib.request.Request(BASE, headers={'User-Agent': UA, 'Accept-Language': 'zh-HK,zh;q=0.9'})
    last = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read().decode('utf-8', 'ignore')
        except Exception as e:
            last = e
    raise last


def parse_rsc(page):
    """RSC 分片 -> allMatchPreview 数组"""
    parts = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', page)
    buf = []
    for p in parts:
        try:
            buf.append(json.loads(p))
        except Exception:
            pass
    t = ''.join(buf)
    i = t.find('"allMatchPreview":[')
    if i < 0:
        raise ValueError('页面里没有 allMatchPreview')
    start = t.index('[', i)
    depth = 0
    end = None
    for j in range(start, len(t)):
        c = t[j]
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if not end:
        raise ValueError('allMatchPreview 括号不闭合')
    return json.loads(t[start:end])


def _lines(h):
    h = h.replace('<br />', '\n').replace('<br/>', '\n').replace('<br>', '\n')
    h = re.sub(r'<[^>]+>', '', h)
    h = h.replace('&nbsp;', ' ').replace('&ndash;', '-').replace('&amp;', '&')
    return [x.strip() for x in h.split('\n')]


def _players(v):
    v = (v or '').strip()
    if v in ('', '／', '/', '—', '-', '無', '無。', '无'):
        return []
    out = []
    for seg in re.split(r'[、，,]', v):
        seg = seg.strip(' 。')
        if not seg or seg in ('／', '/'):
            continue
        m = re.match(r'^(.+?)[（(]([^）)]*)[）)]$', seg)
        if m:
            out.append({'name': _t2s(m.group(1).strip()), 'reason': _t2s(m.group(2).strip())})
        else:
            out.append({'name': _t2s(seg), 'reason': ''})
    return out


def parse_blocks(html_text):
    """-> [(港译队名, {'out':[], 'susp':[], 'doubt':[]})]，顺序即主/客"""
    blocks, cur, last_short = [], None, None
    for ln in _lines(html_text):
        if not ln:
            continue
        m = re.match(r'^(' + '|'.join(_KW) + r')[:：]\s*(.*)$', ln)
        if m:
            kind, val = m.group(1), m.group(2)
            if cur is None and last_short:
                cur = (last_short, {'out': [], 'susp': [], 'doubt': []})
                blocks.append(cur)
            if cur is None:
                continue
            ps = _players(val)
            if kind in ('受傷', '缺陣', '受傷／缺陣'):
                cur[1]['out'] += ps
            elif kind == '停賽':
                cur[1]['susp'] += ps
            else:
                cur[1]['doubt'] += ps
            continue
        if len(ln) <= 14 and '。' not in ln and '，' not in ln and '、' not in ln \
                and not any(k in ln for k in _ERRS):
            last_short = ln
            cur = None
    return blocks


def articles(arr, lo, hi):
    """筛出发布日落在窗口内的稿件，按日期升序（后发覆盖先发）"""
    out = []
    for it in arr:
        p = it.get('path') or ''
        m = re.search(r'/MatchPreview/(\d{4})-(\d{2})/(\d{2})/', p)
        if not m:
            continue
        d = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
        if not (lo <= d <= hi):
            continue
        para = ((it.get('paragraph') or {}).get('value') or '')
        if not para:
            continue
        out.append((d, it.get('name') or '', para))
    out.sort(key=lambda x: x[0])
    return out


# ---------------------------------------------------------------- 主流程
def main():
    try:
        import opencc  # noqa: F401
    except Exception:
        print('[HKJC] 未安装 opencc，繁简转换降级（pip install opencc-python-reimplemented）')
    argv = sys.argv[1:]
    audit = '--audit' in argv
    date = None
    if '--date' in argv:
        date = argv[argv.index('--date') + 1]
    if not date:
        try:
            date = json.load(open('_calc_result.json', encoding='utf-8'))['today']
        except Exception:
            date = __import__('datetime').date.today().isoformat()

    import datetime as dt
    d0 = dt.date.fromisoformat(date)
    lo = (d0 - dt.timedelta(days=WINDOW_DAYS)).isoformat()

    try:
        page = fetch()
    except Exception as e:
        print(f'[HKJC] 抓取失败（沿用已有数据）：{type(e).__name__}')
        return 1
    try:
        arr = parse_rsc(page)
    except Exception as e:
        print(f'[HKJC] 解析失败（沿用已有数据）：{type(e).__name__} {e}')
        return 1

    arts = articles(arr, lo, date)

    if audit:
        seen = {}
        for d, code, para in arts:
            for t, _v in parse_blocks(para):
                seen.setdefault(t, d)
        miss = {t: d for t, d in seen.items() if _team_cn(t) == t and _t2s(t) != t}
        print(f'[HKJC] 窗口 {lo}~{date} 稿件 {len(arts)} 条，港译队名 {len(seen)} 个，未映射 {len(miss)} 个')
        for t, d in sorted(miss.items(), key=lambda x: x[1]):
            print(f'   {d}  {t}')
        return 0

    # 当日对阵
    try:
        calc = json.load(open('_calc_result.json', encoding='utf-8'))
        matches = calc['matches'] if calc.get('today') == date else []
    except Exception:
        matches = []
    if not matches:
        print(f'[HKJC] {date} 无当日对阵（_calc_result.json today 不符），跳过')
        return 0

    pairs = [(m['matchNumStr'], m['home'], m['away']) for m in matches]
    got = {}
    unmatched = {}
    for d, code, para in arts:
        bl = parse_blocks(para)
        if len(bl) != 2:
            continue
        (h_hk, h_d), (a_hk, a_d) = bl
        for num, home, away in pairs:
            if _hit(h_hk, home) and _hit(a_hk, away):
                got[num] = {
                    'home': dict(h_d, team=home, hk=h_hk),
                    'away': dict(a_d, team=away, hk=a_hk),
                    'src': code, 'pub': d,
                }
            elif _hit(h_hk, away) and _hit(a_hk, home):
                got[num] = {
                    'home': dict(a_d, team=home, hk=a_hk),
                    'away': dict(h_d, team=away, hk=h_hk),
                    'src': code, 'pub': d,
                }

    for num, home, away in pairs:
        if num in got:
            continue
        for d, code, para in arts:
            for t, _v in parse_blocks(para):
                if _hit(t, home) or _hit(t, away):
                    unmatched.setdefault(t, d)

    keep = {}
    for num, rec in got.items():
        n = sum(len(rec[s][k]) for s in ('home', 'away') for k in ('out', 'susp', 'doubt'))
        if n:
            keep[num] = rec

    payload = {
        'date': date,
        'updated': dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'window': [lo, date],
        'matches': keep,
    }
    json.dump(payload, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    tot = sum(len(rec[s][k]) for rec in keep.values() for s in ('home', 'away')
              for k in ('out', 'susp', 'doubt'))
    print(f'[HKJC] {date} 简报 {len(keep)}/{len(matches)} 场有伤停，共 {tot} 条（稿件 {len(arts)} 篇，窗口 {lo}~{date}）')
    if unmatched:
        print('[HKJC] 未匹配队名：' + '、'.join(sorted(unmatched)[:12]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
