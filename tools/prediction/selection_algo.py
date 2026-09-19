# -*- coding: utf-8 -*-
"""「今日比分精选 / 大胆档」选取算法——单一事实源（single source of truth）。

背景（2026-09-16）：
  报告渲染（`_gen_report.py`）与每日优化回放（`_optimize_selection.py`）原本各写了一份
  选取逻辑，属近似重复实现，存在口径漂移风险——优化器调出来的旋钮可能不是报告真用的
  那个算法，会让「每日优化」失去意义。本模块把两边共用的纯函数收拢到一处，
  两侧一律 import 使用，杜绝重复。

两块独立板块（2026-09-17 定调：各自成榜、各自计算、互不关联）：
  · 比分精选（pk_*）：**自带模型**——`pk_dist` 由引擎 λ 自建泊松分布，
    再自己缩放到引擎已发布 1X2，自己在该分布上取头条 / 双档；
    随后按「头条概率 × λ 质量系数」排序，退化头条 1:1 降权。
  · 大胆档（bd_*）：**自带模型**——`bd_ref` 用引擎 λ 自建泊松，取量级档 / 极限档。
  两榜都**只把引擎输出当输入**（λ、1X2、候选池），展示的预测各自算各自的；
  两榜**互斥成榜**（`split_boards`）：比分精选先占位，大胆档只在剩余场次中选取，
  同一场比赛不会同时出现在两个榜里。

引擎自身的比分矩阵口径（`hit_pick`/`band_scores`）只服务于报告正文（总览/串关等）
与 gen_review 复盘，不参与两个板块的预测与排序。

档数：以 N_TIER_BASE 场为基准 1 档，每多 N_TIER_STEP 场加 1 档，封顶 TIER_MAX。

本模块只依赖 match dict（引擎输出或历史快照），不读文件、不产生副作用；
快照缺 `prob` 字段时自动由 prob_home/prob_draw/prob_away 还原。
"""
import math
import json

# ---------- 常量 ----------
LISTED_LABELS = {
    '1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '4:0', '4:1', '4:2', '5:0', '5:1', '5:2',
    '0:0', '1:1', '2:2', '3:3',
    '0:1', '0:2', '1:2', '0:3', '1:3', '2:3', '0:4', '1:4', '2:4', '0:5', '1:5', '2:5',
}

TIER_PK = 6        # 比分精选每档场数
TIER_BD = 4        # 大胆档每档场数
N_TIER_BASE = 10   # 基准：10 场 → 1 档
N_TIER_STEP = 8    # 每多 8 场 → 多 1 档（18场→2档、26场→3档、34场→4档…）
TIER_MAX = 5       # 档数上限（切片不足时该档自然不出现）
BD_MAXG = 6        # 大胆档自带泊松网格上限（每侧进球 0..6）
PK_MAXG = 8        # 比分精选自带泊松网格上限（每侧进球 0..8）

DEFAULT_TUNING = {
    # —— 板块 A：比分精选（自带分布：λ 泊松 → 自对齐已发布 1X2）——
    'pk_align_1x2':   1,                        # 1 = 自建分布三象限缩放到引擎已发布 1X2
    'pk_lambda_caps': [2.6, 3.0, 3.4],          # λ 总量质量分界（越低单比分命中率越高）
    'pk_lambda_w':    [1.0, 0.90, 0.78, 0.68],  # 对应质量系数
    'pk_degen_down':  0.85,                     # 退化头条(1:1)低概率降权
    # —— 板块 B：大胆档（自带泊松模型，不读引擎比分矩阵）——
    # 激进程度（bd_total_shift）经 178 天/2462 场大样本验证：参考比分越往高球数推，命中率越低
    # （-1 → 31.5%、0 → 29.1%、+1 → 21.9%、+2 → 17.7%），故默认取 -1。
    'bd_total_shift': -1,   # 量级档总球数 = round(λ总) + 本值（越大越激进、命中率越低）
    'bd_min_total':   2,    # 量级档总球数下限（低进球日不至于挑 0:0/1:0）
    'bd_gap':         1,    # 极限档 = 量级档总球数 + 本值
    'bd_exclusive':   1,    # 1 = 与比分精选互斥成榜（同一场次不上两榜）
    'bd_lean_src':    'engine',  # 倾向来源：engine=引擎 1X2（大样本高 2.5pp）/ self=自身泊松
}


def load_tuning(path='selection_tuning.json'):
    """读取调优参数；文件缺失/损坏时回退默认（绝不让报告崩）。"""
    d = dict(DEFAULT_TUNING)
    try:
        t = json.load(open(path, encoding='utf-8'))
        for k in d:
            if k in t:
                d[k] = t[k]
    except Exception:
        pass
    return d


def save_tuning(d, path='selection_tuning.json'):
    payload = {k: d.get(k, DEFAULT_TUNING[k]) for k in DEFAULT_TUNING}
    json.dump(payload, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


# ---------- 基础读取（兼容引擎输出与历史快照）----------
def prob1x2(m):
    """1X2 概率字典 {'home','draw','away'}；快照无 `prob` 时由 prob_* 还原。"""
    pr = m.get('prob')
    if isinstance(pr, dict) and pr:
        return pr
    return {'home': m.get('prob_home', 0) or 0,
            'draw': m.get('prob_draw', 0) or 0,
            'away': m.get('prob_away', 0) or 0}


def direction_key(m):
    """倾向 key = 1X2 概率最大者（报告侧 direction_pick 的同一判据）。"""
    pr = prob1x2(m)
    return max(('home', 'draw', 'away'), key=lambda k: pr.get(k, 0))


def quad_score(m, okey):
    """倾向象限内的众数比分（兜底比分，引擎无 quad_top 时退化为 1:1）。"""
    qt = (m.get('quad_top') or {}).get(okey) or {}
    return qt.get('score') or '1:1'


def lam_total(m):
    return float(m.get('lam_home', 0) or 0) + float(m.get('lam_away', 0) or 0)


def is_cold(m):
    """冷启动场次（任一侧无近期战绩）：λ 靠联赛基线+赔率反推，分布形状不可信，退出排序。"""
    if m.get('cold'):
        return True
    dn = m.get('data_n') or {}
    return dn.get('home', 1) == 0 or dn.get('away', 1) == 0


# ---------- 比分口径 ----------
# 头条口径（2026-09-19）：首选比分必须与**本场发布倾向同象限**，避免均衡场次清一色
# 平局比分（联合众数在两队 λ 同落 [1,2) 时恒为 1:1，2478 场里占 56%）。
# 规则实现只有一份：`score_engine.headline_reorder`。本模块只做转发，不另写第二份。
_HEAD_RULE = None


def _head_rule():
    """返回 (规则函数, gap)。score_engine 缺失时返回 (None, 5.0) → 退化为纯概率首选。"""
    global _HEAD_RULE
    if _HEAD_RULE is None:
        try:
            import score_engine as _se
            _HEAD_RULE = (_se.headline_reorder, float(_se.DEFAULT.get('head_gap', 5.0) or 5.0))
        except Exception:
            _HEAD_RULE = (None, 5.0)
    return _HEAD_RULE


def headline_pick(cells, okey):
    """在**概率降序**的比分列表上取首选（套用统一的头条口径）。

    cells: [(score, prob%) ...] 概率降序（引擎矩阵或本板块自建分布皆可）。
    okey:  本场倾向 'home'/'draw'/'away'。
    返回 (首选比分, 首选概率%)；口径不可用时退化为概率最高格。
    """
    cells = [c for c in cells if c and c[0]]
    if not cells:
        return None, None
    fn, gap = _head_rule()
    if fn is None:
        return cells[0]
    try:
        ranked = fn([{'score': s, 'prob': p} for s, p in cells], gap, okey)
    except Exception:
        return cells[0]
    return ranked[0]['score'], ranked[0].get('prob')


def hit_pick(m):
    """头条「命中比分」= 倾向象限内优选（概率最高格在倾向不一致时顺延，规则见 headline_reorder）。

    取数顺序：快照 `headline` 字段 → 用本模块方向现算 → 矩阵首个列出比分。
    返回 (比分, 模型给该比分的概率% 或 None)。
    """
    hl = m.get('headline') or {}
    if hl.get('score'):
        return hl['score'], hl.get('prob')
    ts = [t for t in (m.get('top_scores') or []) if t.get('score') in LISTED_LABELS]
    if ts:
        okey = direction_key(m)
        s, p = headline_pick([(t['score'], t.get('prob')) for t in ts], okey)
        return s, p
    return quad_score(m, direction_key(m)), None


def band_scores(m, k=2):
    """双档 = **除头条外**概率最高的 k 个比分（跳过头条，避免与首选重复）。

    返回 [(score, prob) ...]，prob 单位 %；不足 k 档时按模型排序补足。
    """
    ts = [t for t in (m.get('top_scores') or []) if t.get('score') in LISTED_LABELS]
    head, _ = hit_pick(m)
    out, seen = [], {head}
    for t in ts:
        sc = t.get('score')
        if sc in seen:
            continue
        out.append((sc, t.get('prob') or 0.0))
        seen.add(sc)
        if len(out) >= k:
            break
    for t in ts:
        if len(out) >= k:
            break
        sc = t.get('score')
        if sc not in seen:
            out.append((sc, t.get('prob') or 0.0))
            seen.add(sc)
    return out[:k]


def expect_score(m):
    """「量级参考比分」= λ 期望进球四舍五入（无偏口径，非押中口径）。

    强制落在倾向象限内，否则退回该象限众数。返回 (比分, 概率% 或 None, 是否等于象限众数)。
    """
    lh, la = float(m.get('lam_home', 0) or 0), float(m.get('lam_away', 0) or 0)
    okey = direction_key(m)
    dscore = quad_score(m, okey)
    cand = (int(round(lh)), int(round(la)))
    ok = ((cand[0] > cand[1]) if okey == 'home'
          else ((cand[0] == cand[1]) if okey == 'draw' else (cand[0] < cand[1])))
    label = f'{cand[0]}:{cand[1]}' if (ok and f'{cand[0]}:{cand[1]}' in LISTED_LABELS) else dscore
    prob = next((t.get('prob') for t in (m.get('top_scores') or []) if t.get('score') == label), None)
    return label, prob, (label == dscore)


def extreme_pick(m):
    """「极限档」旧口径（量级档+1 球，依赖引擎象限众数）——保留供离线对照/探针。

    生产的大胆档已改用自带模型 `bd_ref`，不再调用本函数。
    返回 (比分, 概率%)。
    """
    lh, la = float(m.get('lam_home', 0) or 0), float(m.get('lam_away', 0) or 0)
    okey = direction_key(m)
    e, _, _ = expect_score(m)
    try:
        eh, ea = (int(x) for x in str(e).split(':'))
    except (ValueError, AttributeError):
        return None, None
    target = eh + ea + 1
    pmf = lambda k, lam: math.exp(-lam) * lam ** k / math.factorial(k)
    best, bp = None, -1.0
    for h in range(6):
        for a in range(6):
            if f'{h}:{a}' not in LISTED_LABELS or h + a != target:
                continue
            if okey == 'home' and not h > a:
                continue
            if okey == 'draw' and h != a:
                continue
            if okey == 'away' and not a > h:
                continue
            p = pmf(h, lh) * pmf(a, la)
            if p > bp:
                bp, best = p, f'{h}:{a}'
    return best, (round(bp * 100, 1) if best else None)


# ---------- 两条独立赛道的质量分 ----------
def lambda_quality(lt, tuning):
    """λ 总量质量系数：λ 越低，单比分命中率越高（score_cred 实测表）。"""
    caps, w = tuning['pk_lambda_caps'], tuning['pk_lambda_w']
    for i, c in enumerate(caps):
        if lt <= c:
            return w[min(i, len(w) - 1)]
    return w[min(len(caps), len(w) - 1)]


def pk_quality(m, tuning):
    """比分精选的「选场」质量分（取自今日引擎计算结果，不自算）。

    = 引擎正常口径的命中比分概率（`hit_pick`）× λ 质量系数；
      退化头条 1:1 且概率偏低时降权。
    注意：这里只用引擎口径**决定选哪几场**；这几场的预测展示由本板块自己在
    `pk_ref` 里算（自建分布），两者口径分离。
    """
    s, p = hit_pick(m)
    pf = float(p or 0.0)
    q = pf * lambda_quality(lam_total(m), tuning)
    if s == '1:1' and pf < 16.0:
        q *= tuning['pk_degen_down']
    return q


# ---------- 大胆档自带模型（输入仅引擎 λ，不读引擎比分矩阵）----------
def _pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def bd_grid(m):
    """大胆档自带的比分概率网格（两侧独立泊松）。"""
    lh = float(m.get('lam_home', 0) or 0)
    la = float(m.get('lam_away', 0) or 0)
    return [[_pois(h, lh) * _pois(a, la) for a in range(BD_MAXG + 1)]
            for h in range(BD_MAXG + 1)], lh, la


def bd_lean(m, src=None):
    """大胆档的倾向象限（决定参考比分落在主/平/客哪个象限）。

    src='engine' → 取引擎 1X2 概率最大者（大样本命中率高约 2.5pp；只用方向概率，不读比分矩阵）；
    src='self'   → 由自身泊松分布求和得出（完全不依赖引擎方向）。
    """
    if (src or 'engine') == 'engine':
        pr = prob1x2(m)
        if any(pr.get(k) for k in ('home', 'draw', 'away')):
            return max(('home', 'draw', 'away'), key=lambda k: pr.get(k, 0))
    d, _, _ = bd_grid(m)
    ph = sum(d[h][a] for h in range(BD_MAXG + 1) for a in range(BD_MAXG + 1) if h > a)
    pd = sum(d[h][h] for h in range(BD_MAXG + 1))
    pa = sum(d[h][a] for h in range(BD_MAXG + 1) for a in range(BD_MAXG + 1) if a > h)
    return max((('home', ph), ('draw', pd), ('away', pa)), key=lambda x: x[1])[0]


def _lean_ok(lean, h, a):
    return (h > a) if lean == 'home' else ((h == a) if lean == 'draw' else (a > h))


def _bd_pick(d, lean, total):
    """象限内「总球数 = total」的最高概率列出格；本象限该球数无列出格则退回象限最高格。"""
    best, bp = None, -1.0
    for h in range(BD_MAXG + 1):
        a = total - h
        if a < 0 or a > BD_MAXG or f'{h}:{a}' not in LISTED_LABELS or not _lean_ok(lean, h, a):
            continue
        if d[h][a] > bp:
            bp, best = d[h][a], f'{h}:{a}'
    if best:
        return best, bp
    for h in range(BD_MAXG + 1):
        for a in range(BD_MAXG + 1):
            if f'{h}:{a}' not in LISTED_LABELS or not _lean_ok(lean, h, a):
                continue
            if d[h][a] > bp:
                bp, best = d[h][a], f'{h}:{a}'
    return best, (bp if best else None)


def bd_ref(m, tuning):
    """大胆档自带的两档参考比分（只用引擎 λ 建模）。

    量级档 = 倾向象限内、总球数 = max(bd_min_total, round(λ总) + bd_total_shift) 的最高概率格；
    极限档 = 同象限、总球数 = 量级档总球数 + bd_gap 的最高概率格。
    返回 (量级档, 量级概率%, 极限档, 极限概率%)。
    """
    d, lh, la = bd_grid(m)
    lean = bd_lean(m, tuning.get('bd_lean_src'))
    base = max(int(tuning.get('bd_min_total') or 2),
               int(round(lh + la)) + int(tuning.get('bd_total_shift') or 0))
    s, ps = _bd_pick(d, lean, base)
    x, px = _bd_pick(d, lean, base + int(tuning.get('bd_gap') or 1))
    return (s, (round(ps * 100, 1) if ps is not None else None),
            x, (round(px * 100, 1) if px is not None else None))


def bold_quality(m, tuning):
    """大胆档质量 = 量级档概率 + 极限档概率（纯自身模型输出，与比分精选口径无关）。"""
    _, ps, _, px = bd_ref(m, tuning)
    return float(ps or 0.0) + float(px or 0.0)


# ---------- 比分精选自带模型（输入 = 引擎 λ + 已发布 1X2，自己出分布与预测）----------
def pk_grid(m):
    """比分精选自带的比分概率网格（两侧独立泊松，只用引擎 λ）。"""
    lh = float(m.get('lam_home', 0) or 0)
    la = float(m.get('lam_away', 0) or 0)
    return [[_pois(h, lh) * _pois(a, la) for a in range(PK_MAXG + 1)]
            for h in range(PK_MAXG + 1)], lh, la


def _quad_of(h, a):
    return 'home' if h > a else ('draw' if h == a else 'away')


def pk_dist(m, tuning=None):
    """比分精选自己的比分分布（dict：'主:客' → 概率，只含列出比分，已归一化）。

    自建管线：引擎 λ → 独立泊松网格 → 三象限缩放到引擎已发布 1X2（`pk_align_1x2`）。
    引擎的比分矩阵（top_scores）**不参与**本分布。
    """
    t = tuning or DEFAULT_TUNING
    d, _, _ = pk_grid(m)
    dist = {}
    for h in range(PK_MAXG + 1):
        for a in range(PK_MAXG + 1):
            s = f'{h}:{a}'
            if s in LISTED_LABELS:
                dist[s] = d[h][a]
    if int(t.get('pk_align_1x2', 1) or 0):
        pr = prob1x2(m)
        for q in ('home', 'draw', 'away'):
            tgt = float(pr.get(q, 0) or 0) / 100.0
            mem = [s for s in dist if _quad_of(*(int(x) for x in s.split(':'))) == q]
            cur = sum(dist[s] for s in mem)
            if mem and cur > 1e-12 and tgt > 0:
                k = tgt / cur
                for s in mem:
                    dist[s] *= k
    tot = sum(dist.values())
    if tot > 0:
        for s in dist:
            dist[s] /= tot
    return dist


def pk_ref(m, tuning=None, band_k=2):
    """比分精选自己的预测：头条 = 本板块分布上套统一头条口径（倾向象限内优选）；双档 = 除头条外概率最高的 2 个。

    λ 推导的分布里，均衡场次 argmax 同样是 1:1（结构性退化），故头条走同一份
    `headline_pick` 规则；回放 225 场实测（pk_head_probe.py，14 天）：
    头条 11.11%→8.89%、双档 17.33%→19.56%**合计不变（28.44%）**，头条 1:1 占比 63%→14%。
    返回 (头条比分, 头条概率%, [(双档比分, 概率%) ...])。
    """
    cells = sorted(((s, round(p * 100, 1)) for s, p in pk_dist(m, tuning).items()), key=lambda x: -x[1])
    if not cells:
        return None, None, []
    head, hp = headline_pick(cells, direction_key(m))
    band = [(s, p) for s, p in cells if s != head][:band_k]
    return head, (round(hp, 1) if hp is not None else None), band


# ---------- 排序与分档 ----------
def pk_tuple(m, tuning):
    """比分精选排序键：(本板块头条, 本板块概率%, λ总量, 选场质量分)。

    排序看第 4 项（引擎正常口径把握度 = 「从今日计算结果里选」）；
    前三项是展示用的本板块自算预测。报告侧按这四项直接渲染，无需再算一遍。
    """
    s, p, _ = pk_ref(m, tuning)
    return s, float(p or 0.0), lam_total(m), pk_quality(m, tuning)


def bd_tuple(m, tuning):
    """大胆档排序键：(质量分, λ总量)。

    两榜独立：本键不引用比分精选的任何量（不再借用其 λ 质量口径）。
    """
    return bold_quality(m, tuning), lam_total(m)


def num_tiers(n_total):
    """档数：以 N_TIER_BASE 场为基准 1 档，每多 N_TIER_STEP 场加 1 档，封顶 TIER_MAX。"""
    t = 1 if n_total < N_TIER_BASE else 1 + (n_total - N_TIER_BASE) // N_TIER_STEP
    return max(1, min(t, TIER_MAX))


def build_tiers(ranked, per_tier, n_tiers=None):
    """把已排序的列表切成若干档；切片不足的档自动不出现。返回 (tier_list, flat_list)。"""
    n = num_tiers(len(ranked)) if n_tiers is None else n_tiers
    tiers = [ranked[i * per_tier:(i + 1) * per_tier] for i in range(n)]
    tiers = [t for t in tiers if t]
    return tiers, [x for t in tiers for x in t]


def rank_pk(matches, tuning, per_tier=TIER_PK):
    """比分精选：排除冷启动 → 按质量降序 → 分档。返回 (tier_list, flat_list, cold_matches)。"""
    allr = [(pk_tuple(m, tuning), m) for m in matches]
    noncold = sorted([x for x in allr if not is_cold(x[1])], key=lambda x: -x[0][3])
    tiers, flat = build_tiers(noncold, per_tier)
    colds = [x[1] for x in sorted(allr, key=lambda x: -x[0][3]) if is_cold(x[1])]
    return tiers, flat, colds


def match_key(m):
    """跨引擎输出/历史快照统一的场次标识（互斥分池靠它判重）。"""
    return m.get('id') or m.get('matchNumStr') or str(id(m))


def rank_bold(matches, tuning, per_tier=TIER_BD, exclude=None):
    """大胆档：排除冷启动 + 排除已被比分精选占用的场次 → 按质量降序 → 分档。

    返回 (tier_list, flat_list)。
    """
    ex = set(exclude or ())
    allr = [(bd_tuple(m, tuning), m) for m in matches if match_key(m) not in ex]
    noncold = sorted([x for x in allr if not is_cold(x[1])], key=lambda x: (-x[0][0], -x[0][1]))
    return build_tiers(noncold, per_tier)


def split_boards(matches, tuning, pk_per=TIER_PK, bd_per=TIER_BD):
    """两块独立成榜（生产的唯一入口）：比分精选先占位 → 大胆档只在剩余场次中独立选取。

    互斥由 `bd_exclusive` 控制（0 = 允许两榜重叠，仅供对照实验）。
    返回 (pk_tiers, pk_flat, bd_tiers, bd_flat, colds)。
    """
    pk_tiers, pk_flat, colds = rank_pk(matches, tuning, pk_per)
    ex = {match_key(x[1]) for x in pk_flat} if int(tuning.get('bd_exclusive', 1) or 0) else set()
    bd_tiers, bd_flat = rank_bold(matches, tuning, bd_per, exclude=ex)
    return pk_tiers, pk_flat, bd_tiers, bd_flat, colds


# ---------- 命中判定（报告回顾与优化回放共用，避免两套口径）----------
def pk_result(m, actual, tuning=None):
    """比分精选命中判定：本板块头条命中 → 'hit'；本板块双档命中 → 'band'；否则 'miss'。"""
    s, _, band = pk_ref(m, tuning or DEFAULT_TUNING)
    if actual == s:
        return 'hit'
    if actual in [sc for sc, _ in band]:
        return 'band'
    return 'miss'


def bd_result(m, actual, tuning=None):
    """大胆档命中判定：量级档命中 → 'scale'；极限档命中 → 'extreme'；否则 'miss'。

    参考比分由该场自身的 bd_* 参数决定，故判定必须与选取用同一份 tuning。
    """
    s, _, x, _ = bd_ref(m, tuning or DEFAULT_TUNING)
    if actual == s:
        return 'scale'
    if x and actual == x:
        return 'extreme'
    return 'miss'
