# -*- coding: utf-8 -*-
"""从「比分盘」反推 1X2 市场概率 —— 解决 ODDS 里 1X2 缺失的场次。

背景：竞彩 ODDS 有部分场次 1X2（胜/平/负）为空，但比分盘（31 档）完整。
天天都有，且常是豪门场次（2026-09-13 就有 5/24：拜仁、巴萨、本菲卡、埃因霍温、哈马比）。
这些场次目前降级为「纯模型 λ」——而项目结论是 纯市场去水 1X2 > 生产@0.80 > 纯模型，
即缺市场输入 = 已知更差的口径。

本脚本验证「比分盘 → 1X2」反推的可信度：
  ① 在所有 1X2 与比分盘**都齐全**的历史场次上，比较
     A = devig(真实 1X2) 与 B = devig(比分盘聚合出的 1X2)
     的平均绝对偏差、方向一致率；
  ② 给出可直接用于生产的反推函数 verify。
"""
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
HOME_CELLS = ['1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '4:0', '4:1', '4:2',
              '5:0', '5:1', '5:2', '胜其他']
DRAW_CELLS = ['0:0', '1:1', '2:2', '3:3', '平其他']
AWAY_CELLS = ['0:1', '0:2', '1:2', '0:3', '1:3', '2:3', '0:4', '1:4', '2:4',
              '0:5', '1:5', '2:5', '负其他']


def _f(x):
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def devig3(a, b, c):
    """三个赔率去水 → 概率（乘法去水）。"""
    if not (a and b and c):
        return None
    inv = [1.0 / a, 1.0 / b, 1.0 / c]
    s = sum(inv)
    return [x / s for x in inv] if s > 0 else None


def onex2_from_scores(sc):
    """比分盘赔率 → 去水 1X2。返回 (p_home, p_draw, p_away) 或 None。"""
    if not isinstance(sc, dict):
        return None
    # 反推前先按等比去掉比分盘自身的水位：直接对 1/odds 归一
    raw = {}
    for k, v in sc.items():
        o = _f(v)
        if o:
            raw[k] = 1.0 / o
    if not raw:
        return None
    tot = sum(raw.values())
    if tot <= 0:
        return None
    p = {k: v / tot for k, v in raw.items()}
    ph = sum(p.get(k, 0.0) for k in HOME_CELLS)
    pd = sum(p.get(k, 0.0) for k in DRAW_CELLS)
    pa = sum(p.get(k, 0.0) for k in AWAY_CELLS)
    s = ph + pd + pa
    if s <= 0:
        return None
    return [ph / s, pd / s, pa / s]


def main():
    h = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    odds = json.loads(re.search(r'const ODDS\s*=\s*(\{.*?\});', h, re.S).group(1))

    both = miss_1x2 = no_scores = 0
    devs = []
    agree = 0
    rows = []
    for k, v in odds.items():
        if not isinstance(v, dict):
            continue
        real = devig3(_f(v.get('胜')), _f(v.get('平')), _f(v.get('负')))
        der = onex2_from_scores(v.get('比分'))
        if real is None:
            if der is not None:
                miss_1x2 += 1
            else:
                no_scores += 1
            continue
        if der is None:
            no_scores += 1
            continue
        both += 1
        d = [abs(real[i] - der[i]) for i in range(3)]
        devs.append((sum(d) / 3, max(d)))
        if real.index(max(real)) == der.index(max(der)):
            agree += 1
        rows.append((k, real, der))

    print("=" * 104)
    print("从比分盘反推 1X2 —— 可信度验证（用 1X2 与比分盘都齐全的历史场次做对照）")
    print("=" * 104)
    print(f"  ODDS 总条数 {len(odds)}")
    print(f"  1X2 与比分盘都齐全（可对照）: {both} 条")
    print(f"  仅缺 1X2、比分盘完整（本修复的目标）: {miss_1x2} 条"
          f"（占 {miss_1x2/max(1,both+miss_1x2)*100:.1f}%）")
    print(f"  两者都缺: {no_scores} 条")
    if not both:
        return
    mean_d = sum(x[0] for x in devs) / len(devs) * 100
    mean_mx = sum(x[1] for x in devs) / len(devs) * 100
    print(f"\n  平均绝对偏差（逐概率、三档均值）: {mean_d:.2f} pp")
    print(f"  平均最大单档偏差: {mean_mx:.2f} pp")
    print(f"  方向一致率（argmax 三档赞同）: {agree}/{both} = {agree/both*100:.1f}%")
    # 分档
    lo = sum(1 for x in devs if x[0] * 100 <= 1.0)
    mid = sum(1 for x in devs if 1.0 < x[0] * 100 <= 3.0)
    hi = sum(1 for x in devs if x[0] * 100 > 3.0)
    print(f"  逐场平均偏差 ≤1pp: {lo}（{lo/both*100:.0f}%） | 1~3pp: {mid}（{mid/both*100:.0f}%）"
          f" | >3pp: {hi}（{hi/both*100:.0f}%）")

    print("\n  偏差最大的 8 场（看是否需要排除某些联赛/玩法）：")
    rows.sort(key=lambda r: -sum(abs(r[1][i] - r[2][i]) for i in range(3)))
    for k, real, der in rows[:8]:
        print(f"    {k:<34} 真实 {real[0]*100:5.1f}/{real[1]*100:5.1f}/{real[2]*100:5.1f}"
              f"   反推 {der[0]*100:5.1f}/{der[1]*100:5.1f}/{der[2]*100:5.1f}")

    print("\n" + "=" * 104)
    print("结论")
    print("=" * 104)
    if agree / both > 0.95 and mean_d <= 2.0:
        print("  ✅ 反推可信：方向一致率 >95%、平均偏差 ≤2pp —— 可用于补齐缺失的 1X2。")
    else:
        print("  ⚠️ 反推偏差偏大，需谨慎；建议仅作 fallback 且标注来源。")


if __name__ == '__main__':
    main()
