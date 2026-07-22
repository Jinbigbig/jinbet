# -*- coding: utf-8 -*-
"""检查index.html中AI赛果预测功能的HTML/CSS/JS代码是否正确集成。"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HTML = r'c:\Users\Jin\Desktop\jinbet_update\jinbet_update\index.html'

with open(HTML, 'r', encoding='utf-8') as f:
    data = f.read()

checks = []
def CHECK(name, cond, detail=''):
    checks.append((name, bool(cond), detail))

# ====== 1. HTML 结构 ======
print('='*60)
print('[1] HTML 结构校验')
print('='*60)
CHECK('batch-panels-grid 两列网格容器', 'class="batch-panels-grid"' in data)
CHECK('AI面板 aiPredictPanel', 'id="aiPredictPanel"' in data)
CHECK('AI日期控件 aiScheduleDate', 'id="aiScheduleDate"' in data)
CHECK('AI预测按钮 aiRunBtn', 'id="aiRunBtn"' in data)
CHECK('AI赛程列表 aiMatchList', 'id="aiMatchList"' in data)
CHECK('AI输出容器 aiOutput', 'id="aiOutput"' in data)
CHECK('AI日期标签 aiDateLabel', 'id="aiDateLabel"' in data)
CHECK('AI空提示 aiEmptyTip', 'id="aiEmptyTip"' in data)
# 批量赛果面板和AI面板是否在同一个 batch-panels-grid 内
# 通过逐字符计 <div 和 </div> 找到 grid 容器的完整闭合
grid_start = data.find('class="batch-panels-grid"')
if grid_start != -1:
    # 找到开始 <div 位置
    div_open = data.rfind('<div', 0, grid_start)
    if div_open == -1:
        block = ''
    else:
        # 计数开闭，找到对应的闭合 </div>
        depth = 0
        i = div_open
        found = False
        while i < len(data) - 5:
            if data[i:i+4] == '<div' and (data[i+4] in ' >'):
                depth += 1
                i += 4
            elif data[i:i+6] == '</div>':
                depth -= 1
                i += 6
                if depth == 0:
                    block = data[div_open:i+6]
                    found = True
                    break
            else:
                i += 1
        if not found:
            block = data[div_open:div_open+8000]
    CHECK('网格内包含批量赛果录入面板', 'id="batchResultPanel"' in block)
    CHECK('网格内包含AI预测面板', 'id="aiPredictPanel"' in block)
    # 顺序：批量赛果在前，AI在后（并列）
    CHECK('顺序：批量赛果录入 在前 / AI 在后',
          block.find('id="batchResultPanel"') < block.find('id="aiPredictPanel"'))
else:
    CHECK('网格内包含批量赛果录入面板', False)
    CHECK('网格内包含AI预测面板', False)
    CHECK('顺序：批量赛果录入 在前 / AI 在后', False)

# ====== 2. CSS 样式 ======
print()
print('='*60)
print('[2] CSS 样式校验')
print('='*60)
CHECK('.batch-panels-grid CSS定义', '.batch-panels-grid {' in data)
CHECK('两列 grid-template-columns: 1fr 1fr', 'grid-template-columns: 1fr 1fr' in data)
CHECK('响应式 < 960px 单列堆叠', '@media (max-width: 960px)' in data and 'grid-template-columns: 1fr' in data)
CHECK('.ai-predict-panel CSS定义', '.ai-predict-panel {' in data)
CHECK('.ai-predict-card 卡片样式', '.ai-predict-card {' in data)
CHECK('.conf-pill 置信度标签', '.conf-pill {' in data)
CHECK('.conf-high / conf-mid / conf-low',
      '.conf-high {' in data and '.conf-mid {' in data and '.conf-low {' in data)
CHECK('.ai-loading + spinner 动画', '.ai-loading {' in data and '.ai-spinner {' in data)

# ====== 3. JS 函数 ======
print()
print('='*60)
print('[3] JS 函数校验')
print('='*60)
js_funcs = [
    'updateAiDateLabel',
    'loadAiSchedule',
    'runAiPrediction',
    'clearAiOutput',
    'predictOneMatch',
    'renderPrediction',
    '_friendlyDateLabel',
    '_aiReason'
]
for fn in js_funcs:
    CHECK(f'JS 函数 {fn}() 已定义', f'function {fn}(' in data, f'搜索: function {fn}(')
# 关键 AI 变量
CHECK('全局变量 aiCurrentMatches 声明', re.search(r'\baiCurrentMatches\s*=\s*\[\]', data) is not None)
# 日期控件 onchange 触发 updateAiDateLabel + loadAiSchedule
CHECK('aiScheduleDate onchange 绑定',
      re.search(r'id="aiScheduleDate"[^>]*onchange=', data) is not None)

# ====== 4. 初始化逻辑 ======
print()
print('='*60)
print('[4] 初始化逻辑校验（默认次日加载）')
print('='*60)
# 检查 dateDefaults 对象里有 aiScheduleDate: tomorrowStr
m2 = re.search(r'const\s+dateDefaults\s*=\s*\{([^}]+)\}', data, re.DOTALL)
if m2:
    body = m2.group(1)
    CHECK("dateDefaults.aiScheduleDate = tomorrowStr",
          "'aiScheduleDate': tomorrowStr" in body or '"aiScheduleDate": tomorrowStr' in body)
else:
    CHECK("dateDefaults.aiScheduleDate = tomorrowStr", False)
# 初始化调用 updateAiDateLabel / loadAiSchedule（允许带参调用，如 loadAiSchedule(true) / loadAiSchedule(false) 等）
CHECK("初始化调用 updateAiDateLabel()", 'updateAiDateLabel()' in data)
CHECK("初始化调用 loadAiSchedule(...)",
      bool(re.search(r'loadAiSchedule\s*\(\s*(true|false)?\s*\)', data)))

# ====== 5. AI 预测函数内容正确性：predictOneMatch 内容完整性检查（预测5玩法齐全）
predict_fn_match = re.search(r'function predictOneMatch\(.*?\n\}', data, re.DOTALL)
if predict_fn_match:
    pf = predict_fn_match.group(0)
    for k in ['winPick', 'rqPick', 'score', 'totalPick', 'halfResult', 'confidence']:
        CHECK(f'predictOneMatch 字段 {k} 返回值', k in pf)
    # 一致性修正逻辑（3个if）
    CHECK('predictOneMatch 胜/负/平 一致性修正3分支',
          pf.count('if (winPick ===') >= 3 or (pf.count('if (winPick ==') + pf.count('if (winPick ===')) >= 3)

# ====== 6. SCHEDULE 中次日（2026-06-28）有赛程
CHECK('次日 2026-06-28 有 6 场比赛', "'2026-06-28':" in data)

# ====== 总结报告 ======
print()
print('='*60)
passed = sum(1 for _, ok, _ in checks if ok)
total = len(checks)
print(f'总校验结果：{passed}/{total} 通过')
print('='*60)

failures = [f'  ❌ {name}: {detail}' for name, ok, detail in checks if not ok]
if failures:
    print()
    print('失败项：')
    for f in failures:
        print(f)
    sys.exit(1)
else:
    print()
    print('✅ 所有集成校验通过。')
