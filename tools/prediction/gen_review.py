"""生成「某日预测 vs 实际赛果」复盘 HTML。

数据来源：
  - 预测：predictions/<date>/pred_snapshot.json（每场含方向概率、top_scores 双档、stars 信心）
  - 赛果：results_data.json + results_history/*.json（键 = 日期_主_客，已修正主客方向）

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=None, help='被复盘日期 YYYY-MM-DD，默认昨天')
    a = ap.parse_args()

    if a.date:
        reviewed = dt.date.fromisoformat(a.date)
    else:
        reviewed = dt.date.today() - dt.timedelta(days=1)
    ds = reviewed.isoformat()
    next_day = (reviewed + dt.timedelta(days=1)).isoformat()

    snap_path = os.path.join(ROOT, 'predictions', ds, 'pred_snapshot.json')
    if not os.path.exists(snap_path):
        print(f'无快照：{snap_path}（该日可能未生成报告）')
        return
    snap = load_json(snap_path)
    recs = load_results_all()

    rows = []
    for m in snap.get('matches') or []:
        home, away = m.get('home'), m.get('away')
        key = f'{ds}_{home}_{away}'
        rec = recs.get(key)
        sc = parse_score(rec) if rec else None
        if not sc:
            rows.append((m, None))
            continue
        rows.append((m, sc))

    n = len(rows)
    dir_hit = score_hit = any_hit = 0
    table = []
    misses = []
    for m, sc in rows:
        home, away, lid = m.get('home'), m.get('away'), m.get('league', '')
        ph, pd, pa = float(m.get('prob_home', 0)), float(m.get('prob_draw', 0)), float(m.get('prob_away', 0))
        pred_dir = '主胜' if ph >= pd and ph >= pa else ('客胜' if pa >= pd else '平局')
        top2 = (m.get('top_scores') or [])[:2]
        s1 = top2[0]['score'] if len(top2) > 0 else '-'
        s2 = top2[1]['score'] if len(top2) > 1 else '-'
        stars = '★' * int(m.get('stars', 0))
        actual = outcome_label(*sc) if sc else '?'
        actual_score = f'{sc[0]}:{sc[1]}' if sc else '?'
        dh = (pred_dir == actual) if sc else False
        sh = (sc is not None and actual_score in {t.get('score') for t in top2})
        ah = dh or sh
        if sc:
            dir_hit += dh
            score_hit += sh
            any_hit += ah
            if not dh:
                misses.append(f'{m.get("id")} {home}vs{away} 预测{pred_dir}实际{actual}')
        table.append(
            f'<tr><td class="b">{m.get("id")}</td><td>{lid}</td><td class="b">{home} vs {away}</td>'
            f'<td class="dir">{pred_dir}</td><td>{s1}/{s2}</td><td>{stars}</td>'
            f'<td class="b">{actual_score}</td><td class="b">{actual}</td>'
            f'<td><span class="{"ok" if dh else "no"}">{"✔" if dh else "✘"}</span></td>'
            f'<td><span class="{"ok" if sh else "no"}">{"✔" if sh else "✘"}</span></td></tr>'
        )

    nres = sum(1 for _, sc in rows if sc)
    concl = (f'{ds} 共预测 {n} 场，赛果到 {nres} 场；方向命中 {dir_hit}/{nres}'
             f'={ (dir_hit/nres*100) if nres else 0:.0f}%，比分双档命中 {score_hit}/{nres}'
             f'={ (score_hit/nres*100) if nres else 0:.0f}%，至少一项命中 {any_hit}/{nres}'
             f'={ (any_hit/nres*100) if nres else 0:.0f}%。')
    miss_note = ('方向失手：' + '；'.join(misses)) if misses else '方向全部命中。'

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{ds} 竞彩预测复盘</title><style>{CSS}</style></head><body>
<h1>{ds} 竞彩预测复盘</h1>
<h2>复盘范围：{ds} {n} 场预测 · 方向命中 {dir_hit}/{nres} · 比分双档命中 {score_hit}/{nres} · 至少一项命中 {any_hit}/{nres}</h2>
<div class="sum"><b>关键复盘结论：</b>{concl}{miss_note}
次日建议：方向失手集中在{"冷门/平局爆冷" if misses else "无"}场次，强弱对话与深让盘依 V3.3 滚动校准自动修正，无需每日手调；若连续多日方向命中率低于 50% 或 λ 总进球偏差持续 >0.2 球，应触发离线重拟合（market_calib / Platt）。</div>
<table>
<tr><th>编号</th><th>联赛</th><th>主队 vs 客队</th><th>预测方向</th><th>预测比分(双档)</th><th>信心</th><th>实际比分</th><th>实际结果</th><th>方向</th><th>比分</th></tr>
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


if __name__ == '__main__':
    main()
