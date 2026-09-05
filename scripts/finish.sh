#!/bin/bash
# finish.sh - AI足球预测任务收尾脚本
# 包含：步骤6(更新索引页) + 步骤7(git提交推送)
# 用法: bash finish.sh
# 前提：报告已生成到 {仓库根}/predictions/{TODAY}/index.html
#       比赛数据在 {仓库根}/scripts/matches_data.json
#       本地运行如需代理: https_proxy=http://127.0.0.1:7897 bash finish.sh

set -euo pipefail

# ---------- 路径解析：以脚本所在位置定位仓库根 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# Git Bash/MSYS 环境下把 /c/... 转成 Windows 可识别的 C:/...（供 python 读取）
case "$REPO_ROOT" in
  /[a-zA-Z]/*) REPO_ROOT="$(cygpath -m "$REPO_ROOT" 2>/dev/null || echo "$REPO_ROOT")" ;;
esac

cd "$REPO_ROOT"

TODAY=$(date +%Y-%m-%d)
DATA_FILE="$REPO_ROOT/scripts/matches_data.json"
INDEX_FILE="$REPO_ROOT/predictions/index.html"

echo "=== AI足球预测收尾 ==="
echo "今天日期: $TODAY"

# ============================================================
# 步骤6：更新索引页
# ============================================================
echo ""
echo "--- 步骤6：更新索引页 ---"

# 从 matches_data.json 读取比赛信息
REPO_ROOT="$REPO_ROOT" python3 << 'PYTHON_EOF'
import json, re, datetime, os

TODAY = datetime.date.today().isoformat()
REPO_ROOT = os.environ['REPO_ROOT']
DATA_FILE = os.path.join(REPO_ROOT, 'scripts', 'matches_data.json')
INDEX_FILE = os.path.join(REPO_ROOT, 'predictions', 'index.html')

with open(DATA_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

matches = data.get('matches', [])
match_count = len(matches)

# 计算联赛分布
league_counts = {}
for m in matches:
    league = m.get('league', '未知')
    league_counts[league] = league_counts.get(league, 0) + 1
leagues_str = ' / '.join(f"{l} x{c}" for l, c in league_counts.items())

# 计算星期几
weekday_map = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
weekday = weekday_map[datetime.date.today().weekday()]

print(f"更新索引: date={TODAY}, weekday={weekday}, matches={match_count}, leagues={leagues_str}")

# 读取 index.html 并更新 reports 数组
with open(INDEX_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# 构建新条目
new_entry = f"{{ date: '{TODAY}', weekday: '{weekday}', matches: {match_count}, leagues: '{leagues_str}' }}"

# 查找 reports 数组（兼容 const/var/let 声明，分号可选）
reports_match = re.search(r'(?:const|var|let)\s+reports\s*=\s*\[([\s\S]*?)\]\s*;?', content)
if reports_match:
    reports_str = reports_match.group(1)
    # 检查是否已有当天条目
    if f"date: '{TODAY}'" in reports_str:
        # 替换已有条目
        pattern = rf"\{{\s*date:\s*'{re.escape(TODAY)}'[^}}]*\}}"
        updated_reports = re.sub(pattern, new_entry, reports_str)
        print("更新已有条目")
    else:
        # 在数组开头插入新条目（倒序排列）
        updated_reports = new_entry + ',\n  ' + reports_str
        print("新增条目")

    # 写回文件
    new_content = content[:reports_match.start(1)] + updated_reports + content[reports_match.end(1):]
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"索引页已更新: {INDEX_FILE}")
else:
    print("⚠️ 未找到 reports 数组，跳过索引更新")
PYTHON_EOF

# ============================================================
# 步骤7：Git 提交并推送
# ============================================================
echo ""
echo "--- 步骤7：Git 提交并推送 ---"

git config user.email "trae-bot@users.noreply.github.com"
git config user.name "Trae Bot"
echo "当前分支: $(git branch --show-current)"

git add predictions/
git diff --cached --quiet || git commit -m "report: $(date +%Y-%m-%d) AI 足球预测分析报告"

echo "拉取远程最新代码..."
git pull --rebase origin gh-pages

git push origin gh-pages

echo "验证推送结果..."
sleep 3
git fetch origin gh-pages
REMOTE_HEAD=$(git rev-parse origin/gh-pages)
LOCAL_HEAD=$(git rev-parse HEAD)

if [ "$REMOTE_HEAD" = "$LOCAL_HEAD" ]; then
  echo "✅ 推送成功，远程已包含最新报告"
else
  echo "⚠️ 推送可能被覆盖，重新合并并推送..."
  git pull --rebase origin gh-pages
  git push origin gh-pages
  sleep 3
  git fetch origin gh-pages
  REMOTE_HEAD2=$(git rev-parse origin/gh-pages)
  LOCAL_HEAD2=$(git rev-parse HEAD)
  if [ "$REMOTE_HEAD2" = "$LOCAL_HEAD2" ]; then
    echo "✅ 二次推送成功"
  else
    echo "❌ 推送仍失败，可能存在并发推送冲突，请手动检查"
  fi
fi

echo ""
echo "=== 收尾完成 ==="
