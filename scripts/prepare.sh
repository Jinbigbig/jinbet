#!/bin/bash
# prepare.sh - AI足球预测任务环境准备脚本
# 包含：步骤0(触发赔率更新) + 步骤1(克隆仓库) + 步骤2(检查已有报告) + 步骤3(提取比赛和赔率数据)
# 用法: GITHUB_TOKEN=xxx bash prepare.sh
#       [可选] JINBET_WORKSPACE=/path/to/dir  指定克隆目标目录(默认 /workspace)
#       本地模式: 若脚本本身位于已克隆的仓库内(存在 .git)，则跳过克隆直接使用该仓库
# 输出: {仓库根}/scripts/matches_data.json (比赛+赔率数据)
#       脚本退出码: 0=正常继续, 10=报告已存在跳过, 20=无比赛数据

set -euo pipefail

# ---------- 路径解析：本地仓库优先，否则克隆到工作区 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_CANDIDATE="$(dirname "$SCRIPT_DIR")"
if [ -d "$REPO_CANDIDATE/.git" ]; then
  REPO_ROOT="$REPO_CANDIDATE"
  LOCAL_MODE=1
else
  REPO_ROOT="${JINBET_WORKSPACE:-/workspace}/jinbet"
  LOCAL_MODE=0
fi
# Git Bash/MSYS 环境下把 /c/... 转成 Windows 可识别的 C:/...（供 python 读取）
case "$REPO_ROOT" in
  /[a-zA-Z]/*) REPO_ROOT="$(cygpath -m "$REPO_ROOT" 2>/dev/null || echo "$REPO_ROOT")" ;;
esac

TOKEN="${GITHUB_TOKEN:?必须通过环境变量 GITHUB_TOKEN 提供 GitHub Token}"
REPO="Jinbigbig/jinbet"
WORKFLOW="daily-update.yml"
API_BASE="https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW"
CLONE_URL="https://${TOKEN}@github.com/${REPO}.git"

TODAY=$(date +%Y-%m-%d)
echo "=== AI足球预测环境准备 ==="
echo "今天日期: $TODAY"

# ============================================================
# 步骤0：触发赔率自动更新工作流
# ============================================================
echo ""
echo "--- 步骤0：触发赔率更新工作流 ---"

BEFORE_RUN_ID=$(curl -s -H "Accept: application/vnd.github.v3+json" -H "Authorization: token $TOKEN" \
  "${API_BASE}/runs?per_page=1" | python3 -c "import sys,json; runs=json.load(sys.stdin)['workflow_runs']; print(runs[0]['id'] if runs else '0')" 2>/dev/null)
echo "触发前最新 run ID: $BEFORE_RUN_ID"

curl -s -X POST -H "Accept: application/vnd.github.v3+json" -H "Authorization: token $TOKEN" \
  "${API_BASE}/dispatches" -d '{"ref":"master"}'

echo "等待 5 秒让新 run 启动..."
sleep 5

echo "等待赔率更新工作流完成（超时10分钟）..."
WORKFLOW_DONE=false
for i in $(seq 1 60); do
  sleep 10
  RESULT=$(curl -s -H "Accept: application/vnd.github.v3+json" -H "Authorization: token $TOKEN" \
    "${API_BASE}/runs?per_page=1" | python3 -c "import sys,json; runs=json.load(sys.stdin)['workflow_runs']; r=runs[0] if runs else {}; print(f\"{r.get('status','unknown')}|{r.get('conclusion','null')}|{r.get('id',0)}\")" 2>/dev/null)
  STATUS=$(echo "$RESULT" | cut -d'|' -f1)
  CONCLUSION=$(echo "$RESULT" | cut -d'|' -f2)
  RUN_ID=$(echo "$RESULT" | cut -d'|' -f3)
  echo "第 $i 次检查: status=$STATUS conclusion=$CONCLUSION run_id=$RUN_ID"
  if [ "$STATUS" = "completed" ] && [ "$RUN_ID" != "$BEFORE_RUN_ID" ]; then
    if [ "$CONCLUSION" = "success" ]; then echo "✅ 工作流成功完成"; WORKFLOW_DONE=true; break
    elif [ "$CONCLUSION" = "failure" ]; then echo "⚠️ 工作流失败，用现有数据继续"; WORKFLOW_DONE=true; break; fi
  fi
done
if [ "$WORKFLOW_DONE" = "false" ]; then echo "⚠️ 超时10分钟，用现有数据继续"; fi
echo "额外等待 10 秒确保远程同步..."
sleep 10

# ============================================================
# 步骤1：克隆项目并切换到 gh-pages（本地已有仓库则跳过克隆）
# ============================================================
echo ""
echo "--- 步骤1：获取仓库 ---"
if [ "$LOCAL_MODE" = "1" ]; then
  echo "本地模式：检测到现有仓库 $REPO_ROOT，跳过克隆"
  cd "$REPO_ROOT"
  git stash list > /dev/null 2>&1 || true
else
  echo "容器模式：克隆到 $REPO_ROOT"
  mkdir -p "$(dirname "$REPO_ROOT")"
  cd "$(dirname "$REPO_ROOT")"
  rm -rf jinbet
  git clone "$CLONE_URL"
  cd "$REPO_ROOT"
fi
git checkout gh-pages
git pull origin gh-pages
echo "当前分支: $(git branch --show-current)"

# ============================================================
# 步骤2：检查当日已有报告
# ============================================================
echo ""
echo "--- 步骤2：检查当日已有报告 ---"
REPORT_PATH="$REPO_ROOT/predictions/${TODAY}/index.html"

# 先从 SCHEDULE 提取当天比赛数量（用于对比）
SCHEDULE_COUNT=$(REPO_ROOT="$REPO_ROOT" python3 -c "
import re, datetime, os
TODAY = datetime.date.today().isoformat()
with open(os.path.join(os.environ['REPO_ROOT'], 'index.html'), 'r', encoding='utf-8') as f:
    html = f.read()
schedule_match = re.search(r'const SCHEDULE\s*=\s*\{([\s\S]*?)\};', html)
if schedule_match:
    schedule_str = schedule_match.group(1)
    date_section = re.search(rf\"['\\\"]?{re.escape(TODAY)}['\\\"]?\s*:\s*\[([\s\S]*?)\]\", schedule_str)
    if date_section:
        entries = re.findall(r'\{([^}]+)\}', date_section.group(1))
        print(len(entries))
    else:
        print(0)
else:
    print(0)
" 2>/dev/null)
echo "SCHEDULE 中当天比赛数量: $SCHEDULE_COUNT"

if [ -f "$REPORT_PATH" ]; then
  # 报告已存在，检查比赛数量
  EXISTING_COUNT=$(grep -c 'match-card\|card-header' "$REPORT_PATH" 2>/dev/null || echo 0)
  echo "已有报告比赛卡片数: $EXISTING_COUNT"
  if [ "$EXISTING_COUNT" -ge "$SCHEDULE_COUNT" ] && [ "$SCHEDULE_COUNT" -gt 0 ]; then
    echo "SKIP:当日报告已存在，无需重新生成"
    exit 10
  fi
  echo "已有报告比赛数不足，将覆盖重新生成"
fi

if [ "$SCHEDULE_COUNT" -eq 0 ]; then
  echo "SKIP:当天无比赛数据"
  exit 20
fi

# ============================================================
# 步骤3：提取比赛列表和赔率数据
# ============================================================
echo ""
echo "--- 步骤3：提取比赛和赔率数据 ---"

REPO_ROOT="$REPO_ROOT" python3 << 'PYTHON_EOF'
import re, json, datetime, os

TODAY = datetime.date.today().isoformat()
REPO_ROOT = os.environ['REPO_ROOT']
OUTPUT_FILE = os.path.join(REPO_ROOT, 'scripts', 'matches_data.json')

with open(os.path.join(REPO_ROOT, 'index.html'), 'r', encoding='utf-8') as f:
    html = f.read()

# 3a: 从 SCHEDULE 提取当日比赛
matches = []
schedule_match = re.search(r'const SCHEDULE\s*=\s*\{([\s\S]*?)\};', html)
if schedule_match:
    schedule_str = schedule_match.group(1)
    date_section = re.search(rf"['\"]?{re.escape(TODAY)}['\"]?\s*:\s*\[([\s\S]*?)\]", schedule_str)
    if date_section:
        section = date_section.group(1)
        entries = re.findall(r'\{([^}]+)\}', section)
        for entry in entries:
            num_match = re.search(r"matchNumStr:\s*['\"]([^'\"]+)['\"]", entry)
            home_match = re.search(r"home:\s*['\"]([^'\"]+)['\"]", entry)
            away_match = re.search(r"away:\s*['\"]([^'\"]+)['\"]", entry)
            league_match = re.search(r"league:\s*['\"]([^'\"]+)['\"]", entry)
            matchId_match = re.search(r"matchId:\s*['\"]([^'\"]+)['\"]", entry)
            if home_match and away_match:
                matches.append({
                    'matchNumStr': num_match.group(1) if num_match else '',
                    'home': home_match.group(1),
                    'away': away_match.group(1),
                    'league': league_match.group(1) if league_match else '',
                    'matchId': matchId_match.group(1) if matchId_match else '',
                    'odds': {}
                })
print(f"从 SCHEDULE 提取到 {len(matches)} 场 {TODAY} 的比赛")

# 3b: 从 ODDS 提取赔率数据
odds_obj = {}
odds_start = html.find('const ODDS = {')
if odds_start >= 0:
    start = html.find('{', odds_start)
    depth, i = 0, start
    while i < len(html):
        if html[i] == '{': depth += 1
        elif html[i] == '}': depth -= 1
        if depth == 0: break
        i += 1
    odds_str = html[start:i+1]
    try:
        odds_obj = json.loads(odds_str)
    except json.JSONDecodeError:
        cleaned = re.sub(r',\s*([}\]])', r'\1', odds_str)
        try:
            odds_obj = json.loads(cleaned)
        except:
            odds_obj = {}
    for m in matches:
        odds_key = f"{TODAY}_{m['home']}_{m['away']}"
        if odds_key in odds_obj:
            m['odds'] = odds_obj[odds_key]
matched = sum(1 for m in matches if m['odds'])
print(f"从 ODDS 变量匹配到 {matched}/{len(matches)} 场比赛的赔率数据")

# 3c: 从 odds_data.json 补充缺失赔率
try:
    with open(os.path.join(REPO_ROOT, 'odds_data.json'), 'r', encoding='utf-8') as f:
        raw_odds = json.load(f)
    for m in matches:
        existing = m.get('odds', {})
        has_odds = existing.get('胜') and existing.get('胜') != ''
        if not has_odds:
            team_key = f"{m['home']} vs {m['away']}"
            if team_key in raw_odds:
                entry = raw_odds[team_key]
                if m.get('odds'):
                    for k, v in entry.items():
                        if k not in m['odds'] or not m['odds'][k]:
                            m['odds'][k] = v
                else:
                    m['odds'] = entry
            elif not m.get('odds'):
                reverse_key = f"{m['away']} vs {m['home']}"
                if reverse_key in raw_odds:
                    m['odds'] = raw_odds[reverse_key]
except Exception as e:
    print(f"读取 odds_data.json 失败: {e}")

# 统计匹配结果
for m in matches:
    odds = m.get('odds', {})
    has_odds = odds.get('胜') and odds.get('胜') != ''
    status = "✅" if has_odds else "⚠️ 赔率缺失"
    print(f"  {m['matchNumStr']}: {m['league']} | {m['home']} vs {m['away']} | 胜={odds.get('胜','')} 平={odds.get('平','')} 负={odds.get('负','')} {status}")

# 按 matchNumStr 排序
matches.sort(key=lambda x: x.get('matchNumStr', ''))

# 输出 JSON
output = {
    'today': TODAY,
    'match_count': len(matches),
    'matches': matches
}
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n最终比赛数量: {len(matches)}")
print(f"数据已保存到: {OUTPUT_FILE}")
PYTHON_EOF

echo ""
echo "=== 环境准备完成 ==="
echo "比赛数据: $REPO_ROOT/scripts/matches_data.json"
echo "请读取该 JSON 文件获取比赛列表和赔率数据，然后进行 AI 深度分析"
exit 0
