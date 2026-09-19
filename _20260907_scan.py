import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
t = open(r'predictions/2026-09-06/index.html', encoding='utf-8').read()
lines = t.split('\n')
keys = ['目录', 'nav', 'href="#', 'summary-grid', 'footer', 'Footer', 'mark-', '四、', '五、', '六、', 'id="', 'data-updated', 'abs', '准入', '积分榜', '晋级', '赛程']
for i, l in enumerate(lines):
    s = l.strip()
    if len(s) > 220:
        s = s[:220]
    if any(k in s for k in keys):
        print(i, s)
