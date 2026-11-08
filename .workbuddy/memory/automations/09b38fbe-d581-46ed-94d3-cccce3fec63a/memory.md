# 午间补充刷新（15:00）执行记录

## 2026-11-08
- 12:00 完整流水线正常（index.html 12:07），本任务为补充刷新（非补跑）。
- ⚠️ **裸 `git show master:update_odds_net.py` 会拿到旧脚本**：本地 `master` 分支是分叉死引用（`897636ae`，3334 行、`grep -c 变更判定`=0）；而 `origin/master`=`fae03fec` 是 3410 行/3 匹配的正确版。本次先误读本地 master，发现行数不对后改取 `HEAD:` 才跑通。**正确姿势：fetch 后用 `git show origin/master:update_odds_net.py`（或 ls-remote 给的 SHA），校验 3410 行 + 变更判定=3。** `git fetch origin master:master` 因 non-ff 被拒，无法快进本地 master。
- 赛果 3796→3797（新增 1 条：周日002 首尔FC 1:2 蔚山现代），ODDS 回填更新 3614 条；[DEDUP-ALIGN] 生效，290 文件写盘备份 `_hist_backup_2026-11-08`。
- 30 场，赔率 30/30 全齐（无缺赔场次）。
- 覆盖：天气 30/30、开赛时间 30/30、红彩 30/30（唯一差异 周日008 国际图/国际图尔 属别名，真错配 0）、伤停 injuries.json 30 队/143 人、阵容 19/30（站点覆盖 21 场中命中 19，2 场 unmapped 荷甲阿尔克马/西甲比利亚雷）、军情 4 场。
- 盘口时序：15:04 新增 26 点、赔率变动 21 场；当日 30/30 场均有 5~8 点。
- **执行顺序改进（本次采用）**：把这 4 个抓取（injuries_extra / match_times / odds_ticks / 另加 lineups）提到 `_gen_report.py` **之前**，否则报告吃不到当午新增的开赛时间与军情。任务原文把这段放在第 7 步，但目的要求「报告体现增量」，故重排。
- 阵容在 15:00 重抓收益≈0（对比 12:06 仅 周日022 客队停赛 1→0 一处），**判断为不值得为它再发一轮 matlas**，已 `git checkout -- lineups.json` 回退，保持 jinbet 与 matlas 一致。
- 推送：gh-pages 303dd1fe → 816432e4（17 文件，ls-remote 核验；Pages Last-Modified 15:05 一致）。红线 grep 0 命中。根 index.html `data-page-node-id`=0 故不 checkout（其改动是 ODDS/RESULTS 内联数据，属本次要推的内容）。
- matlas：导入 892 场 / 赛果 857；restore_extras 缺失 27（全为 2026-10-31 odds_ticks）→ `--apply` → 复核 0；build --strict 0 违规；发布 9be779621（gh-pages 099703f9d→9be779621，main 984b79a8e→c6e9f8174）。**本轮只发布一次。**
- 教训复用：`results_data.json` 顶层是 dict，键 `日期_主队_客队`（无 date 字段），按 `x.get('date')` 筛会得 0 条；查新增用 `git show HEAD~1:results_data.json` 做键差集。
- 教训复用：`_calc_result.json` 的 `today` 是**日期字符串**（len=10 不是 30），场次数看 `matches`（dict，30 键）。

## 2026-11-07
- 12:00 完整流水线正常，本任务为补充刷新（非补跑）。
- 顺序要点：fetch → `git show master:update_odds_net.py` → `--no-push` → `--no-push --results-only`（[DEDUP-ALIGN] 出现，归档 289 文件备份到 `_hist_backup_2026-11-07`）。赛果 3767→3767（0 新增），ODDS 回填更新 3575 条。
- 30 场；赔率 29/30、让球 29/30（周六018 挪超 克里斯蒂vs瓦勒伦加 无赔率）。
- 天气 30/30（周六029 恶劣）；开赛时间 29/30；红彩 30/30、错配 0（周六020 斯达/特尔斯达属别名）；阵容 15/30（5 场 unmapped）；injuries_extra moods 2 场、teams 1 队。
- 盘口时序 16:29 新增 54 点、赔率变动 22 场，当日 28/30 有迹（每场 3~5 点）。
- 关键教训：JSON 键名要用 `matchNumStr`（不是 num）；`match_times.json` 结构是 `times` + `day`（0=当日/1=次日），按 day==0 统计会把晚场误判为缺失；`lineups.json` 是 `matches`；`injuries_extra.json` 是 `teams`/`moods`；`odds_ticks.json` 是 `ticks`（键 `日期_主队_客队`）。
- 复核环：matlas 环节后按指示重跑 `_fetch_hongcai.py` → 18 个字段微差异（天气温湿度 + 周六001 场次计数）→ 重生成报告 + 重新 import/build/publish 保持一致。
- 归档安全：results_history 18 文件净删 20155 行，但唯一键 259=259，确认只是别名去重，非回滚。
- 推送：gh-pages cb55f0e9 → 358968eb → 85393313 → 75649d91（ls-remote 核验）。最后一次为 strength_db.json + update_odds_net.py 同步。
- matlas：导入 862 场/次日 0 回填；restore_extras 缺失 0；build --strict 0 违规；发布 f928f8b69 → 9e88792fe。
- ⚠️ **matlas Pages 部署事故（本次踩到）**：同一会话内 publish 两次（16:31 f928f8b69、16:33 9e88792fe），Pages 内置工作流「页面构建和部署」→ run132 cancelled（被后者顶掉）、run133 部署 10 分 20 秒超时 failure，站点停在 16:21 的 d42725536。
  - 处置：`.publish` 里 `git commit --allow-empty -m "chore: 触发 Pages 重新部署"` + push → run134 success（40 秒），线上 `?v=1794040387` 与 `_site` 逐字一致。
  - **新规矩：matlas 每轮只发布一次，发布后至少等部署完成（约 1 分钟）再决定是否重发；绝不在 3 分钟内连推两次。**
  - 排查手法：无 gh CLI，用 `api.github.com/repos/Jinbigbig/matlas/actions/runs` + `/jobs` + `/deployments/{id}/statuses` 公开接口即可定位到具体 job/step 与部署状态。
