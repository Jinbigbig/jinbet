# LESSONS.md - 新完善规则与踩坑经验

> v7.100.4 ~ v7.101.0 期间通过修复三大连锁问题（赛果未录入 / 归档日期错乱 / 重复比赛）确立的规则和经验。通用框架规范见 [AGENTS.md](file:///AGENTS.md)。

## 队名归一化（v7.101.0 确立）

- Python 端所有队名标准化必须调用全局 `canonical_team_name(name)`，禁止在 `parse_lottery_json` / `main` 合并 / `id_map` 去重 / `normalize_result_team` 等任何位置自行实现归一化逻辑
- 新增队名映射只改 `RESULT_TEAM_NAME_MAP` 一处，`canonical_team_name` 会通过 `_get_sorted_team_mapping()` 自动按 key 长度从长到短匹配
- **禁止保留未使用的映射表死代码**（v7.102.3 确立）：`TEAM_NAME_MAP` 曾与 `RESULT_TEAM_NAME_MAP` 并存但从未被 `_get_sorted_team_mapping()` 调用，导致补充到 `TEAM_NAME_MAP` 的变体映射全部失效。归一化映射表只能保留一个，所有变体必须写入 `RESULT_TEAM_NAME_MAP`
- **变体映射方向必须与已完赛赛果 key 一致**（v7.102.3 确立）：归一化目标名应统一到赛果 key 已使用的短名（如 `埃夫斯堡`/`狼队`/`曼城`），避免历史赛果 key 与 SCHEDULE key 错位导致赛果匹配失败

## 去重规则（v7.101.0 确立）

- 所有去重阶段（schedule_data→schedule 合并、id_map 补赛程、final_dedup）必须使用 `canonical_team_name` 归一化后的**无序对** `(min(home,away), max(home,away))` 比较，禁止直接用字符串原文 `(home, away)` 比较
- matchId 优先级最高；matchId 缺失时 canonical pair 兜底
- 前端 `updateScheduleFromOdds` 的日期-星期校验（v7.100.4 引入）不可删除，它是脏数据流入浏览器的最后一道防线

## 赛果数据录入（v7.101.0 确立）

- `parse_results_json` 对有 `matchId`/`matchNumStr` 但暂缺 `fullScore` 的比赛必须保留占位 key，下次 CI 拿到比分后覆盖回填，禁止跳过丢弃
- `--full` 模式下 `fetch_and_save_results` 返回失败必须 `exit 1`，禁止降级为警告后继续提交无赛果版本
- `archive_results` 写入归档文件前必须调用 `is_weekday_match()` 校验日期与 `matchNumStr` 星期一致性，冲突时拒绝写入并打印 `[AUDIT][SKIP]`
- `archive_results` 结束时必须全量扫描 `results_history/` 目录做审计，脏数据打印 `[AUDIT][脏数据]` 告警

## 双分支推送流程（v7.101.0 确立）

- 绝对禁止 `git push --force origin HEAD:gh-pages`；gh-pages 必须通过白名单静态文件（index.html / odds_data.json / results_data.json / 预测与归档目录 / favicon / .nojekyll / version.txt）从 master `git checkout master -- <白名单>` 后独立 commit + 普通 push
- `--full` 模式分两个阶段：`main()` 更新赔率 + `fetch_and_save_results()` 更新赛果；每个阶段都要**分别** commit+push 两个分支，否则第二阶段写进 index.html 的赛果/归档"看起来抓到了但实际上没上线"
- `--results-only` 模式不能只调用 `fetch_and_save_results()` 就结束，必须在之后再执行一次 `push_to_gh_pages`
- 两个分支都用 `pull --rebase` 再普通 `push`，任何分支都不能 `--force`，rebase 冲突立即 abort 并交给人工

## 踩坑经验

- `merged_odds = dict(existing_odds)` 会把历史错日期 key 全量搬进新对象，合并后必须调用 `is_weekday_match()` 过滤残留，否则脏数据会通过 7 天 cutoff 机制持续累积
- Python `datetime.weekday()` 周一=0...周日=6，JS `Date.getDay()` 周日=0...周六=6，双端做星期校验时各自适配，不能直接复用对方的映射表
- 体彩赛果 API 有入库延迟，深夜比赛比分可能次日中午前仍未录入；占位 key 机制保证不丢场次，下次 CI 自动回填
- 三处队名归一化各自实现会导致 (home,away) pair 去重失败，产生重复比赛；必须统一走 `canonical_team_name()`
- 脚本 `main()` 先 commit 赔率再抓赛果但不再 commit，`--force push HEAD:gh-pages` 会把无赛果版本推上线，导致"赛果抓到了但没上线"
- **[v7.102.3] 队名映射表死代码导致重复比赛**：`TEAM_NAME_MAP` 与 `RESULT_TEAM_NAME_MAP` 并存，但 `canonical_team_name` 只调用后者，前者是死代码。补充到 `TEAM_NAME_MAP` 的 6 组变体映射（埃夫斯堡/狼队/曼城等）全部失效，`canonical` 无法归一，去重逻辑失效，SCHEDULE 同一场比赛的长名（带 matchId）和短名（无 matchId）两份记录共存，前端用变体名查赔率查不到→赔率为空。根因隐蔽在于两个表名相似、代码分散。修复：合并为 `RESULT_TEAM_NAME_MAP` 一个表，删除死代码，变体统一到短名（与赛果 key 一致）

## 赛果同步链路与CI防护（v7.104.0 确立）

### 问题现象
2026-08-16 早间CI跑完后，体彩API已经有 8-15 的 30 场赛果数据，但线上 `results_data.json` 中 8-15 赛果始终为 0 条，用户看不到 8-15 任何比赛的比分与赔率回填。

### 根因
CI工作流 **双保险静默吞错**：
1. 赛果抓取步骤用了 `set +e` 取消 errexit，随后无论脚本退出码是什么都 `exit 0`
2. 外层又加了 `continue-on-error: true`，即使步骤失败也标绿通过
3. 赛果抓取因为API偶尔超时/限流失败时，既不会重试，也不会阻断后续推送步骤，工作流仍然只推送赔率更新到双分支上线
4. 后续3次 cron 定时任务（11:15 / 15:00 / 20:15）都因为体彩分页API同样的原因重复失败，静默吞掉后，8-15 的赛果就永远缺席

### 修复方案
1. **[脚本层硬校验]** [fetch_and_save_results](file:///Users/jin/Library/Mobile%20Documents/com~apple~CloudDocs/Jin/jinbet/update_odds_net.py#L2339-L2354) 返回前做对比：
   - 如果 API 抓到的昨日赛果 `yesterday_api > 0`，但本地写入 `merged_results` 中昨日为 0 → **直接 return False**（退出码 1）
   - 如果已过北京时间中午 12 点、昨日写入仍为 0 → 打印高危警告（多数情况 API 此时早已录完）
2. **[工作流重试+阻断]** [daily-update.yml](file:///Users/jin/Library/Mobile%20Documents/com~apple~CloudDocs/Jin/jinbet/.github/workflows/daily-update.yml#L34-L74)：
   - 删掉 `continue-on-error: true`，删掉 `set +e / exit 0` 的吞错组合
   - 改用 `nick-fields/retry@v3` 最多 3 次尝试，间隔 30 秒，超时 8 分钟；3 次都失败则 **真正阻断CI，不进入推送步骤**
   - 再加一道独立的 "强制校验赛果完整性" 步骤：北京时间过 12 点时昨日赛果必须 ≥ 1 条，否则 `sys.exit(1)` 阻断
3. **[推送步骤set -euo pipefail]** 双分支推送全程严格 errexit，rebase/push 任一步失败就中止，不再吞错

### 防复发
- 赛果抓取结果是用户侧核心数据，任何步骤失败都不允许降级为"只更赔率"，只能重试 / 阻断，防止静默退化
- CI 出问题时 GitHub 会发失败邮件通知，管理员看到邮件即可手动 `workflow_dispatch` 重试，避免 3 次静默都漏掉
- `fetch_and_save_results` 里 yesterday 双计数（API拿到 vs 写入本地）是最低成本的"链路端到端自检"，保留不得删除
