#!/usr/bin/env python3
"""重建 league_profile.json（联赛进球环境画像）。

数据源: results_history/*.json（竞彩赛果，每场含 league/fullScore）
用途:
  1. mean / sd / index   —— 联赛先验收缩目标（calc_engine.shrink_to_league）
  2. p00 / p_under15 ... —— 分布形状参考
  3. score_freq          —— 7x7 实测比分频率（calc_engine 第七步经验混合，
                            walk-forward 验证 Brier -0.45%，低比分四格校准改善）
建议每季度或每积累 2000 场后重跑一次（_meta 记录标定口径）。
"""
import datetime
import glob
import json
import os
import statistics as st
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))


def _find_root():
    """兼容脚本在仓库根（本地）与 tools/prediction/（master）两种位置。"""
    for d in (BASE, os.path.dirname(BASE)):
        if os.path.isdir(os.path.join(d, "results_history")):
            return d
    raise SystemExit("results_history/ not found")


OUT_NAME = "league_profile.json"
MIN_N = 12          # 收缩目标最低样本
FREQ_MIN_N = 40     # 比分频率最低样本
GRID = 7            # 0..6 球
K_FREQ = 50         # 比分频率向均匀分布收缩的伪计数


def load_matches():
    root = _find_root()
    recs = []
    for f in sorted(glob.glob(os.path.join(root, "results_history", "*.json"))):
        if f.endswith("index.json"):
            continue
        date = os.path.basename(f).replace(".json", "")
        for v in json.load(open(f, encoding="utf-8")).values():
            fs = v.get("fullScore") or ""
            if ":" not in fs:
                continue
            try:
                h, a = (int(x) for x in fs.split(":"))
            except ValueError:
                continue
            recs.append({"date": date, "lg": v.get("league") or "其他", "hg": h, "ag": a})
    recs.sort(key=lambda r: r["date"])
    return recs


def main():
    recs = load_matches()
    if not recs:
        raise SystemExit("no results_history data")
    dates = [r["date"] for r in recs]
    recent_cut = dates[int(len(dates) * 0.6)]  # 后 40% 视为近期

    B = defaultdict(lambda: {"tot": [], "h": [], "a": [], "recent": [], "freq": defaultdict(int)})
    for r in recs:
        b = B[r["lg"]]
        b["tot"].append(r["hg"] + r["ag"])
        b["h"].append(r["hg"])
        b["a"].append(r["ag"])
        b["freq"][(min(r["hg"], GRID - 1), min(r["ag"], GRID - 1))] += 1
        if r["date"] >= recent_cut:
            b["recent"].append(r["hg"] + r["ag"])

    GM = st.mean(r["hg"] + r["ag"] for r in recs)
    unif = 1.0 / (GRID * GRID)
    prof = {}
    for lg, b in B.items():
        n = len(b["tot"])
        if n < MIN_N:
            continue
        recent = b["recent"] or b["tot"]
        entry = {
            "n": n,
            "mean": round(st.mean(b["tot"]), 3),
            "sd": round(st.pstdev(b["tot"]), 3),
            "recent_mean": round(st.mean(recent), 3),
            "recent_n": len(recent),
            "home_adv": round(st.mean(b["h"]) - st.mean(b["a"]), 3),
            "p00": round(b["freq"][(0, 0)] / n, 4),
            "p_under15": round(sum(1 for x in b["tot"] if x <= 1) / n, 4),
            "p_over35": round(sum(1 for x in b["tot"] if x >= 4) / n, 4),
            "index": round(st.mean(b["tot"]) / GM, 4),
        }
        if n >= FREQ_MIN_N:
            # 收缩到均匀分布的平滑经验频率（步长 1/81 网格），7x7 归一
            raw = {k: v / n for k, v in b["freq"].items()}
            sm = {k: (n * v + K_FREQ * unif) / (n + K_FREQ) for k, v in raw.items()}
            s = sum(sm.values())
            entry["score_freq"] = {f"{k[0]}-{k[1]}": round(v / s, 5) for k, v in sm.items()}
            entry["score_freq_n"] = n
        prof[lg] = entry

    data = {
        "_meta": {
            "generated": datetime.date.today().isoformat(),
            "source": "results_history/*.json",
            "sample_matches": len(recs),
            "date_range": [dates[0], dates[-1]],
            "global_mean": round(GM, 4),
            "note": ("联赛进球环境画像。mean=基线总进球(收缩目标)；index 仅限冷启动兜底，"
                     "禁止直接乘λ(重复修正,MAE+2.69%)。score_freq=7x7平滑经验比分频率"
                     "(引擎第七步混合 w=0.3, walk-forward Brier -0.45%)。"),
        },
        "shrink": {
            "w": 0.25,
            "w_note": ("λ*(1-w)+联赛基线*w。walk-forward 最优0.40(-3.03%)，5折CV各折一致；"
                       "取0.25保守值"),
            "min_n": MIN_N,
            "fallback_mean": round(GM, 4),
        },
        "score_mix": {
            "w": 0.3,
            "k_shrink": K_FREQ,
            "w_note": ("最终比分矩阵 = (1-w)*模型矩阵 + w*联赛经验频率(score_freq)。"
                       "对照实验: DC τ 仅 -0.09% 且 0-0 校准恶化，经验混合 -0.45% 且四格校准同向改善"),
        },
        "leagues": prof,
    }
    root = _find_root()
    json.dump(data, open(os.path.join(root, OUT_NAME), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_freq = sum(1 for p in prof.values() if "score_freq" in p)
    print(f"league_profile.json 重建完成: {len(prof)} 联赛 (含比分频率 {n_freq} 个), "
          f"样本 {len(recs)} 场, 全局基线 {GM:.3f}")


if __name__ == "__main__":
    main()
