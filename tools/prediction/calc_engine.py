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
import datetime

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


# ---------------------------------------------------------------- 动态校准
def compute_calibration():
    """读取近7天报告的预测总进球均值 vs 实际均值，计算偏差比与校准因子。"""
    results = json.load(open(os.path.join(BASE, "results_data.json"), encoding="utf-8"))
    daily = []
    league_buckets = {}

    for i in range(1, 8):
        d = (datetime.date(2026, 9, 5) - datetime.timedelta(days=i)).isoformat()
        rp = os.path.join(BASE, "predictions", d, "index.html")
        if not os.path.exists(rp):
            continue
        content = open(rp, encoding="utf-8").read()
        scores = re.findall(r'class="pred-score">(\d+):(\d+)<', content)
        if not scores:
            continue
        pred_mean = sum(int(a) + int(b) for a, b in scores) / len(scores)

        actuals = [v for k, v in results.items() if k.startswith(d + "_")]
        tot, cnt = 0, 0
        for v in actuals:
            m = re.match(r"(\d+)\s*[:-]\s*(\d+)", str(v.get("fullScore") or ""))
            if m:
                tot += int(m.group(1)) + int(m.group(2))
                cnt += 1
        if cnt:
            daily.append({"date": d, "pred": round(pred_mean, 2),
                          "actual": round(tot / cnt, 2), "n": cnt})
            # 按联赛累积（用当日所有实际比赛）
            for v in actuals:
                m = re.match(r"(\d+)\s*[:-]\s*(\d+)", str(v.get("fullScore") or ""))
                if not m:
                    continue
                lg = v.get("league") or "其他"
                b = league_buckets.setdefault(lg, {"actual": 0, "n": 0})
                b["actual"] += int(m.group(1)) + int(m.group(2))
                b["n"] += 1

    if not daily:
        return {"ratio": 1.0, "factor": 1.0, "daily": [], "note": "无历史数据"}

    p_mean = sum(d["pred"] for d in daily) / len(daily)
    a_mean = sum(d["actual"] for d in daily) / len(daily)
    ratio = p_mean / a_mean if a_mean else 1.0

    if ratio > 1.10:
        factor, desc = 0.92, "模型系统性高估"
    elif ratio < 0.90:
        factor, desc = 1.08, "模型系统性低估"
    else:
        factor, desc = 1.00, "偏差在容忍区间"

    # 按联赛分组（用联赛实际均值对比整体预测均值）
    lg_cal = {}
    for lg, b in league_buckets.items():
        if b["n"] >= 5:
            am = b["actual"] / b["n"]
            r = p_mean / am if am else 1.0
            if r > 1.10:
                lg_cal[lg] = 0.92
            elif r < 0.90:
                lg_cal[lg] = 1.08
            else:
                lg_cal[lg] = 1.00

    return {
        "ratio": round(ratio, 3),
        "factor": factor,
        "desc": desc,
        "pred_mean": round(p_mean, 2),
        "actual_mean": round(a_mean, 2),
        "daily": daily,
        "league_factors": lg_cal,
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
    print(f"联赛因子: {calib.get('league_factors')}")

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
    print(f"\n共 {len(out)} 场，已写入 _calc_result.json")


if __name__ == "__main__":
    main()
