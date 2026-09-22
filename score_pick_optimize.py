"""比分引擎「选取层」离线优化器（walk-forward 保真回放，2478 场）。

用户 2026-09-22 定调：比分本身就是低可预测度的量，别再执着「选概率最大的格子」。
概率分布（估计）与选题（决策）是两件事 —— 本脚本只动决策层：
  1) 用当前生产引擎 walk-forward 重放历史，导出忠实分布 substrate（_bt_rows3.json）
  2) 在同一份分布上搜索选取规则，目标直接是历史命中率（单点 / 双档 / 每日至少一中）
  3) 训练/留出分段验证，只采纳留出段也改善的规则

用法：
  python score_pick_optimize.py rows     # 生成 _bt_rows3.json（约 1 分钟）
  python score_pick_optimize.py check    # substrate 保真校验
  python score_pick_optimize.py scan     # 规则族全样本扫描
  python score_pick_optimize.py split    # 训练/留出 采纳判据
"""
import collections
import json
import math
import os
import sys

import score_engine as SE

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS_SRC = os.path.join(HERE, "_bt_rows2.json")   # 含赔率/比分盘/实际比分的场次清单
ROWS = os.path.join(HERE, "_bt_rows3.json")       # 本脚本生成的忠实 substrate
VERBOSE = False


# =============== 1. 生成忠实 substrate ===============
def cmd_rows():
    src = json.load(open(ROWS_SRC, encoding="utf-8"))
    hist = SE.Engine.load_history()
    by_date = collections.defaultdict(list)
    for r in hist:
        by_date[r["date"]].append(r)
    tgt = collections.defaultdict(list)
    for r in src:
        tgt[r["date"]].append(r)
    dates = sorted(set(by_date) | set(tgt))
    eng = SE.Engine()                      # 当前生产参数
    out = []
    for date in dates:
        for r in tgt.get(date, []):
            odds = {"胜": r["oh"], "平": r["od"], "负": r["oa"]}
            sd = r.get("score_odds") or {}
            L = eng.lambdas(r["home"], r["away"], r["league"], odds, sd)
            lh, la = float(L["lam_h"]), float(L["lam_a"])
            m = eng.joint_final(lh, la, eng.p["lam3"])
            n = len(m)
            P = {"%d:%d" % (h, a): m[h][a] for h in range(n) for a in range(n)}
            dist = eng.blend_market(P, SE.market_dist(sd))
            t = float(eng.p["prob_temp"])
            if t != 1.0:
                s = sum(max(0.0, v) ** t for v in dist.values())
                if s > 0:
                    dist = {k: max(0.0, v) ** t / s for k, v in dist.items()}
            cells = sorted(dist.items(), key=lambda x: -x[1])
            d = SE.devig(r["oh"], r["od"], r["oa"]) or [0, 0, 0]
            # 发布倾向取引擎 A 的校准 1X2（rows2 的 probs 就是它）。
            # 注意：它与「市场去水 argmax」有 23% 分歧（发布倾向里平局占 14.2%），
            # 不能用市场 argmax 代理。
            pub = r.get("probs") or []
            pub_key = ("home", "draw", "away")[max(range(3), key=lambda i: pub[i])] \
                if len(pub) == 3 else None
            out.append({
                "pub": pub_key, "pub_p": [round(float(x) * 100, 1) for x in pub],
                "date": date, "league": r["league"], "home": r["home"], "away": r["away"],
                "hg": r["hg"], "ag": r["ag"],
                "oh": r["oh"], "od": r["od"], "oa": r["oa"],
                "hc": r.get("hc"), "score_odds": sd,
                "lam_h": round(lh, 3), "lam_a": round(la, 3),
                "mkt": [round(x, 4) for x in d],
                "top": [s for s, _ in cells[:24]],
                "top_p": [round(p * 100, 2) for _, p in cells[:24]],
                "cover24": round(sum(p for _, p in cells[:24]) * 100, 2),
            })
        if date in by_date:
            eng.feed(by_date[date])
    json.dump(out, open(ROWS, "w", encoding="utf-8"), ensure_ascii=False)
    print("已生成 %s：%d 场 / %d 天 / top24 平均覆盖 %.1f%%"
          % (os.path.basename(ROWS), len(out), len({r['date'] for r in out}),
             sum(r["cover24"] for r in out) / max(1, len(out))))


# =============== 2. 分布工具 ===============
_CACHE = {}


def load_rows():
    return json.load(open(ROWS, encoding="utf-8"))


def parse(s):
    h, a = str(s).split(":")
    return int(h), int(a)


def quad(s):
    h, a = parse(s)
    return "home" if h > a else ("away" if a > h else "draw")


def direction(r):
    """发布倾向（引擎 A 的 Platt 校准 1X2 argmax，随 substrate 存入 pub）。"""
    if r.get("pub"):
        return r["pub"]
    m = r.get("mkt") or [0, 0, 0]
    return ("home", "draw", "away")[max(range(3), key=lambda i: m[i])]


def cells_of(r):
    key = id(r)
    c = _CACHE.get(key)
    if c is None:
        c = list(zip(r["top"], [p / 100.0 for p in r["top_p"]]))
        _CACHE[key] = c
    return c


def mkt_cells(r):
    key = ("m", id(r))
    c = _CACHE.get(key)
    if c is None:
        pm = SE.market_dist(r.get("score_odds")) or {}
        c = sorted(pm.items(), key=lambda x: -x[1])
        _CACHE[key] = c
    return c


def mkt_of(r, s):
    pm = dict(mkt_cells(r))
    return pm.get(s, 0.0)


# =============== 3. 选取规则 ===============
def pick_base(cells, r):
    """生产现状：headline_reorder(gap=5.0) 作用于 top6。"""
    top = [{"score": s, "prob": p * 100} for s, p in cells[:6]]
    top = SE.headline_reorder(top, float(SE.DEFAULT["head_gap"]), direction(r))
    return top[0]["score"]


def make_gap_quad(gap):
    def f(cells, r):
        d = direction(r)
        s0, p0 = cells[0]
        if quad(s0) == d:
            return s0
        cands = [(s, p) for s, p in cells if quad(s) == d]
        if not cands:
            return s0
        best = max(cands, key=lambda x: x[1])
        if (p0 - best[1]) * 100 < gap:
            return best[0]
        return s0
    return f


def pick_market(cells, r):
    mc = mkt_cells(r)
    return mc[0][0] if mc else cells[0][0]


def pick_lam_round(cells, r):
    lh, la = r["lam_h"], r["lam_a"]
    s = "%d:%d" % (int(round(lh)), int(round(la)))
    return s if s in dict(cells) else cells[0][0]


# ---- 市场（比分盘）主导的选取 ----
def make_mkt_rule(b_nodraw=0.0, b_dir=0.0, w_model=0.0, pool=None,
                  draw_pen=0.0, b_l1=0.0):
    """以比分盘隐含概率为主的效用打分。

    w_model  > 0 时把模型概率也纳入（对数加权），pool 限制只在模型前 N 格内选。
    b_nodraw> 0 惩罚平局格（比分盘的平局格系统性偏便宜 → 市场 argmax 会过度押平）。
    """
    def f(cells, r):
        d = direction(r)
        lh, la = r["lam_h"], r["lam_a"]
        mkt = dict(mkt_cells(r))
        mod = dict(cells)
        keys = [s for s, _ in cells]
        if pool:
            keys = keys[:pool]
        keys += [s for s, _ in mkt_cells(r) if s not in mod]
        best, bs = None, -1e18
        for s in keys:
            h, a = parse(s)
            q = "home" if h > a else ("away" if a > h else "draw")
            sc = math.log(max(mkt.get(s, 0.0), 1e-9))
            if w_model:
                sc += w_model * math.log(max(mod.get(s, 0.0), 1e-9))
            if b_nodraw:
                sc += b_nodraw * (0.0 if h == a else 1.0)
            if draw_pen:
                sc += draw_pen * (1.0 if h == a else 0.0)
            if b_dir:
                sc += b_dir * (1.0 if q == d else 0.0)
            if b_l1:
                sc += b_l1 * (abs(h - lh) + abs(a - la))
            if sc > bs:
                bs, best = sc, s
        return best or cells[0][0]
    return f


def make_mkt_pool_rule(pool, b_nodraw=0.0):
    """只在模型前 pool 格内按比分盘概率选（避免市场把冷门格抬上来）。"""
    def f(cells, r):
        mkt = dict(mkt_cells(r))
        cand = [(s, mkt.get(s, 0.0)) for s, _ in cells[:pool]]
        if b_nodraw:
            nd = [x for x in cand if parse(x[0])[0] != parse(x[0])[1]]
            cand = nd or cand
        return max(cand, key=lambda x: x[1])[0] if cand else cells[0][0]
    return f


def make_hybrid(gap, w_mkt=0.0, pool=10, b_nodraw=0.0, b_dir=0.0):
    """先做象限顺延（gap），再在 gap 触发的场次改用市场口径。"""
    g = make_gap_quad(gap)

    def f(cells, r):
        s = g(cells, r)
        if s == cells[0][0]:
            return s
        mkt = dict(mkt_cells(r))
        d = direction(r)
        cand = [(x, mkt.get(x, 0.0)) for x, _ in cells[:pool]
                if parse(x)[0] != parse(x)[1] or not b_nodraw]
        if b_dir:
            same = [x for x in cand if quad(x[0]) == d]
            cand = same or cand
        return max(cand, key=lambda x: x[1])[0] if cand else s
    return f


_ALPHA_CACHE = {}
_ENG_CACHE = {}


def eng(market_mix=None):
    """按 market_mix 取一个参数被覆写的引擎实例（仅用于 joint_final/blend_market）。"""
    if market_mix not in _ENG_CACHE:
        e = SE.Engine()
        if market_mix is not None:
            e.p["market_mix"] = float(market_mix)
        _ENG_CACHE[market_mix] = e
    return _ENG_CACHE[market_mix]


def alpha_cells(r, alpha):
    """用指定 market_mix 重算该场分布（不改温度）→ [(score, p)]。"""
    key = (id(r), alpha)
    c = _ALPHA_CACHE.get(key)
    if c is None:
        lh, la = r["lam_h"], r["lam_a"]
        e = eng(market_mix=alpha)
        P = e.joint_final(lh, la, e.p["lam3"])
        n = len(P)
        cells = {"%d:%d" % (h, a): P[h][a] for h in range(n) for a in range(n)}
        dist = e.blend_market(cells, SE.market_dist(r.get("score_odds")))
        t = float(SE.DEFAULT["prob_temp"])
        if t != 1.0:
            s = sum(max(0.0, v) ** t for v in dist.values())
            if s > 0:
                dist = {k: max(0.0, v) ** t / s for k, v in dist.items()}
        c = sorted(dist.items(), key=lambda x: -x[1])
        _ALPHA_CACHE[key] = c
    return c


def make_alpha_rule(alpha, head_rule=None, b_nodraw=0.0, b_dir=0.0, w_mkt=1.0):
    """重算混合权重 alpha，再按给定方式选。

    head_rule=None → 纯 argmax；'gap5' → 沿用现行头条规则；
    否则在模型前 12 格里按比分盘概率选（b_nodraw/b_dir 为平局与象限偏好）。
    """
    def f(cells, r):
        c = alpha_cells(r, alpha)
        if head_rule == "gap5":
            top = [{"score": s, "prob": p * 100} for s, p in c[:6]]
            top = SE.headline_reorder(top, float(SE.DEFAULT["head_gap"]), direction(r))
            return top[0]["score"]
        if not (b_nodraw or b_dir):
            return c[0][0]
        d = direction(r)
        mkt = dict(mkt_cells(r))
        cand = [x for x in c[:12] if parse(x)[0] != parse(x)[1] or not b_nodraw]
        if b_dir:
            same = [x for x in cand if quad(x[0]) == d]
            cand = same or cand
        return max(cand, key=lambda x: mkt.get(x[0], 0.0))[0] if cand else c[0][0]
    return f


def head_rule(name):
    return {"gap0(纯众数)": make_gap_quad(0.0),
            "gap1": make_gap_quad(1.0),
            "gap2": make_gap_quad(2.0),
            "gap5(生产)": make_gap_quad(5.0)}[name]


def make_day_cap(base, cap):
    """同日同比分去重：先取基准规则的首选，该比分当日已满 cap 次则顺延到次优格。

    只解决「一天里同一比分刷屏」的展示问题；被顺延的场次按概率序后退。
    """
    state = {"date": None, "cnt": collections.Counter(), "best": 0}

    def f(cells, r):
        if state["date"] != r["date"]:
            state["date"] = r["date"]
            state["cnt"] = collections.Counter()
        first = base(cells, r) if base else cells[0][0]
        order = [first] + [s for s, _ in cells if s != first]
        for s in order:
            if state["cnt"][s] < cap:
                state["cnt"][s] += 1
                return s
        s = cells[0][0]
        state["cnt"][s] += 1
        return s
    return f


def make_day_cap_opt(base, cap, only=None):
    """按日全局最优分配：在「同一比分当日最多 cap 次」约束下最大化 Σ 概率。

    与逐场顺序贪心的区别：先按全天的 (场次, 得分) 概率降序统一排队再落位，
    避免「前面的场次把好格子吃光、后面的场次被迫退太远」。
    only 给定时只对该比分设上限（例如只限 1:1），其余比分不限。
    """
    state = {"date": None}
    plan = {}

    def build(rows_today):
        cells_map = {id(r): cells_of(r) for r in rows_today}
        order = []
        for r in rows_today:
            for i, (s, p) in enumerate(cells_map[id(r)][:12]):
                order.append((p, r["date"], id(r), s, i))
        order.sort(key=lambda x: -x[0])
        taken = {}
        cnt = collections.Counter()
        for p, d, rid, s, i in order:
            if rid in taken:
                continue
            if only is not None and s != only:
                # 非受限比分：直接取该场最高概率格
                taken[rid] = cells_map[rid][0][0]
                continue
            if cnt[s] < cap:
                cnt[s] += 1
                taken[rid] = s
        # 收尾：极少数场次在受限比分上被排队卡住
        for r in rows_today:
            if id(r) not in taken:
                s = next((x for x in cells_map[id(r)][:12]
                          if not (only is None or x[0] == only) or cnt[x[0]] < cap),
                         cells_map[id(r)][0][0])
                taken[id(r)] = s
                cnt[s] += 1
        return {id(r): taken[id(r)] for r in rows_today}

    def f(cells, r):
        if state["date"] != r["date"]:
            state["date"] = r["date"]
            plan.clear()
            plan.update(build(_TODAY_ROWS.get(r["date"], [r])))
        return plan.get(id(r)) or cells[0][0]
    return f


_TODAY_ROWS = {}


def prime_days(rows):
    """按天分组，供 make_day_cap_opt 使用。"""
    _TODAY_ROWS.clear()
    for r in rows:
        _TODAY_ROWS.setdefault(r["date"], []).append(r)


def make_mkt_draw_rule(w_model=0.3, draw_pen=0.0, one_pen=0.0, pool=24):
    """市场+模型效用，带软性平局/1:1 惩罚（连续可调）→ 可画命中率-平局占比权衡曲线。"""
    def f(cells, r):
        mkt = dict(mkt_cells(r))
        mod = dict(cells)
        best, bs = cells[0][0], -1e18
        for s, _ in cells[:pool]:
            h, a = parse(s)
            sc = math.log(max(mkt.get(s, 0.0), 1e-9)) + w_model * math.log(max(mod.get(s, 0.0), 1e-9))
            if h == a:
                sc += draw_pen
                if h == 1:
                    sc += one_pen
            if sc > bs:
                bs, best = sc, s
        return best
    return f


def make_score_rule(w_p=1.0, w_mkt=0.0, b_dir=0.0, b_nodraw=0.0, b_lambda=0.0,
                    b_l1=0.0, b_goalmag=0.0, b_tie=0.0, b_home=0.0, b_sum_hi=0.0):
    """通用效用打分（不是概率！）→ argmax。

      w_p·log p        模型/混合分布概率（对数）
      w_mkt·log p_mkt  比分盘隐含概率（对数）
      b_dir            象限 == 发布倾向
      b_nodraw         非平局
      b_lambda         恰为 (round λh, round λa)
      b_l1            −(|h−λh|+|a−λa|)
      b_goalmag       −|h+a−(λh+λa)|
      b_tie            平局且 ≥1 球
      b_home           主队进球 > 客队
      b_sum_hi         总进球 ≥ 3（大球倾向）
    """
    def f(cells, r):
        d = direction(r)
        lh, la = r["lam_h"], r["lam_a"]
        lt = lh + la
        rh, ra = int(round(lh)), int(round(la))
        _mkt = dict(mkt_cells(r))
        best, bs = cells[0][0], -1e18
        for s, p in cells:
            h, a = parse(s)
            q = "home" if h > a else ("away" if a > h else "draw")
            sc = w_p * math.log(max(p, 1e-12))
            if w_mkt:
                sc += w_mkt * math.log(max(_mkt.get(s, 0.0), 1e-9))
            if b_dir:
                sc += b_dir * (1.0 if q == d else 0.0)
            if b_nodraw:
                sc += b_nodraw * (1.0 if h != a else 0.0)
            if b_lambda:
                sc += b_lambda * (1.0 if (h == rh and a == ra) else 0.0)
            if b_l1:
                sc += b_l1 * (abs(h - lh) + abs(a - la))
            if b_goalmag:
                sc += b_goalmag * abs(h + a - lt)
            if b_tie:
                sc += b_tie * (1.0 if (h == a and h >= 1) else 0.0)
            if b_home:
                sc += b_home * (1.0 if h > a else 0.0)
            if b_sum_hi:
                sc += b_sum_hi * (1.0 if h + a >= 3 else 0.0)
            if sc > bs:
                bs, best = sc, s
        return best
    return f


# ---- 双档 ----
def band_top2(cells, r, head):
    """生产现状：除首选外概率最高的两个。"""
    return [s for s, _ in cells if s != head][:2]


def band_other_quad(cells, r, head):
    """跨象限双档：优先取「与头条不同象限」的最高概率格，补一个同象限的。"""
    qh = quad(head)
    diff = [s for s, _ in cells if s != head and quad(s) != qh]
    same = [s for s, _ in cells if s != head and quad(s) == qh]
    out = diff[:1] + same[:1]
    if len(out) < 2:
        out += [s for s, _ in cells if s != head and s not in out]
    return out[:2]


def band_same_quad(cells, r, head):
    """同象限双档：头条 + 同象限内最高概率格（同一胜负方向内的进球梯度）。"""
    qh = quad(head)
    same = [s for s, _ in cells if s != head and quad(s) == qh]
    rest = [s for s, _ in cells if s != head and s not in same]
    return (same + rest)[:2]


def band_mkt_pick(cells, r, head):
    """双档 = 除头条外，比分盘概率最高的两个。"""
    pool = [(s, mkt_of(r, s)) for s, _ in cells if s != head]
    pool.sort(key=lambda x: -x[1])
    return [s for s, _ in pool[:2]]


def band_goal_shape(cells, r, head):
    """双档 = 头条之外，与头条总进球相同的最高概率格 + 总进球差 1 的最高概率格。"""
    th, ta = parse(head)
    t1 = th + ta
    a1 = [(s, p) for s, p in cells if s != head and sum(parse(s)) == t1]
    a2 = [(s, p) for s, p in cells if s != head and abs(sum(parse(s)) - t1) == 1]
    out = []
    if a1:
        out.append(max(a1, key=lambda x: x[1])[0])
    if a2:
        out.append(max(a2, key=lambda x: x[1])[0])
    if len(out) < 2:
        out += [s for s, _ in cells if s != head and s not in out]
    return out[:2]


# =============== 4. 评估 ===============
def evaluate(rule, band=band_top2, rows=None, label=""):
    rows = rows if rows is not None else load_rows()
    hit = n = 0
    bhit = 0
    draw = one = 0
    day = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        cells = cells_of(r)
        if not cells:
            continue
        s = rule(cells, r)
        if s is None:
            continue
        n += 1
        act = "%d:%d" % (r["hg"], r["ag"])
        ok = s == act
        hit += 1 if ok else 0
        draw += 1 if quad(s) == "draw" else 0
        one += 1 if s == "1:1" else 0
        b = band(cells, r, s) or []
        bok = ok or (act in b)
        bhit += 1 if bok else 0
        day[r["date"]][0] += 1
        day[r["date"]][1] += 1 if bok else 0
    days = len(day)
    return dict(label=label, n=n, hit=hit / n * 100, band=bhit / n * 100,
                draw=draw / n * 100, one=one / n * 100,
                day_any=(sum(1 for v in day.values() if v[1] > 0) / days * 100) if days else 0,
                days=days)


def fmt(rows, title):
    print("\n%s" % title)
    print("%-34s %6s %9s %9s %8s %7s %11s" %
          ("规则", "场次", "单点命中", "双档命中", "平局占比", "1:1占比", "每日至少一中"))
    for r in rows:
        print("%-34s %6d %8.2f%% %8.2f%% %7.1f%% %6.1f%% %10.1f%%" % (
            r["label"], r["n"], r["hit"], r["band"], r["draw"], r["one"], r["day_any"]))


# =============== 5. 子命令 ===============
def cmd_check():
    rows = load_rows()
    bad = 0
    for r in rows:
        c = cells_of(r)
        if [s for s, _ in c[:6]] != list(r["top"][:6]):
            bad += 1
    print("substrate: %d 场，top6 自洽异常 %d 场；日期 %s → %s" %
          (len(rows), bad, min(x["date"] for x in rows), max(x["date"] for x in rows)))
    for k in ("lam_h", "lam_a"):
        print("  %s 中位 %.2f" % (k, sorted(x[k] for x in rows)[len(rows) // 2]))
    print("  top1 概率中位 %.2f%% / top24 覆盖中位 %.1f%%" %
          (sorted(x["top_p"][0] for x in rows)[len(rows) // 2],
           sorted(x["cover24"] for x in rows)[len(rows) // 2]))


def cmd_scan():
    out = [evaluate(pick_base, band_top2, label="base(生产现状)")]
    out.append(evaluate(pick_base, band_other_quad, label="base + 跨象限双档"))
    out.append(evaluate(pick_base, band_same_quad, label="base + 同象限双档"))
    out.append(evaluate(pick_base, band_mkt_pick, label="base + 比分盘双档"))
    out.append(evaluate(pick_base, band_goal_shape, label="base + 进球梯度双档"))
    fmt(out, "=== 双档口径（头条固定为生产现状）===")

    out = [evaluate(pick_base, band_top2, label="base(生产现状)")]
    for g in (2.0, 3.0, 5.0, 8.0, 12.0, 20.0):
        out.append(evaluate(make_gap_quad(g), band_top2, label="象限顺延 gap%.0f" % g))
    out.append(evaluate(pick_market, band_top2, label="比分盘 argmax"))
    out.append(evaluate(pick_lam_round, band_top2, label="λ 四舍五入"))
    fmt(out, "=== 结构性规则 ===")

    out = [evaluate(pick_base, band_top2, label="base(生产现状)")]
    for bd in (0.2, 0.4, 0.6, 0.8, 1.2):
        out.append(evaluate(make_score_rule(b_dir=bd), band_top2, label="效用 b_dir=%.1f" % bd))
    for bn in (-1.2, -0.8, -0.4, 0.4, 0.8):
        out.append(evaluate(make_score_rule(b_nodraw=bn), band_top2, label="效用 b_nodraw=%.1f" % bn))
    for bl in (-0.1, -0.2, -0.3, -0.5):
        out.append(evaluate(make_score_rule(b_l1=bl), band_top2, label="效用 b_l1=%.2f" % bl))
    for bg in (-0.1, -0.2, -0.4):
        out.append(evaluate(make_score_rule(b_goalmag=bg), band_top2, label="效用 b_goalmag=%.2f" % bg))
    for bt in (-1.5, -0.8, -0.4, 0.4):
        out.append(evaluate(make_score_rule(b_tie=bt), band_top2, label="效用 b_tie=%.1f" % bt))
    for wm in (0.2, 0.4, 0.6, 1.0):
        out.append(evaluate(make_score_rule(w_mkt=wm), band_top2, label="效用 w_mkt=%.1f" % wm))
    for bh in (0.3, 0.6, 1.0):
        out.append(evaluate(make_score_rule(b_home=bh), band_top2, label="效用 b_home=%.1f" % bh))
    for bs in (0.3, 0.6, 1.0):
        out.append(evaluate(make_score_rule(b_sum_hi=bs), band_top2, label="效用 b_sum_hi=%.1f" % bs))
    fmt(out, "=== 效用打分单特征 ===")


def _combo_rules():
    """组合候选（交叉项）。"""
    c = []
    # 象限顺延细网格（含 0 = 纯众数）
    for g in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        c.append(("象限顺延 gap%.1f" % g, make_gap_quad(g), band_top2))
    # 市场主导族
    c.append(("市场 argmax", make_mkt_rule(), band_top2))
    c.append(("市场 argmax·非平局", make_mkt_rule(b_nodraw=1.0), band_top2))
    c.append(("市场 argmax·倾向象限", make_mkt_rule(b_dir=1.0), band_top2))
    c.append(("市场 argmax·非平+倾向", make_mkt_rule(b_nodraw=0.6, b_dir=0.6), band_top2))
    c.append(("市场 argmax·平局罚", make_mkt_rule(draw_pen=-0.5), band_top2))
    for pl in (6, 8, 10, 14):
        c.append(("市场·模型前%d格" % pl, make_mkt_pool_rule(pl), band_top2))
        c.append(("市场·模型前%d格非平" % pl, make_mkt_pool_rule(pl, b_nodraw=1.0), band_top2))
    for wm in (0.3, 0.6, 1.0):
        c.append(("市场+模型 log%.1f" % wm, make_mkt_rule(w_model=wm), band_top2))
    # 顺延 + 市场混合
    for g in (1.0, 2.0):
        c.append(("顺延%.0f→市场" % g, make_hybrid(g), band_top2))
        c.append(("顺延%.0f→市场非平" % g, make_hybrid(g, b_nodraw=1.0), band_top2))
        c.append(("顺延%.0f→市场倾向" % g, make_hybrid(g, b_dir=1.0), band_top2))
    # 效用交叉
    for bd in (0.2, 0.4):
        for bn in (-0.4, -0.8):
            c.append(("效用 dir%.1f+nodraw%.1f" % (bd, bn),
                      make_score_rule(b_dir=bd, b_nodraw=bn), band_top2))
    c.append(("效用 b_dir=0.2", make_score_rule(b_dir=0.2), band_top2))
    c.append(("效用 b_tie=+0.4", make_score_rule(b_tie=0.4), band_top2))
    c.append(("效用 dir0.2+tie0.4", make_score_rule(b_dir=0.2, b_tie=0.4), band_top2))
    c.append(("效用 b_nodraw=-0.8", make_score_rule(b_nodraw=-0.8), band_top2))
    # 双档变体
    c.append(("base+同象限双档", pick_base, band_same_quad))
    c.append(("base+跨象限双档", pick_base, band_other_quad))
    c.append(("base+进球梯度双档", pick_base, band_goal_shape))
    c.append(("市场头条+模型双档", make_mkt_rule(b_nodraw=0.6, b_dir=0.6), band_top2))
    c.append(("市场头条+跨象限双档", make_mkt_rule(b_nodraw=0.6, b_dir=0.6), band_other_quad))
    return c


def cmd_split(frac=0.65):
    rows = load_rows()
    dates = sorted({r["date"] for r in rows})
    cut = dates[int(len(dates) * frac)]
    tr = [r for r in rows if r["date"] < cut]
    te = [r for r in rows if r["date"] >= cut]
    print("训练 %s ~ %s（%d 场）/ 留出 %s ~ %s（%d 场）" %
          (dates[0], cut, len(tr), cut, dates[-1], len(te)))
    cands = [("base(生产现状 gap5)", pick_base, band_top2)] + _combo_rules()

    res = []
    for lb, f, bnd in cands:
        a = evaluate(f, bnd, rows=tr, label=lb)
        b = evaluate(f, bnd, rows=te, label=lb)
        res.append((lb, a, b))

    base_tr = [x for x in res if x[0].startswith("base(生产现状")][0][1]
    base_te = [x for x in res if x[0].startswith("base(生产现状")][0][2]
    print("\n留出段基线（生产现状）：单点 %.2f%% / 双档 %.2f%% / 每日至少一中 %.1f%%"
          % (base_te["hit"], base_te["band"], base_te["day_any"]))

    print("\n%-28s %9s %9s %8s %9s %8s %8s" %
          ("规则", "训练单点", "留出单点", "Δ单点", "留出双档", "Δ双档", "留出每日"))
    for lb, a, b in sorted(res, key=lambda x: -x[2]["hit"])[:26]:
        print("%-28s %8.2f%% %8.2f%% %+7.2f %8.2f%% %+7.2f %7.1f%%" %
              (lb, a["hit"], b["hit"], b["hit"] - base_te["hit"],
               b["band"], b["band"] - base_te["band"], b["day_any"]))

    print("\n同时改善单点与双档、且留出段胜出的规则：")
    ok = [x for x in res if x[2]["hit"] > base_te["hit"] and x[2]["band"] >= base_te["band"]
          and x[1]["hit"] >= base_tr["hit"] - 0.5]
    if not ok:
        print("  （无）")
    for lb, a, b in sorted(ok, key=lambda x: -(x[2]["hit"] + x[2]["band"])):
        print("  %-28s 训练 %5.2f/%5.2f  留出 单点 %+5.2fpp 双档 %+5.2fpp" %
              (lb, a["hit"], a["band"], b["hit"] - base_te["hit"], b["band"] - base_te["band"]))


def cmd_final():
    """最终对比：全样本 + 两套时点切分（65/35、50/50），并报平局/1:1 占比（展示约束）。"""
    rows = load_rows()
    dates = sorted({r["date"] for r in rows})

    def spl(frac, purge_days=0):
        cut = dates[int(len(dates) * frac)]
        if purge_days:
            idx = dates.index(cut)
            hi = dates[min(len(dates) - 1, idx + purge_days)]
            return ([r for r in rows if r["date"] < cut],
                    [r for r in rows if r["date"] >= hi])
        return ([r for r in rows if r["date"] < cut],
                [r for r in rows if r["date"] >= cut])

    s65 = spl(0.65)
    s50 = spl(0.50, 3)

    cands = [
        ("A 现行：gap5 头条", pick_base),
        ("B 纯众数", make_gap_quad(0.0)),
        ("C 顺延 gap1", make_gap_quad(1.0)),
        ("D 顺延 gap2", make_gap_quad(2.0)),
        ("E 比分盘 argmax", make_mkt_rule()),
        ("F 比分盘 argmax·非平局", make_mkt_rule(b_nodraw=1.0)),
        ("G 比分盘 argmax·倾向象限", make_mkt_rule(b_dir=1.0)),
        ("H 市场·模型前8格", make_mkt_pool_rule(8)),
        ("I 市场·模型前8格非平", make_mkt_pool_rule(8, b_nodraw=1.0)),
        ("J 市场+模型 log0.3", make_mkt_rule(w_model=0.3)),
        ("K 市场+模型 log0.3 非平", make_mkt_rule(w_model=0.3, b_nodraw=1.0)),
        ("L 混合权重0.85+argmax", make_alpha_rule(0.85)),
        ("M 混合权重0.92+argmax", make_alpha_rule(0.92)),
        ("N 混合权重1.0+argmax", make_alpha_rule(1.0)),
        ("O 权重0.85+非平局", make_alpha_rule(0.85, b_nodraw=1.0)),
        ("P 权重0.92+非平局", make_alpha_rule(0.92, b_nodraw=1.0)),
        ("Q 权重1.0+非平局", make_alpha_rule(1.0, b_nodraw=1.0)),
        ("R 权重0.92+倾向象限", make_alpha_rule(0.92, b_dir=1.0)),
        ("S 权重0.92+非平+倾向", make_alpha_rule(0.92, b_nodraw=0.6, b_dir=0.6)),
        ("T 权重0.85+gap5", make_alpha_rule(0.85, head_rule="gap5")),
        ("U 权重1.0+gap5", make_alpha_rule(1.0, head_rule="gap5")),
    ]
    print("样本 %d 场 / %d 天（%s → %s）" % (len(rows), len(dates), dates[0], dates[-1]))
    print("切分 65/35：训练 %d / 留出 %d ；50/50(+3天隔离)：训练 %d / 留出 %d" %
          (len(s65[0]), len(s65[1]), len(s50[0]), len(s50[1])))
    print("\n%-26s %8s %8s %8s %8s %8s %7s" %
          ("规则", "全样本", "训练65", "留出65", "训练50", "留出50", "平局%"))
    out = []
    for lb, f in cands:
        full = evaluate(f, band_top2, rows=rows)
        a65 = evaluate(f, band_top2, rows=s65[0])
        b65 = evaluate(f, band_top2, rows=s65[1])
        a50 = evaluate(f, band_top2, rows=s50[0])
        b50 = evaluate(f, band_top2, rows=s50[1])
        out.append((lb, full, b65, b50))
        print("%-26s %7.2f%% %7.2f%% %7.2f%% %7.2f%% %7.2f%% %6.1f%%" %
              (lb, full["hit"], a65["hit"], b65["hit"], a50["hit"], b50["hit"], full["draw"]))
    print("\n稳定性排序（要求两套留出段都 ≥ 现行）：")
    base = out[0]
    ok = []
    for lb, full, b65, b50 in out[1:]:
        if b65["hit"] >= base[2]["hit"] and b50["hit"] >= base[3]["hit"]:
            ok.append((lb, full, b65, b50))
    if not ok:
        print("  （无）")
    for lb, full, b65, b50 in sorted(ok, key=lambda x: -x[1]["hit"]):
        print("  %-26s 全样本 %5.2f%%（%+5.2f）  留出65 %+5.2f  留出50 %+5.2f  双档 %5.2f%%  平局%.1f%%" %
              (lb, full["hit"], full["hit"] - base[1]["hit"],
               b65["hit"] - base[2]["hit"], b50["hit"] - base[3]["hit"],
               full["band"], full["draw"]))


if __name__ == "__main__":
    cmds = {"rows": cmd_rows, "check": cmd_check, "scan": cmd_scan,
            "split": cmd_split, "final": cmd_final}
    cmds[sys.argv[1] if len(sys.argv) > 1 else "check"]()
