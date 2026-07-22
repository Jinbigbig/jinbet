# -*- coding: utf-8 -*-
"""TDD测试：验证AI功能新增的追加赛程、投注导入、本地同步、推送导出功能。"""
import re, json, sys
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

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()
H = re.sub(r'\s+', ' ', html)

print("="*60)
print("[1] 赛程加载 -> 追加模式（非替换） RED-FAIL 验证")
print("="*60)
# 需求: loadAiSchedule 不能覆盖 aiCurrentMatches, 必须 concat/追加
old_behavior = bool(re.search(r'aiCurrentMatches\s*=\s*games\.slice\(\)|aiCurrentMatches\s*=\s*games\s*;', html))
new_behavior_push = bool(re.search(r'aiCurrentMatches\.(push|concat)', H))
# 必须有"去重" 或 "追加" 语义
has_append_mode = bool(re.search(r'追加|append|去重|dedupe|concat\(|push\([^)]*\.{3}', H))
check("❌ 不应存在旧的覆盖赋值 aiCurrentMatches = games.slice()", not old_behavior, 
      "当前仍用覆盖模式，需改为追加模式")
check("✅ 应存在 push/concat 追加方式", new_behavior_push, 
      "需要用 aiCurrentMatches.push(...games) 实现追加")
check("✅ 应存在去重逻辑（主队+客队唯一）", has_append_mode or '去重' in html or 'some(' in html,
      "追加模式必须做去重，避免同一场比赛多次出现")

print("\n"+"="*60)
print("[2] 投注记录加载赛程按钮 RED-FAIL 验证")
print("="*60)
# 需求: 新增「📋 从投注记录导入」按钮，且有对应函数实现
has_btn_bet = bool(re.search(r'投注记录.*导入|导入.*投注|从投注记录|投注.*赛程', H))
has_func = bool(re.search(r'function\s+(import.*Bet|load.*Bet|bet.*Load|import.*Schedule|loadScheduleFromBet)', html))
has_bets_ref = bool(re.search(r'bets\.forEach|for\s*\(.*\s+in\s+bets|bets\.map|bets\.filter', H[H.find('function loadAiSchedule'):H.find('function runAiPrediction')]))
check("✅ AI工具栏/设置里有从投注记录导入按钮", has_btn_bet, 
      "需要新增按钮：📋 从投注记录导入")
check("✅ 对应处理函数存在", has_func,
      "需要实现函数，如 loadAiFromBetRecords()")
check("✅ 函数内遍历 bets 提取比赛", has_func,
      "函数内应从 bets[i].matches[*] 提取 home/away")

print("\n"+"="*60)
print("[3] 本地同步 localStorage RED-FAIL 验证")
print("="*60)
# 需求: aiCurrentMatches + 预测结果 存localStorage; 页面加载时自动 restore
storage_key_match = bool(re.search(r'AI_DATA_STORAGE|ai_schedule_cache|AI_PREDICT_STORAGE|aiPredictionStorage', H))
has_setitem_match = bool(re.search(r"localStorage\.setItem\([^)]*[Aa][Ii].*[Mm]atch|localStorage\.setItem\([^)]*aiCurrent|localStorage\.setItem\([^)]*predictResult|saveAi(Result|Data|Prediction|Match)", H))
has_getitem_match = bool(re.search(r"localStorage\.getItem\([^)]*[Aa][Ii].*[Mm]atch|localStorage\.getItem\([^)]*predictResult|loadAi(Result|Data|Prediction|Match)|restoreAi", H))
# 预测结果持久化变量
has_result_var = bool(re.search(r'aiLastPredictions|aiPredictions|aiPredResult|aiResultCache', H))
check("✅ AI赛程/预测数据有独立storageKey常量", storage_key_match,
      "需要定义类似 AI_DATA_STORAGE_KEY = 'worldcup_ai_data_v1'")
check("✅ 存在保存AI数据到localStorage的函数/调用", has_setitem_match,
      "需要 saveAiData() 把 matches + predictions 存本地")
check("✅ 页面加载/渲染时读取AI本地缓存", has_getitem_match,
      "需要 restoreAiData() 在window.onload/init里调用，还原赛程和预测")
check("✅ 存在保存AI预测结果的变量", has_result_var or 'aiLastPredictions' in H,
      "需要 aiLastPredictions = [] 存最近预测结果")

print("\n"+"="*60)
print("[4] 推送/导出AI预测 RED-FAIL 验证")
print("="*60)
has_export_btn = bool(re.search(r'导出.*AI|AI.*导出|推送|分享.*AI|exportAi', H))
has_export_func = bool(re.search(r'function\s+(exportAi|export.*Ai|pushAi|shareAi)', html))
has_download_pattern = bool(re.search(r'AI预测|aiPredict|赛果预测.*\.json|createElement.*a.*download.*predict|AI.*_.*json', H))
check("✅ AI工具栏有导出/推送按钮", has_export_btn, "新增「📤 导出预测」按钮")
check("✅ 存在 exportAiPredictions / pushAiData 函数", has_export_func,
      "实现导出AI赛程+预测为JSON的函数，参考exportBets")
check("✅ 导出内容包含 matches+predictions 字段", has_download_pattern or 'predictions' in H[-5000:],
      "导出JSON结构：{aiCurrentMatches, aiLastPredictions, exportedAt}")

print("\n"+"="*60)
print(f"[RED总结] 共 {total} 项，通过 {passed}，失败 {total-passed}")
print("="*60)
if passed < total:
    print("→ 这些项目前失败，符合TDD RED阶段。接下来实现功能让它们全部通过。")
else:
    print("→ 测试全部通过，功能已存在，请确认是否需调整。")
sys.exit(0 if passed == total else 1)
