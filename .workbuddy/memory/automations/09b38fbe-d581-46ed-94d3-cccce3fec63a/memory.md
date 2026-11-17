# 午间补充刷新（15:00）执行记录

## 2026-11-16
- 12:00 正常（predictions/2026-11-16/index.html 12:09）→ 本次补充刷新，非补跑。8 场（全欧国联，周一001-008），赔率 8/8。
- 正本 `a3600075`（3410 行/变更判定=3）→ `[DEDUP-ALIGN]` 235/297、备份 `_hist_backup_2026-11-16`；ODDS 回填新增 0/更新 0（12:00 已做）；赛果 3878 条、`[变更判定] 0/0`（早场未开赛）。
- 增量：盘口时序 8/8 各 3 点（11:12/12:10/15:08）、赔率变动 6 场（001/003/004/006/007/008）、开赛时间 8/8（001-002 23:00、003-004 次日01:00、005-008 次日03:45）、天气 8/8、红彩 7/8。
- ⚠️ **红彩错配 周一007：源站返回 `广州城(已退出) vs 广州恒大`（hc_id=2042783，中超 2021-07-24）**，移入 missing 后重生成报告 0 污染。`hongcai.json` 的 `matches` 键是 `matchNumStr`，脚本在 `scripts/matches_data.json` 的 `['matches']` 列表里（顶层是 dict，有 today/match_count/matches）。
- ⚠️ **天气本轮需三次重试**：首轮 0/8、次轮 2/8、第三轮 8/8，全是 `_ssl.c:1015 handshake timed out`。确认「重试即可」，与映射无关；重试会 merge 不覆盖已有场次。
- 头条变化：周一005 瑞士vs苏格兰 1-0 → 2-0（1X2 赔率未变、`top_scores` 序列未变，故由比分盘市场混合重排触发，headline prob 13.8→13.3）。属正常重算，非参数变更。
- 欧国联无 7M id 映射 → 联赛积分 0；裁判源只覆盖俱乐部赛事 → 8 场 0 覆盖；injuries_extra 0 队 0 条（国家队无俱乐部伤停源）。三者均为源站缺口。
- 跳过 step7 的 `_fetch_hongcai.py` 重跑（15:01 已跑并手工清理 007，重跑会写回错配、只增 `updated` 时间戳），避免 11-07 那种复核环；matlas 侧已用清理后的数据。
- 推送：gh-pages 023718d8 → 5317ff1a（279c6e1a 数据、5317ff1a 报告），ls-remote 核验；node-id=0 不 checkout；红线 0；线上 200/208112、8 kickoff、无「广州」。
- matlas：导入 952 场/赛果 938（当日 8 场回填 0）；restore_extras 缺失 32（2026-11-08 odds_ticks×29 + odds_full×3）→ `--apply` → 复核 0；build --strict 0 违规；发布 1285b04be（gh-pages adaa5547a→1285b04be，main 77305409c→0779d6d68）。**本轮只发布一次。**
- 教训：`git status` 里 `workbuddy 无已跟踪改动` 时 `git add -u -- . ':!.workbuddy/memory'` 不必加排除式，本次仍沿用保险写法。

## 2026-11-14
- 12:00 正常（predictions/2026-11-14/index.html 12:10）→ 本次为补充刷新。16 场（欧国联6/荷乙4/日乙2/国际赛2/巴甲2），赔率 15/16（周六015 米拉索尔空）。
- 正本 `8743662a`（3410 行/变更判定=3）→ `[DEDUP-ALIGN]` 235/296、备份 `_hist_backup_2026-11-14`；ODDS 更新 3670 条；赛果 3851→3853（+2 早场 13:00 已完赛）。
- 增量：盘口时序新增 19 点 / 赔率变动 13 场；开赛时间 16/16（001 13:00 → 016 次日 07:30）；天气 16/16；伤停 30 队/138 人 + 补充 2 队/11 条；联赛积分 3（巴甲/日乙/荷乙）。
- ⚠️ **天气首轮 14/16 全是 `_ssl.c:1015 handshake timed out`（非缺 TEAM_CITY 映射），直接重跑一次即 16/16**。别再按「补 CITY 映射」方向排查，先重试。
- ⚠️ 红彩错配与 12:00 完全一致：周六012 源站返回「伯格纳塞 vs 方寿IF」，移入 `missing` 后重生成报告 0 污染。`_gen_report.py` 有补跑红彩的自愈逻辑，但**文件已存在时不触发**，故手工清理不会被覆盖；只有删除/缺失才会重跑写回。
- 顺序沿用 11-08 改进：match_times / injuries_extra / odds_ticks 全部在 `_gen_report.py` 之前跑。⚠️ `_gen_report.py` 不消费 `odds_ticks.json`（`grep tick` 无命中），盘口时序只服务 matlas，报告里查不到 tick 块属正常。
- chain 校验：HEDGE 字样 11/16（`市场混合(...HEDGE动态...)` 只在特定分支写入），与 12:00 版逐字对比一致 → **不是异常，勿当成链路缺项**；必查项应为 市场混合( + 比分矩阵对齐发布1X2 + Platt + Kalman + 动态校准。
- 推送：gh-pages 555d137a → 33a53864（89cf135c 数据、33a53864 报告），ls-remote 核验；node-id=0 不 checkout；红线 0；线上 200/338424、16 kickoff。
- matlas：导入 933 场/赛果 913（当日 16 场回填 2）；restore_extras 缺失 0（无需 --apply）；build --strict 0 违规；publish 11f493c13（gh-pages ada20767b→11f493c13，main cb3917a3e→221dd4503）。**本轮只发布一次。**
- 教训：`git add -u -- . ':!.workbuddy/memory'` 可避免把别的 automation 的 memory.md 混进提交（本次 b0bc3264 那份仍留在工作区未提交）。

## 2026-11-11
- 12:00 流水线正常（predictions/2026-11-11/index.html 12:03）→ 本次为补充刷新，非补跑。今日 6 场：日联赛杯 4（001-004）+ 英锦标赛 2（005 谢周三/阿克宁顿、006 巴恩斯利/奥德汉姆）。
- 正本：ls-remote master=6ed09258 → `git show 6ed09258:update_odds_net.py`（3410 行/变更判定=3）→ `--no-push` 再 `--no-push --results-only`。[DEDUP-ALIGN] 235/293 文件，备份 `_hist_backup_2026-11-11`；ODDS 更新 3645 条；赛果 3828 条、[变更判定] 0/0（当日未开赛，未产生数据提交）。
- 覆盖：天气 6/6、开赛时间 6/6（001-003 18:00、004 18:30、005/006 次日 03:00）、红彩 6/6 错配 0、盘口时序 6/6 各 7 点（末点 15:02，新增 11 点、赔率变动 5 场）；**赔率 5/6**（周三005 主赔率表空，但时序缓存有 1.35/4.40/5.85，属源站不一致，未手工注入）；阵容/结构化伤停/军情 0（日联杯+英锦标赛不在 lineupstoday / injuries(德甲+荷甲) / 7M 映射内）；联赛积分 0（两联赛无 7M id）。
- 顺序沿用 11-08 改进：odds_ticks / injuries_extra / match_times 全部提到 `_gen_report.py` 之前。
- 红彩复跑只改 `updated`（15:01→15:03）→ `git checkout -- hongcai.json` 回退。
- 推送：gh-pages 7cbbb7ad → f2e99e5f（439f1d21 `data: 11-11 赔率/赛果/红彩补充`、f2e99e5f `report:`），ls-remote 核验；node-id=0 不 checkout 根 index.html；红线 grep 0；线上 200/137219 含 6 场 kickoff。
- matlas：导入 900 场 / 赛果 888；restore_extras 缺失 10（2026-11-03 odds_ticks）→ `--apply` → 复核 0；build --strict 0 违规；发布 0839ecb76（gh-pages b06f6695d→0839ecb76，main c168ada42→0ec03e699）。**本轮只发布一次。**
- 新教训：matlas `_ticks_for()` 双向包含仍会漏「谢周三 ↔ 谢菲尔德星期三」这类简称↔全称（非包含关系），当日 005 的 7 点时序未进 matlas 日页（jinbet 侧 `odds_ticks.json` 有）；该类缺口只能靠 `standings_alias` 式映射，勿在 matlas 源码里临时加。另：`_calc_result.json` 的 `matches` 本次是 **list**（不是 dict），需按 list 遍历。

## 2026-11-10
- 12:00 完整流水线正常（index.html 12:08），本任务为补充刷新（非补跑）。今日仅 2 场英锦标赛（周二001 伯顿/诺茨郡、周二002 布罗姆利/米尔顿）。
- 脚本正本取法：`git ls-remote origin master` 得 44968b1e → `git show 44968b1e:update_odds_net.py`（3410 行 / `grep -c 变更判定`=3）→ 先 `--no-push` 再 `--no-push --results-only`。[DEDUP-ALIGN] 受影响 235/292 文件，备份 `_hist_backup_2026-11-10`；ODDS 回填更新 3643 条；赛果 3826 条、[变更判定] 0/0 故未推数据提交。
- 覆盖：赔率 2/2、红彩 2/2（错配 0）、天气 2/2（002 恶劣）、开赛时间 2/2（次日 03:00/03:30）；**阵容 0/2、结构化伤停 0/2、军情 0 场、联赛积分 0** —— 英锦标赛不被 lineupstoday / injuries(德甲+荷甲) / 7M id 映射覆盖，属源站缺覆盖而非失败，报告靠红彩自带伤停（001 1+4、002 2+3）兜底。
- 顺序沿用 11-08 改进：match_times / injuries_extra / odds_ticks 全部提到 `_gen_report.py` 之前，报告直接带上开赛时间（线上页已核实含 03:00/03:30）。
- 盘口时序：15:02 新增 8 点，两场各 3 点（11:11/12:05/15:02），赔率变动 2 场（001 2.18→2.30，002 4.05→4.15）。
- 红彩复跑仅 `updated` 时间戳变化（15:01→15:03），内容零增量 → `git checkout -- hongcai.json` 回退，避免抖动。
- 推送：gh-pages 06bab2e4 → 737e2d61（两个提交：`data: 11-10 赔率/赛果/红彩补充` 31188c6e、`report: 生成11-10 报告午间补充刷新` 737e2d61），ls-remote 核验；根 index.html `data-page-node-id`=0 不 checkout；红线 grep 0 命中；线上 200 且含开赛时间。
- matlas：导入 894 场 / 赛果 886；restore_extras 缺失 0（无需 --apply）；build --strict 0 违规；发布 5ddafb5b6（gh-pages 0c5ce193c→5ddafb5b6，main d55b6c3e2→a382c1baf）。**本轮只发布一次。**
- 新增教训：`odds_ticks.json` 的 key 用竞彩原始全称（`布罗姆利_米尔顿凯恩斯`），matlas 由 `_ticks_for()` 的双向包含兜底命中；**matlas day json 的时序在 `match.extras.odds_ticks`，不在顶层**，别在 match 顶层查而误判为 0。

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
