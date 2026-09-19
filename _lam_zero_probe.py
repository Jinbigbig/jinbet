# -*- coding: utf-8 -*-
"""精查：今日 λ 极小的场次（吉达国民/中国女）在各步的精确取值，找 λa→0 的成因。"""
import importlib.util
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("eng", os.path.join(BASE, "_calc_engine.py"))
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

eng.load_league_profile()
eng.fit_platt_params()
eng.load_market_calib()
calib = eng.compute_calibration()

md = json.load(open(os.path.join(BASE, "scripts", "matches_data.json"), encoding="utf-8"))
matches = {m["matchNumStr"]: dict(m) for m in md["matches"]}
for i in range(1, 7):
    p = os.path.join(BASE, f"_data_batch{i}.json")
    if os.path.exists(p):
        for m in json.load(open(p, encoding="utf-8")).get("matches", []):
            matches[m["matchNumStr"]].update({k: v for k, v in m.items() if v is not None})

print(f"MARKET_W={eng.MARKET_W}  MAX_TOTAL={eng.MAX_TOTAL} MIN_TOTAL={eng.MIN_TOTAL} MAX_SINGLE={eng.MAX_SINGLE}")

_log = []
_orig_p2l = eng.prob_to_lambda


def _wrap_p2l(pb, total):
    out = _orig_p2l(pb, total)
    _log.append((list(pb), total, out))
    return out


eng.prob_to_lambda = _wrap_p2l

for num in ["周一007", "周一014", "周一003", "周一012"]:
    m = matches[num]
    _log.clear()
    r = eng.calc_match(m, calib, None)
    print(f"\n########## {num} {r['home']} vs {r['away']} ##########")
    for pb, total, out in _log:
        print(f"  反解入参 目标1X2=主{pb[0]*100:.2f}%/平{pb[1]*100:.2f}%/客{pb[2]*100:.2f}% 总量={total:.4f}")
        print(f"      grid 下界 λa={total/180:.6f} -> 解出 λh={out[0]:.6f} λa={out[1]:.6f}")
    print(f"  chain: {r['chain']}")
    print(f"  -> 最终 λ 主{r['lam_home']!r} 客{r['lam_away']!r} 总{r['lam_total']!r}")

