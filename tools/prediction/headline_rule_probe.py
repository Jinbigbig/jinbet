"""头条比分口径 A/B：2478 场 walk-forward 回放（数据源 _bt_rows2.json，含逐场 top6 比分+概率）。

比较口径：
  base            现状 = top_scores[0] 联合众数
  gap{X}          「领先才押平局」：top1 为平局比分且领先最好的非平局 < X pp 时，顺延到那个非平局比分
  nodraw          完全排除平局比分（非平局优先，历史已否决，此处复现代价）
  cap{N}          同日同一比分最多用 N 次，超出则顺延到该场次高比分
用法：python headline_rule_probe.py
"""
import json
import collections

ROWS = json.load(open("_bt_rows2.json", encoding="utf-8"))


def parse(s):
    h, a = s.split(":")
    return int(h), int(a)


def is_draw(s):
    h, a = parse(s)
    return h == a


def pick_gap(top, probs, gap, forbid_draw_only=True):
    """top1 为平局且领先非平局不足 gap -> 顺延到非平局；forbid_draw_only=False 时只对 1:1 生效。"""
    s0 = top[0]
    if not is_draw(s0):
        return s0
    if not forbid_draw_only and s0 != "1:1":
        return s0
    for s in top[1:]:
        if not is_draw(s):
            if probs[0] - probs[top.index(s)] < gap:
                return s
            break
    return s0


def pick_nodraw(top):
    for s in top:
        if not is_draw(s):
            return s
    return top[0]


def evaluate(name, picker_by_row=None, picker_global=None):
    hit = n = 0
    psum = 0.0
    draw_pick = 0
    one_one = 0
    for r in ROWS:
        top, probs = r.get("top"), r.get("top_p")
        if not top or not probs:
            continue
        if picker_global:
            s = picker_global(top, probs)
        elif picker_by_row:
            s = picker_by_row(r)
        else:
            s = top[0]
        if s is None:
            continue
        p = probs[top.index(s)]
        n += 1
        psum += p
        if s == "%d:%d" % (r["hg"], r["ag"]):
            hit += 1
        if is_draw(s):
            draw_pick += 1
        if s == "1:1":
            one_one += 1
    return dict(name=name, n=n, hit=hit / n * 100, prob=psum / n, draw=draw_pick / n * 100,
                one=one_one / n * 100)


def cap_by_day(cap):
    """同一天同一比分最多 cap 次；命中率按最终选出的比分计。"""
    by_day = collections.defaultdict(list)
    for r in ROWS:
        if r.get("top"):
            by_day[r["date"]].append(r)
    used = {}
    picks = {}
    for d in sorted(by_day):
        cnt = collections.Counter()
        for r in by_day[d]:
            top = r["top"]
            s = next((x for x in top if cnt[x] < cap), top[0])
            cnt[s] += 1
            picks[id(r)] = (s, r["top_p"][top.index(s)])
    return picks


def evaluate_cap(cap):
    picks = cap_by_day(cap)
    hit = n = 0
    psum = 0.0
    draw = one = 0
    for r in ROWS:
        if id(r) not in picks:
            continue
        s, p = picks[id(r)]
        n += 1
        psum += p
        if s == "%d:%d" % (r["hg"], r["ag"]):
            hit += 1
        if is_draw(s):
            draw += 1
        if s == "1:1":
            one += 1
    return dict(name="cap%d" % cap, n=n, hit=hit / n * 100, prob=psum / n, draw=draw / n * 100,
                one=one / n * 100)


if __name__ == "__main__":
    out = [evaluate("base(现状)")]
    for g in (1.0, 1.5, 2.0, 3.0):
        out.append(evaluate("gap%.1f" % g, picker_global=lambda t, p, g=g: pick_gap(t, p, g)))
    out.append(evaluate("gap2.0(仅1:1)", picker_global=lambda t, p: pick_gap(t, p, 2.0, False)))
    out.append(evaluate("nodraw", picker_global=lambda t, p: pick_nodraw(t)))
    for c in (3, 5):
        out.append(evaluate_cap(c))

    print("%-16s %6s %8s %10s %9s %8s" % ("口径", "场次", "单点命中", "申明概率", "平局占比", "1:1占比"))
    for r in out:
        print("%-16s %6d %7.2f%% %9.2f%% %8.1f%% %7.1f%%" % (
            r["name"], r["n"], r["hit"], r["prob"], r["draw"], r["one"]))
