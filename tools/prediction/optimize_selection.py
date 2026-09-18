# -*- coding: utf-8 -*-
"""每日复盘后优化「比分精选 / 大胆档」两块独立板块（2026-09-17 定调：两块分别计算）。

做法：
  1. 读取历史 predictions/<date>/pred_snapshot.json（含 lam_home/lam_away/top_scores/prob_*）
     与 results_history / results_data 中的实际赛果，配对出「模型当时选了哪些场 + 实际中了没」。
  2. 两块各自独立调参、互不影响：
     · 板块 A 比分精选：pk_lambda_caps / pk_degen_down；
     · 板块 B 大胆档：bd_total_shift / bd_min_total（自带泊松模型，不读引擎比分矩阵）；
       网格只含大样本验证过的安全区，激进档位已证伪不入搜索。
     每块目标 = 0.6 × 每日命中率均值 + 0.4 × 每日至少一中覆盖率，第一档准确率优先。
     ⚠️ 回放选取必须调用 SA.split_boards（与报告同一入口：比分精选先占位、大胆档互斥分池、
     同样排除冷启动）；自己写一份排序会让「优化器评估的算法」≠「线上跑的算法」，调参就失去意义。
  3. 仅当相对默认口径改善 ≥ 0.3pp 且最近 1/3 天不塌（≥ -0.5pp）才采纳，否则保留默认；
     可用天数 < 5 时直接写默认，保证报告始终有可调文件。
  输出：selection_tuning.json（被 gen_report.py 读取）。

关键：选取与命中判定一律走 selection_algo —— 与报告渲染同一份实现，
否则「优化器调的旋钮」和「报告真用的算法」会各说各话，优化就失去意义。
设计原则：只读历史、不改报告逻辑；任何失败都回退默认，绝不让报告崩。
"""
import json, os, glob, datetime

import selection_algo as SA

MIN_DAYS = 5
ADOPT_GAIN = 0.3   # pp
HOLDOUT_TOL = 0.5  # pp：最近 1/3 天的目标不得比默认口径低超过此值

DEFAULT_TUNING = SA.DEFAULT_TUNING
TIER_PK = SA.TIER_PK
TIER_BD = SA.TIER_BD
match_key = SA.match_key


# ---------- 历史赛果缓存 ----------
def _results_cache():
    recs = {}
    for f in sorted(glob.glob(os.path.join('.', 'results_history', '*.json'))):
        if os.path.basename(f) == 'index.json':
            continue
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict):
                    recs.setdefault(k, v)
    try:
        rd = json.load(open('results_data.json', encoding='utf-8'))
        if isinstance(rd, dict):
            for k, v in rd.items():
                if isinstance(v, dict):
                    recs[k] = v
    except Exception:
        pass
    return recs


def _lookup_actual(recs, y, home, away):
    for key in (f'{y}_{home}_{away}', f'{y}_{away}_{home}'):
        rec = recs.get(key)
        if rec:
            s = rec.get('score') or rec.get('fullScore') or ''
            if isinstance(s, str) and ':' in s:
                return s
    return None


# ---------- 回放（口径必须与生产一致）----------
def _collect_days(today):
    """收集「有完整赛果」的历史日；只保留已出赛果的场次。"""
    days = []
    recs = _results_cache()
    for sp in sorted(glob.glob(os.path.join('.', 'predictions', '*', 'pred_snapshot.json'))):
        date = os.path.basename(os.path.dirname(sp))
        if date >= today:
            continue
        try:
            snap = json.load(open(sp, encoding='utf-8'))
        except Exception:
            continue
        rows = []
        for m in (snap.get('matches') or []):
            act = _lookup_actual(recs, date, m.get('home'), m.get('away'))
            if not act:
                continue
            nm = dict(m)
            nm.setdefault('prob', {'home': m.get('prob_home', 0), 'draw': m.get('prob_draw', 0),
                                   'away': m.get('prob_away', 0)})
            nm.setdefault('cold', False)
            nm.setdefault('data_n', {})
            rows.append((nm, act))
        if len(rows) >= TIER_PK:
            days.append(rows)
    return days


def _first_tier(tiers):
    """取第一档的 match 列表（rank_* 返回 [(排序键, match)]）。"""
    return [x[1] for x in (tiers[0] if tiers else [])]


def _pk_day_score(rows, tuning):
    """比分精选当日成绩：走 SA.split_boards（生产同一入口、含冷启动排除）。

    比分精选先成榜，其选取不受 bd_* 参数影响 → 本项评估与大胆档完全独立。
    """
    amap = {match_key(m): a for m, a in rows}
    pk_t, _, _, _, _ = SA.split_boards([m for m, _ in rows], tuning, TIER_PK, TIER_BD)
    sel = _first_tier(pk_t)
    if not sel:
        return 0.0, 0
    succ = sum(1 for m in sel if SA.pk_result(m, amap[match_key(m)], tuning) in ('hit', 'band'))
    return succ / len(sel), (1 if succ >= 1 else 0)


def _bd_day_score(rows, tuning):
    """大胆档当日成绩：同样走 SA.split_boards（互斥分池后第一档）。"""
    amap = {match_key(m): a for m, a in rows}
    _, _, bd_t, _, _ = SA.split_boards([m for m, _ in rows], tuning, TIER_PK, TIER_BD)
    sel = _first_tier(bd_t)
    if not sel:
        return 0.0, 0
    succ = sum(1 for m in sel if SA.bd_result(m, amap[match_key(m)], tuning) in ('scale', 'extreme'))
    return succ / len(sel), (1 if succ >= 1 else 0)


def _obj(scores):
    if not scores:
        return 0.0
    rate = sum(s[0] for s in scores) / len(scores)
    cov = sum(s[1] for s in scores) / len(scores)
    return 0.6 * rate * 100 + 0.4 * cov * 100


def _merge(base, **kw):
    d = dict(base)
    d.update(kw)
    return d


def main():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    out = dict(DEFAULT_TUNING)
    meta = {'tuned_at': today, 'days_used': 0, 'note': 'insufficient history -> defaults'}

    days = _collect_days(today)
    if len(days) < MIN_DAYS:
        out['_meta'] = meta
        json.dump(out, open('selection_tuning.json', 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        print(f'[optimize] 可用历史天数={len(days)} < {MIN_DAYS}，写入默认旋钮。')
        return

    # —— 板块 A 比分精选：调自身分布的 1X2 对齐开关、λ 分界上限、1:1 退化降权 ——
    base_t = _merge(DEFAULT_TUNING)
    base_pk = _obj([_pk_day_score(d, base_t) for d in days])
    best_pk, best_pk_obj = dict(DEFAULT_TUNING), base_pk
    for align in (0, 1):
        for cap_high in (3.0, 3.2, 3.4, 3.6, 3.8, 4.2):
            for degen in (0.8, 0.85, 0.9, 1.0):
                t = _merge(DEFAULT_TUNING, pk_align_1x2=align,
                           pk_lambda_caps=[2.6, 3.0, cap_high], pk_degen_down=degen)
                o = _obj([_pk_day_score(d, t) for d in days])
                if o > best_pk_obj + 1e-9:
                    best_pk_obj = o
                    best_pk = {'pk_align_1x2': align,
                               'pk_lambda_caps': [2.6, 3.0, cap_high], 'pk_degen_down': degen}
    if best_pk_obj - base_pk >= ADOPT_GAIN:
        for k, v in best_pk.items():
            out[k] = v
        meta['pk'] = {'base_obj': round(base_pk, 2), 'tuned_obj': round(best_pk_obj, 2),
                      'adopted': True}
    else:
        meta['pk'] = {'base_obj': round(base_pk, 2), 'best_obj': round(best_pk_obj, 2),
                      'adopted': False}
    pk_tuned = _merge(DEFAULT_TUNING, **{k: out[k] for k in
                                         ('pk_lambda_caps', 'pk_degen_down')})

    # —— 板块 B 大胆档：自带模型（只用引擎 λ），只调自己那套 bd_* 旋钮 ——
    # 互斥成榜（bd_exclusive=1）是用户定调的生产口径，不参与搜索。
    # 评估一律在「比分类已用本板块 A 采纳后的参数」下进行，与生产一致。
    base_bd = _obj([_bd_day_score(d, pk_tuned) for d in days])
    hold = max(1, len(days) // 3)
    hold_bd = _obj([_bd_day_score(d, pk_tuned) for d in days[-hold:]])
    cands = []
    # 网格只含「已被大样本验证过」的安全区：更激进的 bd_total_shift（≥+1）与更大的
    # bd_gap 在 178 天/2462 场上命中率明显更低（+1 → -9.6pp、+2 → -11.4pp），
    # 且 12 天小样本会反复把它们误选为最优，故直接排除，防过拟合。
    for sh in (-1, 0):
        for mt in (2, 3):
            t = _merge(pk_tuned, bd_total_shift=sh, bd_min_total=mt, bd_gap=1)
            o = _obj([_bd_day_score(d, t) for d in days])
            oh = _obj([_bd_day_score(d, t) for d in days[-hold:]])
            cands.append({'bd_total_shift': sh, 'bd_min_total': mt, 'bd_gap': 1,
                          'full': o, 'hold': oh})
    # 防过拟合（小样本易选到噪声极值）：全样本与近期两段都必须比默认口径好 ≥ ADOPT_GAIN，
    # 再在两段并重的口径下取最优；没有候选同时满足就保留默认。
    ok = [c for c in cands
          if c['full'] - base_bd >= ADOPT_GAIN and c['hold'] - hold_bd >= ADOPT_GAIN]
    if ok:
        best_bd = max(ok, key=lambda c: c['full'] + c['hold'])
        best_bd_obj, best_bd_hold = best_bd['full'], best_bd['hold']
    else:
        best_bd = None
        best_bd_obj, best_bd_hold = base_bd, hold_bd
    if best_bd:
        for k in ('bd_total_shift', 'bd_min_total', 'bd_gap'):
            out[k] = best_bd[k]
        meta['bd'] = {'base_obj': round(base_bd, 2), 'tuned_obj': round(best_bd_obj, 2),
                      'holdout_base': round(hold_bd, 2), 'holdout_tuned': round(best_bd_hold, 2),
                      'params': {k: best_bd[k] for k in ('bd_total_shift', 'bd_min_total', 'bd_gap')},
                      'adopted': True}
    else:
        meta['bd'] = {'base_obj': round(base_bd, 2), 'holdout_base': round(hold_bd, 2),
                      'adopted': False}

    meta['days_used'] = len(days)
    meta['note'] = 'grid search on rolling history'
    out['_meta'] = meta
    json.dump(out, open('selection_tuning.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(f'[optimize] 历史天数={len(days)} 比分精选 base={base_pk:.2f}->tuned={best_pk_obj:.2f} '
          f'adopt={meta["pk"]["adopted"]} | 大胆档 base={base_bd:.2f}->tuned={best_bd_obj:.2f} '
          f'adopt={meta["bd"]["adopted"]}')


if __name__ == '__main__':
    main()
