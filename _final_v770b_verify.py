# -*- coding: utf-8 -*-
"""运行多个验证脚本，检查loadSchedule追加逻辑、AI功能、版本号和构建号是否正确。"""
import sys, re, subprocess
sys.stdout.reconfigure(encoding='utf-8')

def run_py(script):
    try:
        r = subprocess.run(['python', script], capture_output=True, text=True, encoding='utf-8', errors='replace')
        lines = r.stdout.splitlines()
        summ = next((l for l in reversed(lines) if ('通过' in l or 'FAIL' in l or 'PASS' in l)), '')
        return r.returncode, r.stdout, summ, r.stderr
    except Exception as e:
        return 1, '', '', str(e)

total = 0; passed = 0
def chk(name, ok):
    global total, passed
    total += 1
    if ok: passed += 1
    print(f"  {'✅' if ok else '❌'} [#{total}] {name} {'PASS' if ok else 'FAIL'}")

with open('index.html','r',encoding='utf-8') as f:
    html = f.read()

print("="*60)
print("[1] 专项: loadSchedule 追加模式 6/6")
print("="*60)
code, out, summ, err = run_py('_tdd_loadSchedule_append.py')
chk(f"loadSchedule 专项测试 exit={code} 总结={summ[:80]}", code == 0 and '6/6 閫氳繃' in summ or (code==0 and ('6/6' in summ or '6/6 閫氳繃' in out or '6/6 通过' in out)))

print("\n"+"="*60)
print("[2] 专项: AI 同步/推送 13/13")
print("="*60)
code, out, summ, err = run_py('_tdd_ai_sync_push.py')
chk(f"AI同步推送13项 exit={code}", code == 0)

print("\n"+"="*60)
print("[3] 专项: AI Integration 40/40")
print("="*60)
code, out, summ, err = run_py('_verify_ai_integration.py')
chk(f"集成40项 exit={code}", code == 0)

print("\n"+"="*60)
print("[4] 专项: AI Logic 40/40")
print("="*60)
code, out, summ, err = run_py('_verify_ai_logic.py')
chk(f"逻辑40项 exit={code}", code == 0)

print("\n"+"="*60)
print("[5] 版本/构建/推送 最终检查")
print("="*60)
chk("title含v7.70", bool(re.search(r'<title>[^<]*v7\.70', html)))
chk("footer含v7.70", bool(re.search(r'<div class="version-footer"[^>]*>[^<]*v7\.70', html)))
chk("CURRENT_BUILD=20260628013000", bool(re.search(r"CURRENT_BUILD\s*=\s*'20260628013000'", html)))
chk("添加投注模态框-追加按钮(loadSchedule(false))", 'loadSchedule(false)' in html and 'schedule-loader' in html)
chk("添加投注模态框-覆盖按钮(loadSchedule(true))", 'loadSchedule(true)' in html and 'schedule-loader' in html)
# 精简要求：AI工具栏(ai-toolbar)里不能有覆盖加载/导出推送，只能保留追加(loadAiSchedule(false))/投注导入/开始预测/清空
toolbar = re.search(r'<div class="ai-toolbar"[^>]*>([\s\S]*?)</div>', html, re.IGNORECASE)
tb_html = toolbar.group(1) if toolbar else ''
chk("AI工具栏-🚫无 loadAiSchedule(true) 覆盖加载按钮",
    not bool(re.search(r'onclick\s*=\s*"loadAiSchedule\s*\(\s*true\s*\)"', tb_html)) and '覆盖加载' not in tb_html)
chk("AI工具栏-🚫无 exportAiPredictions() 导出推送按钮",
    not bool(re.search(r'onclick\s*=\s*"exportAiPredictions\s*\(\s*\)"', tb_html)) and '导出推送' not in tb_html)
chk("AI工具栏-✅ 有 loadAiSchedule(false) 加载赛程（追加模式）",
    bool(re.search(r'onclick\s*=\s*"loadAiSchedule\s*\(\s*false\s*\)"', tb_html)))
chk("AI工具栏-✅ 有 loadAiFromBetRecords 投注导入", 'loadAiFromBetRecords()' in tb_html)
chk("AI工具栏-✅ 按钮数=4", len(re.findall(r'<button[^>]*onclick\s*=\s*"[^"]+"', tb_html, re.IGNORECASE)) == 4)
chk("AI本地同步: saveAiData+restoreAiData", 'function saveAiData' in html and 'function restoreAiData' in html)
chk("AI DATA StorageKey存在", "AI_DATA_STORAGE_KEY = 'worldcup_ai_data_v1'" in html)
chk("loadSchedule 追加模式下条件清空 (if overwrite === true)", "if (overwrite === true)" in html and "container.innerHTML = '';" in html)
chk("loadSchedule 追加去重逻辑 (Set+game-home/.game-away)",
    "const existing = new Set();" in html and ".game-home" in html[html.find('function loadSchedule('):html.find('function loadSchedule(')+4000])
chk("openAddModal 打开模态框时清空容器 (不影响，新增不调用loadSchedule)",
    "document.getElementById('gameListContainer').innerHTML = '';" in html)

print("\n"+"="*60)
print(f"最终汇总: {passed}/{total} 通过")
print("="*60)
sys.exit(0 if passed == total else 1)
