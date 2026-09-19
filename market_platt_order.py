#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Platt 与市场混合的先后顺序检验（样本外）。

market_blend_probe.py 已确定：概率空间混合 0.8 在保住进球总量的前提下
把 1X2 Brier 从 0.5940 降到 0.5739。但引擎现有设计是
「Platt 在**无市场**的分布上拟合，却应用在**含市场**的分布上」——
权重提到 0.8 后这个错配会被放大。

本脚本在最后 30% 样本外比较四种摆放：
  P0 不校准
  P1 Platt 用「纯模型」分布拟合 → 应用在混合后分布（= 现生产逻辑）
  P2 Platt 用「混合后」分布拟合 → 应用在混合后分布（自洽）
  P3 先对模型概率校准，再与市场混合

用法：python market_platt_order.py [K]
"""
import importlib.util
import math
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

# 复用 market_blend_probe 的数据装载与基础λ
_spec = importlib.util.spec_from_file_location(
    "blendprobe", os.path.join(_ROOT, "market_blend_probe.py"))
# 该脚本顶层会跑一遍全量对照，这里只需其数据结构：改用 exec 抓取命名空间
import io
import contextlib

_ns = {"__name__": "blendprobe", "__file__": os.path.join(_ROOT, "market_blend_probe.py")}
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    exec(compile(open(os.path.join(_ROOT, "market_blend_probe.py"), encoding="utf-8").read(),
                 "market_blend_probe.py", "exec"), _ns)

rows = _ns["rows"]
eng = _ns["eng"]
probs = _ns["probs"]
solve_lambda = _ns["solve_lambda"]
snap = _ns["snap"]
_logit = eng._logit
_fit = eng._fit_platt_1d

n = len(rows)
cut = int(n * 0.7)
train, test = rows[:cut], rows[cut:]
print(f"总样本 {n}｜训练 {len(train)}｜样本外 {len(test)}")


def blend_pm(r, w=0.8):
    """模型概率（未校准）"""
    lh, la = r["lam"]
    return probs(snap(lh), snap(la))


def blend_pb(r, w=0.8):
    """概率空间混合后的概率"""
    pm = blend_pm(r)
    pb = [(1 - w) * pm[i] + w * r["mkt"][i] for i in range(3)]
    s = sum(pb)
    return [x / s for x in pb]


def fit_platt(getp, data):
    """在 data 上用 getp 取三路概率，拟合三个一维 Platt"""
    ps = [getp(r) for r in data]
    ys = []
    for r in data:
        hg, ag = r["act"]
        ys.append(0 if hg > ag else (1 if hg == ag else 2))
    params = {}
    for k, name in enumerate(("home", "draw", "away")):
        X = [_logit(p[k]) for p in ps]
        Y = [1.0 if y == k else 0.0 for y in ys]
        params[name] = _fit(X, Y)
    return params


def apply_p(params, P):
    out = []
    for k, name in enumerate(("home", "draw", "away")):
        a, b = params.get(name, (1.0, 0.0))
        q = 1 / (1 + math.exp(-max(-30.0, min(30.0, a * _logit(P[k]) + b))))
        out.append(q)
    t = sum(out)
    return [x / t for x in out]


# ---------- 训练集拟合 ----------
p1_params = fit_platt(lambda r: blend_pm(r), train)          # 纯模型分布
p2_params = fit_platt(lambda r: blend_pb(r), train)          # 混合后分布


def eval_fn(fn):
    b3 = ll = t1 = 0.0
    for r in test:
        P = fn(r)
        hg, ag = r["act"]
        y = (1.0 if hg > ag else 0.0, 1.0 if hg == ag else 0.0, 1.0 if hg < ag else 0.0)
        b3 += sum((P[i] - y[i]) ** 2 for i in range(3))
        ll -= math.log(max(P[y.index(1.0)], 1e-9))
        t1 += 1.0 if max(range(3), key=lambda i: P[i]) == y.index(1.0) else 0.0
    m = len(test)
    return b3 / m, ll / m, t1 / m * 100


print()
print(f"{'口径':<44}{'1X2 Brier':>11}{'LogLoss':>10}{'方向Top1':>10}")
cands = [
    ("P0 无校准，概率空间混合 0.8", lambda r: blend_pb(r)),
    ("P1 Platt(纯模型拟合) → 应用在混合后", lambda r: apply_p(p1_params, blend_pb(r))),
    ("P2 Platt 在混合后分布上拟合 → 应用", lambda r: apply_p(p2_params, blend_pb(r))),
    ("P3 先 Platt(纯模型) 再混合", lambda r: (
        lambda q: [x / sum(q) for x in q])(
            [(1 - 0.8) * apply_p(p1_params, blend_pm(r))[i] + 0.8 * r["mkt"][i] for i in range(3)])),
    ("参考 纯模型无校准", lambda r: blend_pm(r)),
    ("参考 纯市场去水", lambda r: list(r["mkt"])),
]
for label, fn in cands:
    m = eval_fn(fn)
    print(f"{label:<44}{m[0]:>11.4f}{m[1]:>10.4f}{m[2]:>9.1f}%")

print()
print("拟合出的 Platt 参数：")
print("  P1 (纯模型分布):", {k: [round(x, 4) for x in v] for k, v in p1_params.items()})
print("  P2 (混合后分布):", {k: [round(x, 4) for x in v] for k, v in p2_params.items()})
