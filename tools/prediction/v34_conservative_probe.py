# -*- coding: utf-8 -*-
"""对照今日 12 场：生产口径 vs (Kalman / HEDGE w=0.70 / 两者同开) —— 回答「新引擎是否更保守」。"""
import importlib.util
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("eng", os.path.join(BASE, "calc_engine.py"))
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

eng.load_league_profile()
eng.fit_platt_params()
eng.load_market_calib()
calib = eng.compute_calibration()

md = json.load(open(os.path.join(BASE, "scripts", "matches_data.json"), encoding="utf-8"))
matches = {}
for m in md["matches"]:
    mm = dict(m)
    matches[mm["matchNumStr"]] = mm
for i in range(1, 7):
    p = os.path.join(BASE, f"_data_batch{i}.json")
    if os.path.exists(p):
        for m in json.load(open(p, encoding="utf-8")).get("matches", []):
            matches[m["matchNumStr"]].update({k: v for k, v in m.items() if v is not None})

db = eng.ensure_strength_db(verbose=False)

MODES = [
    ("生产(现网)", {"strength_db": db, "kalman_apply": False, "market_w": None}),
    ("+Kalman",   {"strength_db": db, "kalman_apply": True,  "market_w": None}),
    ("HEDGE0.70", {"strength_db": db, "kalman_apply": False, "market_w": 0.70}),
    ("两者同开",  {"strength_db": db, "kalman_apply": True,  "market_w": 0.70}),
]

rows = []
tot = {name: [0.0, 0.0, 0.0, 0.0] for name, _ in MODES[1:]}
for num in sorted(matches.keys()):
    m = matches[num]
    res = {}
    for name, ctx in MODES:
        r = eng.calc_match(m, calib, ctx)
        res[name] = r
    r0 = res["生产(现网)"]
    lt0 = r0["lam_total"]
    print(f"\n{num} {r0['home']} vs {r0['away']}  生产 λ{r0['lam_home']:.2f}/{r0['lam_away']:.2f} 总{lt0:.2f} "
          f"{r0['top_scores'][0]['score']}({r0['top_scores'][0]['prob']}%) {r0['stars']}★")
    for name, _ in MODES[1:]:
        r = res[name]
        d = r["lam_total"] - lt0
        tot[name][0] += d
        tot[name][1] += 1
        if d > 1e-9:
            tot[name][2] += 1
        elif d < -1e-9:
            tot[name][3] += 1
        ts0 = r0["top_scores"][0]
        ts = r["top_scores"][0]
        diff = "同" if ts["score"] == ts0["score"] else f"变 {ts0['score']}→{ts['score']}"
        st = "" if r["stars"] == r0["stars"] else f" 星级{r0['stars']}→{r['stars']}"
        print(f"   {name:<9} λ总{r['lam_total']:.2f} ({'+' if d >= 0 else ''}{d:.2f}) "
              f"首选{ts['score']}({ts['prob']}%) {diff}{st}")

print("\n=== 汇总（对生产口径的 λ 总量差） ===")
for name, _ in MODES[1:]:
    s, n, up, dn = tot[name]
    if n:
        print(f"{name:<9} 平均 {s/n:+.3f} 球/场 | 上调 {up} 场 / 下调 {dn} 场 / 不变 {n-up-dn} 场")
