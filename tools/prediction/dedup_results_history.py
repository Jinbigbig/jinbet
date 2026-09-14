# -*- coding: utf-8 -*-
"""清理 results_history 的镜像重复 + 对齐主客方向到体彩官方锚点。

────────────────────────────────────────────────────────────
背景（2026-09-14 实测，数字均为全库实跑结果）
────────────────────────────────────────────────────────────
1) **跨日孪生**：同一 matchId 在相邻两天的文件里各有一条记录，
   主客互换、比分镜像。v1 版本只在「单个文件内」分组，所以这类
   跨文件的孪生从来没被清掉 —— 全库残留 1531 对。
   哪一侧对？用体彩官方赛果 API 逐场核对：
        孪生「晚副本」反向率  0.3%  ← 正确侧
        孪生「早副本」反向率 99.6%  ← 待删
2) **单条方向错乱**：不重复的单条记录里，**86.8% 也是主客反序的**。
   这不是偶发，而是历史抓取链路的系统性缺陷（网易源反序写入）。
   修正前全库 主胜 35.0% / 客胜 38.6%（客场占优，异常）；
   全部对齐官方后 主胜 42.5% / 平 26.3% / 客胜 31.2%、
   场均 1.57 / 1.28（标准主场优势）。

────────────────────────────────────────────────────────────
判据
────────────────────────────────────────────────────────────
权威锚 = 体彩官方赛果 API
  https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry
按 (matchDate ±2 天, 无序队对) 匹配（队名做 canonical + 前缀兼容，
因两面名称存在「国际图 / 国际图尔」这类截断差异）。
结果缓存到 official_results_cache.json，离线可复用。

处理规则（每个 matchId 一组）：
  · 组内优先保留「与官方同向」的那条；
  · 若选中条为「反向」，就地镜像翻转（key/队名/比分/半场/赔率/让球/比分盘/半全场）;
  · 若官方无此场：同日重复按队名规范性挑一条；跨日的取晚副本（实测 1524/1529）;
  · 其余副本删除。

用法:
  python dedup_results_history.py                  # 只报告，不写盘
  python dedup_results_history.py --apply          # 写盘（先备份 _hist_backup_<日期>/）
  python dedup_results_history.py --apply --no-net # 只用本地缓存锚点（离线）
"""
import argparse
import collections
import datetime
import glob
import importlib.util
import json
import os
import re
import shutil
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, 'official_results_cache.json')
API = ('https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'
       '?matchBeginDate={a}&matchEndDate={b}&leagueId=&pageSize=100&pageNo={p}'
       '&isFix=0&matchPage=1&pcOrWap=1')
HDR = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.sporttery.cn/jc/zqsgkj/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Encoding': 'identity',
    'Origin': 'https://www.sporttery.cn',
}


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_flip = _load_module('_flip_results_lib', os.path.join(ROOT, '_flip_results_lib.py'))
flip_entry = _flip.flip_entry

try:
    _uon = _load_module('_uon_names', os.path.join(ROOT, 'update_odds_net.py'))
    canonical = _uon.canonical_team_name
except Exception as exc:                                   # pragma: no cover
    print(f'⚠️ canonical_team_name 不可用（{exc}），退化为原样比较')
    canonical = lambda n: (n or '').strip()


# ────────────────────────────── 官方锚 ──────────────────────────────
def fetch_official(a, b):
    out = []
    for p in range(1, 12):
        try:
            req = urllib.request.Request(API.format(a=a, b=b, p=p), headers=HDR)
            d = json.loads(urllib.request.urlopen(req, timeout=40).read().decode('utf-8'))
        except Exception as exc:
            print(f'  ⚠️ 官方API {a}~{b} 第{p}页失败: {exc}')
            break
        ms = (d.get('value') or {}).get('matchResult') or []
        out += ms
        if len(ms) < 100:
            break
        time.sleep(0.1)
    return out


def build_official(allow_net=True, lo='2025-12-25', hi='2026-09-10'):
    if os.path.exists(CACHE):
        try:
            rows = json.load(open(CACHE, encoding='utf-8'))
            print(f'官方锚：读缓存 {len(rows)} 场（{CACHE}）')
            return rows
        except Exception:
            pass
    if not allow_net:
        print('官方锚：无缓存且禁网，改用「孪生取晚副本」兜底规则')
        return []
    rows = []
    s = datetime.date.fromisoformat(lo)
    end = datetime.date.fromisoformat(hi)
    while s <= end:
        e = min(s + datetime.timedelta(days=9), end)
        part = fetch_official(s.isoformat(), e.isoformat())
        rows += part
        print(f'  抓取 {s}~{e}: {len(part)} 场')
        s = e + datetime.timedelta(days=1)
    json.dump(rows, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'官方锚：抓取 {len(rows)} 场 → 缓存 {CACHE}')
    return rows


def same_team(x, y):
    if not x or not y:
        return False
    cx = re.sub(r'[\s\-（）()]', '', str(x))
    cy = re.sub(r'[\s\-（）()]', '', str(y))
    return cx == cy or (len(cx) >= 2 and len(cy) >= 2 and (cx.startswith(cy) or cy.startswith(cx)))


class Official:
    def __init__(self, rows):
        self.by_date = collections.defaultdict(list)
        self.by_pair = collections.defaultdict(list)
        for m in rows:
            h, a = m.get('homeTeam'), m.get('awayTeam')
            if not (h and a):
                continue
            self.by_date[(m.get('matchDate'), frozenset((h, a)))].append(m)
            self.by_pair[frozenset((h, a))].append(m)

    def verdict(self, date, home, away):
        """返回 'fwd' / 'rev' / 'none' 与匹配到的官方场次。"""
        try:
            base = datetime.date.fromisoformat(date)
        except Exception:
            base = None
        if base:
            for delta in (0, 1, -1, 2, -2):
                dd = (base + datetime.timedelta(days=delta)).isoformat()
                for m in self.by_date.get((dd, frozenset((home, away))), []):
                    if same_team(m.get('homeTeam'), home) and same_team(m.get('awayTeam'), away):
                        return 'fwd', m
                    if same_team(m.get('homeTeam'), away) and same_team(m.get('awayTeam'), home):
                        return 'rev', m
        return 'none', None


# ────────────────────────────── 工具 ──────────────────────────────
def has_real_score(rec):
    s = rec.get('fullScore') or rec.get('score') or ''
    return isinstance(s, str) and ':' in s and all(p.strip().isdigit() for p in s.split(':', 1))


def richness(rec):
    return sum(1 for f in ('胜', '平', '负', 'hda胜', '让球', '比分', '总进球', '半全场') if rec.get(f))


def raw_is_canonical(rec):
    h, a = rec.get('home'), rec.get('away')
    return int(bool(h) and bool(a) and canonical(h) == h and canonical(a) == a)


def parse_score(s):
    try:
        h, a = str(s).replace('：', ':').split(':')[:2]
        return int(h), int(a)
    except Exception:
        return None


def dist(records, label):
    c = collections.Counter()
    for rec in records:
        p = parse_score(rec.get('fullScore') or rec.get('score'))
        if not p:
            continue
        h, a = p
        c['H' if h > a else ('A' if h < a else 'D')] += 1
        c['gf'] += h
        c['ga'] += a
        c['n'] += 1
    n = c['n'] or 1
    print(f'    {label:<16} n={c["n"]:<5} 主胜{c["H"] / n:6.1%} 平{c["D"] / n:6.1%} '
          f'客胜{c["A"] / n:6.1%}  场均{c["gf"] / n:.2f}/{c["ga"] / n:.2f}')


# ────────────────────────────── 主流程 ──────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--no-net', action='store_true')
    args = ap.parse_args()

    off = Official(build_official(allow_net=not args.no_net))

    files = [f for f in sorted(glob.glob(os.path.join(ROOT, 'results_history', '*.json')))
             if os.path.basename(f) != 'index.json']
    groups = collections.defaultdict(list)          # matchId -> [(path, key, rec)]
    for f in files:
        d = json.load(open(f, encoding='utf-8'))
        for k, rec in d.items():
            if not isinstance(rec, dict):
                continue
            mid = str(rec.get('matchId') or '').strip() or f'__{os.path.basename(f)}__{k}'
            groups[mid].append((f, k, rec))

    before = sum(len(v) for v in groups.values())
    out = {f: {} for f in files}
    stat = collections.Counter()
    flipped_rows = []
    unresolved = []
    collisions = []
    picked_rows = []

    for mid, items in groups.items():
        items = sorted(items, key=lambda x: x[0])
        dates = set(os.path.basename(p)[:-5] for p, _, _ in items)
        same_day = len(dates) == 1
        verdicts = [(p, k, rec) + off.verdict(os.path.basename(p)[:-5], rec.get('home'), rec.get('away'))
                    for p, k, rec in items]

        fwd = [x for x in verdicts if x[3] == 'fwd']
        if fwd:
            # 有官方同向：优先取「字段最全 / 有真实比分」的那条
            chosen = max(fwd, key=lambda x: (has_real_score(x[2]), richness(x[2])))
            stat['留存-与官方同向'] += 1
        elif len(items) > 1 and not same_day:
            chosen = verdicts[-1]                   # 跨日无官方 → 取晚副本（实测 1524/1529）
            stat['留存-无官方取晚副本'] += 1
        else:
            chosen = max(verdicts,
                         key=lambda x: (raw_is_canonical(x[2]), has_real_score(x[2]), richness(x[2])))
            stat['留存-同日按规范性' if same_day and len(items) > 1 else '留存-单条'] += 1

        p, k, rec, v, _m = chosen
        if v == 'rev':
            k2, rec2 = flip_entry(k, rec)
            flipped_rows.append((mid, k, k2))
            rec = rec2
            k = k2
            stat['翻转对齐官方'] += 1
        elif v == 'none':
            stat['无官方-原样保留'] += 1
            why = ('单条无官方' if len(items) == 1
                   else ('同日重复无官方' if same_day else '跨日无官方'))
            unresolved.append((mid, why, k, ''))

        for _p, _k, _r, _v, _m in verdicts:
            if (_p, _k) != (p, chosen[1]):
                stat['删除冗余'] += 1
        if k in out[p]:
            _old = out[p][k]
            stat['键碰撞-合并'] += 1
            collisions.append((p, k, _old, rec))
        out[p][k] = rec
        picked_rows.append(rec)

    after = sum(len(v) for v in out.values())
    print()
    print('=' * 68)
    print(f'记录 {before} → {after}（删除 {before - after} 条冗余；翻转 {len(flipped_rows)} 条对齐官方）')
    print('=' * 68)
    for k, n in stat.most_common():
        print(f'  {k}: {n}')
    print()
    print('胜平负分布对照：')
    dist([r for v in groups.values() for _, _, r in v], '原始')
    dist(picked_rows, '清理后')

    if unresolved:
        cnt = collections.Counter(w for _, w, _, _ in unresolved)
        print(f'\n无官方锚的组 {len(unresolved)} 个（保留原方向，样例）：')
        print('   分类:', dict(cnt))
        for mid, why, k1, k2 in unresolved[:6]:
            print(f'   {mid} [{why}] {k1}' + (f'  |  {k2}' if k2 else ''))
    if flipped_rows:
        print('\n翻转样例（前 8）：')
        for mid, k1, k2 in flipped_rows[:8]:
            print(f'   {k1}  →  {k2}')
    if collisions:
        print(f'\n⚠️ 键碰撞 {len(collisions)} 处（两条记录归一后落同一 key，已合并）：')
        for p, k, old, new in collisions[:6]:
            print(f'   {os.path.basename(p)} {k}: 保留 {new.get("home")} vs {new.get("away")} '
                  f'{new.get("fullScore")} | 覆盖 {old.get("home")} vs {old.get("away")} {old.get("fullScore")}')

    changed = sum(1 for f in files
                  if set(out[f]) != set(json.load(open(f, encoding='utf-8'))))
    print(f'\n受影响文件 {changed} / {len(files)}')

    if not args.apply:
        print('\n（未写盘，加 --apply 执行）')
        return

    bak = os.path.join(ROOT, f'_hist_backup_{datetime.date.today().isoformat()}')
    os.makedirs(bak, exist_ok=True)
    for f in files:
        dst = os.path.join(bak, os.path.basename(f))
        if not os.path.exists(dst):
            shutil.copy2(f, dst)
    for f in files:
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump({k: out[f][k] for k in sorted(out[f])}, fh, ensure_ascii=False, indent=2)
    print(f'\n✅ 已写盘 {len(files)} 个文件，备份 → {bak}')


if __name__ == '__main__':
    main()
