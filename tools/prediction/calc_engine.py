#!/usr/bin/env python3
"""JinBet 泊松模型 V2.2 计算引擎。

实现 ANALYSIS_GUIDE.md 2.3 节的完整七步流程：
  基础λ(指数衰减) → xG融合 → H2H(A总量+B方向再分配) → 市场混合 → 动态校准 → 零封修正 → 泊松
输出: _calc_result.json
"""
import json
import math
import os
import re
import statistics
import datetime
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-09-05"
DECAY = 0.85
HOME_BOOST = 1.15   # 动态主客场系数回退默认值
AWAY_DISCOUNT = 0.90
ALPHA_H2H = 0.35    # B部分 H2H 权重上限
LIMIT_PCT = 0.25    # 单侧调整限幅
# 合理性约束：多重因子复合放大后需守住足球统计的合理区间
MAX_TOTAL = 4.20
MIN_TOTAL = 1.60
MAX_SINGLE = 3.20


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def wavg(vals):
    """指数衰减加权平均，vals[0] 为最近一场。"""
    w = [DECAY ** i for i in range(len(vals))]
    return sum(v * wi for v, wi in zip(vals, w)) / sum(w)


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
    "PLATT_ISOTONIC": {"enabled": False, "min_samples": 300,
                       "note": "胜平负/比分概率可靠性校准(Platt/isotonic)，Brier评估"},
    "DIXON_COLES_TAU": {"enabled": False, "min_samples": 200,
                        "note": "低比分(0-0/1-0/0-1/1-1)相依性τ修正，解决只校准均值不管分布形状"},
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
        d = (datetime.date(2026, 9, 5) - datetime.timedelta(days=i)).isoformat()
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
        lam_h = (1 / float(oh) * 2.5) if oh else 1.4
        lam_a = (1 / float(oa) * 2.5) if oa else 1.1
        note = "无近期战绩，赔率反推"
    steps.append(("基础λ", f"指数衰减0.85^i,{note}", lam_h, lam_a))

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

    # ---------- 第三步 A：H2H 总进球（对称，改变总量） ----------
    h2h_info = ""
    if len(h2h) >= 3:
        h2h_avg = sum(x["home_goals"] + x["away_goals"] for x in h2h) / len(h2h)
        base_total = lam_h + lam_a
        f = h2h_avg / base_total if base_total else 1.0
        if h2h_avg >= 4.0:
            f = max(f, 1.5)
        elif h2h_avg >= 3.0:
            f = max(f, 1.3)
        elif h2h_avg >= 2.5:
            f = max(f, 1.15)
        elif h2h_avg >= 2.0:
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
    ranked = sorted(grid.items(), key=lambda x: -x[1])[:4]

    # 胜平负概率（由修正后的分布求和）
    p_home = sum(p for (k1, k2), p in grid.items() if k1 > k2)
    p_draw = sum(p for (k1, k2), p in grid.items() if k1 == k2)
    p_away = sum(p for (k1, k2), p in grid.items() if k1 < k2)

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
        "zero": {"home_rate": round(zr_h, 3), "away_rate": round(zr_a, 3),
                 "f_home": f_h, "f_away": f_a},
        "signals": signals,
        "stars": stars,
        "news": m.get("news", ""),
        "xg": {"home": xg_h, "away": xg_a},
    }


def main():
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
