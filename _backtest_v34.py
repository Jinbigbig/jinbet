"""JinBet calc_engine V3.4 历史回测 — walk-forward.

每场预测严格使用 **比赛日期之前** 的数据。
输出: 控制台汇总 + backtest_v34_result.json
"""
import glob, json, os, re, math, collections, datetime, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RH_DIR = os.path.join(REPO, "results_history")
OUT = os.path.join(HERE, "backtest_v34_result.json")
sys.path.insert(0, HERE)
import calc_engine as ce

FS_RE = re.compile(r"^\d+\s*[:\-]\s*\d+$")


def load_all():
    recs = []
    for f in sorted(glob.glob(os.path.join(RH_DIR, "*.json"))):
        if "index" in f: continue
        try: data = json.load(open(f, encoding="utf-8"))
        except: continue
        for key, v in data.items():
            fs = v.get("fullScore") or v.get("score") or ""
            if not FS_RE.match(fs): continue
            try: hg, ag = [int(x) for x in re.split(r"[:\-]", fs)]
            except: continue
            try:
                oh, od, oa = float(v["胜"]), float(v["平"]), float(v["负"])
            except: continue
            if not (oh > 1 and od > 1 and oa > 1): continue
            parts = key.split("_", 2)
            if len(parts) < 3: continue
            recs.append({
                "date": parts[0], "home": parts[1], "away": parts[2],
                "league": v.get("league") or "其他",
                "hg": hg, "ag": ag,
                "halfScore": v.get("halfScore") or "",
                "odds": {"胜": oh, "平": od, "负": oa},
            })
    recs.sort(key=lambda r: r["date"])
    return recs


def build_recent(recs_before, team, is_home_filter=None, n=25):
    seq = []
    for r in recs_before:
        if r["home"] == team: gf, ga, ih = r["hg"], r["ag"], True
        elif r["away"] == team: gf, ga, ih = r["ag"], r["hg"], False
        else: continue
        if is_home_filter is not None and ih != is_home_filter: continue
        seq.append({"gf": gf, "ga": ga})
        if len(seq) >= n: break
    return seq


def build_h2h(recs_before, h, a, n=5):
    seq = []
    for r in recs_before:
        if not ((r["home"] == h and r["away"] == a) or (r["home"] == a and r["away"] == h)):
            continue
        hg = r["hg"] if r["home"] == h else r["ag"]
        ag = r["ag"] if r["home"] == h else r["hg"]
        seq.append({"home_goals": hg, "away_goals": ag})
        if len(seq) >= n: break
    return seq


def build_input(match, before):
    return {
        "home": match["home"], "away": match["away"],
        "league": match["league"], "odds": match["odds"],
        "halfScore": match["halfScore"],
        "matchNumStr": match.get("matchNumStr") or "",
        "home_recent": build_recent(before, match["home"], None, ce.RECENT_N),
        "away_recent": build_recent(before, match["away"], None, ce.RECENT_N),
        "home_recent_home": build_recent(before, match["home"], True, ce.RECENT_N),
        "away_recent_away": build_recent(before, match["away"], True, ce.RECENT_N),
        "h2h": build_h2h(before, match["home"], match["away"], 5),
        "xg": {},
    }


# ---------- main ----------
recs = load_all()
print(f"总样本: {len(recs)} 场  日期范围: {recs[0]['date']} → {recs[-1]['date']}")

ce.load_league_profile()
ce.fit_platt_params(force=False)

# Strength db (Kalman) — 每场打完后 update
strength = {"teams": {}}

results = []
confusions = collections.Counter()
league_stats = collections.defaultdict(lambda: {"n": 0, "correct": 0, "brier": []})

brier_total = logloss_total = correct_1x2 = n_eval = 0.0
mkt_correct = mkt_brier = both_ok = mkt_only = model_only = both_bad = 0

R_KALMAN, Q_KALMAN = 3.0, 0.005

# 按日期
dates_sorted = sorted(set(r["date"] for r in recs))
START_OFFSET = 30   # 跳过前 30 天 (冷启动)

for i_d, date in enumerate(dates_sorted):
    day_recs = [r for r in recs if r["date"] == date]
    before = [r for r in recs if r["date"] < date]

    # 所有日期都先跑 Kalman 更新 (哪怕是跳过的)
    for r in day_recs:
        t = strength.setdefault("teams", {})
        _tot = ce.league_baseline(r["league"])
        _eh, _ea = _tot * 0.47, _tot * 0.42
        for team, is_home, agf, aga, exp_gf, exp_ga in [
            (r["home"], True, r["hg"], r["ag"], _eh, _ea),
            (r["away"], False, r["ag"], r["hg"], _ea, _eh),
        ]:
            ha = t.setdefault(team, {"ha": 1.0, "hd": 1.0, "aa": 1.0, "ad": 1.0,
                                     "P_ha": 1.0, "P_hd": 1.0, "P_aa": 1.0, "P_ad": 1.0})
            prefix = "h" if is_home else "a"
            for suffix, res in [("a", max(-1.5, min(1.5, agf - exp_gf))),
                                ("d", max(-1.5, min(1.5, aga - exp_ga)))]:
                sk = f"{prefix}{suffix}"
                pk = f"P_{sk}"
                P = ha[pk]
                K = P / (P + R_KALMAN)
                ha[sk] = ce.clamp(ha[sk] + K * res, 0.70, 1.40)
                ha[pk] = (1 - K) * P + Q_KALMAN

    if i_d < START_OFFSET:
        continue

    calib = {"ratio": 1.0, "factor": 1.0, "league_factors": {}}
    # V3.4: 注入自维护的 Kalman strength, market_w=None 让 calc_match 走 league_market_w 兜底
    _ctx = {"strength_db": strength, "kalman_apply": True, "market_w": None}

    for r in day_recs:
        m = build_input(r, before)
        try:
            out = ce.calc_match(m, calib, ctx=_ctx)
        except Exception as e:
            results.append({"date": date, "league": r["league"], "home": r["home"],
                            "away": r["away"], "error": str(e)[:120]})
            continue

        probs_raw = out.get("prob") or {}
        if not probs_raw:
            results.append({"date": date, "league": r["league"], "home": r["home"],
                            "away": r["away"], "error": f"no_probs keys={list(out.keys())[:6]}"})
            continue
        ph = float(probs_raw.get("home", 0)) / 100.0
        pd = float(probs_raw.get("draw", 0)) / 100.0
        pa = float(probs_raw.get("away", 0)) / 100.0
        s = ph + pd + pa
        if s > 0: ph, pd, pa = ph / s, pd / s, pa / s

        actual_idx = 0 if r["hg"] > r["ag"] else (1 if r["hg"] == r["ag"] else 2)
        label = ["H", "D", "A"]
        pick_idx = 0 if ph >= pd and ph >= pa else (1 if pd >= pa else 2)

        y = [1.0 if actual_idx == i else 0.0 for i in range(3)]
        brier = sum(([ph, pd, pa][i] - y[i]) ** 2 for i in range(3)) / 3.0
        logloss = -math.log(max([ph, pd, pa][actual_idx], 1e-9))
        ok = (pick_idx == actual_idx)
        confusions[(label[pick_idx], label[actual_idx])] += 1

        league_stats[r["league"]]["n"] += 1
        league_stats[r["league"]]["brier"].append(brier)
        if ok:
            league_stats[r["league"]]["correct"] += 1
            correct_1x2 += 1
        brier_total += brier
        logloss_total += logloss
        n_eval += 1

        # Market benchmark
        oh, od, oa = r["odds"]["胜"], r["odds"]["平"], r["odds"]["负"]
        pv = ce.devig_1x2(oh, od, oa)
        mp = 0 if pv[0] >= pv[1] and pv[0] >= pv[2] else (1 if pv[1] >= pv[2] else 2)
        mkt_ok = (mp == actual_idx)
        mkt_correct += int(mkt_ok)
        mkt_brier += sum((pv[i] - y[i]) ** 2 for i in range(3)) / 3.0

        if ok and mkt_ok: both_ok += 1
        elif ok and not mkt_ok: model_only += 1
        elif not ok and mkt_ok: mkt_only += 1
        else: both_bad += 1

        results.append({
            "date": date, "league": r["league"],
            "home": r["home"], "away": r["away"],
            "odds_hda": r["odds"], "half": r["halfScore"],
            "actual_score": f"{r['hg']}:{r['ag']}", "actual_1x2": label[actual_idx],
            "pred_1x2": label[pick_idx], "probs": {"H": round(ph, 4), "D": round(pd, 4), "A": round(pa, 4)},
            "brier": round(brier, 5), "logloss": round(logloss, 5),
            "correct_1x2": ok, "market_correct": mkt_ok,
        })

# ---------- 输出 ----------
N = n_eval
print("\n" + "=" * 90)
print(f"JinBet calc_engine V3.4 回测  有效样本 {N} 场  ({dates_sorted[START_OFFSET]} → {dates_sorted[-1]})")
print("=" * 90)
print(f"{'':>16}{'模型':^24}{'市场去水':^24}{'差异':^12}")
print(f"{'指标':>16}{'':^24}{'':^24}{'':^12}")
print(f"{'1X2 准确率':>16}{f'{correct_1x2/N*100:.2f}%':^24}{f'{mkt_correct/N*100:.2f}%':^24}{f'{(correct_1x2-mkt_correct)/N*100:+.2f}pp':^12}")
print(f"{'Brier(3c)':>16}{f'{brier_total/N:.5f}':^24}{f'{mkt_brier/N:.5f}':^24}{f'{(brier_total-mkt_brier)/N:+.5f}':^12}")
print(f"{'LogLoss':>16}{f'{logloss_total/N:.5f}':^24}{'—':^24}{'—':^12}")

# 混淆矩阵
print(f"\n--- 混淆矩阵 (pred \\ actual) ---")
print(f"{'':>10}  {'H':>10}  {'D':>10}  {'A':>10}  {'total':>8}  {'accuracy':>9}")
for p in ["H", "D", "A"]:
    row = [confusions[(p, a)] for a in ["H", "D", "A"]]
    rs = sum(row)
    acc = confusions[(p, p)] / rs * 100 if rs else 0
    print(f"{p:>10}  {row[0]:>10}  {row[1]:>10}  {row[2]:>10}  {rs:>8}  {acc:>8.1f}%")
tot_h = sum(confusions[("H", a)] for a in ["H", "D", "A"])
tot_d = sum(confusions[("D", a)] for a in ["H", "D", "A"])
tot_a = sum(confusions[("A", a)] for a in ["H", "D", "A"])
print(f"{'actual_total':>10}  {tot_h:>10}  {tot_d:>10}  {tot_a:>10}")

# 正确/错误分布
print(f"\n--- 模型 vs 市场 (拆解) ---")
print(f"  两者都对:    {both_ok:>5}  ({both_ok/N*100:.1f}%)")
print(f"  只模型对:    {model_only:>5}  ({model_only/N*100:.1f}%)  ← 模型有增量的场次")
print(f"  只市场对:    {mkt_only:>5}  ({mkt_only/N*100:.1f}%)  ← 模型偏差的场次")
print(f"  两者都错:    {both_bad:>5}  ({both_bad/N*100:.1f}%)")

# 联赛 top/bottom
print(f"\n--- 联赛表现 (>= 30 场) ---")
rows = []
for lg, st in league_stats.items():
    if st["n"] >= 30:
        br = sum(st["brier"]) / len(st["brier"])
        acc = st["correct"] / st["n"] * 100
        rows.append((lg, st["n"], acc, br))
rows.sort(key=lambda x: -x[2])
print(f"{'联赛':<14}{'场次':>6}{'准确率':>9}{'Brier':>11}")
for lg, nn, acc, br in rows:
    print(f"{lg:<14}{nn:>6}{acc:>8.1f}%{br:>11.5f}")

# 赔率区间
print(f"\n--- 按赔率 (主胜) 分组 ---")
def bkt(oh):
    if oh < 1.6: return "1.0-1.6 主胜热门"
    if oh < 2.1: return "1.6-2.1 主胜次热"
    if oh < 2.8: return "2.1-2.8 均势"
    if oh < 3.8: return "2.8-3.8 客胜热门"
    return "3.8+ 客胜大热"
buckets = collections.defaultdict(lambda: {"n": 0, "ok": 0, "brier": []})
for r in results:
    if r.get("error"): continue
    b = bkt(r["odds_hda"]["胜"])
    buckets[b]["n"] += 1
    if r["correct_1x2"]: buckets[b]["ok"] += 1
    buckets[b]["brier"].append(r["brier"])
for b in ["1.0-1.6 主胜热门", "1.6-2.1 主胜次热", "2.1-2.8 均势", "2.8-3.8 客胜热门", "3.8+ 客胜大热"]:
    d = buckets[b]
    if d["n"]:
        print(f"  {b:<18} n={d['n']:>5}  acc={d['ok']/d['n']*100:>5.1f}%  "
              f"Brier={sum(d['brier'])/len(d['brier']):.5f}")

# 平局专项
print(f"\n--- 平局专项 ---")
draw_actual = [r for r in results if not r.get("error") and r["actual_1x2"] == "D"]
if draw_actual:
    dpred = collections.Counter(r["pred_1x2"] for r in draw_actual)
    dc = sum(1 for r in draw_actual if r["pred_1x2"] == "D")
    print(f"  实际平局 {len(draw_actual)} 场 → 模型预测: H={dpred['H']} D={dpred['D']} A={dpred['A']}")
    print(f"  平局命中率: {dc}/{len(draw_actual)} = {dc/len(draw_actual)*100:.1f}%")
    # 平局预测的概率分布
    draw_probs = [r["probs"]["D"] for r in results if not r.get("error")]
    print(f"  所有比赛的模型平局概率均值: {sum(draw_probs)/len(draw_probs):.3f}")
    mkt_draw_probs = [1.0 / float(r["odds_hda"]["平"]) / sum(1.0/float(r["odds_hda"][k]) for k in ["胜","平","负"])
                      for r in results if not r.get("error")]
    print(f"  市场平局去水概率均值: {sum(mkt_draw_probs)/len(mkt_draw_probs):.3f}")

# 模型增量 vs 市场增量 样本
print(f"\n--- 模型额外命中 ({model_only} 场) — 前 10 ---")
mo = [r for r in results if not r.get("error") and r["correct_1x2"] and not r["market_correct"]]
for r in mo[:10]:
    print(f"  {r['date']} {r['league']:>10}  {r['home']:<8} vs {r['away']:<8}  "
          f"实际={r['actual_score']} 模型={r['pred_1x2']}({r['probs']})  赔率={r['odds_hda']}")

print(f"\n--- 市场额外命中 ({mkt_only} 场) — 前 10 ---")
mk = [r for r in results if not r.get("error") and not r["correct_1x2"] and r["market_correct"]]
for r in mk[:10]:
    print(f"  {r['date']} {r['league']:>10}  {r['home']:<8} vs {r['away']:<8}  "
          f"实际={r['actual_score']} 模型={r['pred_1x2']}({r['probs']})  赔率={r['odds_hda']}")

# Brier Top 15 (最自信的错误)
print(f"\n--- Brier Top 15 (模型最自信但判断错误) ---")
wb = sorted([r for r in results if not r.get("error") and not r.get("correct_1x2")],
            key=lambda x: -x["brier"])[:15]
for r in wb:
    print(f"  Brier={r['brier']:.4f}  {r['date']} {r['league']:>10}  "
          f"{r['home']:<8} vs {r['away']:<8}  实际={r['actual_score']}({r['actual_1x2']})  "
          f"模型={r['pred_1x2']}({r['probs']})  赔率={r['odds_hda']}")

# 保存
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({
        "summary": {
            "n_eval": N, "start": dates_sorted[START_OFFSET], "end": dates_sorted[-1],
            "model_accuracy": correct_1x2 / N,
            "model_brier": brier_total / N, "model_logloss": logloss_total / N,
            "market_accuracy": mkt_correct / N, "market_brier": mkt_brier / N,
            "both_ok": both_ok, "model_only": model_only, "mkt_only": mkt_only, "both_bad": both_bad,
        },
        "confusions": {f"{k[0]}→{k[1]}": v for k, v in confusions.items()},
        "results": results,
    }, f, ensure_ascii=False, indent=2)
print(f"\n详细结果: {OUT}")
