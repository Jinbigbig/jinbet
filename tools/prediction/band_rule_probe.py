"""比分列（可能比分1/2）与双档口径的 2478 场 walk-forward 对照。

背景：头条改为「倾向象限内优选」后，若直接把 top_scores 数组重排，则「可能比分1/2」
两列不再是概率降序（出现 11.8% 在左、12.3% 在右的"颠倒"），且平局比分被挤到第 2 列。
本探针比较两种落地口径：

  raw   纯概率排序（恢复原样）：首选=top[0]，双档=top[1..2]
  quad  倾向象限内排序：首选=象限内最高概率，双档=象限内第 2/3

指标：首选命中率 / 双档命中率 / 前三覆盖 / 首选 1:1 占比 / 首选与盲猜 1:1 对比。
用法：python band_rule_probe.py
"""
import json

ROWS = json.load(open("_bt_rows2.json", encoding="utf-8"))


def quad(s):
    h, a = (int(x) for x in s.split(":"))
    return "home" if h > a else ("away" if a > h else "draw")


def keys(r):
    """本场「发布倾向」三象限键值（与引擎 1X2 同序：主/平/客）。"""
    pr = r.get("probs")
    if isinstance(pr, dict):
        return {k.lower(): pr[k] for k in pr}
    if isinstance(pr, list) and len(pr) >= 3:
        return {"home": pr[0], "draw": pr[1], "away": pr[2]}
    return None


def dir_key(r):
    p = keys(r)
    if not p:
        return None
    return max(("home", "draw", "away"), key=lambda k: p.get(k, 0))


def head_gap5(top, probs, dk):
    """现行头条口径（象限内 + gap5），与本仓 score_engine.headline_reorder 同义。"""
    if len(top) < 2 or quad(top[0]) != "draw":
        return top[0]
    if dk == "draw":
        return top[0]
    want = dk if dk in ("home", "away") else None
    cands = [(i, s) for i, s in enumerate(top[1:], 1) if quad(s) != "draw"] if want is None \
        else [(i, s) for i, s in enumerate(top[1:], 1) if quad(s) == want]
    if not cands:
        return top[0]
    i, s = max(cands, key=lambda x: probs[x[0]])
    return s if probs[0] - probs[i] < 5.0 else top[0]


def rows():
    out = []
    for r in ROWS:
        top, probs = r.get("top"), r.get("top_p")
        if not top or not probs:
            continue
        dk = dir_key(r)
        if not dk:
            continue
        actual = "%d:%d" % (r["hg"], r["ag"])
        out.append({"top": top, "p": probs, "dk": dk, "act": actual, "date": r.get("date")})
    return out


RS = rows()


def ev(name, top_pick, band_pick=None, subset=None):
    rr = subset or RS
    n = hit1 = hit2 = hit3 = 0
    one1 = 0
    for r in rr:
        p1 = top_pick(r)
        if p1 is None:
            continue
        n += 1
        if p1 == r["act"]:
            hit1 += 1
        if p1 == "1:1":
            one1 += 1
        if band_pick:
            b = band_pick(r)
            if r["act"] in b[:2]:
                hit2 += 1
            if r["act"] in (b + [p1])[:3]:
                hit3 += 1
    line = f"{name}: 首选{hit1 / n * 100:.2f}%  双档{hit2 / n * 100:.2f}%  前三{hit3 / n * 100:.2f}%  首选1:1占比{one1 / n * 100:.0f}%"
    return line


def raw1(r):
    return r["top"][0]


def rawb(r):
    return r["top"][1:3]


def quad_list(r):
    dk = r["dk"]
    got = [s for s in r["top"] if quad(s) == dk]
    return got[:3] or r["top"][:3]


def quad1(r):
    return quad_list(r)[0]


def quadb(r):
    return quad_list(r)[1:3]


def gap1(r):
    return head_gap5(r["top"], r["p"], r["dk"])


def gap_band(r):
    """头条(象限+gap5) 之外，象限内概率最高的两个。"""
    got = [s for s in quad_list(r) if s]
    rest = [s for s in got if s != gap1(r)]
    if len(rest) < 2:
        rest += [s for s in r["top"] if s not in got and s != gap1(r)]
    return rest[:2]


print("样本:", len(RS), "场")
print(ev("raw  (纯概率排序)      ", raw1, rawb))
print(ev("gap5 (现行头条+raw双档) ", gap1, lambda r: [s for s in r["top"] if s != gap1(r)][:2]))
print(ev("quad (象限内排序)      ", quad1, quadb))
print(ev("gap5+象限双档          ", gap1, gap_band))

rs = sorted(RS, key=lambda r: r["date"])
h = len(rs) // 2
print("\n-- 分半稳健性 --")
for lbl, sub in (("前半", rs[:h]), ("后半", rs[h:])):
    print(lbl, ev("raw ", raw1, rawb, sub))
    print(lbl, ev("gap5", gap1, lambda r: [s for s in r["top"] if s != gap1(r)][:2], sub))
    print(lbl, ev("quad", quad1, quadb, sub))
    print(lbl, ev("g5+q", gap1, gap_band, sub))

both = sum(1 for r in RS if raw1(r) == gap1(r))
print(f"\n首选与纯众数一致: {both}/{len(RS)} = {both / len(RS) * 100:.0f}%")
same_list = sum(1 for r in RS if [s for s in r['top'] if s != gap1(r)][:2] == quadb(r))
print(f"双档两列一致: {same_list}/{len(RS)} = {same_list / len(RS) * 100:.0f}%")
