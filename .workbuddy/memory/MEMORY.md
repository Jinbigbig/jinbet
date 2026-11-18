# JinBet 长期笔记（日更细则见 automations/<id>/memory.md）

## 流水线（顺序不可乱）
0. `git ls-remote origin master` 取 SHA → `git show <SHA>:update_odds_net.py > update_odds_net.py`（3410 行、`grep -c 变更判定`=3）→ 先 `--no-push` 再 `--no-push --results-only`（顺序错→ODDS 单引号 JS、步骤1「赔率 0/N」）。判据 `[DEDUP-ALIGN]`；跑前清 `_data_batch*.json`。
1. `mkdir -p predictions/<date>` → `_local_prepare.py`（0 场=无赛）→ `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py` → `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`（旋钮变更才重跑报告）→ `_update_index.py` → 根 index.html 有 `data-page-node-id` 才 checkout → 只推 gh-pages。**严禁 `git add -A`**：`git add -u` + 显式 add `predictions/<date>`。
- 链路核验 `_calc_result.json` 的 `chain` 须含「市场混合(」「比分矩阵对齐发布1X2」「Platt」「Kalman」「动态校准」；HEDGE 只在特定分支写入，缺失非异常。matches 可能是 list 或 dict。

## 分支与推送
- origin=SSH；只信 `git ls-remote`（`origin/*` 恒滞后）；禁 force/GITHUB_TOKEN。本地 `master` 是分叉死引用 → 取正本一律 ls-remote SHA。
- gh-pages 被拒：`git rebase --no-fork-point <云端SHA>`；撞死→`reset --hard <云端SHA>`+`checkout <好提交> -- .`+单提交推；续跑 `GIT_EDITOR=true`。
- 推 master：`git worktree add --detach "C:/Users/Jin/_wt_master" <SHA>` → 整文件 cp → `git add -- <单文件>` → commit → `push origin HEAD:refs/heads/master` → `worktree remove --force`。
- ⚠️ `reset --hard` 会删被跟踪 root `_` 脚本/league_data.json、抹 `.workbuddy/memory/` → 先 `git tag -f backup_<日期>_pre`。⚠️ `git show <未 fetch ref>` 会 fatal 并截成 0 字节 → 先 fetch。⚠️ 未跟踪文件挡 ff → `git checkout <远端SHA> -- <路径>`。
- ⚠️ results_history 净删几万行≠回滚（远端每日重写）；判据只看唯一 matchId。归档=dict（键 `日期_主队_客队`，值 26 字段）。

## 云端正本布局
- master `tools/prediction/`=脚本正本（去 `_` 前缀，LF）+ 根 update_odds_net.py/platt_params.json/league_profile.json。⚠️ `tools/prediction/gen_report.py` 远落后本地（无 std_rows/CUP_EXTRA），勿整文件覆盖。
- 脚本丢失恢复法：`git show origin/master:tools/prediction/<去下划线名>.py > _<名>.py`（已验：build_today_extras/fetch_league_data/fetch_injuries/fetch_lineups/flip_results_lib/fetch_sporttery_standings）。⚠️ `_flip_results_lib.py` 缺失则 dedup 静默失败（无 `[DEDUP-ALIGN]`，只在 stderr 报 FileNotFoundError）。
- gh-pages=运行态：predictions/、odds_data/results_data、odds_history/、scripts/、各 json（_calc_result/v34_state/strength_db/selection_tuning/weather/injuries/intel/hongcai/match_times/odds_ticks/sporttery_standings…）+ root score_engine.py/selection_algo.py/score_pick_optimize.py/_fetch_weather.py。root 其余 `_` 脚本 + league_data/qq_standings/fox_standings 未跟踪。

## 队名归一（最贵的坑）
canonical=官方简称；缺映射补 `RESULT_TEAM_NAME_MAP`。同编号双行→丢让球/比分盘与评级历史（症状：matches_data 行数>场次、_calc_result 该场 rq 空）；修完重跑 1→4。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛收缩 w=0.25；score_mix.w=0.3；`league_market_w` 0.65~0.95；改市场混合必重拟合 platt_params.json。保险丝 MAX_TOTAL4.2/MIN_TOTAL1.6/MAX_SINGLE3.2/MIN_SINGLE0.18/ZF1.0/EB_K40。SCORE_ALIGN 勿回退；冷启动不进比分精选。星级阈值 0.44/0.50/0.57/0.66。
- 五模块：BRIER_OPT/KALMAN ON·生效；HEDGE ON·观察（apply=False 故意）；CLV/DRIFT 只监控。
- 已否决勿再启用（均验证无增益）：比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS、市场权重>0.85、平局权重缩放、λ缩放、非平局优先、爆冷过滤。单点/方向已贴天花板。
- 比分推演过程不进公开页（`match_card()` 不挂 `chain_table()`）。

## 比分 / 两档 / 三引擎口径
- 首选唯一实现 `score_engine.headline_reorder`：带 `mkt` → argmax[log p_比分盘+0.3·log p_模型]，不要求同象限；无 mkt 退回 gap 规则。`head_day_cap=4`。⚠️ 禁重排 `top_scores`（恒纯概率降序）；首选另存 `headline`；跨象限渲染 `hm_mark`。落位 `_apply_headline_plan(out,TODAY,raw)`→`_headline_cells`；双档=除首选外概率最高两个。单日 15 场单点期望 2.3 场是天花板。
- 两档唯一入口 `SA.split_boards`，只调 `rank_pk/rank_bold`、`pk_result/bd_result`。TIER_PK=6/TIER_BD=4；档数=非冷启动 10 场 1 档、每+8 场+1（N_BASE=10/STEP=8/MAX=5）。生产值 bd_min_total=2、bd_gap=1、bd_exclusive=1、bd_lean_src='engine'；`bd_tuple` 必须 2 元组。护栏：改善≥0.3pp、天数<5 用默认。⚠️ 严禁在 `_gen_report.py`/`_optimize_selection.py` 另写排序或命中判定（曾分叉 31.8% vs 11.4%）。
- A=`_calc_engine`（4.1/4.4/4.5）；B=`score_engine`（4.2，prob_temp=1.20、market_mix=0.70 勿降）；C=`selection_algo`；另 4.3 进球/4.6 大比分。快照 prob_* 是百分数（0-100）。
- 半全场 `htft_analysis`（半场 λ=全场×HALF_SHARE 0.45，独立泊松 9 格）；每场 `htft` 入 `_calc_result`+快照；卡片「进球倾向」下 +4.3 末列；复盘 `_recap_htft()`。渲染 `HTFT_HI=40/HTFT_MID=26`（默认 60/45 会全灰）。
- 词表 可用/慎用/别跟；让球分级唯一 `rq_grade(prob,conf)`；快照无置信度用 `_rq_conf_of(hc)`。概率唯一渲染器 `_conf_tag(p,nd=1,hi=60,mid=45)`；`_conf_tag/_conf_bucket/_conf_split/_star_txt` 必须在 `build_league_sec` 前定义。
- 4.1「备选方向」：`op2*100<50` 渲染三率第二高者+概率，否则「—」。⚠️ 双选是三选二（基线 67%），禁当准确率。
- 红线 grep 公开页须空：`用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar`。

## 报告布局（11-08 定稿）
- 章节序：总览/市场信心/逐场/预测汇总/联赛与杯赛形势/串关推荐/动态校准/今日比分精选/大胆档。第六节自检卡只落 `_internal_strategy/<date>.md`（未跟踪），公开页只留两张串关表+串关前日回顾；免责条已删。
- 折叠唯一实现 `_fold(label,hint,body,cls,head_tag,open_)`，必须在 `_sub()` 之后、`deep_sec` 装配之前定义（否则 `match_card` NameError）。原生 `<details class="fold" data-fold>`；空内容不落块；无全局展开/收起控制条。
- ① 卡片只常驻「卡头+队名+赔率」「🎯比分与方向预测」，中间 11 项合成 `mid_fold`；② 4.2~4.6 `_sub_table(fold=True)`，**4.1 常驻**；③ 第五节 h2 常驻、按联赛独立折叠（`_fold_league_cards()` div 栈切卡，联赛名上移为折叠头并删原 `<h4>`）。
- 前日回顾装配层统一 `_wrap_recap()` 折叠（3 类渲染器/10 块），剥重复标题、日期并入折叠头。TOC `SKIP_TOC=/前日回顾|动态校准|^(方向|比分)串关推荐$/`；点目录项自动展开所在 `details.fold`。
- 说明段落全删：`.league-src/.inj-src/.std-legend/.parlay-note` CSS `display:none`。**保留**历史底蕴荣誉、前日命中统计、`cmp-note/league-note/pred-note` 结论、`fold-hint`。
- 4.2 表 9 列：编号/主队/客队/预期进球(主/客)/比分预测/比分双档/±1球覆盖/Top3覆盖/可信度。
- 回顶 `#backTop`：`right:14px;bottom:22px`，≤1399px `bottom:78px`（避开 toc-toggle）。天气 chip：`ok` 淡绿（降雨<70% 且风<35km/h）、`warn` 橙、`bad` 红。
- ⚠️ 折叠只减可见高度不减体积；判据用可见区是否还有回顾表格，不看文件大小。
- 第三节序：队名+排名→赔率三格→积分排名·赛事→H2H 两卡→底蕴→交锋+战绩→伤停→冷门/让球→比分与方向。入口 `std_rows(lg)`/`std_of(team,lg)`。窄屏 `@media(max-width:640px)` 用 `minmax(0,1fr)`。

## 榜源
- **主源=中国体育彩票**：`_fetch_sporttery_standings.py`→`sporttery_standings.json`。`webapi.sporttery.cn` 的 `getLeagueListV1`（枚举联赛+赛季，取 seasonList[0]）→ `getTablesV2?seasonId=&uniformLeagueId=`；一次 49 联赛、大陆简体。含 gf/ga 无 gd，`_std_teams` 已补 gd=gf-ga。`_gen_report.py` 加载 `SPORT_STD/SPORT_STD_AT`，`std_rows()` 与第五节体彩优先；单组 `std_league_card`、多组 `std_group_card`。**CUP_EXTRA 手写榜仅 `SPORT_OVERRIDE_CUP={'欧国联'}` 改用体彩**。json 键是联赛名。
- 兜底链（体彩无该联赛）：7M→腾讯 `qq_standings.json`→Fox `fox_standings.json`(SSR `<table id="live-standings-table-N">`)→UEFA `uefa_standings.json`（本机 timeout，用 WebFetch 落盘）。腾讯赛事 ID 欧冠5/英超8/意甲21/德甲22/西甲23/法甲24。渲染器 `std_table()`，分栏 `.lg-split`；分组赛 `std_group_card()` 只展开本日队小组。
- ⚠️ 7M 榜是港澳台译名 → 唯一归一处 `standings_alias.py::cn()`（11 联赛 200 队，幂等），三处必过：`_fetch_league_data` 落盘前、`_gen_report._std_teams`+`_qq_team`、`_build_today_extras` 读榜后。opencc 解决不了港译人名。
- ⚠️ 7M 会把两段榜拼进同组 → `parse_standing` 按 `tid` 去重、保留 `p` 最大行并重排名次；判据 `len(teams)==len({tid})`。

## 赛前信息
- 阵容 lineupstoday.com（`_fetch_lineups.py`→lineups.json），URL `/<league>/<home-slug>-<away-slug>-<DD-MM-YYYY>/`，slug 表 `_RAW_TEAMS`（存全称，报告用简称，查不到静默 skip）。区块 id `opstelling`/`absenties`，按 id 切块别按 h2；`is-twijfel`=存疑。`injury_html()` 优先 lineups.json（按 matchNumStr）→ 回退 injuries.json。`_ensure_side_data` 顺序：阵容→赛马会→天气→伤停兜底→开赛时间。
- 天气 `_fetch_weather.py`→weather.json（Open-Meteo 18–23 时）；**须步骤3 之后跑**（读 `_calc_result.json` today，同 `_fetch_referee.py`）。⚠️ 首轮常见 `_ssl.c:1015 handshake timed out`，**直接重跑即可**（会 merge），别按缺 TEAM_CITY 映射排查。
- 开赛时间 `_fetch_match_times.py`→match_times.json（网易 `matchList/1?days=` 的 `matchTime`，按 `jcNum`；结构 `times`+`day` 0=当日/1=次日）；卡片 `match-time` 后 `<span class="kickoff">` 再天气；校验 date==TODAY。
- 赛前情报 `_fetch_intel.py`→intel.json（直播吧公开新闻，按竞彩编号索引，含标题+链接+来源+摘要）；须步骤1 后跑，`_gen_report.py` 按编号注入逐场卡「赛前情报」块。
- 伤停 `_fetch_injuries.py`→injuries.json（仅德甲+荷甲）；`_fetch_injuries_extra.py`→injuries_extra.json（7M 军情+lineupstoday）。国家队赛事覆盖≈0，属源站缺口。
- 赔率时序 `_fetch_odds_ticks.py`→odds_ticks.json（`ticks`，键 `日期_主队_客队`，每点 `{t,胜,平,负,让球[]}`）；`_gen_report.py` **不消费**它，只服务 matlas。
- ⚠️ 红彩 `_fetch_hongcai.py`→hongcai.json 的 matchId 会指向旧场次 → 每次核对 `matches.<编号>.home/away` 与 `scripts/matches_data.json`，错配移入 `missing`（list）。重跑会写回错配。
- 实测不可用勿再试：Transfermarkt 405、premierinjuries 403、Sports.ru 403、OTempo 超时、premierleague.com JS、百度体育 SPA。

## 复盘/诊断
- 指标：方向/双选/比分单点/比分双档/半全场首选/总进球众数/λ偏差。连续多日方向<50% 或 λ偏差>0.2 → 重拟合。`daily_diag.py --days 10`。
- 长期基准（约 2478 场有赔率快照）：方向 51.2%（市场去水 51.9%，已贴天花板）/单点 15.1%/双档 24.0%/比分精选前三档累计 39.1%/大胆档第一档 ~22%/头条±1 球 68.2%。⚠️ 旧「599 场」口径已过期；<300 场不调参。

## 赛果补录（每日 08:00 automation）
- `_sync_results.py`（master `tools/prediction/sync_results.py`）：对齐远端→`--no-push --results-only`→`[变更判定]`→0/0 不推→`commit -- pathspec`→push。
- ⚠️ 不能直接 `update_odds_net.py --results-only`（硬要求 master 分支）。⚠️ `existing_results` 必须优先读 results_data.json（26 字段），读 index.html 的 `const RESULTS` 会丢 3242 条。⚠️ 变更判定须 `_norm()`。

## Matlas（C:\Users\Jin\matlas，零 import）
- jinbet=算，Matlas=发（per-match 页/留档/llms.txt/sitemap/Schema.org）。耦合仅 `matlas/models.py` 契约 v1.0。仓库 Jinbigbig/matlas：main=源码+数据（`_site/` 不进）、gh-pages=产物。
- 顺序：`import_jinbet.py` → `_restore_extras.py`（在 `C:/Users/Jin/_matlas_tools/`，dry-run→缺>0 才 `--apply`→复核 0）→ `python -m matlas.fetch_squads` → `enrich_squads` → `build.py --strict` → `SKIP_BUILD=1 TMPDIR=/c/tmp/matlas-trash bash publish.sh`。⚠️ `import_jinbet.py` 有损（清历史 injuries/weather/form_net/mood）→ 必须事后 restore。⚠️ `publish.sh` 护栏：`data/` 以外改动拒发布。⚠️ 每轮只发布一次。
- 线上 `jinbigbig.github.io/matlas/` + `matlas.app.workbuddy.host/?sharecode=…`（裸路径 403）；当日页 `/matlas/days/<date>.html`；红线落 `matlas/rules.py`；`prob_tag()` 唯一渲染器。时序在 day json 的 `match.extras.odds_ticks`（不在顶层）；`_ticks_for()` 会漏「谢周三↔谢菲尔德星期三」这类简称↔全称。
- 球员情报源=球小策 `player-rankings` 的 `ABV2_DC.nonce` + admin-ajax `abv2_dc_rankings`（nonce 现取，写死即 403）；对外仅 6 项（GIM/OTI/DII/状态/稳定度/疲劳）。渲染 `pages.py::_squad_panel`，每队 ≥8 人才出。详情页序：结论→基本面→人员→市场推演→环境。
