# JinBet 长期笔记（日更细则见 automations/<id>/memory.md）

## 流水线（顺序不可乱）
0. `git ls-remote origin master` 取 SHA → `git show <SHA>:update_odds_net.py > update_odds_net.py`（3410 行、`grep -c 变更判定`=3）→ 先 `--no-push` 再 `--no-push --results-only`（顺序错→ODDS 单引号 JS、步骤1「赔率 0/N」）。判据 `[DEDUP-ALIGN]`；跑前清 `_data_batch*.json`。
1. `mkdir -p predictions/<date>` → `_local_prepare.py`（0 场=无赛）→ `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py` → `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`（旋钮变更才重跑报告）→ `_update_index.py`（日期/场次/联赛写死）→ 根 index.html 有 `data-page-node-id` 才 checkout → 只推 gh-pages。**严禁 `git add -A`**：`git add -u` + 显式 add `predictions/<date>`。
- 链路核验 `_calc_result.json`（calibration/matches/today；matches 内 `chain` 长字符串）：须含「市场混合(」「比分矩阵对齐发布1X2」「Platt」；stdout ON·生效/ON·观察。

## 分支与推送
- origin=SSH；只信 `git ls-remote`（本地 `origin/*` 恒滞后）；禁 force/GITHUB_TOKEN。
- ⚠️ 本地 `master` 是已分叉死引用（11-08 `897636ae`，3334 行、无 `[变更判定]`）→ 取正本一律 `origin/master` 或 ls-remote SHA，绝不用裸 `master`。
- gh-pages 被拒：`git rebase --no-fork-point <云端SHA>`；撞死→`reset --hard <云端SHA>`+`checkout <好提交> -- .`+单提交推；续跑 `GIT_EDITOR=true`。
- 推 master：`git worktree add --detach "C:/Users/Jin/_wt_master" <SHA>` → 整文件 cp → `git add -- <单文件>` → commit → `push origin HEAD:refs/heads/master` → `worktree remove --force`。diff 用普通 `git diff --stat`。
- ⚠️ `reset --hard` 删被跟踪 root `_` 脚本/league_data.json、抹 `.workbuddy/memory/` 改动 → 先 `git tag -f backup_<日期>_pre`。⚠️ `git show <未 fetch ref>:路径` 会 fatal 并把目标截成 0 字节 → 先 fetch。⚠️ 未跟踪文件挡 ff → `git checkout <远端SHA> -- <路径>` 恢复。
- ⚠️ results_history 净删几万行≠回滚（远端每日重写）；判据只看唯一 matchId 是否下降。归档=dict（键 `日期_主队_客队`，值 26 字段）。

## 云端正本布局
- master `tools/prediction/`=脚本正本（去 `_` 前缀，LF）+ 根 update_odds_net.py/platt_params.json/league_profile.json。⚠️ `tools/prediction/gen_report.py` 落后（无 CUP_EXTRA 杯赛卡、行数差 6671）→ 勿覆盖本地 `_gen_report.py`。
- gh-pages=运行态：predictions/、odds_data/results_data、odds_history/、scripts/、各 json（_calc_result/v34_state/strength_db/selection_tuning/weather/injuries…）+ root 的 score_engine.py/selection_algo.py/score_pick_optimize.py/_fetch_weather.py（少数 `_` 被跟踪）。root 其余 `_` 脚本 + league_data/qq_standings/fox_standings 未跟踪。

## 队名归一（最贵的坑）
canonical=官方简称；缺映射补 `RESULT_TEAM_NAME_MAP`，别手工删。同编号双行→丢让球/比分盘与评级历史（症状：matches_data 行数>场次、_calc_result 该场 rq 空）；修完重跑 1→4。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛收缩 w=0.25；score_mix.w=0.3；`league_market_w` 0.65~0.95；改市场混合必重拟合 platt_params.json。保险丝 MAX_TOTAL4.2/MIN_TOTAL1.6/MAX_SINGLE3.2/MIN_SINGLE0.18/ZF1.0/EB_K40。SCORE_ALIGN 勿回退；冷启动不进比分精选。星级阈值 0.44/0.50/0.57/0.66。
- 五模块：BRIER_OPT/KALMAN ON·生效；HEDGE ON·观察（apply=False 故意）；CLV/DRIFT 只监控。
- 已否决勿再启用：比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS、市场权重>0.85、平局权重缩放、λ缩放、非平局优先、爆冷过滤。单点/方向已贴天花板。
- 比分推演过程不进公开页（`match_card()` 不挂 `chain_table()`）。

## 比分 / 两档 / 三引擎口径
- 首选唯一实现 `score_engine.headline_reorder`：带 `mkt` → argmax[log p_比分盘+0.3·log p_模型]，不要求同象限；无 mkt 退回 gap 规则。`head_day_cap=4`。⚠️ 禁重排 `top_scores`（恒纯概率降序）；首选另存 `headline`；跨象限渲染 `hm_mark`。落位 `_apply_headline_plan(out,TODAY,raw)`→`_headline_cells`；双档=除首选外概率最高两个。单日 15 场单点期望 2.3 场是天花板。
- 两档唯一入口 `SA.split_boards`，只调 `rank_pk/rank_bold`、`pk_result/bd_result`。TIER_PK=6/TIER_BD=4；档数=非冷启动 10 场 1 档、每+8 场+1（N_TIER_BASE=10/STEP=8/MAX=5）。生产值 bd_min_total=2（11-12 起采纳）、bd_gap=1、bd_exclusive=1、bd_lean_src='engine'；`bd_tuple` 必须 2 元组。护栏：改善≥0.3pp、天数<5 保留默认。⚠️ 严禁在 `_gen_report.py`/`_optimize_selection.py` 另写排序或命中判定（曾分叉 31.8% vs 11.4%）。
- A=`_calc_engine`（4.1/4.4/4.5）；B=`score_engine`（4.2，prob_temp=1.20、market_mix=0.70 勿降）；C=`selection_algo`；另 4.3 进球/4.6 大比分。
- 半全场 `htft_analysis`（半场 λ=全场×HALF_SHARE 0.45，独立泊松 9 格）；每场 `htft` 入 `_calc_result`+快照；卡片「进球倾向」下 +4.3 末列；复盘 `_recap_htft()`。渲染 `HTFT_HI=40/HTFT_MID=26`（默认 60/45 会全灰）。
- 词表 可用/慎用/别跟；让球分级唯一 `rq_grade(prob,conf)`；快照无置信度用 `_rq_conf_of(hc)`。概率唯一渲染器 `_conf_tag(p,nd=1,hi=60,mid=45)`；`_conf_tag/_conf_bucket/_conf_split/_star_txt` 必须在 `build_league_sec` 前定义。
- 4.1「备选方向」：`op2*100<50` 渲染三率第二高者+概率，否则「—」。回测 599 场 <45% 档 43%→73%、45-50 56%→82%、≥60 69%→88%。⚠️ 双选是三选二（基线 67%），禁当准确率。
- 红线 grep 公开页须空：`用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar`。

## 报告布局（11-08 定稿）
- 章节序：总览/市场信心/逐场/预测汇总/联赛与杯赛形势/串关推荐/动态校准/今日比分精选/大胆档。**第六节 9 张策略自检卡 11-08 起内部化**：只落 `_internal_strategy/<date>.md`（未跟踪、不发布），公开页只留两张串关表+串关前日回顾；风险提示免责条也已删。
- 折叠唯一实现 `_fold(label,hint,body,cls,head_tag,open_)`，定义在 `_sub()` 之后、`deep_sec` 装配之前（否则 `match_card` NameError）。原生 `<details class="fold" data-fold>`，禁用 JS 也能展开；空内容不落块；CSS 在追加块末尾；`.fold-cta::after` 纯 CSS 切文字。⚠️ 不要全局展开/收起控制条（已删）；`FOLD_JS` 只留 beforeprint 全展开。
- ① 每场卡片只常驻「卡头+队名+赔率」「🎯比分与方向预测」，中间 11 项合成一条 `mid_fold`；② 4.2~4.6 `_sub_table(fold=True)`，**4.1 常驻**（走 `_fold(open_=True)` 共用外壳，回顾条才落在区块内）；③ 第五节 h2 常驻、**13 个按联赛独立折叠**（`_fold_league_cards()` 用 div 栈切卡，联赛名上移为折叠头并删原 `<h4>`；已去 `.league-overview-grid` 外层，与 4.x 等宽）。
- 所有前日回顾在装配层统一 `_wrap_recap()` 折叠（3 类渲染器/10 块）；它剥掉内容区自带重复标题、把日期并入折叠头。TOC `SKIP_TOC=/前日回顾|动态校准|^(方向|比分)串关推荐$/`（14 项，第六节只留一个 h2），目录项与滚动高亮拆两份列表；点目录项自动展开所在 `details.fold`，`spy()` 跳过 `offsetParent===null`。
- 11-08 说明段落全删：`_sub_table` 不渲染 note；四章说明、比分精选/大胆档前后说明、积分榜来源、回顾口径句、卡片让球分档句均删；`.league-src/.inj-src/.std-legend/.parlay-note` 用 CSS `display:none` 隐藏（56 处）。**保留**历史底蕴荣誉 notes、前日命中统计数字、`cmp-note/league-note/pred-note` 结论、`fold-hint`。
- 4.2 表 9 列（去掉「可能进球(主)/(客)」；`_mode_h/_mode_a` 已删）：编号/主队/客队/预期进球(主/客)/比分预测/比分双档/±1球覆盖/Top3覆盖/可信度。
- 回顶 `#backTop` 在 `TOC_BLOCK`/`FOLD_JS`（滚动>400px 显示、平滑、尊重 reduced-motion、打印隐藏）；`right:14px;bottom:22px` 与 `toc-toggle` 冲突 → ≤1399px `bottom:78px`，≥1400px 回 22px。
- 天气 chip 三档：`ok` 淡绿底（未触发警示：降雨<70% 且风<35km/h）、`warn` 橙、`bad` 红。
- ⚠️ 折叠只减可见高度不减体积；判据用可见区是否还有回顾表格，不看文件大小。
- 榜源四级链 7M→腾讯 `qq_standings.json`(limit=50)→Fox `fox_standings.json`(SSR `<table id="live-standings-table-N">`)→UEFA `uefa_standings.json`（本机 timeout，用 WebFetch 落盘）。腾讯/Fox/UEFA 走 `std_league_card()`；分组赛 `std_group_card()` 只展开本日队小组；收官（场次齐平且≥3）不做名次模拟。腾讯赛事 ID 欧冠5/英超8/意甲21/德甲22/西甲23/法甲24。积分榜唯一渲染器 `std_table()`，左右分栏 `.lg-split`(1fr 1fr，≤900px 单列)。
- ⚠️ 7M 榜全是港澳台译名，`name`=繁体港译、`name_zh`=简体港译 → 唯一归一处 `standings_alias.py::cn()`（11 联赛 200 队，幂等），三处必过：`_fetch_league_data` 落盘前、`_gen_report._std_teams`+`_qq_team`、`_build_today_extras` 读榜后。opencc 只能繁→简，解决不了港译人名。
- ⚠️ 7M 会把两段榜拼进同组（芬超 24 项）→ `parse_standing` 按 `tid` 去重、保留 `p` 最大行并重排名次；判据 `len(teams)==len({tid})`。
- 第三节序：队名+排名→赔率三格→积分排名·赛事→H2H 两卡→底蕴→交锋+战绩→伤停→冷门/让球→比分与方向。入口 `std_rows(lg)`/`std_of(team,lg)`。不写「怎么看表」说明句；缺口用最短一句。窄屏 `@media(max-width:640px)` 用 `minmax(0,1fr)`。

## 赛前信息
- 阵容主源 lineupstoday.com（`_fetch_lineups.py`→lineups.json），URL `/<league>/<home-slug>-<away-slug>-<DD-MM-YYYY>/`，slug 表 `_RAW_TEAMS`（存全称，报告用简称，查不到静默 skip → 欧战新军补别名；同步 master）。区块 id `opstelling`/`absenties`，按 id 切块别按 h2；`is-twijfel`=存疑；「Not in the squad」丢弃。`injury_html()` 优先 lineups.json（按 matchNumStr）→ 回退 injuries.json。`_ensure_side_data` 顺序：阵容→赛马会→天气→伤停兜底→开赛时间。
- 天气 `_fetch_weather.py`→weather.json（Open-Meteo 18–23 时，bad 降雨≥70% 或风≥35km/h）；**须步骤3 之后跑**（读 `_calc_result.json` today，同 `_fetch_referee.py`）。缺场次补 TEAM_CITY/CITY_ZH。
- 开赛时间 `_fetch_match_times.py`→match_times.json（网易 `matchList/1?days=...` 的 `matchTime`，date±1，按 `jcNum`）；卡片 `match-time` 后 `<span class="kickoff">` 再天气；加载校验 date==TODAY（编号每周复用）。
- ⚠️ 红彩 matchId 会指向旧场次（不校验队名）→ 每次核对 `hongcai.json` home/away，错配移入 `missing`。
- 实测不可用勿再试：Transfermarkt 405、premierinjuries 403、Sports.ru 403、OTempo 超时、premierleague.com JS、百度体育 SPA。

## 复盘/诊断
- 六指标 方向/方向双选/比分单点/比分双档/半全场首选/总进球众数/λ偏差。连续多日方向<50% 或 λ偏差>0.2 → 重拟合。`daily_diag.py --days 10` 或 `gen_review.py --kpi`。
- 长期基准（daily_diag 长期口径，约 2478 场有赔率快照）：方向 51.2%（市场去水 51.9%，已贴天花板）/单点 15.1%/双档 24.0%/比分精选前三档累计 39.1%/大胆档第一档约 22%/头条±1 球 68.2%。⚠️ 旧「599 场」口径（方向 57.8%/双选 81.0%）样本已过期，勿再引用；<300 场不调参。

## 赛果补录（每日 08:00 automation）
- `_sync_results.py`（master `tools/prediction/sync_results.py`）：对齐远端→`--no-push --results-only`→`[变更判定]`→0/0 不推→`commit -- pathspec`→push。
- ⚠️ 不能直接 `update_odds_net.py --results-only`（硬要求 master 分支）。⚠️ `existing_results` 必须优先读 results_data.json（26 字段），读 index.html 的 `const RESULTS` 会丢 3242 条。⚠️ 变更判定须 `_norm()`。待办：归档 1637 条带「让球」记录可回填。

## Matlas（C:\Users\Jin\matlas，零 import）
- jinbet=算，Matlas=发（per-match 页/留档/llms.txt/sitemap/Schema.org）。耦合仅 `matlas/models.py` 契约 v1.0。仓库 github.com/Jinbigbig/matlas：main=源码+数据（`_site/` 不进）、gh-pages=产物。
- 顺序：`import_jinbet.py` → `_restore_extras.py`（脚本在 `C:/Users/Jin/_matlas_tools/`，dry-run→`--apply`→复核 0）→ `python -m matlas.fetch_squads` → `enrich_squads` → `build.py --strict` → `TMPDIR=/c/tmp/matlas-trash bash publish.sh`（可 `SKIP_BUILD=1`）。⚠️ `import_jinbet.py` 有损（清空历史 injuries/weather/form_net/mood）→ 必须事后 restore。⚠️ `publish.sh` 护栏：`data/` 以外改动拒发布。
- 线上 `jinbigbig.github.io/matlas/` + `matlas.app.workbuddy.host/?sharecode=…`（裸路径 403）；当日页 `/matlas/days/<date>.html`；域名只在 `config.DEFAULT_BASE_URL`；红线落 `matlas/rules.py`（`--strict` 非零退出）；`prob_tag()` 唯一渲染器。
- 球员情报源=球小策 `player-rankings` 的 `ABV2_DC.nonce` + admin-ajax `abv2_dc_rankings`（nonce 每次现取，写死即 403 `-1`）；对外仅 6 项（GIM/OTI/DII/状态/稳定度/疲劳）；球员名不可跨源匹配。渲染 `pages.py::_squad_panel`，每队 ≥8 人才出，评分走普通数字。详情页序：结论→基本面→人员→市场推演→环境；「留档核验」整块删除（`_ledger`→`_settled_panel` 只留赛果+四维命中）。
