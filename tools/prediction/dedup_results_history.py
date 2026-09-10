"""清理 results_history/*.json 中残留的「反向孪生」条目，并把方向对齐到官方锚点。

背景：update_odds_net.py 早期的 fetch_163_results 会对每场比赛「主客反序双写」
（写 `日期_主_客` 与 `日期_客_主` 两条），导致 results_history/ 归档里同一 matchId
出现两条方向相反的记录（235 个文件里 215 个有孪生，共 2677 条多余）。

危害：_calc_engine.fit_platt_params 与 build_league_profile 都读 results_history，
孪生把同一场比赛以镜像方向重复计入 → 主客优势互相抵消（实测主胜率 43% 被稀释到 35%），
Platt 校准与联赛基线都建在被污染样本上。

方向锚点（按 matchId，队名用 canonical_team_name 归一后比较）：
  results_data.json（已去重、已校正 2988 条）→ odds_history/<date>.json 的官方 schedule。
  方向相反的记录会被就地翻转（flip_entry），而非仅丢弃。

用法:
  python dedup_results_history.py           # 只报告，不写盘
  python dedup_results_history.py --apply    # 写盘（先自动备份到 _hist_backup/）
"""
import argparse
import glob
import importlib.util
import json
import os
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = BASE
for _ in range(3):
    if os.path.isdir(os.path.join(ROOT, 'results_history')):
        break
    ROOT = os.path.dirname(ROOT)


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


_flip = _load_module('_flip_results_lib', os.path.join(ROOT, '_flip_results_lib.py'))
flip_entry = _flip.flip_entry

try:
    _uon = _load_module('_uon_for_names', os.path.join(ROOT, 'update_odds_net.py'))
    canonical = _uon.canonical_team_name
except Exception as exc:            # pragma: no cover
    print(f'⚠️ 无法加载 canonical_team_name（{exc}），退化为原样比较')
    canonical = lambda n: (n or '').strip()


def build_anchors():
    """matchId -> (home, away)（canonical），(date, frozenset) -> (home, away)。"""
    by_id, by_pair = {}, {}
    n_rd = n_oh = 0
    rd = os.path.join(ROOT, 'results_data.json')
    if os.path.exists(rd):
        for k, v in load(rd).items():
            if not isinstance(v, dict):
                continue
            h, a = v.get('home'), v.get('away')
            if not (h and a):
                continue
            ch, ca = canonical(h), canonical(a)
            mid = str(v.get('matchId') or '')
            if mid:
                by_id.setdefault(mid, (ch, ca))
                n_rd += 1
            by_pair.setdefault((k.split('_', 1)[0], frozenset((ch, ca))), (ch, ca))
    for f in sorted(glob.glob(os.path.join(ROOT, 'odds_history', '*.json'))):
        if os.path.basename(f) == 'index.json':
            continue
        try:
            d = load(f)
        except Exception:
            continue
        date = os.path.basename(f)[:10]
        for g in (d.get('schedule') or []):
            h, a = g.get('home'), g.get('away')
            if not (h and a):
                continue
            ch, ca = canonical(h), canonical(a)
            mid = str(g.get('matchId') or '')
            if mid and mid not in by_id:
                by_id[mid] = (ch, ca)
                n_oh += 1
            by_pair.setdefault((date, frozenset((ch, ca))), (ch, ca))
    print(f'方向锚点：results_data {n_rd} 条 matchId；odds_history 补充 {n_oh} 条')
    return by_id, by_pair


def has_real_score(rec):
    s = rec.get('score') or rec.get('fullScore') or ''
    return isinstance(s, str) and ':' in s and all(p.strip().isdigit() for p in s.split(':', 1))


def richness(rec):
    return sum(1 for f in ('胜', '平', '负', 'hda胜', '让球', '比分', '总进球', '半全场') if rec.get(f))


def dir_of(rec, key):
    """返回 (canonical_home, canonical_away) —— 以记录自身 home/away 为准，缺则退回 key。"""
    h, a = rec.get('home'), rec.get('away')
    if h and a:
        return canonical(h), canonical(a)
    q = key.split('_', 2)
    if len(q) == 3:
        return canonical(q[1]), canonical(q[2])
    return '', ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()

    by_id, by_pair = build_anchors()
    files = [f for f in sorted(glob.glob(os.path.join(ROOT, 'results_history', '*.json')))
             if os.path.basename(f) != 'index.json']

    tot_before = tot_after = removed = flipped = unresolved = 0
    detail = []
    out = {}
    for f in files:
        d = load(f)
        groups = {}
        for k, rec in d.items():
            if not isinstance(rec, dict):
                continue
            mid = str(rec.get('matchId') or '')
            q = k.split('_', 2)
            pair = (q[0], frozenset((canonical(q[1]), canonical(q[2])))) if len(q) == 3 else (k, frozenset())
            groups.setdefault(('id', mid) if mid else ('pair',) + pair, []).append(k)

        keep = {}
        for gk, keys in groups.items():
            anchor = by_id.get(gk[1]) if gk[0] == 'id' else None
            if anchor is None and len(gk) >= 3:
                anchor = by_pair.get(gk[1:3])
            # 选一条作代表：有真实数字比分 + 字段最完整
            cands = [k for k in keys if has_real_score(d[k])] or keys
            chosen = max(cands, key=lambda k: richness(d[k]))
            rec = d[chosen]
            if anchor:
                cur = dir_of(rec, chosen)
                if cur == anchor:
                    pass
                elif cur == (anchor[1], anchor[0]):
                    chosen, rec = flip_entry(chosen, rec)
                    flipped += 1
                else:
                    unresolved += 1
            elif len(keys) > 1:
                # 无锚点（新联赛/名称完全变体）：保留字段最全的一条，记为待核
                unresolved += len(keys) - 1
            keep[chosen] = rec
            removed += len(keys) - 1
        tot_before += len(d)
        tot_after += len(keep)
        if len(keep) != len(d):
            detail.append((os.path.basename(f), len(d), len(keep)))
        out[f] = keep

    print(f'\n条目 {tot_before} → {tot_after}（移除孪生 {removed} 条；就地翻转对齐 {flipped} 条）')
    print(f'无法用锚点判定方向的记录 {unresolved} 条（多为名称完全变体，保留字段最全的一条）')
    print('受影响文件数', len(detail), '（前 8）:', detail[:8])

    bad = 0
    for f, keep in out.items():
        for k, rec in keep.items():
            mid = str(rec.get('matchId') or '')
            anchor = by_id.get(mid)
            if anchor and dir_of(rec, k) != anchor:
                bad += 1
                if bad <= 5:
                    print('  ⚠️ 仍与锚点不符:', os.path.basename(f), k, dir_of(rec, k), '锚点', anchor)
    print(f'清理后与锚点方向不符: {bad}')

    if not a.apply:
        print('\n（未写盘，加 --apply 执行）')
        return
    bak = os.path.join(ROOT, '_hist_backup')
    os.makedirs(bak, exist_ok=True)
    for f, keep in out.items():
        path = os.path.join(bak, os.path.basename(f))
        if not os.path.exists(path):
            shutil.copy2(f, path)
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(keep, fh, ensure_ascii=False, indent=2)
    print(f'\n✅ 已写盘，备份在 {bak}')


if __name__ == '__main__':
    main()
