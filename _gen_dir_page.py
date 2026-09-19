# -*- coding: utf-8 -*-
"""生成 1X2 方向命中逐场明细页（可核对清单）。"""
import os, json, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, '_dir_rows.json'), encoding='utf-8'))
CN = {'home': '主胜', 'draw': '平局', 'away': '客胜'}
SZ = {'home': '胜', 'draw': '平', 'away': '负'}

days = []
for r in rows:
    if not days or days[-1][0] != r['date']:
        days.append((r['date'], []))
    days[-1][1].append(r)

n = len(rows)
hit = sum(r['hit'] for r in rows)
wk = '一二三四五六日'


def cls(r):
    return 'ok' if r['hit'] else 'bad'


def blocks(date, rs):
    out = []
    h = sum(x['hit'] for x in rs)
    out.append('<div class="day"><div class="dhead"><span class="dt">%s</span>'
               '<span class="ds">%d / %d 命中<span class="pct">%.0f%%</span></span></div><table>' %
               (date, h, len(rs), h / len(rs) * 100))
    out.append('<thead><tr><th>联赛</th><th>对阵</th><th>预测倾向</th><th>实际比分</th><th>实际</th><th>核对</th></tr></thead><tbody>')
    for r in rs:
        pre = '%s <i>%.0f%%</i>' % (CN[r['pick']], r['marg'])
        if r['pick'] != r['actual']:
            pre += '<em class="wag">（实际%s）</em>' % SZ[r['actual']]
        out.append('<tr class="%s"><td class="lg">%s</td><td class="mt">%s <span class="vs">vs</span> %s</td>'
                   '<td>%s</td><td class="sc">%s</td><td>%s</td><td class="mk">%s</td></tr>' %
                   (cls(r), r['lg'], r['home'], r['away'], pre, r['score'], CN[r['actual']],
                    '✓' if r['hit'] else '✗'))
    out.append('</tbody></table></div>')
    return ''.join(out)


pk = [r for r in rows if r['pick'] == 'home']
dr = [r for r in rows if r['pick'] == 'draw']
aw = [r for r in rows if r['pick'] == 'away']
act = {k: [r for r in rows if r['actual'] == k] for k in ('home', 'draw', 'away')}
b50 = [r for r in rows if r['marg'] >= 50]
b40 = [r for r in rows if 40 <= r['marg'] < 50]
b30 = [r for r in rows if r['marg'] < 40]

HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>方向（1X2）命中逐场核对 · 近 10 天</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f4f6fa;color:#1c2331;font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:23px;margin:0 0 6px}
.sub{color:#68738a;font-size:13px;margin-bottom:22px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:26px}
.card{background:#fff;border:1px solid #e3e8f0;border-radius:12px;padding:14px 16px}
.card .k{font-size:12px;color:#68738a;margin-bottom:4px}
.card .v{font-size:22px;font-weight:700;letter-spacing:-.5px}
.card .n{font-size:12px;color:#8a94a8}
.red{color:#d92b3a}.gray{color:#8a94a8}
h2{font-size:16px;margin:26px 0 10px;padding-left:10px;border-left:3px solid #2f6fed}
table{width:100%%;border-collapse:collapse;background:#fff}
th{background:#eef2f9;color:#48536b;font-size:12px;font-weight:600;text-align:left;padding:8px 10px;white-space:nowrap}
td{padding:8px 10px;border-top:1px solid #eef1f6;font-size:13px;vertical-align:top}
tr.bad td{background:#fff7f7}
tr.ok td{background:#fff}
.mk{font-weight:700;text-align:center;width:44px}
tr.ok .mk{color:#12805c}tr.bad .mk{color:#d92b3a}
.lg{color:#68738a;font-size:12px;white-space:nowrap}
.mt{font-weight:600}
.vs{color:#aab3c5;font-weight:400;font-size:12px}
.sc{font-family:ui-monospace,Consolas,monospace;font-weight:700}
i{font-style:normal;color:#8a94a8;font-size:12px}
em.wag{font-style:normal;color:#c9821a;font-size:12px}
.day{margin-bottom:18px;border:1px solid #e3e8f0;border-radius:12px;overflow:hidden}
.dhead{display:flex;justify-content:space-between;align-items:center;background:#fff;padding:10px 14px;border-bottom:1px solid #eef1f6}
.dt{font-weight:700}
.ds{font-size:13px;color:#48536b}
.pct{display:inline-block;margin-left:8px;background:#eaf1ff;color:#2f6fed;border-radius:6px;padding:1px 7px;font-weight:600;font-size:12px}
.day table th{background:#fbfcfe}
.note{background:#eef4ff;border:1px solid #d6e3ff;border-radius:10px;padding:14px 16px;font-size:13px;color:#2b3a55;margin:20px 0}
.note b{color:#1c2331}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:700px){.cards{grid-template-columns:repeat(2,1fr)}.g2{grid-template-columns:1fr}}
ul{margin:6px 0 0 18px;padding:0}li{margin:3px 0}
</style></head><body><div class="wrap">
<h1>方向（1X2）命中逐场核对</h1>
<div class="sub">窗口 2026-09-08 → 2026-09-17 · 共 %(n)d 场 · 口径：胜平负三项中取概率最大者，与实际比分比较（不含让球）</div>

<div class="cards">
  <div class="card"><div class="k">方向命中</div><div class="v">%(hit)d / %(n)d</div><div class="n">%(rate).1f%%</div></div>
  <div class="card"><div class="k">按预测方向</div><div class="v">%(pk)d 主 · %(dr)d 平 · %(aw)d 客</div><div class="n">模型几乎不报平局</div></div>
  <div class="card"><div class="k">实际打出平局</div><div class="v">%(actd)d 场</div><div class="n">只抓到 %(actd_hit)d 场</div></div>
  <div class="card"><div class="k">把握 ≥50%%</div><div class="v">%(b50_hit)d / %(b50)d</div><div class="n">%(b50_r).1f%%（40~50%% 档仅 %(b40_r).1f%%）</div></div>
</div>

<h2>错在哪里（60 场错判的结构）</h2>
<div class="note">
<b>1. 平局是最大失血点。</b>实际打出平局 <b>%(actd)d 场</b>，而模型全窗口只报出 <b>%(dr)d 场</b>平局（对 %(actd_hit)d 场）——
即这 %(actd)d 场平局里 <b>%(actd_miss)d 场</b>被判成了胜负。这 %(actd_miss)d 场已占全部 %(nmiss)d 场错判的 <b>%(share).0f%%</b>。<br>
<b>2. 低把握场次方向不可信。</b>最大概率在 40%%~50%% 的 <b>%(b40)d 场</b>，命中率只有 <b>%(b40_r).1f%%</b>（低于抛硬币）；
≥50%% 的 <b>%(b50)d 场</b>命中 <b>%(b50_r).1f%%</b>；&lt;40%% 的 %(b30)d 场为 %(b30_r).1f%%。<br>
<b>3. 只看「谁赢」其实是 %(nnp)s。</b>剔除平局后 %(nnpn)d 场非平局比赛里方向对了 %(nnph)d 场（%(acc2).1f%%）—— 判断谁赢比判断会不会平容易得多。
</div>

<h2>逐日核对（每天对/错场次，红底=错判）</h2>
%(days)s

<h2>按预测方向 / 按实际结果的拆解</h2>
<div class="g2">
<div><table><thead><tr><th>预测倾向</th><th>场次</th><th>命中</th><th>命中率</th></tr></thead><tbody>
<tr><td>主胜</td><td>%(_pk)d</td><td>%(_pkh)d</td><td>%(_pkr).1f%%</td></tr>
<tr><td>平局</td><td>%(_dr)d</td><td>%(_drh)d</td><td>%(_drr).1f%%</td></tr>
<tr><td>客胜</td><td>%(_aw)d</td><td>%(_awh)d</td><td>%(_awr).1f%%</td></tr>
</tbody></table></div>
<div><table><thead><tr><th>实际结果</th><th>场次</th><th>被猜中</th><th>召回率</th></tr></thead><tbody>
<tr><td>主胜</td><td>%(_ah)d</td><td>%(_ahh)d</td><td>%(_ahr).1f%%</td></tr>
<tr><td>平局</td><td>%(_ad)d</td><td>%(_adh)d</td><td>%(_adr).1f%%</td></tr>
<tr><td>客胜</td><td>%(_aa)d</td><td>%(_aah)d</td><td>%(_aar).1f%%</td></tr>
</tbody></table></div>
</div>

<div class="note" style="margin-top:22px">
长期基准对照（2478 场 walk-forward）：1X2 方向 <b>51.2%%</b>，纯市场去水 <b>51.9%%</b>。本窗口 60.5%% 属于偏高的样本，
不是模型变好；同样口径下窗口内 <b>52 场</b>有赔率的比赛，纯市场去水命中 <b>73.1%%</b>、模型 <b>65.4%%</b>，且两者同选 <b>92.3%%</b> —— 方向能力与市场基本重合。
</div>
</div></body></html>"""

miss = [r for r in rows if not r['hit']]
actd_miss = len([r for r in act['draw'] if not r['hit']])
nonp = [r for r in rows if r['actual'] != 'draw']
nonp_hit = sum(r['hit'] for r in nonp)


def rate(a, b):
    return a / max(1, b) * 100


body = ''.join(blocks(d, rs) for d, rs in days)
out = HTML % dict(
    n=n, hit=hit, rate=rate(hit, n), pk=len(pk), dr=len(dr), aw=len(aw),
    actd=len(act['draw']), actd_hit=sum(r['hit'] for r in act['draw']), actd_miss=actd_miss,
    nmiss=len(miss), share=actd_miss / max(1, len(miss)) * 100,
    b50=len(b50), b50_hit=sum(r['hit'] for r in b50), b50_r=rate(sum(r['hit'] for r in b50), len(b50)),
    b40=len(b40), b40_r=rate(sum(r['hit'] for r in b40), len(b40)),
    b30=len(b30), b30_r=rate(sum(r['hit'] for r in b30), len(b30)),
    nnp='%d/%d' % (nonp_hit, len(nonp)), acc2=rate(nonp_hit, len(nonp)),
    nnpn=len(nonp), nnph=nonp_hit,
    _pk=len(pk), _pkh=sum(r['hit'] for r in pk), _pkr=rate(sum(r['hit'] for r in pk), len(pk)),
    _dr=len(dr), _drh=sum(r['hit'] for r in dr), _drr=rate(sum(r['hit'] for r in dr), len(dr)),
    _aw=len(aw), _awh=sum(r['hit'] for r in aw), _awr=rate(sum(r['hit'] for r in aw), len(aw)),
    _ah=len(act['home']), _ahh=sum(r['hit'] for r in act['home']), _ahr=rate(sum(r['hit'] for r in act['home']), len(act['home'])),
    _ad=len(act['draw']), _adh=sum(r['hit'] for r in act['draw']), _adr=rate(sum(r['hit'] for r in act['draw']), len(act['draw'])),
    _aa=len(act['away']), _aah=sum(r['hit'] for r in act['away']), _aar=rate(sum(r['hit'] for r in act['away']), len(act['away'])),
    days=body,
)
open(os.path.join(HERE, 'diag_dir_2026-09-18.html'), 'w', encoding='utf-8').write(out)
print('写出 diag_dir_2026-09-18.html', len(out))

# 供回复使用：逐日命中场次清单
for d, rs in days:
    hits = [r for r in rs if r['hit']]
    print()
    print('【%s】%d/%d' % (d, len(hits), len(rs)))
    print('  对：' + '、'.join('%s(%s %.0f%%)' % (r['home'] if r['pick'] == 'home' else (r['away'] if r['pick'] == 'away' else r['home'] + '平'),
                              SZ[r['actual']], r['marg']) for r in hits))
    bad = [r for r in rs if not r['hit']]
    print('  错：' + '、'.join('%s vs %s(预测%s→实际%s %s)' % (r['home'], r['away'], SZ[r['pick']], SZ[r['actual']], r['score']) for r in bad))
