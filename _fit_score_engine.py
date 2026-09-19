# -*- coding: utf-8 -*-
"""比分引擎参数拟合 / A/B（walk-forward，逐场严格只用比赛日之前的赛果）。

对 _bt_rows2.json（引擎回测导出的逐场明细：队名/联赛/赔率/让球/比分盘/实际比分）
逐场重建评级，比较不同参数档下**精确比分**的表现，并与现有引擎的候选比分同场对照。

用法:
  python _fit_score_engine.py            # 扫 混合权重 × 共同分量 × 低比分修正
  python _fit_score_engine.py scorew     # 扫 总量里比分盘权重
  python _fit_score_engine.py opp        # 对手强度调整 开/关
"""
import itertools
import json
import math
import os
import sys

import score_engine as SE

ROWS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bt_rows2.json")


def near(score, hg, ag):
    try:
        h, a = (int(x) for x in score.split(":"))
    except Exception:
        return False
    return abs(h - hg) <= 1 and abs(a - ag) <= 1


def combos_for(mode):
    if mode == "scorew":
        return [{"score_w": w, "market_mix": 0.70, "lam3": 0.08, "tau": 0.0}
                for w in (0.0, 0.25, 0.50, 0.75, 1.00)]
    if mode == "opp":
        return [{"opp_adj": o, "market_mix": 0.5, "lam3": 0.10, "tau": 0.0}
                for o in (0, 1)]
    out = []
    for mm, l3, tau in itertools.product((0.0, 0.25, 0.40, 0.55, 0.70, 0.85),
                                         (0.0, 0.08, 0.16), (0.0, 1.0)):
        out.append({"market_mix": mm, "lam3": l3, "tau": tau})
    return out


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "all").strip().lower()
    combos = combos_for(mode)
    needs_state_pass = mode in ("opp",)
    hist = SE.Engine.load_history()
    rows = json.load(open(ROWS, encoding="utf-8"))
    tgt = {}
    for r in rows:
        tgt.setdefault(r["date"], []).append(r)
    by_date = {}
    for r in hist:
        by_date.setdefault(r["date"], []).append(r)
    dates = sorted(by_date)
    print("历史 %d 场 / 待评 %d 场 / %s → %s"
          % (len(hist), len(rows), dates[0], dates[-1]))
    cut = dates[int(len(dates) * 0.7)]

    def run(eng_params, combo_list):
        eng = SE.Engine(params=eng_params)
        acc = [{"n": 0, "h1": 0, "h3": 0, "nr": 0, "ll": 0.0, "x2": 0}
               for _ in combo_list]
        seg = [{"n": 0, "h1": 0, "h3": 0} for _ in range(2 * len(combo_list))]
        b = {"n": 0, "h1": 0, "h3": 0, "nr": 0}
        bseg = [{"n": 0, "h1": 0, "h3": 0} for _ in range(2)]
        for date in dates:
            for r in tgt.get(date, []):
                actual = "%d:%d" % (r["hg"], r["ag"])
                odds = {"胜": r["oh"], "平": r["od"], "负": r["oa"]}
                sd = r.get("score_odds") or {}
                L = eng.lambdas(r["home"], r["away"], r["league"], odds, sd)
                lh, la = L["lam_h"], L["lam_a"]
                pm = SE.market_dist(sd)
                si = 0 if date < cut else 1
                t0 = r["top"][0] if r["top"] else None
                if t0:
                    b["n"] += 1
                    o1 = t0 == actual
                    o3 = actual in r["top"][:3]
                    b["h1"] += 1 if o1 else 0
                    b["h3"] += 1 if o3 else 0
                    b["nr"] += 1 if near(t0, r["hg"], r["ag"]) else 0
                    bseg[si]["n"] += 1
                    bseg[si]["h1"] += 1 if o1 else 0
                    bseg[si]["h3"] += 1 if o3 else 0
                for i, c in enumerate(combo_list):
                    eng.p["tau_low"] = c.get("tau", 0.0)
                    m = eng.joint_final(lh, la, c["lam3"])
                    n = len(m)
                    P = {("%d:%d" % (h, a)): m[h][a] for h in range(n) for a in range(n)}
                    dist = eng.blend_market(P, pm, c["market_mix"]) if pm else P
                    cells = sorted(dist.items(), key=lambda x: -x[1])
                    t = cells[0][0]
                    a_ = acc[i]
                    a_["n"] += 1
                    o1 = t == actual
                    o3 = actual in [x for x, _ in cells[:3]]
                    a_["h1"] += 1 if o1 else 0
                    a_["h3"] += 1 if o3 else 0
                    a_["nr"] += 1 if near(t, r["hg"], r["ag"]) else 0
                    a_["ll"] += -math.log(max(dist.get(actual, 1e-6), 1e-6))
                    ph = sum(v for s, v in dist.items()
                             if (":" in s and int(s.split(":")[0]) > int(s.split(":")[1])
                                 or s == "胜其他"))
                    pdd = sum(v for s, v in dist.items()
                              if (":" in s and s.split(":")[0] == s.split(":")[1]) or s == "平其他")
                    pk = 0 if (ph >= pdd and ph >= 1 - ph - pdd) else (1 if pdd >= 1 - ph - pdd else 2)
                    act = 0 if r["hg"] > r["ag"] else (1 if r["hg"] == r["ag"] else 2)
                    a_["x2"] += 1 if pk == act else 0
                    seg[2 * i + si]["n"] += 1
                    seg[2 * i + si]["h1"] += 1 if o1 else 0
                    seg[2 * i + si]["h3"] += 1 if o3 else 0
            if date in by_date:
                eng.feed(by_date[date])
        return acc, seg, b, bseg

    if mode == "opp":
        for o in (0, 1):
            print("\n########## opp_adj=%d ##########" % o)
            c = [{"market_mix": 0.5, "lam3": 0.10, "tau": 0.0}]
            acc, seg, b, bseg = run({"opp_adj": o}, c)
            for i, cc in enumerate(c):
                a_ = acc[i]
                n = max(1, a_["n"])
                print("  %-24s n=%d Top1 %.2f%% Top3 %.2f%% ±1 %.2f%%  (训练 %.2f%% / 验证 %.2f%%)"
                      % ("opp_adj=%d" % o, a_["n"], a_["h1"] / n * 100, a_["h3"] / n * 100,
                         a_["nr"] / n * 100,
                         seg[0]["h1"] / max(1, seg[0]["n"]) * 100,
                         seg[1]["h1"] / max(1, seg[1]["n"]) * 100))
        return
    acc, seg, b, bseg = run({}, combos)

    bn = max(1, b["n"])
    print("\n%-34s %6s %8s %8s %8s %10s %8s"
          % ("参数档", "n", "Top1", "Top3", "±1球", "比分logloss", "1X2"))
    print("%-34s %6d %7.2f%% %7.2f%% %7.2f%% %10.4f %7.2f%%"
          % ("【基线】现有引擎口径", b["n"], b["h1"] / bn * 100, b["h3"] / bn * 100,
             b["nr"] / bn * 100, 0.0, 0.0))
    rank = []
    for i, c in enumerate(combos):
        a_ = acc[i]
        n = max(1, a_["n"])
        tag = " ".join("%s=%s" % (k, v) for k, v in c.items())
        print("%-34s %6d %7.2f%% %7.2f%% %7.2f%% %10.4f %7.2f%%"
              % (tag, a_["n"], a_["h1"] / n * 100, a_["h3"] / n * 100,
                 a_["nr"] / n * 100, a_["ll"] / n, a_["x2"] / n * 100))
        rank.append((a_["h1"] / n, a_["h3"] / n, i, tag))
    rank.sort(reverse=True)
    print("\n--- 训练/验证分段（前 70%% / 后 30%%）---")
    for h1, h3, i, tag in rank[:8]:
        tr, va = seg[2 * i], seg[2 * i + 1]
        print("  %-30s Top1 %.2f%% | 训练 %5.2f%% 验证 %5.2f%% | Top3 训练 %5.2f%% 验证 %5.2f%%"
              % (tag, h1 * 100,
                 tr["h1"] / max(1, tr["n"]) * 100, va["h1"] / max(1, va["n"]) * 100,
                 tr["h3"] / max(1, tr["n"]) * 100, va["h3"] / max(1, va["n"]) * 100))
    print("  %-30s Top1 %.2f%% | 训练 %5.2f%% 验证 %5.2f%% | Top3 训练 %5.2f%% 验证 %5.2f%%"
          % ("【基线】现有引擎", b["h1"] / bn * 100,
             bseg[0]["h1"] / max(1, bseg[0]["n"]) * 100,
             bseg[1]["h1"] / max(1, bseg[1]["n"]) * 100,
             bseg[0]["h3"] / max(1, bseg[0]["n"]) * 100,
             bseg[1]["h3"] / max(1, bseg[1]["n"]) * 100))


if __name__ == "__main__":
    main()
