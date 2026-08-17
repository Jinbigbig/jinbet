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

## 赛果同步链路与CI防护（v7.104.0 确立，v7.104.1 修正降级模式）

### 问题现象
2026-08-16 早间CI跑完后，体彩API已经有 8-15 的 30 场赛果数据，但线上 `results_data.json` 中 8-15 赛果始终为 0 条，用户看不到 8-15 任何比赛的比分与赔率回填。8-16 的 37 场赛果同样缺失。

### 根本根因（v7.104.1 确认）
**体彩赛果API（webapi.sporttery.cn）对 GitHub Actions 的美国IP返回 HTTP 567 反爬封锁**，这是稳定的 IP 级封锁，不是偶发故障：
- 网易赔率API（sports.163.com）不受影响，CI 每次都能正常抓取赔率
- 体彩赛果API在本地（中国IP）完全正常，在 CI 环境每次必失败
- 改进请求头（加完整浏览器 Sec-Fetch-* / sec-ch-ua / Origin 等）无法绕过，确认是 IP 封锁而非 WAF 反爬
- 3次重试全部被 HTTP 567 拒绝

### v7.104.0 初版修复（过度阻断）
1. 脚本层：`fetch_and_save_results` 加昨日赛果硬校验，API有但写入为0→`return False`
2. 工作流：移除 `set +e / exit 0` 吞错，改用 `nick-fields/retry@v3` 重试3次
3. 工作流：加强制校验步骤，过12点昨日赛果为0→`sys.exit(1)` 阻断推送
4. **问题**：体彩API是稳定IP封锁而非偶发故障，3次重试必全部失败→CI每次都阻断→连赔率也不推送了→比原来更糟

### v7.104.1 最终修复（降级模式+通知）
1. 赛果步骤 `continue-on-error: true` + retry 3次：体彩567时降级，不阻断CI
2. `RESULTS_OK` 环境变量标记赛果成功/失败
3. 赛果校验步骤仅在 `RESULTS_OK=true` 时执行（体彩567时跳过，不误阻断）
4. 推送步骤始终执行：commit message 标注"仅赔率(赛果API被封567)"或"赔率+赛果"
5. 赛果失败时自动创建 GitHub Issue 通知管理员补抓（每日去重，不重复创建）
6. 赔率步骤仍然严格：赔率失败=直接阻断CI（网易API稳定，失败才是真问题）

### 防复发
- CI 出 Issue 通知后，管理员在本地跑 `python update_odds_net.py --results-only` 补抓，推送 master + gh-pages
- 体彩API的IP封锁是基础设施层面的限制，除非更换 CI 运行位置（如自托管中国 runner），否则 CI 无法直接抓赛果
- 网易API不含比分数据，不能作为赛果备选数据源
