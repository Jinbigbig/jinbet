# -*- coding: utf-8 -*-
"""星级（=象限众数比分概率）到底有没有信息量？

回答的问题：报告里「信心评级 ★」是按象限众数比分概率分档（≥15%→5★、≥12%→4★、
≥9%→3★、≥7%→2★、其余1★）。用户质疑：「概率高又有什么意义」。

本探针按该概率分档，逐档实测：
  期望比分单点命中 / 双档命中 / ±1球覆盖 / 方向命中 / 平均|Δ总进球|
若各档指标不单调（或高概率档反而更差），则「概率高」在该口径下无决策价值。

同时给出对照：按「期望比分自身的模型概率」分档是否更好。

数据：_probe_rows_lamlevel.json（生产口径重建的 1591 场历史行）。
用法：python star_value_probe.py
"""
import collections
import importlib.util
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

spec = importlib.util.spec_from_file_location("srp", os.path.join(ROOT, "score_rule_probe.py"))
srp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srp)


def star_of(p):
    if p >= 0.15:
        return 5
    if p >= 0.12:
        return 4
    if p >= 0.09:
        return 3
    if p >= 0.07:
        return 2
    return 1


def main():
    rows = json.load(open(os.path.join(ROOT, "_probe_rows_lamlevel.json"), encoding="utf-8"))
    eng = srp.engine()
    eng.load_league_profile()
    eng.fit_platt_params()
    data = srp.build_published(eng, rows, eng.MARKET_W)
    print(f"样本 {len(data)} 场（生产口径重建）")

    # ---------- A. 按现行星级口径（象限众数比分概率）分档 ----------
    print()
    print("A. 现行「信心评级」口径 = 象限众数比分概率，逐档实测")
    print(f"  {'星级':<8}{'档内概率':>12}{'n':>7}{'平均λ总':>9}{'期望比分单点':>13}{'双档命中':>10}"
          f"{'±1球覆盖':>10}{'方向命中':>10}{'平均Δ总进球':>13}")
    buckets = collections.defaultdict(lambda: {"n": 0, "exp": 0, "b2": 0, "near": 0,
                                               "dir": 0, "dg": 0.0, "p": [], "lam": 0.0})
    for r, g, marg, lh2, la2 in data:
        qi = srp.dir_of(marg)
        pool = [(c, p) for c, p in g.items() if srp.in_quad(c, qi) and srp.listed(c)]
        if not pool:
            continue
        dmode, pmode = max(pool, key=lambda x: x[1])          # 象限众数（现行星级依据）
        e = srp.r7_round_lambda(g, marg, lh2, la2)                    # 新头条：期望比分
        if e is None:
            continue
        # 双档 = 期望比分 + 同倾向内次高（与报告 expect_band 一致）
        rest = [(c, p) for c, p in pool if c != e]
        band2 = [e] + ([max(rest, key=lambda x: x[1])[0]] if rest else [])
        hg, ag = r["hg"], r["ag"]
        k = star_of(pmode)
        b = buckets[k]
        b["n"] += 1
        b["p"].append(pmode)
        b["lam"] += lh2 + la2
        b["exp"] += 1 if e == (hg, ag) else 0
        b["b2"] += 1 if (hg, ag) in band2 else 0
        b["near"] += 1 if (abs(e[0] - hg) <= 1 and abs(e[1] - ag) <= 1) else 0
        b["dir"] += 1 if qi == srp.act_dir(hg, ag) else 0
        b["dg"] += (e[0] + e[1]) - (hg + ag)
    for k in sorted(buckets, reverse=True):
        b = buckets[k]
        n = b["n"]
        print(f"  {k}★{'':<5}{statistics.mean(b['p'])*100:>11.1f}%{n:>7}{b['lam']/n:>9.2f}"
              f"{b['exp']/n*100:>12.1f}%{b['b2']/n*100:>9.1f}%"
              f"{b['near']/n*100:>9.1f}%{b['dir']/n*100:>9.1f}%{b['dg']/n:>+13.2f}")

    # ---------- B. 对照：按「期望比分自身概率」分档 ----------
    print()
    print("B. 对照口径 = 头条（期望比分）自身的模型概率，逐档实测")
    print(f"  {'概率档':<14}{'n':>7}{'期望比分单点':>13}{'双档命中':>10}"
          f"{'±1球覆盖':>10}{'方向命中':>10}{'平均Δ总进球':>13}")
    edges = [(0.0, 0.06), (0.06, 0.08), (0.08, 0.10), (0.10, 0.12), (0.12, 1.0)]
    for lo, hi in edges:
        n = exp = b2 = near = dirn = 0
        dg = 0.0
        for r, g, marg, lh2, la2 in data:
            qi = srp.dir_of(marg)
            pool = [(c, p) for c, p in g.items() if srp.in_quad(c, qi) and srp.listed(c)]
            if not pool:
                continue
            e = srp.r7_round_lambda(g, marg, lh2, la2)
            if e is None:
                continue
            pe = g.get(e, 0.0)
            if not (lo <= pe < hi):
                continue
            rest = [(c, p) for c, p in pool if c != e]
            band2 = [e] + ([max(rest, key=lambda x: x[1])[0]] if rest else [])
            hg, ag = r["hg"], r["ag"]
            n += 1
            exp += 1 if e == (hg, ag) else 0
            b2 += 1 if (hg, ag) in band2 else 0
            near += 1 if (abs(e[0] - hg) <= 1 and abs(e[1] - ag) <= 1) else 0
            dirn += 1 if qi == srp.act_dir(hg, ag) else 0
            dg += (e[0] + e[1]) - (hg + ag)
        if n:
            print(f"  {lo:.2f}~{hi:.2f}{'':<5}{n:>7}{exp/n*100:>12.1f}%{b2/n*100:>9.1f}%"
                  f"{near/n*100:>9.1f}%{dirn/n*100:>9.1f}%{dg/n:>+13.2f}")

    # ---------- C. 单调性检验：方向命中率是否随星级单调 ----------
    print()
    print("C. 单调性检验（现行星级）：若概率高真有价值，方向命中/±1球应随★递增")
    seq = [buckets[k] for k in sorted(buckets)]
    ok_dir = all(seq[i]["dir"] / seq[i]["n"] <= seq[i + 1]["dir"] / seq[i + 1]["n"]
                 for i in range(len(seq) - 1) if seq[i]["n"] > 30 and seq[i + 1]["n"] > 30)
    ok_near = all(seq[i]["near"] / seq[i]["n"] <= seq[i + 1]["near"] / seq[i + 1]["n"]
                  for i in range(len(seq) - 1) if seq[i]["n"] > 30 and seq[i + 1]["n"] > 30)
    print(f"  方向命中随★单调递增: {'是' if ok_dir else '否 ← 概率高不代表方向更准'}")
    print(f"  ±1球覆盖随★单调递增: {'是' if ok_near else '否 ← 概率高不代表比分更容易命中'}")


if __name__ == "__main__":
    sys.exit(main())


def layered():
    """D. 分层检验：控制 λ 总量后，「概率高」是否仍有增量信息。"""
    rows = json.load(open(os.path.join(ROOT, "_probe_rows_lamlevel.json"), encoding="utf-8"))
    eng = srp.engine()
    eng.load_league_profile()
    eng.fit_platt_params()
    data = srp.build_published(eng, rows, eng.MARKET_W)
    recs = []
    for r, g, marg, lh2, la2 in data:
        qi = srp.dir_of(marg)
        pool = [(c, p) for c, p in g.items() if srp.in_quad(c, qi) and srp.listed(c)]
        if not pool:
            continue
        e = srp.r7_round_lambda(g, marg, lh2, la2)
        if e is None:
            continue
        dmode, pmode = max(pool, key=lambda x: x[1])
        hg, ag = r["hg"], r["ag"]
        recs.append({"lt": lh2 + la2, "p": pmode, "exp": e == (hg, ag),
                     "near": abs(e[0] - hg) <= 1 and abs(e[1] - ag) <= 1,
                     "dir": qi == srp.act_dir(hg, ag),
                     "mode": dmode == (hg, ag)})
    print()
    print("D. 分层检验：在相同 λ 区间内，按众数概率高低分组")
    print(f"  {'λ区间':<14}{'组':<12}{'n':>6}{'众数单点':>10}{'期望单点':>10}{'±1球':>9}{'方向':>8}")
    bins = [(0, 2.4), (2.4, 3.0), (3.0, 3.6), (3.6, 99)]
    for lo, hi in bins:
        sub = [x for x in recs if lo < x["lt"] <= hi]
        if len(sub) < 40:
            continue
        med = statistics.median(x["p"] for x in sub)
        for lbl, grp in (("概率高半", [x for x in sub if x["p"] >= med]),
                         ("概率低半", [x for x in sub if x["p"] < med])):
            n = len(grp)
            lbl2 = f"{lo:g}<λ≤{hi:g}" if hi < 99 else f"λ>{lo:g}"
            print(f"  {lbl2:<14}{lbl:<12}{n:>6}"
                  f"{sum(x['mode'] for x in grp)/n*100:>9.1f}%"
                  f"{sum(x['exp'] for x in grp)/n*100:>9.1f}%"
                  f"{sum(x['near'] for x in grp)/n*100:>8.1f}%"
                  f"{sum(x['dir'] for x in grp)/n*100:>7.1f}%")
        d = [x for x in sub if x["p"] >= med]
        w = [x for x in sub if x["p"] < med]
        gap = (sum(x["near"] for x in d)/len(d) - sum(x["near"] for x in w)/len(w)) * 100
        gapd = (sum(x["dir"] for x in d)/len(d) - sum(x["dir"] for x in w)/len(w)) * 100
        print(f"  {'':<14}{'→ 差值':<12}{'':>6}{'':>10}{'':>10}{gap:>+8.1f}%{gapd:>+7.1f}%")
    # 控制 λ 后的偏相关（简化：分箱内符号一致性）
    print()
    print("  判读：若各 λ 箱内「概率高半」的 ±1球/方向 优势接近 0，则星级只是 λ 的代理变量。")


if __name__ == "__main__":
    main()
    layered()


def prob_compare():
    """E. 判别力对比：哪个概率最适合定义「信心评级」？
    候选：① 象限众数比分概率（现状）② 期望比分概率 ③ 胜平负倾向概率 max(1X2)
    指标：分五档后的方向命中率跨度、±1球覆盖跨度、单点精确率跨度。
    """
    rows = json.load(open(os.path.join(ROOT, "_probe_rows_lamlevel.json"), encoding="utf-8"))
    eng = srp.engine()
    eng.load_league_profile()
    eng.fit_platt_params()
    data = srp.build_published(eng, rows, eng.MARKET_W)
    recs = []
    for r, g, marg, lh2, la2 in data:
        qi = srp.dir_of(marg)
        pool = [(c, p) for c, p in g.items() if srp.in_quad(c, qi) and srp.listed(c)]
        if not pool:
            continue
        e = srp.r7_round_lambda(g, marg, lh2, la2)
        if e is None:
            continue
        dmode, pmode = max(pool, key=lambda x: x[1])
        hg, ag = r["hg"], r["ag"]
        recs.append({"pmode": pmode, "pexp": g.get(e, 0.0), "pmax": max(marg),
                     "exp": e == (hg, ag),
                     "near": abs(e[0] - hg) <= 1 and abs(e[1] - ag) <= 1,
                     "dir": qi == srp.act_dir(hg, ag)})
    n = len(recs)

    def quint(field):
        s = sorted(recs, key=lambda x: x[field])
        out = []
        sz = n // 5
        for i in range(5):
            grp = s[i * sz:(i + 1) * sz] if i < 4 else s[4 * sz:]
            m = len(grp)
            out.append((min(x[field] for x in grp), max(x[field] for x in grp), m,
                        sum(x["dir"] for x in grp) / m * 100,
                        sum(x["near"] for x in grp) / m * 100,
                        sum(x["exp"] for x in grp) / m * 100))
        return out

    print()
    print("E. 三种候选概率的五等分档（按概率升序 Q1→Q5）")
    for field, name in (("pmode", "① 象限众数比分概率（现状星级）"),
                        ("pexp", "② 头条=期望比分概率"),
                        ("pmax", "③ 胜平负倾向概率 max(1X2)")):
        print()
        print(f"  {name}")
        print(f"    {'档':<6}{'概率区间':>16}{'n':>6}{'方向命中':>10}{'±1球':>9}{'单点':>8}")
        q = quint(field)
        for i, (lo, hi, m, d, nr, ex) in enumerate(q):
            print(f"    Q{i+1:<5}{lo:>7.3f}~{hi:<7.3f}{m:>6}{d:>9.1f}%{nr:>8.1f}%{ex:>7.1f}%")
        print(f"    {'跨度':<6}{'':>16}{'':>6}{q[4][3]-q[0][3]:>+9.1f}%"
              f"{q[4][4]-q[0][4]:>+8.1f}%{q[4][5]-q[0][5]:>+7.1f}%")


if __name__ == "__main__":
    prob_compare()


def star_new_audit():
    """F. 新星级（方向确定性）逐档实测：方向命中 / 冷门率 / ±1球 / 单点。
    冷门 = 市场首选方向未命中（与报告 4.4 节定义一致）。"""
    rows = json.load(open(os.path.join(ROOT, "_probe_rows_lamlevel.json"), encoding="utf-8"))
    eng = srp.engine()
    eng.load_league_profile()
    eng.fit_platt_params()
    data = srp.build_published(eng, rows, eng.MARKET_W)

    def star_new(p):
        if p >= 0.66:
            return 5
        if p >= 0.57:
            return 4
        if p >= 0.50:
            return 3
        if p >= 0.44:
            return 2
        return 1

    b = collections.defaultdict(lambda: {"n": 0, "dir": 0, "upset": 0, "near": 0,
                                         "exp": 0, "p": 0.0})
    for r, g, marg, lh2, la2 in data:
        qi = srp.dir_of(marg)
        e = srp.r7_round_lambda(g, marg, lh2, la2)
        if e is None:
            continue
        p_new = max(marg)
        k = star_new(p_new)
        hg, ag = r["hg"], r["ag"]
        ad = srp.act_dir(hg, ag)
        # 市场首选方向
        mkt = None
        try:
            pv = eng.devig_1x2(*r["o12"])
            mkt = 0 if (pv[0] >= pv[1] and pv[0] >= pv[2]) else (1 if pv[1] >= pv[2] else 2)
        except Exception:
            pass
        d = b[k]
        d["n"] += 1
        d["p"] += p_new
        d["dir"] += 1 if qi == ad else 0
        if mkt is not None:
            d["upset"] += 1 if mkt != ad else 0
        d["near"] += 1 if (abs(e[0] - hg) <= 1 and abs(e[1] - ag) <= 1) else 0
        d["exp"] += 1 if e == (hg, ag) else 0
    print()
    print("F. 新星级（= max(1X2) 倾向概率）逐档实测")
    print(f"  {'星级':<7}{'倾向概率':>10}{'n':>7}{'占比':>8}{'方向命中':>10}"
          f"{'冷门率(市场视角)':>16}{'±1球':>9}{'单点':>8}")
    tot = sum(v["n"] for v in b.values())
    for k in sorted(b, reverse=True):
        d, n = b[k], b[k]["n"]
        print(f"  {k}★{'':<4}{d['p']/n*100:>9.1f}%{n:>7}{n/tot*100:>7.1f}%"
              f"{d['dir']/n*100:>9.1f}%{d['upset']/n*100:>15.1f}%"
              f"{d['near']/n*100:>8.1f}%{d['exp']/n*100:>7.1f}%")
    print(f"  合计 {tot} 场")


if __name__ == "__main__":
    star_new_audit()
