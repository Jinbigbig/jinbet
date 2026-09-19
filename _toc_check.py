# -*- coding: utf-8 -*-
"""校验报告完整性（结构配平 + 导航注入 + 无 IDE 注入）。"""
import re

P = 'predictions/2026-09-13/index.html'
s = open(P, encoding='utf-8').read()
out = []

out.append('=== 结构配平 ===')
for tag in ('div', 'table', 'nav', 'ul', 'li'):
    o = len(re.findall(r'<%s[ >]' % tag, s))
    c = s.count('</%s>' % tag)
    out.append('  %-6s 开 %4d / 闭 %4d  %s' % (tag, o, c, 'OK' if o == c else '!! 不配平'))

out.append('')
out.append('=== 导航注入 ===')
for k in ('id="tocNav"', 'id="tocList"', 'id="tocToggle"', 'toc-mask', 'scroll-margin-top', '--toc-w'):
    out.append('  %-22s %d' % (k, s.count(k)))
out.append('  nav 在 body 内: %s' % (s.find('id="tocNav"') < s.rfind('</body>')))

out.append('')
out.append('=== 章节完整性 ===')
for k in ('大胆档', '今日比分精选', '联赛形势', '串关', '逐场深度分析', '预测汇总'):
    out.append('  %-12s %d' % (k, s.count(k)))

out.append('')
out.append('=== IDE 注入 ===')
out.append('  data-page-node-id: %d' % s.count('data-page-node-id'))

txt = '\n'.join(out)
open('_toc_check.txt', 'w', encoding='utf-8').write(txt)
print(txt)
