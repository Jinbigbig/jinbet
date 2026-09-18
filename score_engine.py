"""JinBet 独立比分引擎 (score_engine) —— 三套引擎中的「比分引擎」。

设计目标：与胜平负引擎（`_calc_engine.py`）、两档选取引擎（`selection_algo.py`）
**完全解耦** —— 自带数据读取、自带球队评级、自带参数档，运行期不读写任何一方的
中间状态；改本文件的任何参数都不会改变另两套引擎的输出。

建模链条
--------
1. 球队评级（自建、对手强度调整）
   每队按主/客分拆，对自己每场比赛的**调整后进球**做指数时间衰减加权
   （半衰期 `half_life` 天）：
       调整后进球 = 本队进球 / 对手的防守力
       调整后失球 = 本队失球 / 对手的攻击力
   对手强弱用「喂到该场之前」的当前评级估计（在线 Gauss-Seidel），
   再除以同期联赛主/客基准，得到攻击力 `att` 与防守力 `def`；
   样本不足时向 1.0 收缩（伪计数 `k_shrink`）。这是球队级 xG 代理。
2. 期望进球（λ）
   · 总量 T：球队评级 λ 合计，若有**比分盘**则取「评分盘隐含总量」与评级总量
     各半（比分盘是最直接的进球总量市场）。
   · 分配：固定总量 T，用市场 1X2（去水）一维搜索 split，使联合分布的 1X2
     贴合市场；无 1X2 时用评级 split。
   → λ主 = (T+split)/2，λ客 = (T−split)/2
3. 联合分布（双变量泊松，Karlis–Ntzoufras 共同分量）
       X = Y1 + Y3, Y = Y2 + Y3, Y1~P(λ1), Y2~P(λ2), Y3~P(λ3)
       λ1 = λ主 − λ3, λ2 = λ客 − λ3
   λ3 引入两队进球的共同波动（同一场次的节奏/天气/裁判等共同因子）。
4. 低比分修正 + 象限归一（保持 1X2 不变，只改「象限内挑哪一格」）。
5. 精确比分市场融合：若有比分盘，把「去水后的比分盘分布」与模型分布按
   `market_mix` 加权（比分盘未覆盖的尾部用模型补，不丢概率质量）。
6. 蒙特卡洛：抽 `mc_n` 场校验解析网格，并提供净胜球/让球盘等派生分布。

对外接口
--------
`Engine(history)` / `engine_asof(cutoff)` / `eng.predict(match)` /
`eng.lambdas(...)` / `eng.joint_final(...)` / `eng.monte_carlo(...)`
参数全部集中在 `DEFAULT`（回测拟合值），与另两套引擎参数互不相通。
"""
from __future__ import annotations

import datetime
import glob
import json
import math
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RH_DIR = os.path.join(HERE, "results_history")
FS_RE = re.compile(r"^\d+\s*[:\-]\s*\d+$")

# ---------- 参数档（全部由 2478 场 walk-forward 回测拟合，可单独回放）----------
DEFAULT = {
    "half_life": 120.0,    # 球队评级指数衰减半衰期（天）
    "k_shrink": 4.0,       # 评级向 1.0 收缩的伪计数（等效样本数）
    "opp_adj": 1,          # 是否做对手强度调整（在线 Gauss-Seidel）
    "score_w": 0.50,       # 总量 T 里「比分盘隐含总量」的权重
    "lam3": 0.08,          # 双变量泊松共同分量（2478 场拟合：0.08 与 0 无显著差）
    "tau_low": 0.0,        # 低比分修正总开关（拟合未通过，默认关闭；机制保留）
    "tau00": 1.06, "tau01": 0.98, "tau10": 0.98, "tau11": 0.94,
    "market_mix": 0.70,    # 精确比分市场与模型分布的混合权重（拟合最优 0.55~0.85）
    "max_goal": 8,         # 联合矩阵最大格（0..8）
    "mc_n": 20000,         # 蒙特卡洛抽样场数
    "league_eb_k": 40.0,   # 联赛基准向全局收缩的等效场数
    "prob_temp": 1.20,     # 申明概率的温度校准指数（混合分布系统性低估，见 predict）
}

LISTED = ["%d:%d" % (h, a) for h in range(6) for a in range(6)]
MARKET_LABELS = set(LISTED) | {"胜其他", "平其他", "负其他"}


def clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def pois(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def devig(oh, od, oa):
    """1X2 去水 → [主, 平, 客]；非法返回 None。"""
    try:
        oh, od, oa = float(oh), float(od), float(oa)
    except (TypeError, ValueError):
        return None
    if not (oh > 1 and od > 1 and oa > 1):
        return None
    v = [1.0 / oh, 1.0 / od, 1.0 / oa]
    s = sum(v)
    return [v[0] / s, v[1] / s, v[2] / s]


def market_dist(score_odds):
    """比分盘赔率 → 去水后的比分分布（只取明确列出比分的格）。

    竞彩比分盘除 0:0~3:3 外还有「胜其他/平其他/负其他」三个汇总档，其覆盖的比分
    与本引擎 0..8 网格重叠，直接混入会重复计数 → 这里只用明确比分格，
    汇总档的尾部分布交给模型补足（见 `blend_market`）。
    """
    d = {}
    for k, v in (score_odds or {}).items():
        if k not in LISTED:
            continue
        try:
            o = float(v)
        except (TypeError, ValueError):
            continue
        if o > 1.0:
            d[k] = 1.0 / o
    s = sum(d.values())
    if s <= 0:
        return None
    return {k: v / s for k, v in d.items()}


def score_dist_to_lambdas(score_odds):
    """由比分盘隐含分布取边缘均值 → (λ主, λ客)。"""
    d = market_dist(score_odds)
    if not d:
        return None
    th = ta = w = 0.0
    for k, p in d.items():
        if k not in LISTED:
            continue
        h, a = (int(x) for x in k.split(":"))
        th += p * h
        ta += p * a
        w += p
    if w <= 0:
        return None
    return th / w, ta / w


def _days(d1, d2):
    if not d1 or not d2:
        return 0
    try:
        a = [int(x) for x in d1.split("-")]
        b = [int(x) for x in d2.split("-")]
        return (datetime.date(*b) - datetime.date(*a)).days
    except Exception:
        return 0


class _Team:
    __slots__ = ("w_h", "gf_h", "ga_h", "n_h", "w_a", "gf_a", "ga_a", "n_a")

    def __init__(self):
        self.w_h = self.gf_h = self.ga_h = 0.0
        self.w_a = self.gf_a = self.ga_a = 0.0
        self.n_h = self.n_a = 0


class Engine:
    def __init__(self, history=None, params=None):
        self.p = dict(DEFAULT)
        if params:
            self.p.update(params)
        self.league = {}
        self.g = [0.0, 0.0, 0.0, 0.0, 0]
        self.teams = {}
        self.cur = None
        self._mkt_cache = {}
        self._grid_cache = {}
        if history:
            self.feed(history)

    # ---------- 数据 ----------
    @staticmethod
    def load_history(rh_dir=RH_DIR):
        recs = []
        for f in sorted(glob.glob(os.path.join(rh_dir, "*.json"))):
            if "index" in os.path.basename(f):
                continue
            try:
                data = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            for key, v in data.items():
                if not isinstance(v, dict):
                    continue
                fs = v.get("fullScore") or v.get("score") or ""
                if not FS_RE.match(fs):
                    continue
                try:
                    hg, ag = (int(x) for x in re.split(r"[:\-]", fs))
                except Exception:
                    continue
                parts = key.split("_", 2)
                if len(parts) < 3:
                    continue
                try:
                    oh, od, oa = float(v["胜"]), float(v["平"]), float(v["负"])
                except Exception:
                    oh = od = oa = 0.0
                recs.append({"date": parts[0], "home": parts[1], "away": parts[2],
                             "league": v.get("league") or "其他",
                             "hg": hg, "ag": ag, "oh": oh, "od": od, "oa": oa})
        recs.sort(key=lambda r: r["date"])
        return recs

    # ---------- 增量喂入 ----------
    def feed(self, recs):
        for r in recs:
            self._decay(r["date"])
            self._update(r)
        return self

    def _decay(self, date):
        d = _days(self.cur, date)
        if d <= 0:
            self.cur = date
            return
        f = 0.5 ** (d / float(self.p["half_life"]))
        for t in self.teams.values():
            t.w_h *= f; t.gf_h *= f; t.ga_h *= f
            t.w_a *= f; t.gf_a *= f; t.ga_a *= f
        self.cur = date

    def _update(self, r):
        lg = r["league"]
        st = self.league.setdefault(lg, [0.0, 0.0, 0.0, 0.0, 0])
        st[0] += 1.0; st[1] += r["hg"]
        st[2] += 1.0; st[3] += r["ag"]
        st[4] += 1
        g = self.g
        g[0] += 1.0; g[1] += r["hg"]
        g[2] += 1.0; g[3] += r["ag"]
        g[4] += 1
        gh, ga = self._base(None)
        # 对手强度调整：用「本场之前」的当前评级
        if self.p.get("opp_adj"):
            _, dh, _ = self._rates(r["home"], True, gh, ga)
            ath, _, _ = self._rates(r["home"], True, gh, ga)
            aa, da, _ = self._rates(r["away"], False, gh, ga)
            ata, _, _ = self._rates(r["away"], False, gh, ga)
        else:
            dh = da = ath = ata = 1.0
        pairs = ((r["home"], True, r["hg"] / max(0.45, da), r["ag"] / max(0.45, ata)),
                 (r["away"], False, r["ag"] / max(0.45, dh), r["hg"] / max(0.45, ath)))
        for team, is_home, gf, ga_ in pairs:
            t = self.teams.get(team)
            if t is None:
                t = self.teams[team] = _Team()
            if is_home:
                t.w_h += 1.0; t.gf_h += gf; t.ga_h += ga_; t.n_h += 1
            else:
                t.w_a += 1.0; t.gf_a += gf; t.ga_a += ga_; t.n_a += 1

    # ---------- 基准 ----------
    def _base(self, league=None):
        g = self.g
        if g[4] < 8:
            return 1.35, 1.10
        gh = g[1] / max(1e-9, g[0])
        ga = g[3] / max(1e-9, g[2])
        if not league:
            return gh, ga
        st = self.league.get(league)
        if not st or st[4] < 4:
            return gh, ga
        k = float(self.p["league_eb_k"])
        n = float(st[4])
        bh = (st[1] / st[0] * n + gh * k) / (n + k)
        ba = (st[3] / st[2] * n + ga * k) / (n + k)
        return bh, ba

    def _rates(self, team, is_home, gh, ga):
        t = self.teams.get(team)
        k = float(self.p["k_shrink"])
        if t is None:
            return 1.0, 1.0, 0
        if is_home:
            w, gf, ga_, n, base_o, base_d = t.w_h, t.gf_h, t.ga_h, t.n_h, gh, ga
        else:
            w, gf, ga_, n, base_o, base_d = t.w_a, t.gf_a, t.ga_a, t.n_a, ga, gh
        if w <= 1e-9 or n == 0:
            return 1.0, 1.0, 0
        att = (gf / w) / max(1e-9, base_o)
        dfn = (ga_ / w) / max(1e-9, base_d)
        att = (att * w + k) / (w + k)
        dfn = (dfn * w + k) / (w + k)
        return clamp(att, 0.35, 2.60), clamp(dfn, 0.35, 2.60), n

    def rating_lambdas(self, home, away, league):
        gh, ga = self._base(None)
        bh, ba = self._base(league)
        ah, dh, nh = self._rates(home, True, gh, ga)
        aa, da, na = self._rates(away, False, gh, ga)
        return (clamp(bh * ah * da, 0.15, 4.50), clamp(ba * aa * dh, 0.15, 4.50),
                {"home_n": nh, "away_n": na})

    # ---------- 联合分布 ----------
    def joint(self, lh, la, lam3, maxg=None, tau=True):
        maxg = int(self.p["max_goal"] if maxg is None else maxg)
        lam3 = clamp(float(lam3), 0.0, 0.85 * min(lh, la))
        key = (round(lh, 3), round(la, 3), round(lam3, 3), maxg, bool(tau),
               float(self.p["tau_low"]))
        hit = self._grid_cache.get(key)
        if hit is not None:
            return [row[:] for row in hit]
        l1 = max(1e-6, lh - lam3)
        l2 = max(1e-6, la - lam3)
        p1 = [pois(k, l1) for k in range(maxg + 1)]
        p2 = [pois(k, l2) for k in range(maxg + 1)]
        p3 = [pois(k, lam3) for k in range(maxg + 1)]
        m = [[0.0] * (maxg + 1) for _ in range(maxg + 1)]
        for h in range(maxg + 1):
            row = m[h]
            for a in range(maxg + 1):
                s = 0.0
                for k in range(min(h, a) + 1):
                    s += p1[h - k] * p2[a - k] * p3[k]
                row[a] = s
        if tau and float(self.p["tau_low"]) > 0:
            t = float(self.p["tau_low"])
            f = {(0, 0): self.p["tau00"], (0, 1): self.p["tau01"],
                 (1, 0): self.p["tau10"], (1, 1): self.p["tau11"]}
            for (h, a), kk in f.items():
                if h <= maxg and a <= maxg:
                    m[h][a] *= (1.0 + t * (kk - 1.0))
        if len(self._grid_cache) < 20000:
            self._grid_cache[key] = [row[:] for row in m]
        return m

    def joint_final(self, lh, la, lam3, maxg=None):
        """低比分修正后按象限缩放到未修正的象限合计（1X2 守恒）。"""
        if float(self.p["tau_low"]) <= 0:
            return self.joint(lh, la, lam3, maxg, tau=False)
        base = self.joint(lh, la, lam3, maxg, tau=False)
        adj = self.joint(lh, la, lam3, maxg, tau=True)
        n = len(base)
        for pick in ("h", "d", "a"):
            cells = [(h, a) for h in range(n) for a in range(n)
                     if ("h" if h > a else ("d" if h == a else "a")) == pick]
            cur = sum(adj[h][a] for h, a in cells)
            tgt = sum(base[h][a] for h, a in cells)
            if cur > 1e-12 and tgt > 0:
                k = tgt / cur
                for h, a in cells:
                    adj[h][a] *= k
        return adj

    # ---------- 市场隐含 λ ----------
    _STEPS = (0.60, 0.30, 0.15, 0.07, 0.035, 0.017, 0.008)
    _DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))

    def market_lambdas(self, probs, start=None, maxg=6):
        """去水 1X2 → (λ主, λ客, 残差)：固定步长调度 + 8 方向下降。"""
        if not probs:
            return None
        key = (round(probs[0], 4), round(probs[1], 4))
        hit = self._mkt_cache.get(key)
        if hit is not None:
            return hit
        th, td = float(probs[0]), float(probs[1])
        lh, la = start if start else (max(0.4, th * 3.4), max(0.4, td * 3.4))
        lh, la = clamp(lh, 0.15, 4.5), clamp(la, 0.15, 4.5)

        def err(x, y):
            m = self.joint(x, y, 0.0, maxg, tau=False)
            ph = pd = 0.0
            for h in range(maxg + 1):
                row = m[h]
                for a in range(maxg + 1):
                    if h > a:
                        ph += row[a]
                    elif h == a:
                        pd += row[a]
            return (ph - th) ** 2 + (pd - td) ** 2

        best = err(lh, la)
        for step in self._STEPS:
            for _rep in range(3):
                moved = False
                for dx, dy in self._DIRS:
                    x = clamp(lh + dx * step, 0.15, 4.5)
                    y = clamp(la + dy * step, 0.15, 4.5)
                    e = err(x, y)
                    if e < best - 1e-13:
                        best, lh, la, moved = e, x, y, True
                if not moved:
                    break
        out = (lh, la, best)
        self._mkt_cache[key] = out
        return out

    def _split_for(self, total, probs, start):
        """固定总量，一维搜索分配使模型 1X2 贴合市场。返回 split。"""
        if not probs or total <= 0.4:
            return start
        th, td = probs[0], probs[1]

        def err(s):
            x, y = (total + s) / 2.0, (total - s) / 2.0
            if x <= 0.10 or y <= 0.10:
                return 9.9
            m = self.joint(x, y, 0.0, 6, tau=False)
            ph = pd = 0.0
            for h in range(7):
                for a in range(7):
                    if h > a:
                        ph += m[h][a]
                    elif h == a:
                        pd += m[h][a]
            return (ph - th) ** 2 + (pd - td) ** 2

        lo, hi = -total + 0.25, total - 0.25
        best, bs = None, start
        for i in range(41):
            s = lo + (hi - lo) * i / 40.0
            e = err(s)
            if best is None or e < best:
                best, bs = e, s
        for step in (0.16, 0.06, 0.02, 0.008):
            for dd in (-step, step):
                s = clamp(bs + dd, lo, hi)
                e = err(s)
                if e < best:
                    best, bs = e, s
        return bs

    # ---------- 期望进球（对外）----------
    def lambdas(self, home, away, league, odds=None, score_odds=None):
        lh_r, la_r, info = self.rating_lambdas(home, away, league)
        probs = devig((odds or {}).get("胜"), (odds or {}).get("平"), (odds or {}).get("负"))
        sd = score_dist_to_lambdas(score_odds) if score_odds else None
        T_r = lh_r + la_r
        if sd:
            k = float(self.p["score_w"])
            T = k * (sd[0] + sd[1]) + (1 - k) * T_r
        else:
            T = T_r
        s_r = lh_r - la_r
        if probs:
            s = self._split_for(T, probs, s_r)
        else:
            s = s_r
        lh, la = (T + s) / 2.0, (T - s) / 2.0
        return {"lam_h": clamp(lh, 0.15, 4.50), "lam_a": clamp(la, 0.15, 4.50),
                "lam_h_rating": lh_r, "lam_a_rating": la_r,
                "lam_total": T, "lam_total_rating": T_r,
                "lam_total_score": (sd[0] + sd[1]) if sd else None,
                "used_score_odds": bool(sd), "n_hist": info}

    # ---------- 比分盘融合 ----------
    def blend_market(self, P, pm, alpha=None):
        """模型分布 P 与比分盘分布 pm 混合（pm 未覆盖的尾部由模型补足质量）。"""
        alpha = float(self.p["market_mix"] if alpha is None else alpha)
        if not pm or alpha <= 0:
            return P
        keys = set(P) | set(pm)
        psum = sum(P.values())
        if psum <= 0:
            return P
        covered = sum(P.get(k, 0.0) for k in pm) / psum
        covered = clamp(covered, 0.30, 0.995)
        pn = {k: v / sum(pm.values()) for k, v in pm.items()}
        out = {}
        for k in keys:
            mv = covered * pn.get(k, 0.0)
            if k not in pm:
                mv += (1 - covered) * (P.get(k, 0.0) / max(1e-12, psum * (1 - covered)))
            out[k] = alpha * mv + (1 - alpha) * (P.get(k, 0.0) / psum)
        s = sum(out.values())
        return {k: v / s for k, v in out.items()} if s > 0 else P

    # ---------- 蒙特卡洛 ----------
    def monte_carlo(self, lh, la, lam3, n=None, seed=20260918):
        n = int(n or self.p["mc_n"])
        rnd = random.Random(seed)
        lam3 = clamp(float(lam3), 0.0, 0.85 * min(lh, la))
        l1, l2 = max(1e-6, lh - lam3), max(1e-6, la - lam3)

        def draw(lam):
            u, k, c, s = rnd.random(), 0, math.exp(-lam), math.exp(-lam)
            while u > s and k < 30:
                k += 1
                c *= lam / k
                s += c
            return k

        sc, hh, aa = {}, {}, {}
        for _ in range(n):
            x = draw(l1) + draw(lam3)
            y = draw(l2) + draw(lam3)
            k = "%d:%d" % (x, y)
            sc[k] = sc.get(k, 0) + 1
            hh[x] = hh.get(x, 0) + 1
            aa[y] = aa.get(y, 0) + 1
        return sc, hh, aa

    # ---------- 单场预测 ----------
    def predict(self, match, want_mc=False):
        home = match.get("home") or ""
        away = match.get("away") or ""
        league = match.get("league") or ""
        od = match.get("odds") or {}
        sd = match.get("score_odds") or od.get("比分") or {}
        L = self.lambdas(home, away, league, od, sd)
        lh, la = float(L["lam_h"]), float(L["lam_a"])
        lam3 = clamp(float(self.p["lam3"]), 0.0, 0.85 * min(lh, la))
        m = self.joint_final(lh, la, lam3)
        n = len(m)
        P = {("%d:%d" % (h, a)): m[h][a] for h in range(n) for a in range(n)}
        pm = market_dist(sd)
        dist = self.blend_market(P, pm)
        # 申明概率的温度校准。混合分布的申明值系统性低于实际频率：
        # 1248 场样本外，±1 球申明 62.9% 而实际 68.9%、Top3 申明 31.7% 而实际 38.0%、
        # 头条比分申明 11.8% 而实际 16.4%。按 p^T 重归一（T=1.2：±1 球 68.8%、Top3 36.1%，
        # 与实际基本吻合；前半段拟合、后半段验证 LogLoss −0.49%）。
        # 该变换单调 → 不改变任何选取（头条/Top3/±1 的格集合完全不变），只让申明概率说实话。
        _T = float(self.p.get("prob_temp", 1.0) or 1.0)
        if _T != 1.0:
            _s = sum(max(0.0, v) ** _T for v in dist.values())
            if _s > 0:
                dist = {k: max(0.0, v) ** _T / _s for k, v in dist.items()}
        cells = sorted(dist.items(), key=lambda x: -x[1])
        top = [{"score": s, "prob": round(p * 100, 1)} for s, p in cells[:6] if p > 0]

        n_dist = len(dist)
        home_dist = [0.0] * n
        away_dist = [0.0] * n
        for s, v in dist.items():
            if ":" not in s:
                continue
            h, a = (int(x) for x in s.split(":"))
            if h >= n or a >= n:
                continue
            home_dist[h] += v
            away_dist[a] += v
        # 方向三率取模型矩阵口径（混合分布只覆盖列出比分，不含尾部）
        ph = pd = 0.0
        for h in range(n):
            for a in range(n):
                if h > a:
                    ph += m[h][a]
                elif h == a:
                    pd += m[h][a]
        home_dist = [round(x * 100, 1) for x in home_dist]
        away_dist = [round(x * 100, 1) for x in away_dist]
        hm = max(range(n), key=lambda i: home_dist[i])
        am = max(range(n), key=lambda i: away_dist[i])

        th, ta = (int(x) for x in top[0]["score"].split(":")) if top and ":" in top[0]["score"] else (0, 0)
        near = 0.0
        for dh in (-1, 0, 1):
            for da in (-1, 0, 1):
                near += dist.get("%d:%d" % (th + dh, ta + da), 0.0)

        out = dict(L)
        out.update({
            "lam3": round(lam3, 3),
            "prob": {"home": round(ph * 100, 1), "draw": round(pd * 100, 1),
                     "away": round(max(0.0, 1 - ph - pd) * 100, 1)},
            "top_scores": top,
            "home_dist": home_dist, "away_dist": away_dist,
            "home_mode": hm, "home_mode_p": home_dist[hm],
            "away_mode": am, "away_mode_p": away_dist[am],
            "cover1": round(near * 100, 1),
            "top3": round(sum(p for _, p in cells[:3]) * 100, 1),
            "market_mix_used": bool(pm),
            "matrix": [[round(x, 5) for x in row] for row in m],
        })
        if want_mc:
            sc, hh, aa = self.monte_carlo(lh, la, lam3)
            tot = float(sum(sc.values()))
            out["mc"] = {
                "top": [{"score": s, "prob": round(c / tot * 100, 1)}
                        for s, c in sorted(sc.items(), key=lambda x: -x[1])[:6]],
                "home_mean": round(sum(k * v for k, v in hh.items()) / tot, 3),
                "away_mean": round(sum(k * v for k, v in aa.items()) / tot, 3),
                "n": int(tot),
            }
        return out


# ---------- 生产入口 ----------
_ENGINE_CACHE = {}


def engine_asof(cutoff_date=None):
    """取「只喂入 cutoff_date 之前比赛」的引擎实例（按截止日缓存）。"""
    key = cutoff_date or "ALL"
    eng = _ENGINE_CACHE.get(key)
    if eng is not None:
        return eng
    hist = Engine.load_history()
    if cutoff_date:
        hist = [r for r in hist if r["date"] < cutoff_date]
    eng = Engine(hist)
    _ENGINE_CACHE[key] = eng
    return eng


def predict_batch(matches, cutoff_date=None, want_mc=False):
    eng = engine_asof(cutoff_date)
    out = {}
    for m in matches:
        key = "%s_%s" % (m.get("home") or "", m.get("away") or "")
        out[key] = eng.predict(m, want_mc=want_mc)
    return out


if __name__ == "__main__":
    hist = Engine.load_history()
    eng = Engine(hist)
    print("历史 %d 场  %s → %s  球队 %d" % (len(hist), hist[0]["date"], hist[-1]["date"],
                                          len(eng.teams)))
    gh, ga = eng._base(None)
    print("全局基准 主 %.2f 客 %.2f" % (gh, ga))
    demo = {"home": "拜仁", "away": "柏林联合", "league": "德甲",
            "odds": {"胜": 1.25, "平": 6.2, "负": 11.0}}
    r = eng.predict(demo, want_mc=True)
    print(json.dumps({k: v for k, v in r.items() if k != "matrix"},
                     ensure_ascii=False, indent=1))
