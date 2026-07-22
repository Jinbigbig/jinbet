# -*- coding: utf-8 -*-
"""TDD测试：验证赛程加载时默认追加到现有赛程，而不是替换。"""
import re, sys
sys.stdout.reconfigure(encoding='utf-8')

total = 0; passed = 0
def check(name, cond, detail=''):
    global total, passed
    total += 1
    if cond:
        passed += 1
        print(f"  [PASS #{total}] {name}")
    else:
        print(f"  [FAIL #{total}] {name}  {detail}")

with open('index.html','r',encoding='utf-8') as f:
    html = f.read()
H = re.sub(r'\s+',' ',html)

print("[1] 添加投注模态框按钮 - 双按钮（追加/覆盖）RED")
# 当前只有 1 个 "📅 加载赛程"，必须变成 2 个
count_single = len(re.findall(r'onclick\s*=\s*"loadSchedule\(\)"', html))
count_dual = len(re.findall(r'loadSchedule\((?:true|false)\)', html))
has_append_btn = ('追加加载' in html[:50000] and 'loadSchedule(false)' in html[:50000]) or ('追加加载' in H[:100000] and 'loadSchedule(false)' in H[:100000])
has_overwrite_btn = ('覆盖加载' in html[:50000] and 'loadSchedule(true)' in html[:50000]) or ('覆盖加载' in H[:100000] and 'loadSchedule(true)' in H[:100000])
# schedule-loader (添加记录的) 内不应只有"加载赛程"单一按钮
# scheduleDate 所在的 schedule-loader 里的按钮数量
# 用正则提取 schedule-loader 内部按钮
m = re.search(r'<div class="schedule-loader">(.*?)</div>', html, re.DOTALL)
sched_html = m.group(1) if m else ''
btn_cnt_in_sched = len(re.findall(r'<button[^>]*onclick="loadSchedule', sched_html))
check(f"❌ 不应只有1个loadSchedule()无参按钮（当前{count_single}）", count_single == 0,
      "需要拆成 loadSchedule(false)追加 / loadSchedule(true)覆盖 两个按钮")
check("✅ 添加投注模态框里应有 loadSchedule(false) 追加按钮", count_dual >= 2 and 'loadSchedule(false)' in sched_html,
      "在 schedule-loader 内加入 追加加载 / 覆盖加载 按钮")
check("✅ 添加投注模态框里应有 loadSchedule(true) 覆盖按钮", 'loadSchedule(true)' in sched_html,
      "保留覆盖加载模式供特殊场景使用")

print("\n[2] loadSchedule 函数 - 支持 overwrite 参数 + 追加去重逻辑 RED")
# 旧行为: container.innerHTML = '' 必触发，必须在 overwrite=true 才清空
fn_block = re.search(r'function\s+loadSchedule\s*\(\s*(\w+)?\s*\)\s*\{([\s\S]*?)\n\}\s*//\s*=', html)
if not fn_block:
    # 找从 function loadSchedule 起直到下一个 "// ======"
    i = html.find('function loadSchedule(')
    end = html.find('\n// ======\n//  打开/编辑模态框', i) if i>0 else -1
    fn_body = html[i:end] if i>0 and end>i else ''
else:
    fn_body = fn_block.group(0)
has_param = bool(re.search(r'function\s+loadSchedule\s*\(\s*\w+\s*\)', html)) or 'overwrite' in fn_body[:200]
has_cond_clear = 'if (overwrite === true)' in fn_body or 'if (overwrite)' in fn_body or 'overwrite == true' in fn_body[:600]
# 追加逻辑应调用 addGameRow 追加（而不是清空后再addGameRow）且有去重（判断 home+away 已存在）
has_dedupe = ('game-home' in fn_body and 'querySelectorAll' in fn_body) or '_dedupeGames' in fn_body or 'existing' in fn_body
check(f"✅ loadSchedule 函数签名接收参数", has_param, "需要变成 function loadSchedule(overwrite) {...}")
check("✅ container.innerHTML='' 仅在 overwrite=true 时执行（条件清空）", has_cond_clear,
      "无条件清空=覆盖模式，必须改为：if (overwrite===true) 才清空")
check("✅ 追加模式下做去重（从UI读取已有比赛，跳过重复）", has_dedupe,
      "需要从 gameListContainer 遍历已有 .game-home/.game-away 做 Set 去重")

print(f"\nRED总结: {passed}/{total} 通过")
sys.exit(0 if passed == total else 1)
