# -*- coding: utf-8 -*-
"""让球盘选取规则离线探针（只读，不改生产）。"""
import importlib.util, json, os, statistics as st
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("M", os.path.join(ROOT, "market_calib_fit.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

BETA = json.load(open(os.path.join(ROOT, "market_calib.json"), encoding="utf-8"))["handicap"]["beta"]
rows = M.build_rows()
ss = M.rq_samples_of(rows)
cal_of = {}
for s in ss:
    cal_of[(s["date"], s["k"], s["dir"])] = M.apply_handicap_beta(BETA, s["mkt"], s["mod"])

games = defaultdict(dict)
for s in ss:
    key = (s["date"], s["k"])
    cal = cal_of[(s["date"], s["k"], s["dir"])]
    h = 0
    try:
        h = int(str(s["h"]).replace("+", ""))
    except Exception:
        pass
    games[key][s["dir"]] = dict(mkt=s["mkt"], mod=s["mod"], cal=cal, odds=s["odds"],
                                y=s["y"], h=h)
print("样本：%d 场，%d 个 WDL 观测，日期 %s → %s" % (
    len(games), len(ss), min(k[0] for k in games), max(k[0] for k in games)))

def ev_g(d):
    return d["cal"] * d["odds"]

RULES = {
    "A 现状(EV 最大)": lambda g: max("WDL", key=lambda k: ev_g(g[k])),
    "B 校准概率最大": lambda g: max("WDL", key=lambda k: g[k]["cal"]),
    "C B+|盘|<=1": lambda g: max("WDL", key=lambda k: g[k]["cal"]) if abs(g["W"]["h"]) <= 1 else None,
    "D EV最大+|盘|<=1": lambda g: max("WDL", key=lambda k: ev_g(g[k])) if abs(g["W"]["h"]) <= 1 else None,
    "E B+概率>=45%": lambda g: (lambda k: k if g[k]["cal"] >= 0.45 else None)(max("WDL", key=lambda k: g[k]["cal"])),
    "F 方向跟随(胜/负)": lambda g: max(("W", "L"), key=lambda k: g[k]["cal"]),
    "G 市场概率最大": lambda g: max("WDL", key=lambda k: g[k]["mkt"]),
}

def evaluate(fn, sub):
    n = h = 0
    pnl = 0.0
    ods = []
    for key, g in sub:
        try:
            k = fn(g)
        except Exception:
            k = None
        if not k:
            continue
        n += 1
        ok = g[k]["y"] == 1
        h += ok
        pnl += (g[k]["odds"] - 1.0) if ok else -1.0
        ods.append(g[k]["odds"])
    if not n:
        return (0, 0.0, 0.0, 0.0)
    return (n, h / n * 100, pnl / n * 100, st.mean(ods))

items = sorted(games.items())
dates = sorted(set(k[0] for k in games))
cut = dates[int(len(dates) * 0.75)]
seg = {
    "全样本": items,
    "前75%": [(k, g) for k, g in items if k[0] < cut],
    "后25%(留出)": [(k, g) for k, g in items if k[0] >= cut],
}
for label, sub in seg.items():
    print("\n== %s（n=%d 场）" % (label, len(sub)))
    for name, fn in RULES.items():
        n, hit, roi, avg = evaluate(fn, sub)
        print("  %-18s n=%4d 下注 命中%5.1f%% ROI%+6.1f%% 均赔%.2f" % (name, n, hit, roi, avg))
