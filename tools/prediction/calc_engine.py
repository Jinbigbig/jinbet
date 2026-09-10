#!/usr/bin/env python3
"""JinBet 泊松模型 V2.2 计算引擎。

实现 ANALYSIS_GUIDE.md 2.3 节的完整七步流程：
  基础λ(指数衰减) → xG融合 → H2H(A总量+B方向再分配) → 市场混合 → 动态校准 → 零封修正 → 泊松
输出: _calc_result.json
"""
import glob
import json
import math
import os
import re
import statistics
import datetime
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
# 当日日期：默认取系统当天，可用命令行参数覆盖（python calc_engine.py 2026-09-07）
TODAY = __import__("sys").argv[1] if len(__import__("sys").argv) > 1 else datetime.date.today().isoformat()
# 【2026-09-08 回测调优】基础λ的历史窗口与衰减
# 依据 window_sweep.py（2961 场 walk-forward，泊松对数似然）：
#   现行 N=10/DECAY=0.85 → 场均 logL -3.1314, 进球 MSE 1.6451
#   最优 N=30/DECAY=1.00 → -3.1029, MSE 1.5996（+0.91%）
#   平台区 N=20~30 × DECAY=0.95~1.00（+0.024~0.029），取保守值 N=25/DECAY=0.96
# 说明：长窗口降低估计噪声的收益 > 时效性的损失；DECAY=1.0 虽最优但完全丢弃近期
#       变化（换帅/转会/伤停），故保留轻微衰减 0.96（有效样本约 25 场）。
# 注意：RECENT_N 需与 _build_today_extras.py 的 recent 切片长度保持一致。
RECENT_N = 25
DECAY = 0.96
HOME_BOOST = 1.15   # 动态主客场系数回退默认值
AWAY_DISCOUNT = 0.90
ALPHA_H2H = 0.35    # B部分 H2H 权重上限
LIMIT_PCT = 0.25    # 单侧调整限幅
# 合理性约束：多重因子复合放大后需守住足球统计的合理区间
MAX_TOTAL = 4.20
MIN_TOTAL = 1.60
MAX_SINGLE = 3.20
# 第七步B 混合权重随强弱差自适应衰减（2026-09-07 实装，walk-forward 2462 场验证）
# 背景：固定 w=0.5 会用联赛平均形状稀释极端热门，实测 λ比≥1.8 的场次系统性低估强队 7~9pp
#       （周一005 利雅新月：纯泊松主胜 73.9% → 混合后 57.8%，市场隐含 79.2%）
# 公式：w_eff = w0 * max(FLOOR, 1 - K*(λ比-1))，λ比 = max(λh,λa)/min(λh,λa)
ADAPTIVE_MIX_K = 0.20      # 衰减斜率：λ比=2 → w0×0.80；λ比=3 → w0×0.60
ADAPTIVE_MIX_FLOOR = 0.35  # 衰减下限，保留一部分经验形状修正

# ---------------------------------------------------------------- 联赛进球环境画像
# 来源：results_history/ 全量赛果离线标定（7174 场）
# 用途：作为「先验收缩」目标，降低球队近5场小样本噪声
# 铁律：只做收缩（向联赛均值靠拢），禁止把 index 直接乘到 λ 上——
#       基础 λ 已由球队近期实际进球隐含了联赛环境，相乘=重复修正，实测 MAE 恶化 2.7%
LEAGUE_PROFILE = {"_meta": {}, "shrink": {"w": 0.25, "fallback_mean": 2.83, "min_n": 12},
                  "leagues": {}}


def _find_profile_file():
    """在脚本目录及其上两级目录查找 league_profile.json。"""
    here = BASE
    for _ in range(3):
        p = os.path.join(here, "league_profile.json")
        if os.path.exists(p):
            return p
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None


def load_league_profile():
    """加载联赛画像，失败则保持内置默认值（不阻断流水线）。"""
    global LEAGUE_PROFILE
    p = _find_profile_file()
    if not p:
        return LEAGUE_PROFILE
    try:
        d = json.load(open(p, encoding="utf-8"))
        if isinstance(d, dict) and d.get("leagues"):
            LEAGUE_PROFILE = d
    except Exception as e:  # noqa: BLE001
        print(f"[warn] league_profile.json 读取失败({e})，使用内置默认")
    return LEAGUE_PROFILE


def league_baseline(league):
    """返回该联赛的基线总进球均值；样本不足时用全局均值。"""
    prof = LEAGUE_PROFILE.get("leagues", {})
    g = prof.get(league)
    if not g:
        # 别名兜底：去掉「杯/联赛」等后缀再试
        for k, v in prof.items():
            if k and league and (k in league or league in k):
                g = v
                break
    if g and g.get("n", 0) >= LEAGUE_PROFILE.get("shrink", {}).get("min_n", 12):
        return float(g.get("mean") or LEAGUE_PROFILE["shrink"]["fallback_mean"])
    return float(LEAGUE_PROFILE.get("shrink", {}).get("fallback_mean", 2.83))


def league_score_freq(league):
    """返回该联赛平滑后的 7x7 经验比分频率 {(h,a): p}；无数据返回 None。

    数据来自 league_profile.json 的 score_freq（已按 K=50 向均匀分布收缩），
    用于第七步泊松矩阵的形状混合（walk-forward: Brier -0.45%，低比分四格校准改善）。
    """
    prof = LEAGUE_PROFILE.get("leagues", {})
    g = prof.get(league)
    if not g:
        for k, v in prof.items():
            if k and league and (k in league or league in k):
                g = v
                break
    if not g or "score_freq" not in g:
        return None
    freq = {}
    try:
        for k, v in g["score_freq"].items():
            h, a = k.split("-")
            freq[(int(h), int(a))] = float(v)
    except (ValueError, KeyError):
        return None
    return freq or None


def mix_score_matrix(grid, league, lam_ratio=None):
    """第七步形状后处理：模型矩阵与联赛经验比分频率按 w=0.5 混合。

    依据（2026-09-06 晚 二次 walk-forward 2438 场，前60%训练/后40%验证，双指标一致）：
      Top1 命中率随 w 单调升：w=0 → 11.03%，w=0.3 → 12.43%，w=0.5 → 13.37%，w=0.6 → 13.90%；
      Brier 同步改善：0.9376 → 0.9317 → 0.9296 → 0.9291；后40%段同样成立（14.14%/14.55%）。
      w=0.5~0.7 为平台区，取保守值 0.5（保留更多比赛特异性信号）。
      对照：「大球导向」（P(≥3)≥58% 时强选 3+ 球比分）Top1 降至 11.36%/8.66%，否决。

    【2026-09-07 自适应衰减】lam_ratio = max(λh,λa)/min(λh,λa) 越大（强弱越悬殊），
    经验频率的稀释越有害——联赛平均形状会把强队胜率拉回 40% 出头。
    故 w_eff = w0 * max(FLOOR, 1 - K*(λ比-1))。walk-forward 2462 场验证（k=0.20）：
      1X2 Brier 0.6303 → 0.6279（配对 +0.0025，Z=+2.3 显著）；后40%段 0.6203 → 0.6149；
      5 段时序中 4 段一致改善；
      Top1 13.28% → 13.04%（-0.24pp，Z=-0.8 不显著，噪声范围内）；
      强队方向校准偏差：λ比≥2.5 桶 -7.2pp → +1.0pp，λ比1.8~2.5 桶 -9.1pp → -6.8pp。
    注意：这里的衰减只作用于「形状混合」，与 λ clamp（MAX_TOTAL 等）无关。
    """
    freq = league_score_freq(league)
    if not freq:
        return grid
    w = float(LEAGUE_PROFILE.get("score_mix", {}).get("w", 0.5))
    if lam_ratio and lam_ratio > 1.0:
        w *= max(ADAPTIVE_MIX_FLOOR, 1.0 - ADAPTIVE_MIX_K * (lam_ratio - 1.0))
    out = {}
    for key, p in grid.items():
        out[key] = (1 - w) * p + w * freq.get(key, 0.0)
    tot = sum(out.values())
    if tot <= 0:
        return grid
    return {k: v / tot for k, v in out.items()}


def shrink_to_league(total_lambda, league, league_note_out=None):
    """联赛先验收缩：λ_total_final = λ_total*(1-w) + 联赛基线均值*w

    与「动态校准的联赛因子」职责不同：
      - 本函数处理的是**球队近5场小样本噪声**（先验，降方差）
      - 动态校准处理的是**模型系统性残差**（后验，纠偏差）
    两者串联不冲突。
    """
    w = float(LEAGUE_PROFILE.get("shrink", {}).get("w", 0.25))
    base = league_baseline(league)
    new_total = total_lambda * (1 - w) + base * w
    return new_total, w, base


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- Platt 概率校准（PLATT_ISOTONIC，V3.1）
# 病灶：泊松独立性导致平局全桶系统性低估（预测 22.6% vs 实际 26.6%，各概率桶 -3~-7pp）。
# 方案：胜/平/负三类各自做一维逻辑回归（特征=logit(p)），牛顿法拟合，缓存 platt_params.json。
# 验证（2026-09-06 walk-forward 2364 场测试集）：多类 Brier -0.37%，LogLoss -0.61%，
#       平局偏差 -3.8pp → +0.2pp；5 折时序 CV 3/5 折改善、另 2 折近似持平。
# 对照弃用：isotonic -0.15%、温度缩放 -0.02%、对角线膨胀 δ=1.2 虽修平局但比分 Top1 命中率 -1pp。
# 注意：不动比分矩阵（1X2 后处理），星级（基于首选比分概率）不受影响；
#       凯利信号改用校准后概率，方向不变但更贴近真实命中率。
PLATT_W = 1.0          # 校准强度（1.0=全量；若线上发现与市场混合叠加过修可降到 0.5）
PLATT_PARAMS = None


def _repo_root():
    here = BASE
    for _ in range(3):
        if os.path.isdir(os.path.join(here, "results_history")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return BASE


def _logit(p):
    p = clamp(p, 1e-4, 1 - 1e-4)
    return math.log(p / (1 - p))


def _fit_platt_1d(X, Y, iters=30):
    """牛顿法一维逻辑回归。X=logit(模型概率)，Y=0/1。返回 (a, b)。"""
    a, b = 1.0, 0.0
    for _ in range(iters):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(X, Y):
            p = 1 / (1 + math.exp(-clamp(a * x + b, -30, 30)))
            w = p * (1 - p) + 1e-9
            e = y - p
            ga += e * x
            gb += e
            haa -= w * x * x
            hab -= w * x
            hbb -= w
        haa -= 1e-6
        hbb -= 1e-6
        det = haa * hbb - hab * hab
        if abs(det) < 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a -= da
        b -= db
        if abs(da) < 1e-8 and abs(db) < 1e-8:
            break
    return a, b


def fit_platt_params(force=False):
    """从 results_history 重建模型流水线样本并拟合 Platt 参数。

    样本重建复刻引擎主链路（联赛收缩 + 经验形状混合 + 零封修正），
    保证拟合分布与应用分布一致。结果缓存 platt_params.json，当日已拟合则跳过。
    """
    global PLATT_PARAMS
    root = _repo_root()
    cache_path = os.path.join(root, "platt_params.json")
    today = datetime.date.today().isoformat()
    if not force and os.path.exists(cache_path):
        try:
            d = json.load(open(cache_path, encoding="utf-8"))
            if d.get("fitted_at") == today and d.get("params"):
                PLATT_PARAMS = d
                return PLATT_PARAMS
        except Exception:  # noqa: BLE001
            pass
    load_league_profile()
    recs = []
    rh = os.path.join(root, "results_history")
    if not os.path.isdir(rh):
        return None
    for f in sorted(glob.glob(os.path.join(rh, "*.json"))):
        if f.endswith("index.json"):
            continue
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for v in data.values():
            fs = v.get("fullScore") or ""
            if ":" not in fs:
                continue
            try:
                hg, ag = [int(x) for x in fs.split(":")]
            except ValueError:
                continue
            recs.append({"lg": v.get("league") or "其他", "home": v.get("home"),
                         "away": v.get("away"), "hg": hg, "ag": ag})
    recs.sort(key=lambda r: r.get("date", ""))
    gf, ga, zr = {}, {}, {}
    lg_tot, lg_hist = {}, {}
    MAXG = 8
    # 与 mix_score_matrix 同源（实际值取 league_profile.json 的 score_mix.w，当前 0.5）。
    # 历史遗留：此处字面量曾为 0.3，是 w=0.3 时代的 fallback，2026-09-06 改 w=0.5 时漏同步；
    # 因实际读档案值故从未生效，仅为代码卫生对齐，无功能影响。
    # 注意：实跑已启用自适应衰减(w_eff 随 λ比)，此处仍是固定 w —— 轻微不同源，影响有限。
    mix_w = float(LEAGUE_PROFILE.get("score_mix", {}).get("w", 0.5))
    k_shrink = float(LEAGUE_PROFILE.get("score_mix", {}).get("k_shrink", 50))
    shrink_w = float(LEAGUE_PROFILE.get("shrink", {}).get("w", 0.25))
    samples = []
    for r in recs:
        H, A, lg = r["home"], r["away"], r["lg"]
        gh, ga_ = gf.get(H, []), ga.get(A, [])
        if len(gh) >= 3 and len(gf.get(A, [])) >= 3 and len(ga.get(H, [])) >= 3 and len(ga_) >= 3:
            # 【2026-09-08】与实跑同源：近 RECENT_N 场 + DECAY 加权（原为近 5 场简单均值）
            h_gf = recent_avg(gh)
            h_ga = recent_avg(ga[H])
            a_gf = recent_avg(gf[A])
            a_ga = recent_avg(ga_)
            lh = h_gf * 0.75 + a_ga * 0.25
            la = a_gf * 0.75 + h_ga * 0.25
            base = league_baseline(lg)
            t = (lh + la) * (1 - shrink_w) + base * shrink_w
            if lh + la > 0:
                lh, la = lh * t / (lh + la), la * t / (lh + la)
            zh = zr.get(H, [])
            za = zr.get(A, [])
            f_h = (0.6 if len(zh) and sum(zh[-5:]) / len(zh[-5:]) <= 0.15 else
                   0.8 if len(zh) and sum(zh[-5:]) / len(zh[-5:]) <= 0.25 else
                   1.0 if len(zh) and sum(zh[-5:]) / len(zh[-5:]) <= 0.40 else 1.2) if zh else 0.8
            f_a = (0.6 if len(za) and sum(za[-5:]) / len(za[-5:]) <= 0.15 else
                   0.8 if len(za) and sum(za[-5:]) / len(za[-5:]) <= 0.25 else
                   1.0 if len(za) and sum(za[-5:]) / len(za[-5:]) <= 0.40 else 1.2) if za else 0.8
            ph = [pmf(i, lh) * (f_h if i == 0 else 1.0) for i in range(MAXG + 1)]
            pa = [pmf(j, la) * (f_a if j == 0 else 1.0) for j in range(MAXG + 1)]
            m = [[ph[i] * pa[j] for j in range(MAXG + 1)] for i in range(MAXG + 1)]
            s = sum(sum(row) for row in m)
            m = [[v / s for v in row] for row in m]
            hist = lg_hist.get(lg, [])
            if len(hist) >= 40 and mix_w > 0:
                cnt = Counter(hist)
                n2 = len(hist)
                tot = 0.0
                out = [[0.0] * (MAXG + 1) for _ in range(MAXG + 1)]
                for i in range(MAXG + 1):
                    for j in range(MAXG + 1):
                        ev_ = (n2 * cnt.get((i, j), 0) / n2 + k_shrink * (1 / 81)) / (n2 + k_shrink)
                        out[i][j] = (1 - mix_w) * m[i][j] + mix_w * ev_
                        tot += out[i][j]
                m = [[v / tot for v in row] for row in out]
            p_hw = sum(m[i][j] for i in range(MAXG + 1) for j in range(MAXG + 1) if i > j)
            p_dr = sum(m[i][i] for i in range(MAXG + 1))
            y = 0 if r["hg"] > r["ag"] else (1 if r["hg"] == r["ag"] else 2)
            samples.append((p_hw, p_dr, 1 - p_hw - p_dr, y))
        for team, gs, gc in ((H, r["hg"], r["ag"]), (A, r["ag"], r["hg"])):
            gf.setdefault(team, []).append(gs)
            ga.setdefault(team, []).append(gc)
            zr.setdefault(team, []).append(1 if gc == 0 else 0)
        lg_tot.setdefault(lg, []).append(r["hg"] + r["ag"])
        lg_hist.setdefault(lg, []).append((r["hg"], r["ag"]))
    if len(samples) < 300:
        return None
    params = {}
    for k, name in enumerate(("home", "draw", "away")):
        X = [_logit(s[k]) for s in samples]
        Y = [1.0 if s[3] == k else 0.0 for s in samples]
        params[name] = [round(v, 4) for v in _fit_platt_1d(X, Y)]
    PLATT_PARAMS = {"fitted_at": today, "n_samples": len(samples), "w": PLATT_W,
                    "params": params,
                    "note": "胜平负 Platt 校准；样本复刻引擎主链路（收缩+形状混合+零封）"}
    try:
        json.dump(PLATT_PARAMS, open(cache_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    except OSError:
        pass
    return PLATT_PARAMS


def apply_platt(p_home, p_draw, p_away):
    """胜平负概率 Platt 校准；无参数时原样返回。"""
    if not PLATT_PARAMS or PLATT_W <= 0:
        return p_home, p_draw, p_away
    w = float(PLATT_PARAMS.get("w", PLATT_W))
    params = PLATT_PARAMS.get("params", {})
    if not params:
        return p_home, p_draw, p_away
    out = []
    for k, p in enumerate((p_home, p_draw, p_away)):
        name = ("home", "draw", "away")[k]
        a, b = params.get(name, (1.0, 0.0))
        q = 1 / (1 + math.exp(-clamp(a * _logit(p) + b, -30, 30)))
        out.append((1 - w) * p + w * q)
    tot = sum(out)
    return tuple(v / tot for v in out)


def pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def wavg(vals):
    """指数衰减加权平均，vals[0] 为最近一场。"""
    w = [DECAY ** i for i in range(len(vals))]
    return sum(v * wi for v, wi in zip(vals, w)) / sum(w)


def recent_avg(seq_oldest_first):
    """历史场均（由旧到新的序列）→ 取最近 RECENT_N 场做 DECAY 加权。

    【2026-09-08】Platt 拟合原本写死近 5 场简单均值，与实跑（近 N 场 + 指数衰减）
    不同源；统一走此函数，保证校准拟合与实跑分布一致。
    """
    return wavg(list(seq_oldest_first)[-RECENT_N:][::-1])


# ------------------------------------------------- V3 自适应校准路线图
# 说明：每个模块登记"是否启用 + 启用所需样本量"。运行时 roadmap_status() 打印进度，
# 达到样本量却仍未启用的会标记为 READY，提醒及时接入，避免改进项被遗忘。
V3_CONFIG = {
    "EWMA_MAD": {"enabled": True, "min_samples": 0, "alpha": 0.25, "mad_k": 3.0,
                 "damp": 0.6, "clamp": (0.88, 1.15),
                 "note": "EWMA(a=0.25)+MAD去极值求全局偏差比，替代三档跳变系数"},
    "LEAGUE_SHRINK": {"enabled": True, "min_samples": 0, "prior_k": 8, "min_n": 5,
                      "damp": 0.6, "clamp": (0.85, 1.15),
                      "note": "按联赛分层+经验贝叶斯收缩，样本不足时向全局因子收缩"},
    # ---- V3.1 联赛进球环境（2026-09-06 实装，经 walk-forward + 5折时序CV 验证）----
    "LEAGUE_PRIOR_SHRINK": {"enabled": True, "min_samples": 0, "w": 0.25,
                            "note": "联赛先验收缩 λ*(1-w)+联赛基线*w（w=0.25）。"
                                    "实测MAE 1.2892→1.2538(-2.75%)，配对Z=5.06；5折时序CV各折一致改善(-2.19%)。"
                                    "数据: league_profile.json（7174场/44联赛）。"
                                    "警告: 禁止改成 index 直接相乘——实测恶化+2.69%"},
    "H2H_LEAGUE_NORM": {"enabled": True, "min_samples": 0,
                        "note": "H2H分档阈值按联赛基线归一(1.41/1.06/0.88/0.71×)，"
                                "解决德甲3.0球≠韩职3.0球的问题。弱验证(样本80场)，需持续观察"},
    "LEAGUE_DIST_SHAPE": {"enabled": True, "min_samples": 0,
                          "note": "联赛经验比分频率混合(第七步B, w=0.5, K=50收缩)："
                                  "walk-forward Brier -0.45%，0-0高估+3.0pp→+1.6pp，1-1校准改善。"
                                  "数据: league_profile.json score_freq(34联赛)。"
                                  "2026-09-07 加自适应衰减 w_eff=w0×max(0.35,1-0.20×(λ比-1))："
                                  "1X2 Brier -0.38%(Z=+2.3)，λ比≥2.5桶强队低估-7.2pp→+1.0pp，Top1 -0.24pp(不显著)"},
    "PLATT_ISOTONIC": {"enabled": True, "min_samples": 300,
                       "note": "胜平负 Platt 校准已启用(V3.1)：Brier -0.37%、平局偏差-3.8pp→+0.2pp；"
                               "isotonic/温度缩放/对角线膨胀均已验证劣于 Platt，弃用"},
    "DIXON_COLES_TAU": {"enabled": False, "min_samples": 0, "rejected": True,
                        "note": "❌ 2026-09-06 验证不通过：全局ρ网格搜索最优-0.12，Brier仅-0.09%，"
                                "且0-0校准恶化(9.5%→10.7%，实际6.5%)。由 LEAGUE_DIST_SHAPE 经验混合替代"},
    "BRIER_OPT": {"enabled": False, "min_samples": 500,
                  "note": "周期寻优衰减0.85/xG权重/H2H权重/市场混合α/clamp边界，walk-forward防过拟合"},
    "HEDGE_ENSEMBLE": {"enabled": False, "min_samples": 500,
                       "note": "泊松/DC/Elo/市场多专家Hedge加权 w∝exp(-ηL)"},
    "KALMAN_STRENGTH": {"enabled": False, "min_samples": 200,
                        "note": "按xG残差在线更新攻防强度，主客场分离，赛季初向联赛均值回归"},
    "CLV_TRACK": {"enabled": False, "min_samples": 100,
                  "note": "记录推荐时赔率与收盘赔率，CLV长期为负则提高市场混合权重α"},
    "DRIFT_MONITOR": {"enabled": False, "min_samples": 200,
                      "note": "PSI/KS监控特征与预测分布漂移，超阈值自动触发重标定"},
}


def ratio_to_factor(ratio, damp=0.6, bounds=(0.88, 1.12)):
    """平滑映射偏差比→λ系数：模型高估(ratio>1)则下调λ；damp<1 表示只修正部分偏差。"""
    if not ratio or ratio <= 0:
        return 1.0
    return clamp((1.0 / ratio) ** damp, *bounds)


def robust_ewma(daily, cfg):
    """先按中位数绝对偏差剔除异常期（如8球大战），再对 ratio 做指数加权，抗单期噪声。"""
    pairs = [(d["date"], d["pred"] / d["actual"])
             for d in sorted(daily, key=lambda x: x["date"]) if d.get("actual") and d.get("pred")]
    if not pairs:
        return 1.0, [], []
    vals = [r for _, r in pairs]
    med = statistics.median(vals)
    mad = statistics.median([abs(v - med) for v in vals]) or 1e-9
    thr = cfg["mad_k"] * 1.4826 * mad
    kept = [(dt, r) for dt, r in pairs if abs(r - med) <= thr] or pairs
    dropped = [{"date": dt, "ratio": round(r, 3)}
               for dt, r in pairs if abs(r - med) > thr]
    ewma, series = None, []
    for dt, r in kept:
        ewma = r if ewma is None else cfg["alpha"] * r + (1 - cfg["alpha"]) * ewma
        series.append({"date": dt, "ratio": round(r, 3), "ewma": round(ewma, 3)})
    return ewma, dropped, series


def shrink_league(buckets, pred_mean, global_factor, cfg):
    """按联赛分层：f = (n·f_local + K·f_global) / (n + K)，样本少自动向全局收缩。"""
    factors, detail = {}, {}
    for lg, b in buckets.items():
        n = b["n"]
        if n < cfg["min_n"]:
            factors[lg] = round(global_factor, 3)
            detail[lg] = {"n": n, "factor": round(global_factor, 3), "shrunk": True}
            continue
        am = b["actual"] / n
        f_local = ratio_to_factor(pred_mean / am if am else 1.0, cfg["damp"], cfg["clamp"])
        f = clamp((n * f_local + cfg["prior_k"] * global_factor) / (n + cfg["prior_k"]), *cfg["clamp"])
        factors[lg] = round(f, 3)
        detail[lg] = {"n": n, "actual_mean": round(am, 2), "local": round(f_local, 3),
                      "factor": round(f, 3), "shrunk": False}
    return factors, detail


def roadmap_status(n_samples):
    """返回各模块启用进度；达到样本量却未启用的标记 READY，提醒接入。"""
    lines = []
    for name, cfg in V3_CONFIG.items():
        need = cfg["min_samples"]
        if cfg["enabled"]:
            state = "ON"
        elif cfg.get("rejected"):
            state = "REJECTED"
        elif need and n_samples >= need:
            state = "READY"
        else:
            state = f"{n_samples}/{need}"
        lines.append(f"  [{'x' if cfg['enabled'] else ' '}] {name:<15} {state:<8} {cfg['note'][:40]}")
    return lines


# ------------------------------------------------- 待启用模块占位（达到样本量后实现）
def platt_calibrate(probs, outcomes):
    """TODO(V3)：Platt/isotonic 概率校准，让"说60%的场次真有60%命中"。触发：≥300场带结果样本。"""
    raise NotImplementedError("PLATT_ISOTONIC 未实现：需先累积标注样本并评估可靠性曲线")


def dixon_coles_tau(score_matrix):
    """TODO(V3)：拟合低比分相依参数 τ，修正 0-0/1-0/0-1/1-1。触发：≥200场。"""
    raise NotImplementedError("DIXON_COLES_TAU 未实现")


def brier_optimize(history):
    """TODO(V3)：以 Brier/对数损失为目标周期寻优超参。触发：≥500场 + walk-forward。"""
    raise NotImplementedError("BRIER_OPT 未实现")


def hedge_weights(losses, eta=0.5):
    """TODO(V3)：多专家 Hedge 加权 w ∝ exp(-η·L)。触发：≥500场。"""
    raise NotImplementedError("HEDGE_ENSEMBLE 未实现")


def kalman_update_strength(team, xg_residual):
    """TODO(V3)：卡尔曼/Elo 在线更新攻防强度，主客场分离。触发：≥200场。"""
    raise NotImplementedError("KALMAN_STRENGTH 未实现")


def track_clv(pick_odds, closing_odds):
    """TODO(V3)：CLV 反馈，长期为负则提高市场混合权重 α。触发：≥100场。"""
    raise NotImplementedError("CLV_TRACK 未实现")


def drift_check(feat_hist, feat_now):
    """TODO(V3)：PSI/KS 漂移监控，超阈值触发重标定。触发：≥200场。"""
    raise NotImplementedError("DRIFT_MONITOR 未实现")


def read_daily_pred(d):
    """读取某日预测口径。

    优先 predictions/<d>/pred_snapshot.json（λ 期望口径，最准）；
    否则回退解析 HTML：先用 λ=主x/客y 求总进球期望，无 λ 才用首选比分（众数口径，天然偏低）。
    返回 {"n": 场次数, "pred_mean": 均值, "caliber": "lambda"/"score"}
    """
    jp = os.path.join(BASE, "predictions", d, "pred_snapshot.json")
    if os.path.exists(jp):
        try:
            snap = json.load(open(jp, encoding="utf-8"))
            lams = [m["lam_total"] for m in snap.get("matches", []) if m.get("lam_total")]
            if lams:
                return {"n": len(lams), "pred_mean": sum(lams) / len(lams), "caliber": "lambda"}
        except Exception:
            pass

    rp = os.path.join(BASE, "predictions", d, "index.html")
    if not os.path.exists(rp):
        return None
    content = open(rp, encoding="utf-8").read()
    # λ 口径：取每处 λ=主a/客b 的总进球（同一场多处以最终值为准，取均值仍无偏）
    lam = re.findall(r'λ[^0-9]{0,8}([0-9]+\.[0-9]+)\s*/\s*(?:客)?([0-9]+\.[0-9]+)', content)
    if lam:
        tots = [float(a) + float(b) for a, b in lam]
        return {"n": len(tots), "pred_mean": sum(tots) / len(tots), "caliber": "lambda"}
    # 兜底：首选比分口径（旧版冒号 / 新版连字符，且带 data-page-node-id 等属性）
    scores = re.findall(r'class="pred-score"[^>]*>\s*(\d+)\s*[:\-]\s*(\d+)\s*<', content)
    if not scores:
        return None
    tot = sum(int(a) + int(b) for a, b in scores)
    return {"n": len(scores), "pred_mean": tot / len(scores), "caliber": "score"}


def dump_prediction_snapshot(out_matches, date=None):
    """把当日预测写成 predictions/<date>/pred_snapshot.json，供后续校准直接读取。

    目的：不再依赖解析 HTML（版式一变就失效），并为 PLATT/Brier 等后续模块留存标注基础。
    """
    d = date or TODAY
    folder = os.path.join(BASE, "predictions", d)
    if not os.path.isdir(folder):
        return None
    rows = []
    for m in out_matches:
        top = (m.get("top_scores") or [{}])[0]
        rows.append({
            "id": m.get("matchNumStr"), "home": m.get("home"), "away": m.get("away"),
            "league": m.get("league"), "lam_home": m.get("lam_home"), "lam_away": m.get("lam_away"),
            "lam_total": m.get("lam_total"), "top_score": top.get("score"),
            "top_prob": top.get("prob"), "stars": m.get("stars"),
            "prob_home": (m.get("prob") or {}).get("home"),
            "prob_draw": (m.get("prob") or {}).get("draw"),
            "prob_away": (m.get("prob") or {}).get("away"),
            "top_scores": m.get("top_scores"),
            "quad_top": m.get("quad_top"),
        })
    data = {"date": d, "count": len(rows), "engine": "poisson-v2.2", "matches": rows}
    json.dump(data, open(os.path.join(folder, "pred_snapshot.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return os.path.join(folder, "pred_snapshot.json")


# ---------------------------------------------------------------- 动态校准
def compute_calibration():
    """近7天预测总进球 vs 实际：EWMA+MAD 抗噪求全局因子，再按联赛分层收缩。"""
    results = json.load(open(os.path.join(BASE, "results_data.json"), encoding="utf-8"))
    daily = []
    league_buckets = {}

    for i in range(1, 8):
        d = (datetime.date.fromisoformat(TODAY) - datetime.timedelta(days=i)).isoformat()
        pred = read_daily_pred(d)
        if not pred:
            continue
        pred_mean = pred["pred_mean"]

        actuals = [v for k, v in results.items() if k.startswith(d + "_")]
        tot, cnt = 0, 0
        for v in actuals:
            m = re.match(r"(\d+)\s*[:-]\s*(\d+)", str(v.get("fullScore") or ""))
            if m:
                tot += int(m.group(1)) + int(m.group(2))
                cnt += 1
        if cnt:
            daily.append({"date": d, "pred": round(pred_mean, 2),
                          "actual": round(tot / cnt, 2), "n": cnt,
                          "caliber": pred["caliber"], "pred_n": pred["n"]})
            # 按联赛累积（用当日所有实际比赛）
            for v in actuals:
                m = re.match(r"(\d+)\s*[:-]\s*(\d+)", str(v.get("fullScore") or ""))
                if not m:
                    continue
                lg = v.get("league") or "其他"
                b = league_buckets.setdefault(lg, {"actual": 0, "n": 0})
                b["actual"] += int(m.group(1)) + int(m.group(2))
                b["n"] += 1

    labeled = sum(1 for v in results.values() if v.get("fullScore"))
    if not daily:
        return {"ratio": 1.0, "factor": 1.0, "daily": [], "note": "无历史数据",
                "labeled_samples": labeled}

    # 口径统一：只保留与主流口径一致的期（λ期望口径优先），
    # 避免"首选比分(众数)口径"与"实际均值(期望)口径"混算造成恒定低估。
    cnt_cal = Counter(d["caliber"] for d in daily)
    main_cal = "lambda" if cnt_cal.get("lambda") else cnt_cal.most_common(1)[0][0]
    used = [d for d in daily if d["caliber"] == main_cal] or daily
    excluded = [{"date": d["date"], "caliber": d["caliber"],
                 "pred": d["pred"], "actual": d["actual"]}
                for d in daily if d["caliber"] != main_cal]

    p_mean = sum(d["pred"] for d in used) / len(used)
    a_mean = sum(d["actual"] for d in used) / len(used)
    raw_ratio = p_mean / a_mean if a_mean else 1.0

    cfg_e = V3_CONFIG["EWMA_MAD"]
    ewma_ratio, dropped, series = robust_ewma(used, cfg_e)
    if cfg_e["enabled"]:
        ratio = ewma_ratio
        factor = ratio_to_factor(ratio, cfg_e["damp"], cfg_e["clamp"])
    else:  # 旧版三档跳变（保留回退）
        ratio = raw_ratio
        factor = 0.92 if ratio > 1.10 else (1.08 if ratio < 0.90 else 1.00)

    if ratio > 1.10:
        desc = "模型系统性高估"
    elif ratio < 0.90:
        desc = "模型系统性低估"
    else:
        desc = "偏差在容忍区间"

    # 按联赛分组：V3 经验贝叶斯收缩，否则旧版三档
    cfg_l = V3_CONFIG["LEAGUE_SHRINK"]
    if cfg_l["enabled"]:
        lg_cal, lg_detail = shrink_league(league_buckets, p_mean, factor, cfg_l)
    else:
        lg_cal, lg_detail = {}, {}
        for lg, b in league_buckets.items():
            if b["n"] >= 5:
                am = b["actual"] / b["n"]
                r = p_mean / am if am else 1.0
                lg_cal[lg] = 0.92 if r > 1.10 else (1.08 if r < 0.90 else 1.00)

    return {
        "ratio": round(ratio, 3),
        "raw_ratio": round(raw_ratio, 3),
        "factor": round(factor, 3),
        "desc": desc,
        "pred_mean": round(p_mean, 2),
        "actual_mean": round(a_mean, 2),
        "daily": daily,
        "league_factors": lg_cal,
        "league_detail": lg_detail,
        "ewma_series": series,
        "dropped_periods": dropped,
        "caliber": main_cal,
        "excluded_periods": excluded,
        "labeled_samples": labeled,
        "v3_enabled": [k for k, v in V3_CONFIG.items() if v["enabled"]],
    }


# ---------------------------------------------------------------- 主计算
def calc_match(m, calib):
    home, away = m["home"], m["away"]
    league = m.get("league") or "其他"
    hr = m.get("home_recent") or []
    ar = m.get("away_recent") or []
    h2h = m.get("h2h") or []
    odds = m.get("odds") or {}
    xg = m.get("xg") or {}
    steps = []

    # ---------- 第一步：指数衰减加权基础λ ----------
    if hr and ar:
        h_gf, h_ga = wavg([x["gf"] for x in hr]), wavg([x["ga"] for x in hr])
        a_gf, a_ga = wavg([x["gf"] for x in ar]), wavg([x["ga"] for x in ar])
        lam_h = (h_gf * 0.75 + a_ga * 0.25) * HOME_BOOST
        lam_a = (a_gf * 0.75 + h_ga * 0.25) * AWAY_DISCOUNT
        note = f"主{h_gf:.2f}进/{h_ga:.2f}失 客{a_gf:.2f}进/{a_ga:.2f}失"
    else:
        oh, oa = odds.get("胜"), odds.get("负")
        # 【V3.1】赔率反推的锚点改用联赛基线均值，而非硬编码全局 2.5
        # 例：解放者杯基线 2.11 vs 德甲 3.31，用错锚点会系统性偏离 1.2 球
        _anchor = league_baseline(league)
        lam_h = (1 / float(oh) * _anchor) if oh else _anchor * 0.5
        lam_a = (1 / float(oa) * _anchor) if oa else _anchor * 0.4
        note = f"无近期战绩，按{league}基线{_anchor:.2f}赔率反推"
    steps.append(("基础λ", f"指数衰减{DECAY:g}^i,{note}", lam_h, lam_a))

    # ---------- 第二步：xG融合 ----------
    xg_h, xg_a = xg.get("home"), xg.get("away")
    if xg_h and xg_a:
        lam_h_xg = float(xg_h) * HOME_BOOST
        lam_a_xg = float(xg_a) * AWAY_DISCOUNT
        lam_h = 0.6 * lam_h + 0.4 * lam_h_xg
        lam_a = 0.6 * lam_a + 0.4 * lam_a_xg
        steps.append(("xG融合", f"40%,xG主{xg_h}/客{xg_a}", lam_h, lam_a))
    else:
        steps.append(("无xG数据", "无xG数据，沿用进球λ", lam_h, lam_a))

    # ---------- 第二步B：联赛先验收缩（V3.1 新增）----------
    # 球队近5场均值噪声大，向该联赛基线均值收缩 w=0.25（保持主客比例=总进球方向不变）
    # 实测（walk-forward 2364 场）：MAE 1.2892→1.2538(-2.75%)，5折时间序列CV各折一致改善
    # 注意：这里是「收缩」不是「相乘」——相乘会重复修正联赛环境，实测恶化 2.69%
    _tot = lam_h + lam_a
    if _tot > 0:
        _new_tot, _w, _base = shrink_to_league(_tot, league)
        _r = _new_tot / _tot
        lam_h *= _r
        lam_a *= _r
        steps.append(("联赛收缩", f"向{league}基线{_base:.2f}收缩{_w:.0%} "
                                  f"(总{_tot:.2f}→{_new_tot:.2f})", lam_h, lam_a))

    # ---------- 第三步 A：H2H 总进球（对称，改变总量） ----------
    h2h_info = ""
    if len(h2h) >= 3:
        h2h_avg = sum(x["home_goals"] + x["away_goals"] for x in h2h) / len(h2h)
        base_total = lam_h + lam_a
        f = h2h_avg / base_total if base_total else 1.0
        # 【V3.1】阈值按联赛基线归一：同样的 H2H 3.0 球，在韩职(基线2.40)是「极高频」，
        # 在德甲(基线3.31)只是「偏低」——绝对阈值会系统性误判。
        # 归一化系数由全局基线 2.83 反推：4.0→1.41× / 3.0→1.06× / 2.5→0.88× / 2.0→0.71×
        _lb = league_baseline(league)
        _t4, _t3, _t25, _t2 = _lb * 1.41, _lb * 1.06, _lb * 0.88, _lb * 0.71
        h2h_rel = h2h_avg / _lb if _lb else 1.0
        if h2h_avg >= _t4:
            f = max(f, 1.5)
        elif h2h_avg >= _t3:
            f = max(f, 1.3)
        elif h2h_avg >= _t25:
            f = max(f, 1.15)
        elif h2h_avg >= _t2:
            f = max(f, 1.0)
        else:
            f = min(f, 0.9)
        f = clamp(f, 0.85, 1.40)
        lam_h_A, lam_a_A = lam_h * f, lam_a * f
        h2h_info = f"近{len(h2h)}场场均{h2h_avg:.2f}球,总量因子{f:.3f}x"
    else:
        lam_h_A, lam_a_A = lam_h, lam_a
        f = 1.0
        h2h_info = f"H2H数据不足3场(仅{len(h2h)}场),跳过总量调整"

    # ---------- 第三步 B：方向性再分配（非对称，总量守恒） ----------
    dir_info = ""
    if len(h2h) >= 3:
        w = [DECAY ** i for i in range(len(h2h))]
        sw = sum(w)
        score_sum = 0.0
        hg_wsum = 0.0
        tot_wsum = 0.0
        for x, wi in zip(h2h, w):
            hg, ag = x["home_goals"], x["away_goals"]
            sc = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
            score_sum += wi * sc
            hg_wsum += wi * hg
            tot_wsum += wi * (hg + ag)
        s_h2h = score_sum / sw
        p_h2h = hg_wsum / tot_wsum if tot_wsum else 0.5
        adv = 0.6 * p_h2h + 0.4 * s_h2h
        total_A = lam_h_A + lam_a_A
        p_base = lam_h_A / total_A if total_A else 0.5
        p_mix = (1 - ALPHA_H2H) * p_base + ALPHA_H2H * adv
        lam_h_B = total_A * p_mix
        lam_a_B = total_A * (1 - p_mix)
        # ±25% 限幅并重新配平
        lam_h_B = clamp(lam_h_B, lam_h_A * (1 - LIMIT_PCT), lam_h_A * (1 + LIMIT_PCT))
        lam_a_B = clamp(total_A - lam_h_B,
                        lam_a_A * (1 - LIMIT_PCT), lam_a_A * (1 + LIMIT_PCT))
        lam_h_B = total_A - lam_a_B
        dir_info = (f"方向再分配:加权胜率{s_h2h*100:.0f}%+进球占比{p_h2h*100:.0f}%"
                    f"→优势度{adv:.3f},混合占比{p_mix:.3f},总量守恒{total_A:.2f}")
    else:
        lam_h_B, lam_a_B = lam_h_A, lam_a_A
        dir_info = "H2H数据不足3场,跳过方向调整"

    steps.append(("H2H调整", f"{h2h_info}|{dir_info}", lam_h_B, lam_a_B))

    # ---------- 第四步：市场隐含λ混合 ----------
    oh, oa = odds.get("胜"), odds.get("负")
    if oh and oa:
        try:
            mh, ma = 1 / float(oh) * 2.5, 1 / float(oa) * 2.5
            lam_h = 0.65 * lam_h_B + 0.35 * mh
            lam_a = 0.65 * lam_a_B + 0.35 * ma
            steps.append(("市场混合", f"35%,市场隐含主{mh:.2f}/客{ma:.2f}", lam_h, lam_a))
        except (ValueError, ZeroDivisionError):
            lam_h, lam_a = lam_h_B, lam_a_B
            steps.append(("市场混合", "赔率异常,跳过", lam_h, lam_a))
    else:
        lam_h, lam_a = lam_h_B, lam_a_B
        steps.append(("市场混合", "无赔率数据,跳过", lam_h, lam_a))

    # ---------- 第五步：动态校准 + 总量合理性约束 ----------
    lg_factor = calib.get("league_factors", {}).get(league, calib["factor"])
    lam_h *= lg_factor
    lam_a *= lg_factor
    cnote = f"×{lg_factor:.2f}({league})"
    # 多重因子复合放大后守住合理区间，避免产出统计上不可能的总进球
    total = lam_h + lam_a
    if total > MAX_TOTAL:
        s = MAX_TOTAL / total
        lam_h, lam_a = lam_h * s, lam_a * s
        cnote += f",总量约束→{MAX_TOTAL}"
    elif total < MIN_TOTAL:
        s = MIN_TOTAL / total
        lam_h, lam_a = lam_h * s, lam_a * s
        cnote += f",总量托底→{MIN_TOTAL}"
    if lam_h > MAX_SINGLE:
        lam_h = MAX_SINGLE
        cnote += ",主λ封顶"
    if lam_a > MAX_SINGLE:
        lam_a = MAX_SINGLE
        cnote += ",客λ封顶"
    steps.append(("动态校准", cnote, lam_h, lam_a))

    # ---------- 第六步：零封修正 ----------
    def zero_rate(rec):
        if not rec:
            return 0.25
        return sum(1 for x in rec if x["gf"] == 0) / len(rec)

    def zfactor(rate):
        if rate <= 0.15:
            return 0.6
        if rate <= 0.25:
            return 0.8
        if rate <= 0.40:
            return 1.0
        return 1.2

    zr_h, zr_a = zero_rate(hr), zero_rate(ar)
    f_h, f_a = zfactor(zr_h), zfactor(zr_a)
    steps.append(("零封修正",
                  f"P0主×{f_h}(零封{zr_h*100:.0f}%)/客×{f_a}(零封{zr_a*100:.0f}%)",
                  lam_h, lam_a))

    # ---------- 第七步：泊松计算 ----------
    grid = {}
    for k1 in range(7):
        for k2 in range(7):
            p = pmf(k1, lam_h) * pmf(k2, lam_a)
            if k1 == 0:
                p *= f_h
            if k2 == 0:
                p *= f_a
            grid[(k1, k2)] = p
    tot = sum(grid.values())
    grid = {k: v / tot for k, v in grid.items()}
    # ---------- 第七步B：联赛经验比分频率混合（LEAGUE_DIST_SHAPE，V3.1）----------
    # 泊松形状与联赛实测比分分布存在系统性偏差（0-0 高估、1-1 低估45%），
    # 与联赛平滑经验频率混合 w=0.3：walk-forward Brier -0.45%，低比分四格校准改善
    _lam_lo, _lam_hi = min(lam_h, lam_a), max(lam_h, lam_a)
    _lam_ratio = (_lam_hi / _lam_lo) if _lam_lo > 1e-9 else 99.0
    grid = mix_score_matrix(grid, league, _lam_ratio)
    ranked = sorted(grid.items(), key=lambda x: -x[1])[:4]

    # 胜平负概率（由修正后的分布求和）
    p_home = sum(p for (k1, k2), p in grid.items() if k1 > k2)
    p_draw = sum(p for (k1, k2), p in grid.items() if k1 == k2)
    p_away = sum(p for (k1, k2), p in grid.items() if k1 < k2)
    # ---------- 象限内首选比分（条件口径）：若倾向=主胜/平/负，该象限内概率最高的比分 ----------
    quad_top = {}
    for qname, qfilter in (("home", lambda k: k[0] > k[1]),
                           ("draw", lambda k: k[0] == k[1]),
                           ("away", lambda k: k[0] < k[1])):
        qcells = [(k, v) for k, v in grid.items() if qfilter(k)]
        (bk, bv) = max(qcells, key=lambda x: x[1])
        quad_top[qname] = {"score": f"{bk[0]}:{bk[1]}", "prob": round(bv * 100, 1)}
    # ---------- 第七步C：胜平负 Platt 校准（PLATT_ISOTONIC，V3.1）----------
    # 泊松独立性使平局系统性低估约 4pp；walk-forward Brier -0.37%、LogLoss -0.61%
    p_home_raw, p_draw_raw, p_away_raw = p_home, p_draw, p_away
    p_home, p_draw, p_away = apply_platt(p_home, p_draw, p_away)
    platt_applied = abs(p_draw - p_draw_raw) > 1e-6

    # ---------- 冷门信号 ----------
    signals = []
    try:
        if oh and p_home * float(oh) > 1.0:
            signals.append(f"凯利指数{p_home*float(oh):.2f}>1.0(主胜有价值)")
        if oa and p_away * float(oa) > 1.0:
            signals.append(f"凯利指数{p_away*float(oa):.2f}>1.0(客胜有价值)")
    except (ValueError, TypeError):
        pass
    rk_h, rk_a = m.get("home_rank"), m.get("away_rank")
    if rk_h and rk_a and oh and oa:
        try:
            # 排名明显占优却赔率更高 → 赔率与实力背离
            if rk_h < rk_a - 4 and float(oh) > float(oa):
                signals.append(f"排名背离(主{rk_h}位优于客{rk_a}位却赔率更高)")
            if rk_a < rk_h - 4 and float(oa) > float(oh):
                signals.append(f"排名背离(客{rk_a}位优于主{rk_h}位却赔率更高)")
        except (ValueError, TypeError):
            pass
    if len(signals) == 0:
        signals.append("无明显冷门信号")

    # ---------- 信心评级 ----------
    top_p = ranked[0][1]
    if top_p >= 0.15:
        stars = 5
    elif top_p >= 0.12:
        stars = 4
    elif top_p >= 0.09:
        stars = 3
    elif top_p >= 0.07:
        stars = 2
    else:
        stars = 1
    if any("凯利指数" in s or "排名背离" in s for s in signals):
        stars = max(1, stars - 1)
    if calib.get("ratio", 1.0) > 1.15:
        stars = max(1, stars - 1)

    # ---------- 链路字符串 ----------
    chain = " → ".join(
        f"{name}({info},主{lh:.2f}客{la:.2f})" if name != "零封修正"
        else f"{name}({info})"
        for name, info, lh, la in steps
    )
    chain += f" → 最终λ 主{lam_h:.2f} 客{lam_a:.2f}"
    if platt_applied:
        chain += (f" → Platt校准(1X2: 平局{p_draw_raw*100:.1f}%→{p_draw*100:.1f}%)")

    return {
        "matchNumStr": m["matchNumStr"], "league": league,
        "home": home, "away": away,
        "home_rank": rk_h, "away_rank": rk_a,
        "odds": odds,
        "lam_home": round(lam_h, 3), "lam_away": round(lam_a, 3),
        "lam_total": round(lam_h + lam_a, 3),
        "h2h_count": len(h2h),
        "h2h_factor": round(f, 3),
        "dir_applied": len(h2h) >= 3,
        "chain": chain,
        "top_scores": [{"score": f"{k1}:{k2}", "prob": round(p * 100, 1)}
                       for (k1, k2), p in ranked],
        "prob": {"home": round(p_home * 100, 1), "draw": round(p_draw * 100, 1),
                 "away": round(p_away * 100, 1)},
        "quad_top": quad_top,
        "zero": {"home_rate": round(zr_h, 3), "away_rate": round(zr_a, 3),
                 "f_home": f_h, "f_away": f_a},
        "signals": signals,
        "stars": stars,
        "news": m.get("news", ""),
        "xg": {"home": xg_h, "away": xg_a},
    }


def main():
    # 加载联赛进球环境画像（先验收缩 + H2H 阈值归一 + 赔率反推锚点）
    load_league_profile()
    # Platt 胜平负概率校准（当日已拟合则读缓存）
    pp = fit_platt_params()
    if pp:
        print(f"=== Platt 概率校准 === 样本 {pp['n_samples']} 场 | "
              f"home={pp['params']['home']} draw={pp['params']['draw']} away={pp['params']['away']}")
    _lp = LEAGUE_PROFILE
    print("=== 联赛进球环境画像 ===")
    print(f"来源 {_lp.get('_meta', {}).get('source', '?')} | "
          f"{_lp.get('_meta', {}).get('sample_matches', '?')} 场 | "
          f"{len(_lp.get('leagues', {}))} 个联赛 | 全局基线 {_lp.get('_meta', {}).get('global_mean', '?')}")
    print(f"收缩权重 w={_lp.get('shrink', {}).get('w')} "
          f"(向联赛基线收缩，非相乘——相乘会重复修正，实测恶化)")

    md = json.load(open(os.path.join(BASE, "scripts", "matches_data.json"), encoding="utf-8"))
    matches = {m["matchNumStr"]: m for m in md["matches"]}

    extra = {}
    for i in range(1, 7):
        p = os.path.join(BASE, f"_data_batch{i}.json")
        if os.path.exists(p):
            for m in json.load(open(p, encoding="utf-8")).get("matches", []):
                extra[m["matchNumStr"]] = m

    print("=== 动态校准 ===")
    calib = compute_calibration()
    print(f"偏差比 {calib['ratio']} (预测均值{calib.get('pred_mean')} vs 实际均值{calib.get('actual_mean')}) "
          f"→ λ×{calib['factor']}  [{calib.get('desc')}]")
    for d in calib.get("daily", []):
        print(f"  {d['date']}  预测{d['pred']}  实际{d['actual']}  ({d['n']}场)")
    if calib.get("ewma_series"):
        print(f"  EWMA 轨迹: " + " → ".join(f"{s['date'][5:]}:{s['ewma']}" for s in calib["ewma_series"]))
    if calib.get("dropped_periods"):
        print(f"  MAD 剔除异常期: {calib['dropped_periods']}")
    print(f"联赛因子: {calib.get('league_factors')}")
    print("\n=== V3 校准路线图（达到样本量标记 READY 后即可启用）===")
    for line in roadmap_status(calib.get("labeled_samples", 0)):
        print(line)

    out = []
    print("\n=== 逐场计算 ===")
    for num in sorted(matches.keys()):
        m = dict(matches[num])
        m.update({k: v for k, v in extra.get(num, {}).items() if v is not None})
        r = calc_match(m, calib)
        out.append(r)
        top = r["top_scores"][0]
        flag = "B✓" if r["dir_applied"] else "B✗"
        print(f"{num} {r['home']}vs{r['away']:<10} λ{r['lam_home']:.2f}/{r['lam_away']:.2f} "
              f"总分{r['lam_total']:.2f} | {top['score']}({top['prob']}%) "
              f"{r['stars']}★ | H2H{r['h2h_count']}场 f={r['h2h_factor']} {flag}")

    json.dump({"today": TODAY, "calibration": calib, "matches": out},
              open(os.path.join(BASE, "_calc_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    snap = dump_prediction_snapshot(out)
    print(f"\n共 {len(out)} 场，已写入 _calc_result.json")
    if snap:
        print(f"预测快照已写入 {snap}（后续校准直接读取，不再解析 HTML）")


if __name__ == "__main__":
    main()
