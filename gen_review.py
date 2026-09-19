"""生成「某日预测 vs 实际赛果」复盘 HTML。

数据来源：
  - 预测：predictions/<date>/pred_snapshot.json（每场含方向概率、λ、top_scores、stars 信心）
  - 赛果：results_data.json + results_history/*.json（键 = 日期_主_客，已修正主客方向）

比分口径（2026-09-13 起与报告同步）：
  - 头条 = 「命中比分」= 已对齐矩阵的联合众数（= top_scores 首个列出比分），
    这是「押中次数」目标函数下的最优解（与 _gen_report.hit_pick 同规则；4036 场回测 14.94%）；
  - 双档 = 模型排序第 2、第 3 可能比分（_gen_report.hit_band；4036 场回测 Top2 11.6% + Top3 8.9% ≈ 20.5%）。
  旧口径（λ 期望取整 + 同倾向次高，单点 13.8%/双档 26.0%）与「头条+第2档」口径均已弃用，λ 期望值仅作「量级参考」。

特点：
  - 不依赖市场赔率，覆盖该日全部预测场次（含只有让球盘、无 1X2 赔率的场次）。
  - 输出落到 predictions/<date+1 天>/review_<date>.html（沿用历史约定：复盘 D 放在 D+1 当日目录）。

用法：
  python gen_review.py --date 2026-09-10     # 生成 09-10 复盘
  python gen_review.py                        # 默认复盘「昨天」
"""
import argparse
import datetime as dt
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))

# 竞彩比分盘的列出比分（与 _gen_report._LISTED_LABELS 保持一致；λ 取整结果不在此列时退回象限众数）
LISTED_LABELS = {
    '1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '4:0', '4:1', '4:2', '5:0', '5:1', '5:2',
    '0:0', '1:1', '2:2', '3:3',
    '0:1', '0:2', '1:2', '0:3', '1:3', '2:3', '0:4', '1:4', '2:4', '0:5', '1:5', '2:5',
}


def _parse_score(s):
    try:
        h, a = (int(x) for x in str(s).split(':'))
        return (h, a)
    except (ValueError, AttributeError):
        return None


def _in_quad(c, okey):
    return ((c[0] > c[1]) if okey == 'home' else
            ((c[0] == c[1]) if okey == 'draw' else (c[0] < c[1])))


def predict_scores(m):
    """按报告口径取 (命中比分, 双档集合, 量级参考比分)。

    2026-09-13 二次定调（目标函数 = 比分命中次数，概率幅值不作为指标）：
      头条 = 已对齐矩阵的**联合众数**（= top_scores 里首个列出比分）= 押中次数目标函数的最优解；
      双档 = 模型排序第 2、第 3 可能比分（4036 场回测 Top2 单档 11.6% / Top3 单档 8.9% ≈ 20.5%）；
      量级参考 = λ 期望进球取整（无偏但不为押中，总进球偏差 −0.22 球/场）。
    旧口径「期望比分 + 同倾向次高」为 Top1 13.8% / Top2 26.0%，已弃用。
    """
    ts = [t for t in (m.get('top_scores') or [])
          if _parse_score(t.get('score')) and t.get('score') in LISTED_LABELS]
    hit = ts[0]['score'] if ts else '-'
    band = {t['score'] for t in ts[1:3]}
    ph, pd, pa = (float(m.get('prob_home', 0) or 0), float(m.get('prob_draw', 0) or 0),
                  float(m.get('prob_away', 0) or 0))
    okey = 'home' if ph >= pd and ph >= pa else ('away' if pa >= pd else 'draw')
    lh = float(m.get('lam_home', 0) or 0)
    la = float(m.get('lam_away', 0) or 0)
    cand = (int(round(lh)), int(round(la)))
    if _in_quad(cand, okey) and f'{cand[0]}:{cand[1]}' in LISTED_LABELS:
        mag = f'{cand[0]}:{cand[1]}'
    else:
        mag = hit
    return hit, band, mag


def load_json(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def load_results_all():
    recs = {}
    for f in sorted(glob.glob(os.path.join(ROOT, 'results_history', '*.json'))):
        if os.path.basename(f) == 'index.json':
            continue
        try:
            d = load_json(f)
        except Exception:
            continue
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict):
                    recs.setdefault(k, v)
    rd = os.path.join(ROOT, 'results_data.json')
    if os.path.exists(rd):
        d = load_json(rd)
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict):
                    recs[k] = v
    return recs


def parse_score(rec):
    s = rec.get('score') or rec.get('fullScore') or ''
    if not isinstance(s, str) or ':' not in s:
        return None
    a, b = s.split(':', 1)
    try:
        return int(a), int(b)
    except Exception:
        return None


def outcome_label(h, a):
    return '主胜' if h > a else ('平局' if h == a else '客胜')


CSS = """body{font-family:'Microsoft YaHei',sans-serif;margin:24px;background:#f5f6fa;color:#222}
h1{font-size:22px;border-bottom:3px solid #2c3e50;padding-bottom:8px}
h2{font-size:14px;color:#666;font-weight:normal}
table{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.08);margin-top:12px}
th{background:#2c3e50;color:#fff;padding:10px 8px;font-size:13px}
td{border:1px solid #e5e5e5;padding:9px 8px;font-size:13px;text-align:center}
tr:nth-child(even){background:#fafafa}
.b{font-weight:bold}
.hot{background:#f0fff0}
.dir{color:#e60012;font-weight:bold}
.sum{background:#fff3cd;padding:10px 14px;border-radius:6px;margin-top:10px;font-size:13px;line-height:1.8}
.ok{color:#2a9d8f;font-weight:bold}
.no{color:#e63946;font-weight:bold}
"""


def day_rows(ds):
    """读某日快照并与赛果配对 → (snap, [(match, (h,a) | None)])；无快照返回 (None, None)"""
    snap_path = os.path.join(ROOT, 'predictions', ds, 'pred_snapshot.json')
    if not os.path.exists(snap_path):
        return None, None
    snap = load_json(snap_path)
    recs = load_results_all()
    rows = []
    for m in snap.get('matches') or []:
        key = f'{ds}_{m.get("home")}_{m.get("away")}'
        rec = recs.get(key)
        rows.append((m, parse_score(rec) if rec else None))
    return snap, rows


def tally(rows):
    """统计 (已出赛果场次, 方向命中, 命中比分单点, 双档命中)"""
    nres = dh = hh = bh = 0
    for m, sc in rows:
        if not sc:
            continue
        hit_sc, band, _ = predict_scores(m)
        ph, pd, pa = (float(m.get('prob_home', 0) or 0), float(m.get('prob_draw', 0) or 0),
                      float(m.get('prob_away', 0) or 0))
        pred_dir = '主胜' if ph >= pd and ph >= pa else ('客胜' if pa >= pd else '平局')
        actual = f'{sc[0]}:{sc[1]}'
        nres += 1
        dh += 1 if pred_dir == outcome_label(*sc) else 0
        hh += 1 if actual == hit_sc else 0
        bh += 1 if actual in band else 0
    return nres, dh, hh, bh


def cumulative_kpi(up_to, since='2026-09-08'):
    """累计目标函数：把所有已出赛果的预测快照按日累加（2026-09-13 起的目标函数 = 命中次数）。

    这是「函数好优化」的度量基准：任何口径/模型改动都看这里的累计命中次数是否上升。

    起点 since 默认 2026-09-08：更早的快照（engine=poisson-v2.2 旧链路）没有 top_scores 字段，
    且 09-10 之前赛果库存在主客颠倒 bug，纳入会污染基准。
    基准线（4036 场生产口径回测，_baseline_probe.py）：单点 14.94% / 双档（第2+第3档）≈20.5%；
    常数基线（全场猜 1:1）12.93% —— 模型净多中 81 场，McNemar χ²=19.34（p<0.001）。
    """
    import glob as _g
    days = []
    tot = [0, 0, 0, 0]
    files = sorted(_g.glob(os.path.join(ROOT, 'predictions', '*', 'pred_snapshot.json')))
    for f in files:
        ds = os.path.basename(os.path.dirname(f))
        if ds < since or ds > up_to:
            continue
        snap, rows = day_rows(ds)
        if not rows or not any(m.get('top_scores') for m, _ in rows):
            continue
        nres, dh, hh, bh = tally(rows)
        if not nres:
            continue
        days.append((ds, nres, dh, hh, bh))
        for i, v in enumerate((nres, dh, hh, bh)):
            tot[i] += v
    return days, tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=None, help='被复盘日期 YYYY-MM-DD，默认昨天')
    ap.add_argument('--kpi', action='store_true', help='只打印累计目标函数（命中次数）序列')
    a = ap.parse_args()

    if a.date:
        reviewed = dt.date.fromisoformat(a.date)
    else:
        reviewed = dt.date.today() - dt.timedelta(days=1)
    ds = reviewed.isoformat()
    next_day = (reviewed + dt.timedelta(days=1)).isoformat()

    if a.kpi:
        days, tot = cumulative_kpi(ds)
        print(f'累计目标函数（截止 {ds}，口径 = 报告头条联合众数 / 双档）')
        print(f"{'日期':<12}{'场次':>6}{'方向':>10}{'命中比分单点':>14}{'双档':>10}")
        for d_, n_, dh_, hh_, bh_ in days:
            print(f'{d_:<12}{n_:>6}{dh_:>7}({dh_/n_*100:.0f}%){hh_:>8}({hh_/n_*100:.0f}%){bh_:>6}({bh_/n_*100:.0f}%)')
        if tot[0]:
            print(f"{'合计':<12}{tot[0]:>6}{tot[1]:>7}({tot[1]/tot[0]*100:.1f}%)"
                  f"{tot[2]:>8}({tot[2]/tot[0]*100:.1f}%){tot[3]:>6}({tot[3]/tot[0]*100:.1f}%)")
        return

    snap, rows = day_rows(ds)
    if snap is None:
        print(f'无快照：predictions/{ds}/pred_snapshot.json（该日可能未生成报告）')
        return

    n = len(rows)
    dir_hit = score_hit = any_hit = exp_hit = 0
    lam_model_sum = 0.0
    lam_actual_sum = 0.0
    table = []
    misses = []
    for m, sc in rows:
        home, away, lid = m.get('home'), m.get('away'), m.get('league', '')
        ph, pd, pa = float(m.get('prob_home', 0)), float(m.get('prob_draw', 0)), float(m.get('prob_away', 0))
        pred_dir = '主胜' if ph >= pd and ph >= pa else ('客胜' if pa >= pd else '平局')
        hit_sc, band, mag_sc = predict_scores(m)
        band_order = ([hit_sc] + sorted(band - {hit_sc}))
        exp_sc = hit_sc
        stars = '★' * int(m.get('stars', 0))
        actual = outcome_label(*sc) if sc else '?'
        actual_score = f'{sc[0]}:{sc[1]}' if sc else '?'
        dh = (pred_dir == actual) if sc else False
        sh = (sc is not None and actual_score in band)
        eh = (sc is not None and actual_score == exp_sc)
        ah = dh or sh
        if sc:
            dir_hit += dh
            score_hit += sh
            exp_hit += eh
            any_hit += ah
            lt = m.get('lam_total') or (float(m.get('lam_home', 0) or 0) + float(m.get('lam_away', 0) or 0))
            lam_model_sum += float(lt)
            lam_actual_sum += (sc[0] + sc[1])
            if not dh:
                misses.append(f'{m.get("id")} {home}vs{away} 预测{pred_dir}实际{actual}')
        table.append(
            f'<tr><td class="b">{m.get("id")}</td><td>{lid}</td><td class="b">{home} vs {away}</td>'
            f'<td class="dir">{pred_dir}</td>'
            f'<td class="b">{exp_sc}</td><td>{"/".join(band_order)}</td><td>{stars}</td>'
            f'<td class="b">{actual_score}</td><td class="b">{actual}</td>'
            f'<td><span class="{"ok" if dh else "no"}">{"✔" if dh else "✘"}</span></td>'
            f'<td><span class="{"ok" if sh else "no"}">{"✔" if sh else "✘"}</span></td></tr>'
        )

    nres = sum(1 for _, sc in rows if sc)
    lam_bias = (lam_model_sum - lam_actual_sum) / nres if nres else 0.0
    concl = (f'{ds} 共预测 {n} 场，赛果到 {nres} 场；方向命中 {dir_hit}/{nres}'
             f'={ (dir_hit/nres*100) if nres else 0:.0f}%，命中比分单点 {exp_hit}/{nres}'
             f'={ (exp_hit/nres*100) if nres else 0:.0f}%，比分双档命中 {score_hit}/{nres}'
             f'={ (score_hit/nres*100) if nres else 0:.0f}%，至少一项命中 {any_hit}/{nres}'
             f'={ (any_hit/nres*100) if nres else 0:.0f}%，λ总进球偏差 {lam_bias:+.2f} 球/场。')
    miss_note = ('方向失手：' + '；'.join(misses)) if misses else '方向全部命中。'

    _days, _tot = cumulative_kpi(ds)
    cum_html = ''
    if _tot[0]:
        cum_html = (f'<div class="sum"><b>累计命中（{len(_days)} 个比赛日 · {_tot[0]} 场）：</b>'
                    f'方向 <b>{_tot[1]}</b>（{_tot[1]/_tot[0]*100:.1f}%）· '
                    f'命中比分单点 <b>{_tot[2]}</b>（{_tot[2]/_tot[0]*100:.1f}%）· '
                    f'双档 <b>{_tot[3]}</b>（{_tot[3]/_tot[0]*100:.1f}%）。'
                    f'长期基准：单点约 15% · 双档约 20%。</div>')

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{ds} 竞彩预测复盘</title><style>{CSS}</style></head><body>
<h1>{ds} 竞彩预测复盘</h1>
<h2>复盘范围：{ds} {n} 场预测 · 方向命中 {dir_hit}/{nres} · 命中比分单点 {exp_hit}/{nres} · 双档命中 {score_hit}/{nres} · 至少一项命中 {any_hit}/{nres}</h2>
{cum_html}
<div class="sum"><b>关键复盘结论：</b>{concl}{miss_note}
次日建议：方向失手集中在{"冷门/平局爆冷" if misses else "无"}场次，强弱对话与深让盘依 V3.3 滚动校准自动修正，无需每日手调；若连续多日方向命中率低于 50% 或 λ 总进球偏差持续 >0.2 球，应触发离线重拟合（market_calib / Platt）。</div>
<table>
<tr><th>编号</th><th>联赛</th><th>主队 vs 客队</th><th>预测方向</th><th>命中比分(头条)</th><th>双档</th><th>信心</th><th>实际比分</th><th>实际结果</th><th>方向</th><th>比分</th></tr>
{''.join(table)}
</table></body></html>"""

    out_dir = os.path.join(ROOT, 'predictions', next_day)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'review_{ds}.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'已生成：{out_path}')
    print(concl)
    if misses:
        print(miss_note)
    print(f'复盘指标: 方向 {dir_hit}/{nres}={(dir_hit/nres*100) if nres else 0:.0f}% | '
          f'命中比分单点 {exp_hit}/{nres}={(exp_hit/nres*100) if nres else 0:.0f}% | '
          f'比分双档 {score_hit}/{nres}={(score_hit/nres*100) if nres else 0:.0f}% | '
          f'λ总进球偏差 {lam_bias:+.2f} 球/场')


if __name__ == '__main__':
    main()
