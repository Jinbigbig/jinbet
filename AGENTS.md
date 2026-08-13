# AGENTS.md - jinbet 项目约束

## 双分支架构

- `master` — 开发环境：源码、Python 脚本、CI 配置、测试脚本、工具目录、文档
- `gh-pages` — 生产环境：仅包含用户访问的静态文件（index.html, odds_data.json, .nojekyll, predictions/, version.txt, favicon.ico/png/svg），禁止包含开发文件
- 开发改动先提交 master，通过 CI 或手动同步静态文件到 gh-pages
- 推送到远端前必须先 `pull --rebase`，避免分支分叉导致 push 失败
- GitHub Actions 从 master 分支运行，将生成的静态文件推送到 gh-pages
- master 与 gh-pages 需保持双向同步，保留 2026-07-23/25/26 的原始报告

## 版本管理

- 遵循 SemVer 格式：MAJOR.MINOR.PATCH（当前版本：7.101.0）
  - PATCH (x.x.1)：bug 修复、样式调整
  - MINOR (x.1x.0)：新功能、功能修改
  - MAJOR (1.xx.0)：重大调整、架构重构
- `APP_VERSION` 常量驱动版本号，用于自动清理旧 localStorage 数据
- `version.txt` 使用时间戳格式，供 CI 检测是否需要刷新
- 版本更新时必须保留并自动迁移投注记录，使用 `jinbet_force_update` 标记强制加载线上赔率

## localStorage 规范

- 所有 key 必须带版本号（如 `jinbet_bets_7921`），版本更新时自动清理旧数据
- 赔率数据 key 统一使用 `STORAGE_KEY_ODDS` 变量，禁止硬编码
- 投注数据存在浏览器 localStorage 中，清缓存或换设备会丢失

## 数据格式约束

- 赔率 key 格式：`日期_主队_客队`（autoUpdateOdds 使用）
- `getOddsForMatch` 必须兼容多种 key 格式：`date_home_away`、`date_home vs away`、`home vs away`
- `updateScheduleFromOdds` 只能追加比赛，不能删除已有比赛
- 联赛字段优先从 `oddsData[key].league` 取，兜底填"国际赛"
- `aiCurrentMatches` 必须包含 `league` 字段，防止联赛标签丢失
- `loadAiSchedule` 函数中 `aiCurrentMatches` 必须携带 `league` 字段

### 队名归一化（v7.101.0 确立）

- Python 端所有队名标准化必须调用全局 `canonical_team_name(name)`，禁止在 `parse_lottery_json` / `main` 合并 / `id_map` 去重 / `normalize_result_team` 等任何位置自行实现归一化逻辑
- 新增队名映射只改 `RESULT_TEAM_NAME_MAP` 一处，`canonical_team_name` 会通过 `_get_sorted_team_mapping()` 自动按 key 长度从长到短匹配

### 去重规则（v7.101.0 确立）

- 所有去重阶段（schedule_data→schedule 合并、id_map 补赛程、final_dedup）必须使用 `canonical_team_name` 归一化后的**无序对** `(min(home,away), max(home,away))` 比较，禁止直接用字符串原文 `(home, away)` 比较
- matchId 优先级最高；matchId 缺失时 canonical pair 兜底
- 前端 `updateScheduleFromOdds` 的日期-星期校验（v7.100.4 引入）不可删除，它是脏数据流入浏览器的最后一道防线

### 赛果数据录入（v7.101.0 确立）

- `parse_results_json` 对有 `matchId`/`matchNumStr` 但暂缺 `fullScore` 的比赛必须保留占位 key，下次 CI 拿到比分后覆盖回填，禁止跳过丢弃
- `--full` 模式下 `fetch_and_save_results` 返回失败必须 `exit 1`，禁止降级为警告后继续提交无赛果版本
- `archive_results` 写入归档文件前必须调用 `is_weekday_match()` 校验日期与 `matchNumStr` 星期一致性，冲突时拒绝写入并打印 `[AUDIT][SKIP]`
- `archive_results` 结束时必须全量扫描 `results_history/` 目录做审计，脏数据打印 `[AUDIT][脏数据]` 告警

## 前端规范

- HTML 必须包含 Cache-Control、Pragma、Expires meta 标签，防止浏览器缓存旧版本
- 版本号通过 `APP_VERSION` 动态渲染到 id 为 `appVersion` 的 footer 元素
- Favicon 使用相对路径，多格式兼容（ICO、PNG、SVG），Safari 需要 `rel="shortcut icon"` 并优先 PNG
- 移除 apple-touch-icon 标签（会导致 Safari favicon 显示异常）
- 禁止使用 emoji 内联 SVG（存在编码问题）
- 使用绝对路径会导致子目录部署 404，统一用相对路径

## Git 规范

- commit 格式：`type(scope): 中文描述`
- type 类型：feat / fix / data / style / ci / report
- `.DS_Store` 必须被 gitignore 忽略

## 踩坑经验

- force push 会导致分支内容重复，保持分支独立
- 绝对禁止 `git push --force origin HEAD:gh-pages`；gh-pages 必须通过白名单静态文件（index.html / odds_data.json / results_data.json / 预测与归档目录 / favicon / .nojekyll / version.txt）从 master `git checkout master -- <白名单>` 后独立 commit + 普通 push，否则开发文件会暴露给用户访问、赛果修改只停留在本地文件不被 commit
- `--full` 模式分两个阶段：`main()` 更新赔率 + `fetch_and_save_results()` 更新赛果；每个阶段都要**分别** commit+push 两个分支，否则第二阶段写进 index.html 的赛果/归档"看起来抓到了但实际上没上线"
- `--results-only` 模式不能只调用 `fetch_and_save_results()` 就结束，必须在之后再执行一次 push_to_gh_pages（results-only 不走 main()，内部无自动 commit）
- 两个分支都用 `pull --rebase` 再普通 `push`，任何分支都不能 `--force`，rebase 冲突立即 abort 并交给人工，避免历史被覆盖破坏
- gh-pages 包含开发文件会暴露源码给用户
- 未暂存的修改切换分支会导致 CI 失败
- Safari 对 favicon 缓存极强，需提示用户手动清缓存
- Game 对象缺少 `match` 字段会在导入时显示 `undefined`
- `aiCurrentMatches` 与 `SCHEDULE` 数据源字段不一致会导致联赛标签丢失
- `merged_odds = dict(existing_odds)` 会把历史错日期 key 全量搬进新对象，合并后必须调用 `is_weekday_match()` 过滤残留，否则脏数据会通过 7 天 cutoff 机制持续累积
- Python `datetime.weekday()` 周一=0...周日=6，JS `Date.getDay()` 周日=0...周六=6，双端做星期校验时各自适配，不能直接复用对方的映射表
- 体彩赛果 API 有入库延迟，深夜比赛比分可能次日中午前仍未录入；占位 key 机制保证不丢场次，下次 CI 自动回填
- 三处队名归一化各自实现会导致 (home,away) pair 去重失败，产生重复比赛；必须统一走 `canonical_team_name()`
