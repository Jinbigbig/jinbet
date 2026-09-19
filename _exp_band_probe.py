"""双档口径对照（本地诊断，不 comm）：含「期望比分」的双档 vs 现状「象限概率前两档」。

背景：2026-09-13 起报告头条比分改为 λ 期望值取整（expect_score）。
但「比分双档」现取「同象限概率前两档」，可能出现双档不含头条比分的情形（如 003 期望 2-1，双档 1-0+2-0），
同一行自相矛盾。本探针比较三种双档定义的 1591 场命中率：
  A 象限概率前两档（现状标签 25.5%）
  B {期望比分} ∪ {象限内概率最高的另一档}
  C {期望比分} ∪ {象限内前两档}（最多 3 档）
"""
import json
import importlib.util

spec = importlib.util.spec_from_file_location("srp", "score_rule_probe.py")
srp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srp)

eng = srp.engine()
eng.load_league_profile()
eng.fit_platt_params()

rows = json.load(open("_probe_rows_lamlevel.json", encoding="utf-8"))
data = srp.build_published(eng, rows, eng.MARKET_W)
print("样本:", len(data))


def quad_pool(g, marg):
    qi = srp.dir_of(marg)
    pool = [(c, p) for c, p in g.items() if srp.in_quad(c, qi) and srp.listed(c)]
    pool.sort(key=lambda x: -x[1])
    return pool


def exp_pick(g, marg, lh, la):
    """λ 期望值取整（引擎/报告同口径）"""
    qi = srp.dir_of(marg)
    cand = (int(round(lh)), int(round(la)))
    ok = ((cand[0] > cand[1]) if qi == 0 else ((cand[0] == cand[1]) if qi == 1 else (cand[0] < cand[1])))
    if ok and srp.listed(cand):
        return cand
    pool = quad_pool(g, marg)
    return pool[0][0] if pool else None


stat = {"A": [0, 0], "B": [0, 0], "C": [0, 0]}   # [命中, 档数合计]
for r, g, marg, lh2, la2 in data:
    hg, ag = r["hg"], r["ag"]
    pool = quad_pool(g, marg)
    if not pool:
        continue
    e = exp_pick(g, marg, lh2, la2)
    top2 = [c for c, _ in pool[:2]]
    others = [c for c, _ in pool if c != e]
    sets = {
        "A": top2,
        "B": [e] + others[:1] if e is not None else top2,
        "C": [e] + [c for c in top2 if c != e] if e is not None else top2,
    }
    for k, ss in sets.items():
        stat[k][0] += 1 if (hg, ag) in ss else 0
        stat[k][1] += len(set(ss))

n = len(data)
print()
print(f"{'双档定义':<42}{'命中':>8}{'平均档数':>10}")
print(f"  {'A 象限概率前两档（现状）':<38}{stat['A'][0]/n*100:>7.1f}%{stat['A'][1]/n:>10.2f}")
print(f"  {'B 期望比分 + 象限次高（共2档）':<38}{stat['B'][0]/n*100:>7.1f}%{stat['B'][1]/n:>10.2f}")
print(f"  {'C 期望比分 + 象限前两档（≤3档）':<38}{stat['C'][0]/n*100:>7.1f}%{stat['C'][1]/n:>10.2f}")


# ---------- 期望比分口径的可信度分档（原分档按象限众数测得，需按新头条口径复核）----------
print()
print("期望比分口径按 λ 总量分档：")
bk = {(0, 2.3): [0, 0], (2.3, 3.0): [0, 0], (3.0, 99): [0, 0]}
nb = {(0, 2.3): [0, 0], (2.3, 3.0): [0, 0], (3.0, 99): [0, 0]}
for r, g, marg, lh2, la2 in data:
    e = exp_pick(g, marg, lh2, la2)
    if e is None:
        continue
    lt = lh2 + la2
    for (lo, hi) in bk:
        if lo < lt <= hi:
            bk[(lo, hi)][0] += 1 if e == (r["hg"], r["ag"]) else 0
            bk[(lo, hi)][1] += 1
            break
for (lo, hi), (hit, cnt) in bk.items():
    lbl = f"λ≤{hi}" if lo == 0 else (f"{lo}<λ≤{hi}" if hi < 99 else f"λ>{lo}")
    print(f"  {lbl:<12} 期望比分单点命中 {hit/cnt*100:>5.1f}%  (n={cnt})")


print()
print("细粒度分档（期望比分口径）：单点命中 / ±1球覆盖")
edges = [0, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.2, 3.5, 99]
for i in range(len(edges) - 1):
    lo, hi = edges[i], edges[i + 1]
    hit = cov = cnt = 0
    for r, g, marg, lh2, la2 in data:
        lt = lh2 + la2
        if not (lo < lt <= hi):
            continue
        e = exp_pick(g, marg, lh2, la2)
        if e is None:
            continue
        hg, ag = r["hg"], r["ag"]
        cnt += 1
        hit += 1 if e == (hg, ag) else 0
        cov += 1 if (abs(e[0] - hg) <= 1 and abs(e[1] - ag) <= 1) else 0
    if cnt:
        print(f"  {lo}<λ≤{hi:<6} 单点 {hit/cnt*100:>5.1f}%   ±1球 {cov/cnt*100:>5.1f}%   n={cnt}")
