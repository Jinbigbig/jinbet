import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
t = open(r'predictions/2026-09-06/index.html', encoding='utf-8').read()
# 找到"四、预测汇总"位置
idx = t.find('四、预测汇总')
print('四、位置:', idx)
print('===== 从四开始到最后 3000 字符 =====')
print(t[idx:idx+3000])
