# JinBet 长期笔记（日更细则见 automations/<id>/memory.md）

## 流水线（顺序不可乱）
0. `git fetch origin master` → `git show $(git ls-remote origin master|cut -f1):update_odds_net.py > update_odds_net.py` → 先 `--no-push` 再 `--no-push --results-only`（顺序错→ODDS 单引号 JS）。判据 `[DEDUP-ALIGN]`；跑前清 `_data_batch*.json`。
1. `mkdir -p predictions/<date>` → `_local_prepare.py`（0 场=无赛）→ `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py`。链路标记只在 stdout：grep `MARKET_BLEND_PROB|SCORE_ALIGN|ON·生效|ON·观察`；实际文案「市场概率混合已启用(V3.2)」「比分矩阵对齐发布的 1X2 已启用(V3.3)」。→ `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`（变更则重跑报告）→ 索引 `_update_index.py`（日期/场次/联赛写死，每日先改）→ 根 index.html 有 `data-page-node-id` 才 checkout → 只推 gh-pages。**严禁 `git add -A`**（`git add -u` + 显式 add 目录）。

## 分支与推送
- origin=SSH；只信 `git ls-remote`（本地 `origin/*` 恒滞后）；禁 force/GITHUB_TOKEN。
- gh-pages 被拒：`rebase --no-fork-point <云端SHA>`（不带第二参数）；撞死→`reset --hard <云端SHA>`+`checkout <好提交> -- .`+单提交推；续须 `GIT_EDITOR=true`。
- 推 master：`git worktree add --detach "C:/Users/Jin/_wt_master" <SHA>`（须 C:/ 风格）→覆盖→`git add -- <单文件>`→commit→`push origin HEAD:refs/heads/master`→`worktree remove --force`。
- ⚠️ `reset --hard` 会删被跟踪的 root `_` 脚本与 league_data.json、抹掉 `.workbuddy/memory/` 未提交改动 → 先 `git tag -f backup_<日期>_pre`；记忆随当日 commit 入库。
- ⚠️ `git show <未 fetch 的 ref>:路径` 会 fatal 且把目标截成 0 字节 → 先 fetch 再 show。
- ⚠️ 未跟踪文件挡 ff：只删不够（可能已跟踪，删后是 ` D`）→ `git checkout <远端SHA> -- <路径>` 恢复基线。
- ⚠️ results_history 净删几万行≠回滚（远端每日自动提交会重写膨胀归档）；判据只用「唯一 matchId 是否下降」。归档结构=dict（键 `日期_主队_客队`，值 26 字段），按 list 解析得 0 条。
- ⚠️ 同步 master 时 `git -c core.autocrlf=false diff` 会让全树显示变更（LF/CRLF 噪声）。

## 云端正本布局
- master `tools/prediction/`=脚本正本（去 `_` 前缀，LF）+ 根 update_odds_net.py/platt_params.json/league_profile.json。⚠️ `tools/prediction/gen_report.py` 已落后（无 CUP_EXTRA 杯赛卡）→ 勿用 master 覆盖本地 `_gen_report.py`。
- gh-pages=数据运行态（predictions/、odds_data/results_data、odds_history/、scripts/、_calc_result.json、v34_state.json、strength_db.json、selection_tuning.json、weather/injuries/injuries_extra/referee/hongcai/match_times/odds_ticks/lineups/hkjc.json）+ 仅 root 的 score_engine.py/selection_algo.py/score_pick_optimize.py。root `_` 脚本未跟踪 → 只同步 master。

## 队名归一（最贵的坑）
canonical=官方简称（沃夫斯堡、布城、奥斯KFUM、卡塔尔23…）；缺映射补 `RESULT_TEAM_NAME_MAP`，别手工删。同编号双行→丢让球/比分盘与评级历史；症状=matches_data 行数>场次、_calc_result 该场 rq 空；修完重跑 1→4。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛收缩 w=0.25；score_mix.w=0.3；市场权重动态 `league_market_w` 0.65~0.95；改市场混合必重拟合 platt。保险丝 MAX_TOTAL4.2/MIN_TOTAL1.6/MAX_SINGLE3.2/MIN_SINGLE0.18/ZF1.0/EB_K40。SCORE_ALIGN 勿回退；冷启动不进比分精选。星级 0.44/0.50/0.57/0.66。
- 五模块：BRIER_OPT/KALMAN ON·生效；HEDGE ON·观察（apply=False 故意）；CLV/DRIFT 只监控。
- 已否决勿再启用：比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS、市场权重>0.85、平局权重缩放、λ缩放、非平局优先、爆冷过滤。单点/方向已贴天花板，只剩扩覆盖或加场次。
- 比分推演过程不进公开页：`match_card()` 不挂 `chain_table()`。

## 比分口径（09-22 定稿）
- 首选唯一实现 `score_engine.headline_reorder`：带 `mkt`（比分盘去水）→ argmax[log p_比分盘+0.3·log p_模型]，不要求与方向同象限；无 mkt 退回旧 gap 规则。同日同比分上限 `head_day_cap=4`。
- ⚠️ 禁止重排 `top_scores` 位次（恒纯概率降序）；首选另存 `headline`。跨象限渲染 `hm_mark`，别写「方向倾向内的首选比分」。
- 落位走引擎B 候选格：`_apply_headline_plan(out,TODAY,raw)`→`_headline_cells`。双档=除首选外概率最高的两个。单日 15 场单点期望 2.3 场是天花板，勿反复提示用户。

## 两档（selection_algo 唯一实现）
- 唯一入口 `SA.split_boards`；只调 `SA.rank_pk/rank_bold`、`pk_result/bd_result`。TIER_PK=6/TIER_BD=4；档数=10 场 1 档、每 +8 场 +1 档（N_TIER_BASE=10/N_TIER_STEP=8/TIER_MAX=5），按当日全部非冷启动场次算、两榜同档数。
- 生产值：bd_min_total=3、bd_gap=1、bd_exclusive=1、bd_lean_src='engine'。护栏：改善≥0.3pp、天数<5 保留默认。`bd_tuple` 必须 2 元组。
- 严禁在 `_gen_report.py`/`_optimize_selection.py` 另写排序或命中判定（曾口径分叉：大胆档虚高 31.8% vs 真实 11.4%）。

## 三引擎 / 渲染纪律
- A=`_calc_engine`（4.1 胜负/4.4 让球/4.5 冷门）；B=`score_engine`（4.2 比分，prob_temp=1.20、market_mix=0.70 勿降）；C=`selection_algo`（两档）；另 4.3 进球/4.6 大比分。
- 半全场：`htft_analysis`（半场 λ=全场×`HALF_SHARE`0.45，独立泊松 9 格，纯模型）；每场 `htft` 入 `_calc_result`+快照；卡片「进球倾向」下「半全场」行 +4.3 表末列；复盘 `_recap_htft()`。渲染 `HTFT_HI=40/HTFT_MID=26`（默认 60/45 会全灰）。
- 词表统一 可用/慎用/别跟；让球分级唯一实现 `rq_grade(prob,conf)`；快照无置信度用 `_rq_conf_of(hc)` 还原。
- 概率唯一渲染器 `_conf_tag(p,nd=1,hi=60,mid=45)` → `pct-hi|pct-mid|pct-lo`，禁裸百分比 span；`_conf_tag/_conf_bucket/_conf_split/_star_txt` 必须在 `build_league_sec` 之前定义。
- 4.1「备选方向」列：`op2*100<50` 时渲染三率第二高者+概率，否则「—」。回测 599 场：<45% 档 43%→73%、45-50 档 56%→82%、≥60 档 69%→88%。⚠️ 双选是三选二（基线 67%），禁当准确率。
- 红线 grep 公开页须空：`用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar`。

## 报告布局（10-22 定稿）
- 章节序：总览/市场信心/逐场/预测汇总/联赛与杯赛形势/核心策略与风险提示/动态校准/今日比分精选/大胆档。
- 第五节左积分榜右形势；积分榜完整表格常驻（禁色块/折叠），唯一渲染器 `std_table()`；外层单列，分栏只在卡内（`.lg-split` 1fr 1fr，≤900px 单列）。「关键线」「历史补跑说明」每赛事一次。
- 榜源四级链：7M→腾讯 `qq_standings.json`（limit=50）→Fox `fox_standings.json`（SSR 正则 `<table id="live-standings-table-N">`，bifrost 恒 401）→UEFA `uefa_standings.json`（本机 timeout，用 WebFetch 抓官方页落盘）。腾讯/Fox/UEFA 用 `std_league_card()`；分组赛 `std_group_card()` 只展开本日队小组；收官（场次齐平且≥3）不做名次模拟。腾讯赛事 ID：欧冠5/英超8/意甲21/德甲22/西甲23/法甲24（18 无效）。
- 第三节序：队名+排名 → 赔率三格 → 积分排名·赛事 → H2H 两卡 → 历史底蕴 → 历史交锋+近期战绩（始终并列）→ 伤停与赛前分析 → 冷门/让球 → 比分与方向。榜位入口 `std_rows(lg)`/`std_of(team,lg)`。
- 文案红线：不写「怎么看表」说明句；缺口用最短一句（`暂无交锋记录`）。窄屏 `@media(max-width:640px)` 用 `minmax(0,1fr)`。

## 赛前信息：阵容/伤停 + 天气 + 时间
- 主源 lineupstoday.com（`_fetch_lineups.py`→lineups.json），URL `/<league>/<home-slug>-<away-slug>-<DD-MM-YYYY>/`，slug 表 `_RAW_TEAMS`。⚠️ 表存全称、报告用简称，查不到静默 skip（reason=unmapped）→ 欧战新军须补简称别名；改表同步 master `tools/prediction/fetch_lineups.py`。区块 id 荷兰语：`opstelling`（ov-veld__speler）、`absenties`（li.ov-absentie），按 id 切块别按 h2。赛后页无 `absenties`；`is-twijfel` 标注存疑；「Not in the squad」丢弃。
- `injury_html()` 优先 lineups.json（按 matchNumStr）→ 阵型徽标+缺阵数+`<details class="inj-xi">` 折首发；无数据回退 injuries.json。天气 `_fetch_weather.py`→weather.json（Open-Meteo，18–23 时，bad≥35km/h 或降雨≥70%）；**读 `_calc_result.json` 的 today → 步骤3 之后跑**；缺场次=TEAM_CITY/CITY_ZH 没该队，补两表即 100%；该脚本在 gh-pages 被跟踪，master 正本常更旧 → 整文件 cp。`_ensure_side_data` 顺序：阵容→赛马会→天气→伤停兜底→开赛时间（jobs 3 元组）。
- 开赛时间：`_fetch_match_times.py`→match_times.json，源=网易竞彩赛程 `matchList/1?days=YYYY-MM-DD 12:00:00` 的 `matchTime`（北京毫秒），抓 date±1 合并、按 `jcNum` 建表。卡片 `match-time` 后紧 `<span class="kickoff">` 再天气；入口 `kickoff_of(num)`；加载须校验 date==TODAY（编号每周复用）。
- ⚠️ 红彩 matchId 会指向旧场次：`_fetch_hongcai.py` 直接把 matches_data 的 matchId 当 matchInfoId，返回可能是别的比赛（11-03 周二002→「水户蜀葵vs山口雷诺」）。必须核对 `hongcai.json` 的 home/away，错配移入 `missing`；任何一次重跑都会写回，matlas 环节后要再剔。队名差异如「斯达/特尔斯达」属别名，不算错配。
- 实测不可用勿再试：Transfermarkt 405、premierinjuries 403、Sports.ru 403、OTempo 超时、premierleague.com JS、百度体育 SPA。

## 复盘/诊断
- 六指标：方向 / 方向双选 / 比分单点 / 比分双档 / 半全场首选 / 总进球众数 / λ偏差。连续多日方向<50% 或 λ偏差>0.2 → 提示重拟合。问准不准 → `daily_diag.py --days 10` 或 `gen_review.py --kpi`。
- 累计（599 场 since 09-08）：方向 57.8%/双选 81.0%/单点 10.2%/双档 21.2%/半全首选 34.9%/总进球 20.7%。同口径 658 场（09-05→10-25）：方向 55.9%/比分首选 11.2%/双档 21.0%/总进球首选 19.0%·前二 38.4%/半全 33.7%·前二 52.1%·前三 65.0%。
- ⚠️「单点约 15%」是 4036 场旧口径，近期实测 10~11%，勿引用。⚠️ 杯赛不降权（杯赛 61.3% > 联赛 56.3%）。⚠️ <300 场不调参。对标球小策 62% 是双选口径（拆开单选 53.9%/双选 62.1%），同口径六项我们赢五项；其 xG/OTI/GIM 不外泄。HALF_SHARE 0.30~0.35 未显著，暂不改。

## 赛果补录定时任务（每日 08:00）
- 入口 `_sync_results.py`（master `tools/prediction/sync_results.py`）：[0/3] 对齐远端 → `--no-push --results-only` 落盘 → `[变更判定]` → 0/0 不推 → `git add` 5 路径 + `commit -- pathspec` → push（被拒才 `rebase --autostash`）。
- `align_to_remote()` 在抓取之前：纯落后 `merge --ff-only`（脏文件挡退 `reset --keep`）；分叉且本地全是 `data: 赛果补录` → `reset --keep` 重算；含人工提交退出码 2 交人工。10-28 补 `unblock_worktree()`（未跟踪备份到 `_untracked_backup/<时间戳>/` 后移走，脏跟踪文件 `git checkout HEAD -- <路径>`）+ `force_align()` 四级阶梯（ff-only→清理后 ff-only→reset --keep→reset --mixed+只还原 RESULT_FILES，绝不用 reset --hard），失败 `fail(...,2)`。
- ⚠️ commit 必带 pathspec + 之后 `git reset -q`。⚠️ 不能直接跑 `update_odds_net.py --results-only`（`push_to_gh_pages()` 硬要求 master 分支）。⚠️ `existing_results` 必须优先读 results_data.json（26 字段），读 index.html 的 `const RESULTS` 静默丢 3242 条让球/比分盘/总进球/半全场。⚠️ 变更判定须 `_norm()` 归一。
- 待办：归档仍有 1637 条带「让球」记录可回填 results_data.json。

## 兄弟项目 Matlas（C:\Users\Jin\matlas，零 import）
- 定位：jinbet=算，Matlas=发（per-match 落地页、留档、llms.txt/sitemap/Schema.org）。唯一耦合=`matlas/models.py` 契约 v1.0。仓库 github.com/Jinbigbig/matlas（SSH）：`main`=源码+数据（`_site/` 不进 main）、`gh-pages`=产物。发布 `./publish.sh`（`TMPDIR=/c/tmp/matlas-trash`，可 `SKIP_BUILD=1`），勿手工混提交。
- 线上：`jinbigbig.github.io/matlas/` + `matlas.app.workbuddy.host/?sharecode=…`（裸路径 403）。域名只在 `config.DEFAULT_BASE_URL`。红线落成 `matlas/rules.py`（`build.py --strict` 非零退出）；`prob_tag()` 唯一渲染器。
- ⚠️ `import_jinbet.py` 有损：会清空历史日 injuries/weather/form_net/mood → 事后用 `C:/Users/Jin/_matlas_tools/_restore_extras.py`（dry-run→`--apply`→复核 0；不能留仓库内）从 HEAD 补回再 build。
- ⚠️ `publish.sh` 护栏：`git status` 出现 `data/` 以外改动（源码 WIP、README/SLOTS）直接拒发布，只自动提交 `data/`。遇到即如实报告，禁止擅自在 main 提交或改源码。
- 球员情报（2026-11-07）：import 后、build 前加 `python -m matlas.fetch_squads`（→`data/squads/<league_id>.json`）与 `python -m matlas.enrich_squads`（注入 `match["squad"]`，默认近 3 天，范围外清）。源=球小策 `player-rankings` 的 `ABV2_DC.nonce` + admin-ajax `abv2_dc_rankings`（nonce 每次现取，写死即 403 `-1`）。对外仅 6 项（GIM/OTI/DII/状态/稳定度/疲劳），无「硬仗属性」「缺阵影响」；球员名不可跨源匹配（0/107）。渲染 `pages.py::_squad_panel`，每队 ≥8 人才出；评分走普通数字，不能过 `pct` 类。`main_pick` 0/148 有值。
- 详情页序：结论→基本面→人员→市场推演→环境；「留档核验」整块删除（`_ledger`→`_settled_panel` 只留赛果+四维命中）。
