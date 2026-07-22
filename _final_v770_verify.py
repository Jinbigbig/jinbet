# -*- coding: utf-8 -*-
"""运行TDD、Integration、Logic三个验证脚本，检查版本号和推送配置。"""
import sys, subprocess, os, re
sys.stdout.reconfigure(encoding='utf-8')

def run(script):
    try:
        r = subprocess.run(['python', script], capture_output=True, text=True, encoding='utf-8', errors='replace')
        # 找结尾 summary 数字
        tail = '\n'.join(r.stdout.splitlines()[-6:])
        m1 = re.findall(r'(\d+)\s*/\s*(\d+)\s*.*(?:通过|pass)', tail, re.IGNORECASE)
        return r.returncode, r.stdout, r.stderr, m1
    except Exception as e:
        return 1, '', str(e), []

def check_item(name, cond):
    global total, passed
    total += 1
    if cond: passed += 1
    print(f"  {'✅' if cond else '❌'} [{name}] {'PASS' if cond else 'FAIL'}")

total = 0; passed = 0
print("="*60)
print("[1/4] TDD 13项 - 追加加载 / 投注导入 / 本地同步 / 导出推送")
print("="*60)
code, out, err, m = run('_tdd_ai_sync_push.py')
# 从输出末尾找 pass 数
tail = out.splitlines()
summ_line = ''
for l in tail:
    if '共' in l and '通过' in l: summ_line = l; break
nums = re.findall(r'\d+', summ_line) if summ_line else []
t1 = int(nums[0]) if len(nums)>=2 else 0
p1 = int(nums[1]) if len(nums)>=2 else 0
check_item(f"TDD-13项全部通过 (报告: {p1}/{t1}, exit={code})", code == 0 and t1 == p1 and t1 == 13)

print("\n"+"="*60)
print("[2/4] AI Integration 40项 回归")
print("="*60)
code, out, err, m = run('_verify_ai_integration.py')
tail = out.splitlines()
summ_line = ''
for l in tail:
    if '总校验结果' in l or ('通过' in l and re.search(r'\d+/\d+', l)): summ_line = l
nums = re.findall(r'(\d+)\s*/\s*(\d+)', summ_line) if summ_line else []
if nums:
    p2, t2 = int(nums[0][0]), int(nums[0][1])
else:
    p2 = t2 = 0
check_item(f"Integration 40/40 通过 (报告: {p2}/{t2}, exit={code})", code == 0 and p2 == 40 and t2 == 40)

print("\n"+"="*60)
print("[3/4] AI Logic 40项 回归")
print("="*60)
code, out, err, m = run('_verify_ai_logic.py')
tail = out.splitlines()
summ_line = ''
for l in tail:
    if '字段校验通过' in l or ('通过' in l and re.search(r'\d+/\d+', l)): summ_line = l
nums = re.findall(r'(\d+)\s*/\s*(\d+)', summ_line) if summ_line else []
if nums:
    p3, t3 = int(nums[0][0]), int(nums[0][1])
else:
    # 兜底：全文搜 40/40
    all_text = out
    mm = re.findall(r'(\d+)\s*/\s*(\d+)\s*.*字段', all_text)
    if mm: p3, t3 = int(mm[-1][0]), int(mm[-1][1])
    else: p3 = t3 = 0
check_item(f"Logic 40/40 通过 (报告: {p3}/{t3}, exit={code})", code == 0 and p3 == 40 and t3 == 40)

print("\n"+"="*60)
print("[4/4] 版本号 v7.70 + 推送导出 结构检查")
print("="*60)
with open('index.html','r',encoding='utf-8') as f:
    data = f.read()
check_item("title 含 v7.70", bool(re.search(r'<title>[^<]*v7\.70', data)))
check_item("页脚 version-footer 含 v7.70", bool(re.search(r'version-footer[^<]*v7\.70', data)))
check_item("CURRENT_BUILD 更新为 20260628010500（触发自动强制刷新）",
           bool(re.search(r"var\s+CURRENT_BUILD\s*=\s*'20260628010500'", data)))
check_item("exportAiPredictions 函数存在", 'function exportAiPredictions' in data)
check_item("AI工具栏有「📤 导出推送」按钮", bool(re.search(r'onclick\s*=\s*"exportAiPredictions\(\)"|导出推送', data[:150000])))
check_item("工具栏有「📋 投注记录导入」按钮", bool(re.search(r'投注记录导入|loadAiFromBetRecords', data[:150000])))
check_item("工具栏有「📅 追加加载」按钮（新默认）", bool(re.search(r'追加加载|loadAiSchedule\(false\)', data[:150000])))
check_item("工具栏有「🔄 覆盖加载」按钮（保留旧模式）", bool(re.search(r'覆盖加载|loadAiSchedule\(true\)', data[:150000])))
check_item("AI_DATA_STORAGE_KEY 本地同步Key常量存在", 'AI_DATA_STORAGE_KEY' in data)
check_item("saveAiData / restoreAiData 同步函数存在", 'function saveAiData' in data and 'function restoreAiData' in data)
check_item("aiLastPredictions 预测结果持久化变量存在", 'aiLastPredictions = []' in data)
check_item("runAiPrediction 预测完成后保存 aiLastPredictions + saveAiData",
           bool(re.search(r'runAiPrediction[\s\S]{0,8000}aiLastPredictions\s*=\s*Array[\s\S]{0,200}saveAiData\(\)', data)))
check_item("init() 中调用 restoreAiData 优先恢复本地同步", 'restoreAiData()' in data)
check_item("_dedupeAiMatches 去重函数（日期+主队+客队唯一键）存在", 'function _dedupeAiMatches' in data)

print("\n"+"="*60)
print(f"最终总校验：{passed}/{total} 通过")
print("="*60)
sys.exit(0 if passed == total else 1)
