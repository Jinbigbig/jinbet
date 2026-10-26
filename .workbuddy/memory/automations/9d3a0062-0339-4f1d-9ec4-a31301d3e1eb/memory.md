# 自动化：08:00 每日赛果补录 + matlas 站点同步

## 2026-10-24 08:00 执行

**结果：失败（推送阶段）· matlas 环节按规则跳过**

- **抓取**：网易 117 场唯一 → 89 场已完赛 → 入库 3546 条。
- **[变更判定]** 新增 12 条 / 更新 0 条。
- **提交**：本地 commit `b229728e` 已生成（index.html、odds_history/2026-10-15.json、results_data.json、results_history/2026-10-17.json、results_history/index.json）。
- **推送**：直接推被拒（远端领先 3 个提交）→ 脚本自动 rebase 失败 → 已 abort → **未推送，退出码 1**。
- **冲突根因（只读诊断）**：本地基点 `c01ccee8`，远端 gh-pages 已到 `37b46842`（2026-10-23 08:32 / 09:53 / 17:03 三次自动更新）。两侧同时改动 `index.html`、`results_data.json`、`odds_history/2026-10-15.json` → 数据类 JSON 必然冲突，脚本 rebase 无法自动合并。
- **当前仓库态**：分支 gh-pages，无 rebase 残留（abort 已生效），本地 HEAD=`b229728e` 领先远端 1 个提交（待人工推送）；工作区另有 `odds_data.json`/`odds_ticks.json`/2026-10-23.md 改动，非本任务产生。

## 2026-10-25 08:00 执行

**结果：自动执行失败（推送阶段，同因复发）→ 09:45 手工解决并推送 `fed4faf4`；matlas 同步完成（`01b93164`）**

- **前置**：分支 gh-pages；上一日 `b229728e` 已由人工处理完毕（远端基线为 `71198929`，本地无残留）。
- **抓取**：网易 121 场唯一 → 91 场已完赛 → 入库 3575 条。[变更判定] 新增 29 条 / 更新 0 条。
- **提交**：本地 commit `a4657f91`（index.html、odds_history/2026-10-16.json、results_data.json、results_history/2026-10-18.json、results_history/index.json）。
- **推送**：直接推被拒 → `rebase --autostash --no-fork-point 39698947` 冲突 → abort，**未推送，退出码 1**。
- **冲突根因（只读诊断）**：远端 2026-10-24 有三次「自动更新赔率+赛果」（`25a0c50d` 08:07 / `04f8bf79` 09:23 / `39698947` 15:54），与本任务同时改 `index.html`、`odds_history/2026-10-16.json`、`results_data.json`（`results_history/index.json` 亦重叠）。
- **仓库态**：无 rebase 中间态残留；本地 HEAD=`a4657f91` 领先远端 1 提交待人工推送；工作区另有 `odds_data.json`/`odds_ticks.json` 改动（非本任务）。

## 待人工处理（累积）
- ✅ 当前无待推提交。10-25 遗留 `a4657f91` 已解决（最终 `fed4faf4`）；10-26 遗留 `4b211af4` 已由新逻辑自动丢弃重算并推送 `cf41d6d1`。

## 推送冲突的标准解法（10-25 实证，下次直接照做）
**不要 rebase，也不要整树提交本地版**，改用「以远端为基重算增量」：
1. `git tag -f backup_<日期>_pre <本地失败提交>`，备份 `results_data.json` 等关键文件。
2. 先做键级对比：`git show <远端>:results_data.json` vs 本地，确认「本地独有 N / 远端独有 0 / 共有零差异」。若远端独有 >0 说明本地是真旧态，不能直接用。
3. `git reset --mixed <远端SHA>`（mixed 不动工作区，规避 `reset --hard` 丢 `_` 脚本的老坑）。
4. `git restore --source=<远端SHA> --worktree -- index.html results_data.json results_history/ odds_history/ version.txt`，删掉本地当天新建的 `results_history/<日期>.json` 交脚本重建。
5. 重跑 `_sync_results.py` → 通常快进推送成功。
6. **务必验证去重没被回滚**：统计全库跨日重复 matchId 应为 0；抽查被删记录的 matchId 是否在官方日期文件里保留。

⚠️ `results_history/` 本地常年落后于远端（远端有去重后的精简版，本地是旧的膨胀版，差异可达 5 万行）。整树提交 = 回滚去重成果，这是最大的坑。

## 2026-10-26 08:00 执行（当日 08:2x 已修复并补推）

**结果：首次运行推送失败 → 当日修改脚本根治 → 重跑推送成功 `cf41d6d1` → matlas 已发布 `d786bf05b`**

- **首次运行**：网易 119 场唯一 / 114 场已完赛 / 库内 3604 条，[变更判定] 新增 27 条 / 更新 0 条；commit `4b211af4`，推送被拒 → rebase 冲突 → abort，退出码 1。matlas 环节按规则跳过。
- **根治**：`_sync_results.py` 新增 `[0/3] align_to_remote()`——抓赛果**之前**先 fetch 并站到远端基线（纯落后→快进；分叉且本地提交全是 `data: 赛果补录`→reset --keep 回基线重算；含人工数据提交→退出码 2 不丢弃）。commit 改带 pathspec + 提交后 `git reset -q`；version.txt 纳入提交。
- **重跑**：识别并丢弃 1 个未推送补录提交 → 回 `381d52b8` 重算（新增 11 条）→ 推送成功 `cf41d6d1`，退出码 0。
- **去重核验**：基线 5119 条 / 1531 跨日重复 → 本次 3596 条 / **0 重复**（正常去重，无丢数据）。幂等复跑：基线已最新 → 0/0 → 跳过，退出码 0。
- **同步**：master 正本 `tools/prediction/sync_results.py` 已更新（`692bcbd0`）；记忆提交 `5a52a738`。
- **matlas**：import 670 场 / 赛果 664 场 → build --strict 1195 文件 / 0 违规 → publish `d786bf05b`。

## 历史执行（10-24 / 10-25 失败归档）

## 备注
- 分支校验正常（gh-pages），非退出码 2 情形。
- **连续三日（10-24/25/26）同一失败模式已根治**（10-26 起由 `align_to_remote()` 前置对齐解决）：远端每天 3 次「自动更新赔率+赛果」提交与本任务在 index.html / results_data.json / results_history/ 必然重叠 → 旧逻辑 rebase 恒失败、退出码 1。现改为「先 fetch 站到远端基线再算」，推送走 fast-forward；上面「推送冲突的标准解法」降级为人工兜底。
- 残留边界：若工作区对 `index.html`/`results_data.json` 有未提交改动且远端也改了同一文件，快进与 `reset --keep` 都会被拒 → 会打警告后照旧流程跑（可能失败）。此时人工先 `git restore` 掉这些脏改动即可。
- matlas 侧须知（沿用 19:00 任务经验）：import 会改 `data/days/*.json`，publish.sh 有 main 干净校验，脏则被拦。
- 10-25 实测：matlas import+build+publish 全绿（641 场 / 635 赛果 / 1161 文件 / 0 违规）。
