# -*- coding: utf-8 -*-
"""「今日比分精选 / 大胆档」选取算法——单一事实源（single source of truth）。

背景（2026-09-16）：
  报告渲染（`_gen_report.py`）与每日优化回放（`_optimize_selection.py`）原本各写了一份
  选取逻辑，属近似重复实现，存在口径漂移风险——优化器调出来的旋钮可能不是报告真用的
  那个算法，会让「每日优化」失去意义。本模块把两边共用的纯函数收拢到一处，
  两侧一律 import 使用，杜绝重复。

两条独立赛道（互不以对方为输入）：
  · 比分精选 pk_quality  = 命中比分（联合众数）概率 × λ 质量系数，并对退化头条 1:1 降权。
  · 大胆档   bold_quality = max(极限档概率, 量级档概率)，可选 λ 总量下限门槛。

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

DEFAULT_TUNING = {
    'pk_lambda_caps': [2.6, 3.0, 3.4],        # λ 总量质量分界（越低单比分命中率越高）
    'pk_lambda_w':    [1.0, 0.90, 0.78, 0.68],  # 对应质量系数
    'pk_degen_down':  0.85,                   # 退化头条(1:1)低概率降权
    'bd_lambda_min':  0.0,                    # 大胆档最低 λ 总量门槛（0=不限）
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
def hit_pick(m):
    """头条「命中比分」= 已对齐比分矩阵的联合众数（top_scores[0] 中的首个列出比分）。

    目标函数为单场命中次数，argmax 即最优解，故不做任何"大胆化"变换。
    返回 (比分, 模型给该比分的概率% 或 None)。
    """
    for t in (m.get('top_scores') or []):
        if t.get('score') in LISTED_LABELS:
            return t['score'], t.get('prob')
    return quad_score(m, direction_key(m)), None


def band_scores(m, k=2):
    """双档 = 模型排序第 2、第 3 可能比分（跳过头条）。

    返回 [(score, prob) ...]，prob 单位 %；不足 k 档时按模型排序补足。
    """
    ts = [t for t in (m.get('top_scores') or []) if t.get('score') in LISTED_LABELS]
    out, seen = [], set()
    for t in ts[1:1 + k]:
        sc = t.get('score')
        if sc in seen:
            continue
        out.append((sc, t.get('prob') or 0.0))
        seen.add(sc)
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
    """「极限档」= 同倾向象限内、总进球 = 量级档 +1 的最高概率列出格。返回 (比分, 概率%)。"""
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
    """比分精选质量 = 命中比分概率 × λ 质量系数；退化头条 1:1 且概率偏低时降权。"""
    s, p = hit_pick(m)
    lt = lam_total(m)
    pf = float(p) if p else 0.0
    q = pf * lambda_quality(lt, tuning)
    if s == '1:1' and pf < 16.0:
        q *= tuning['pk_degen_down']
    return q


def bold_quality(m, tuning):
    """大胆档质量 = max(极限档概率, 量级档概率)；低于 λ 门槛的场次直接出局。"""
    _, ep, _ = expect_score(m)
    _, xp = extreme_pick(m)
    lt = lam_total(m)
    bp = max(xp or 0.0, ep or 0.0)
    if tuning['bd_lambda_min'] and lt < tuning['bd_lambda_min']:
        bp = -1.0
    return bp


# ---------- 排序与分档 ----------
def pk_tuple(m, tuning):
    """比分精选排序键：(比分, 概率%, λ总量, 质量分)。"""
    s, p = hit_pick(m)
    lt = lam_total(m)
    pf = float(p) if p else 0.0
    return s, pf, lt, pk_quality(m, tuning)


def bd_tuple(m, tuning):
    """大胆档排序键：(质量分, λ总量)。"""
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


def rank_bold(matches, tuning, per_tier=TIER_BD):
    """大胆档：排除冷启动 → 按质量降序 → 分档。返回 (tier_list, flat_list)。"""
    allr = [(bd_tuple(m, tuning), m) for m in matches]
    noncold = sorted([x for x in allr if not is_cold(x[1])], key=lambda x: (-x[0][0], -x[0][1]))
    return build_tiers(noncold, per_tier)


# ---------- 命中判定（报告回顾与优化回放共用，避免两套口径）----------
def pk_result(m, actual):
    """比分精选命中判定：头条命中 → 'hit'；落在第2/3档 → 'band'；否则 'miss'。"""
    s, _ = hit_pick(m)
    if actual == s:
        return 'hit'
    if actual in [sc for sc, _ in band_scores(m, 2)]:
        return 'band'
    return 'miss'


def bd_result(m, actual):
    """大胆档命中判定：量级档命中 → 'scale'；极限档命中 → 'extreme'；否则 'miss'。"""
    e, _, _ = expect_score(m)
    x, _ = extreme_pick(m)
    if actual == e:
        return 'scale'
    if x and actual == x:
        return 'extreme'
    return 'miss'
