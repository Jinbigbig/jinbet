# -*- coding: utf-8 -*-
"""TDD测试：验证AI工具栏移除了「覆盖加载」和「导出推送」按钮。"""
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

# 提取 AI 工具栏（ai-toolbar 整个 div 块）
toolbar_match = re.search(r'<div class="ai-toolbar"[^>]*>([\s\S]*?)</div>', html, re.IGNORECASE)
tb_html = toolbar_match.group(1) if toolbar_match else ''
# AI 面板：工具栏 + 其外的按钮（aiPredictPanel 内到 aiMatchList 之前）
panel_html = tb_html

print("[1] AI工具栏结构 RED - 不应存在的按钮")
# 需求: AI 工具栏里，用户说"不需要覆盖加载日期，也不需要导出"
# 即 AI 工具栏里不能有以下 2 个按钮：
#   (1) onclick=loadAiSchedule(true)   → 覆盖加载
#   (2) onclick=exportAiPredictions()  → 导出推送
# 同时也不应该显示 "覆盖加载" 或 "导出推送" 文字
has_cover_btn_in_panel = bool(re.search(r'onclick\s*=\s*"loadAiSchedule\s*\(\s*true\s*\)"', panel_html))
has_cover_txt_in_panel = bool(re.search(r'覆盖加载', panel_html))
has_export_btn_in_panel = bool(re.search(r'onclick\s*=\s*"exportAiPredictions\s*\(\s*\)"', panel_html))
has_export_txt_in_panel = bool(re.search(r'导出推送', panel_html))
check("❌ AI工具栏不应有 loadAiSchedule(true) 覆盖加载按钮", not has_cover_btn_in_panel,
      f"当前按钮仍存在: btn={has_cover_btn_in_panel} txt={has_cover_txt_in_panel}")
check("❌ AI工具栏不应出现「覆盖加载」文字", not has_cover_txt_in_panel)
check("❌ AI工具栏不应有 exportAiPredictions() 导出推送按钮", not has_export_btn_in_panel,
      f"当前按钮仍存在: btn={has_export_btn_in_panel} txt={has_export_txt_in_panel}")
check("❌ AI工具栏不应出现「导出推送」文字", not has_export_txt_in_panel)

print("\n[2] AI工具栏应保留的按钮（RED不应该提前不存在）")
# 保留：📅 加载赛程(追加) / 📋 投注导入 / 🚀 开始预测 / 🗑 清空
keep1 = bool(re.search(r'onclick\s*=\s*"loadAiSchedule\s*\(\s*false\s*\)"', panel_html))
keep2 = bool(re.search(r'onclick\s*=\s*"loadAiFromBetRecords\s*\(\s*\)"', panel_html))
keep3 = bool(re.search(r'id\s*=\s*"aiRunBtn"', panel_html))
keep4 = bool(re.search(r'onclick\s*=\s*"clearAiData\s*\(', panel_html)) or bool(re.search(r'onclick\s*=\s*"clearAiOutput\s*\(', panel_html))
check("✅ 保留：📅 加载赛程(loadAiSchedule(false)追加)", keep1, "应保留追加模式按钮")
check("✅ 保留：📋 投注导入", keep2)
check("✅ 保留：🚀 开始预测(aiRunBtn)", keep3)
check("✅ 保留：🗑 清空按钮", keep4)

print("\n[3] AI工具栏按钮总数 RED")
# 预期 4 个按钮在 ai-toolbar 内： 加载赛程 / 投注导入 / 开始预测 / 清空
btns = re.findall(r'<button[^>]*onclick\s*=\s*"[^"]+"', tb_html, re.IGNORECASE)
onclicks = [re.search(r'onclick="([^"]+)"', b).group(1) for b in btns] if len(btns) <= 10 else [f'{len(btns)}个']
check(f"✅ AI工具栏按钮数=4（当前{len(btns)}个 {onclicks}）", len(btns) == 4)

print(f"\nRED总结: {passed}/{total} 通过（当前修改前应多数失败）")
sys.exit(0 if passed == total else 1)
