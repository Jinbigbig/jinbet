# -*- coding: utf-8 -*-
"""基线对照：模型挑的比分 vs 常数基线（无脑猜同一格）。

这是检验「比分层是否有技术含量」的唯一硬标准：
  若 argmax 命中率 <= 「总是猜最高频比分」的常数命中率，
  则该层没有任何增量信息 —— 用户说的「众数没意义」就是被实证了。
顺带给出：
  · 各比分的真实出现频率（数据集的形状先验）
  · 模型的比分矩阵平均质量（是否被形状先验压扁）
  · 「因素排序 vs 常数」的配对 McNemar 检验
缓存：_grid_cache.json（每场 λ/众数/矩阵前5/实际，避免重复算）
"""
import importlib.util
import json
import math
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
CACHE = os.path.join(ROOT, "_grid_cache.json")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build():
    F = _load("fhp", "factor_hit_probe.py")
    eng = F.engine()
    eng.fit_platt_params()
    F.sync_from_profile(eng)          # 旋钮以 league_profile.json 为准（勿硬编码）
    rows = F.load_rows()
    P = dict(F.P0)
    print(f"[build] 缓存口径：mixw={P['mixw']}（档案值）  ws={P['ws']}  样本 {len(rows)} 场")
    out = []
    for r in rows:
        _, _, (lh, la) = F.lam_from_factors(eng, r, P)
        g, lh2, la2 = F.grid_of(eng, r, P, lh, la)
        if g is None:
            continue
        pool = sorted(g.items(), key=lambda x: -x[1])[:6]
        out.append({
            "d": r["date"], "h": r["home"], "a": r["away"], "lg": r["lg"],
            "hg": r["hg"], "ag": r["ag"],
            "lh": round(lh2, 3), "la": round(la2, 3),
            "top": [[f"{c[0]}:{c[1]}", round(p, 5)] for c, p in pool],
            "p11": round(g.get((1, 1), 0.0), 5),
        })
    json.dump(out, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def mc(a_hit, b_hit):
    """McNemar：a 独中 vs b 独中。"""
    w01 = sum(1 for x, y in zip(a_hit, b_hit) if (not x) and y)
    w10 = sum(1 for x, y in zip(a_hit, b_hit) if x and (not y))
    if w01 + w10 == 0:
        return 0.0, 0.0
    chi = (abs(w01 - w10) - 1) ** 2 / (w01 + w10)
    return chi, w01, w10


def main():
    D = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else build()
    n = len(D)
    print("=" * 112)
    print(f"比分层技术含量检验 —— 样本 {n} 场（2026-01-01 ~ 2026-09-12，竞彩口径）")
    print("=" * 112)

    # ---------- 1. 数据集真实形状 ----------
    print("\n1  数据集真实比分频率（前 12）—— 这是「无脑猜」的天花板")
    print("-" * 112)
    freq = Counter(f"{x['hg']}:{x['ag']}" for x in D)
    tot = sum(freq.values())
    for s, c in freq.most_common(12):
        bar = "█" * int(c / tot * 260)
        print(f"  {s:<6}{c:>5}  {c/tot*100:>5.2f}%  {bar}")
    best_const, best_c = freq.most_common(1)[0]
    print(f"\n  ⇒ 最高频比分 = {best_const}（{best_c/tot*100:.2f}%）。这就是常数基线。")

    # ---------- 2. 常数基线 vs 模型 ----------
    print("\n2  常数基线 vs 模型的单比分命中次数")
    print("-" * 112)
    model_hit = [x["top"][0][0] == f"{x['hg']}:{x['ag']}" for x in D]
    top2_hit = [f"{x['hg']}:{x['ag']}" in [t[0] for t in x["top"][:2]] for x in D]
    top3_hit = [f"{x['hg']}:{x['ag']}" in [t[0] for t in x["top"][:3]] for x in D]

    def show(tag, hits):
        h = sum(hits)
        print(f"  {tag:<40}{h:>5} / {n}   {h/n*100:>6.2f}%")

    show(f"常数：全猜 {best_const}（无模型）", [f"{x['hg']}:{x['ag']}" == best_const for x in D])
    for s in [c for c, _ in freq.most_common(6)][1:5]:
        show(f"常数：全猜 {s}", [f"{x['hg']}:{x['ag']}" == s for x in D])
    show("模型 argmax（本次部署，单档）", model_hit)
    show("模型 Top2（双档）", top2_hit)
    show("模型 Top3", top3_hit)

    cbase = [f"{x['hg']}:{x['ag']}" == best_const for x in D]
    # mc 返回 (chi, w01=后者独中, w10=前者独中) —— 注意顺序
    chi, only_const, only_model = mc(model_hit, cbase)
    print(f"\n  McNemar  模型 vs 常数{best_const}：模型独中 {only_model} / 常数独中 {only_const}"
          f"  χ²={chi:.2f}  → {'显著' if chi > 3.84 else '不显著'}")
    print(f"  （共同命中 = {sum(model_hit) - only_model}）")
    if only_model <= only_const:
        print("  ⚠️ 模型择格**没能跑赢常数**：比分层是净负贡献 —— 与用户直觉一致。")
    else:
        print(f"  ✅ 模型择格跑赢常数：净多中 {only_model - only_const} 场"
              f"（{sum(model_hit)}/{n} = {sum(model_hit)/n*100:.2f}% vs 常数 {sum(cbase)/n*100:.2f}%）。")

    # ---------- 3. 模型的比分矩阵是否被形状先验压扁 ----------
    print("\n3  模型给 1:1 的平均概率 vs 数据集 1:1 真实频率（检验矩阵是否被压扁）")
    print("-" * 112)
    avg11 = sum(x["p11"] for x in D) / n
    real11 = freq.get("1:1", 0) / n
    print(f"  模型平均 P(1:1) = {avg11*100:.2f}%     数据集实际频率 = {real11*100:.2f}%")
    deg = sum(1 for x in D if x["top"][0][0] == "1:1")
    print(f"  argmax 落在 1:1 的场次 = {deg}/{n} = {deg/n*100:.1f}%（'退化率'）")
    # 模型首选比分分布
    print("\n  模型首选比分分布（前 8）：", end="")
    print(", ".join(f"{s}×{c}" for s, c in Counter(x["top"][0][0] for x in D).most_common(8)))

    # ---------- 4. 分层：模型有没有在「本该是它的场次」上赢 ----------
    print("\n4  分层检验：按模型自己给的首选概率分档（能不能挑出它该赢的场次）")
    print("-" * 112)
    qs = sorted(x["top"][0][1] for x in D)
    cuts = [qs[int(n * f)] for f in (0.2, 0.4, 0.6, 0.8)]
    print(f"  {'概率档':<16}{'场次':>7}{'模型命中':>10}{'常数命中':>10}{'差':>9}")
    for i in range(5):
        lo = 0 if i == 0 else cuts[i - 1]
        hi = cuts[i] if i < 4 else 9
        sub = [x for x in D if lo <= x["top"][0][1] < hi]
        if not sub:
            continue
        mh = sum(1 for x in sub if x["top"][0][0] == f"{x['hg']}:{x['ag']}") / len(sub) * 100
        ch = sum(1 for x in sub if f"{x['hg']}:{x['ag']}" == best_const) / len(sub) * 100
        print(f"  第{i+1}档 {lo:.3f}~{hi if i<4 else 1:.3f}{len(sub):>8}{mh:>9.1f}%{ch:>9.1f}%{mh-ch:>+8.1f}pp")


if __name__ == "__main__":
    main()
