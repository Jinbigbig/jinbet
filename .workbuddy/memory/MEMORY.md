# JinBet 长期笔记（日更细则见 automations/<id>/memory.md）

## 流水线（顺序不可乱）
0. `git ls-remote origin master` 取 SHA → `git show <SHA>:update_odds_net.py > update_odds_net.py`（须 3410 行、`grep -c 变更判定` = 3）→ 先 `--no-push` 再 `--no-push --results-only`（顺序错→ODDS 单引号 JS、步骤1 报「赔率 0/N」）。判据 `[DEDUP-ALIGN]`；跑前清 `_data_batch*.json`。
1. `mkdir -p predictions/<date>`（缺目录→快照静默跳过、步骤4 FileNotFoundError）→ `_local_prepare.py`（0 场=无赛）→ `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py` → `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`（旋钮变更才重跑报告）→ `_update_index.py`（日期/场次/联赛写死，每日先改）→ 根 index.html 有 `data-page-node-id` 才 checkout → 只推 gh-pages。**严禁 `git add -A`**：`git add -u` + 显式 add `predictions/<date>`。
- 链路核验读 `_calc_result.json`（顶层 dict：calibration/matches/today；matches 内 `chain` 为长字符串）：须含「市场混合(」「比分矩阵对齐发布1X2」「Platt」；stdout 有 ON·生效/ON·观察。

## 分支与推送
- origin=SSH；只信 `git ls-remote`（本地 `origin/*` 恒滞后）；禁 force/GITHUB_TOKEN。
- ⚠️ **本地 `master` 分支是个已分叉的死引用（11-08 `897636ae`，脚本只有 3334 行、无 `[变更判定]`），`git show master:update_odds_net.py` 会静默拿到旧脚本**；`git fetch origin master:master` 因 non-ff 被拒，无法快进。取正本一律用 `origin/master` 或 ls-remote 给的 SHA，绝不用裸 `master`。
- gh-pages 被拒：`git rebase --no-fork-point <云端SHA>`（不带第二参数）；撞死→`reset --hard <云端SHA>`+`checkout <好提交> -- .`+单提交推；续跑须 `GIT_EDITOR=true`。
- 推 master：`git worktree add --detach "C:/Users/Jin/_wt_master" <ls-remote SHA>`（须 C:/ 风格）→ 整文件 cp → `git add -- <单文件>` → commit → `push origin HEAD:refs/heads/master` → `worktree remove --force`。真实 diff 用普通 `git diff --stat`；`-c core.autocrlf=false` 会全树 LF/CRLF 噪声。
- ⚠️ `reset --hard` 会删被跟踪的 root `_` 脚本与 league_data.json、抹掉 `.workbuddy/memory/` 未提交改动 → 先 `git tag -f backup_<日期>_pre`；记忆随当日 commit 入库。
- ⚠️ `git show <未 fetch 的 ref>:路径` 会 fatal 并把目标截成 0 字节 → 先 fetch。
- ⚠️ 未跟踪文件挡 ff：删掉可能变 ` D`（本就已跟踪）→ `git checkout <远端SHA> -- <路径>` 恢复基线。
- ⚠️ results_history 净删几万行≠回滚（远端每日重写膨胀归档）；判据只用「唯一 matchId 是否下降」。归档=dict（键 `日期_主队_客队`，值 26 字段），按 list 解析得 0 条。

## 云端正本布局
- master `tools/prediction/`=脚本正本（去 `_` 前缀，LF）+ 根 update_odds_net.py/platt_params.json/league_profile.json。⚠️ `tools/prediction/gen_report.py` 落后（无 CUP_EXTRA 杯赛卡）→ 勿覆盖本地 `_gen_report.py`。
- gh-pages=数据运行态：predictions/、odds_data/results_data、odds_history/、scripts/、_calc_result.json、v34_state.json、strength_db.json、selection_tuning.json、weather/injuries/injuries_extra/referee/hongcai/match_times/odds_ticks/lineups/hkjc.json + root 的 score_engine.py/selection_algo.py/score_pick_optimize.py/_fetch_weather.py（**少数 `_` 脚本被跟踪**）。root 其余 `_` 脚本 + league_data/qq_standings/fox_standings 未跟踪。

## 队名归一（最贵的坑）
canonical=官方简称（沃夫斯堡、布城、奥斯KFUM、卡塔尔23…）；缺映射补 `RESULT_TEAM_NAME_MAP`，别手工删。同编号双行→丢让球/比分盘与评级历史；症状=matches_data 行数>场次、_calc_result 该场 rq 空；修完重跑 1→4。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛收缩 w=0.25；score_mix.w=0.3；市场权重动态 `league_market_w` 0.65~0.95；改市场混合必重拟合 platt_params.json。保险丝 MAX_TOTAL4.2/MIN_TOTAL1.6/MAX_SINGLE3.2/MIN_SINGLE0.18/ZF1.0/EB_K40。SCORE_ALIGN 勿回退；冷启动不进比分精选。星级阈值 0.44/0.50/0.57/0.66。
- 五模块：BRIER_OPT/KALMAN ON·生效；HEDGE ON·观察（apply=False 故意）；CLV/DRIFT 只监控。
- 已否决勿再启用：比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS、市场权重>0.85、平局权重缩放、λ缩放、非平局优先、爆冷过滤。单点/方向已贴天花板。
- 比分推演过程不进公开页：`match_card()` 不挂 `chain_table()`。

## 比分口径（09-22 定稿）
- 首选唯一实现 `score_engine.headline_reorder`：带 `mkt`（比分盘去水）→ argmax[log p_比分盘+0.3·log p_模型]，不要求与方向同象限；无 mkt 退回旧 gap 规则。同日同比分上限 `head_day_cap=4`。
- ⚠️ 禁止重排 `top_scores` 位次（恒纯概率降序）；首选另存 `headline`；跨象限渲染 `hm_mark`，别写「方向倾向内的首选比分」。
- 落位走引擎B 候选格：`_apply_headline_plan(out,TODAY,raw)`→`_headline_cells`。双档=除首选外概率最高的两个。单日 15 场单点期望 2.3 场是天花板，勿反复提示用户。

## 两档（selection_algo 唯一实现）
- 唯一入口 `SA.split_boards`；只调 `SA.rank_pk/rank_bold`、`pk_result/bd_result`。TIER_PK=6/TIER_BD=4；档数=非冷启动场次 10 场 1 档、每 +8 场 +1 档（N_TIER_BASE=10/N_TIER_STEP=8/TIER_MAX=5），两榜同档数。
- 生产值：bd_min_total=3、bd_gap=1、bd_exclusive=1、bd_lean_src='engine'；`bd_tuple` 必须 2 元组。护栏：改善≥0.3pp、天数<5 保留默认。
- 严禁在 `_gen_report.py`/`_optimize_selection.py` 另写排序或命中判定（曾口径分叉：大胆档虚高 31.8% vs 真实 11.4%）。
- 场次少时「第一档 N 场…共 M 场」会自相矛盾（池内不足），属展示瑕疵。

## 三引擎 / 渲染纪律
- A=`_calc_engine`（4.1 胜负/4.4 让球/4.5 冷门）；B=`score_engine`（4.2 比分，prob_temp=1.20、market_mix=0.70 勿降）；C=`selection_algo`（两档）；另 4.3 进球/4.6 大比分。
- 半全场：`htft_analysis`（半场 λ=全场×`HALF_SHARE`0.45，独立泊松 9 格）；每场 `htft` 入 `_calc_result`+快照；卡片「进球倾向」下「半全场」行 +4.3 表末列；复盘 `_recap_htft()`。渲染 `HTFT_HI=40/HTFT_MID=26`（默认 60/45 会全灰）。
- 词表统一 可用/慎用/别跟；让球分级唯一实现 `rq_grade(prob,conf)`；快照无置信度用 `_rq_conf_of(hc)` 还原。
- 概率唯一渲染器 `_conf_tag(p,nd=1,hi=60,mid=45)` → `pct-hi|pct-mid|pct-lo`，禁裸百分比 span；`_conf_tag/_conf_bucket/_conf_split/_star_txt` 必须在 `build_league_sec` 之前定义。
- 4.1「备选方向」列：`op2*100<50` 渲染三率第二高者+概率，否则「—」。回测 599 场：<45% 档 43%→73%、45-50 档 56%→82%、≥60 档 69%→88%。⚠️ 双选是三选二（基线 67%），禁当准确率。
- 红线 grep 公开页须空：`用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar`。

## 报告布局（10-22 定稿）
- 章节序：总览/市场信心/逐场/预测汇总/联赛与杯赛形势/核心策略与风险提示/动态校准/今日比分精选/大胆档。
- 第五节左积分榜右形势；积分榜仍完整保留（唯一渲染器 `std_table()`），但 **11-08 起整节正文默认折叠**（用户新指令覆盖旧「禁折叠」约定，展开后表格原样）。外层单列，分栏只在卡内（`.lg-split` 1fr 1fr，≤900px 单列）。「关键线」「历史补跑说明」每赛事一次。
- **折叠唯一实现 `_fold(label,hint,body,cls,head_tag)`**：定义在 `_sub()` 之后、`deep_sec` 装配之前（否则 `match_card` 调用时 NameError）。原生 `<details class="fold" data-fold>`，禁用 JS 也能展开；空内容不落块。CSS 在追加块末尾；`.fold-cta::after` 纯 CSS 切「展开/收起」文字。⚠️ **11-08 用户明确不要全局「全部展开/收起」控制条**（`#foldAll/#foldNone`/`fold-bar` 已全删），`FOLD_JS` 只保留 beforeprint 打印前全展开；只留各区块自己的展开按钮。
- **11-08 说明段落全部去除**（用户「不需要说明描述，都检查一下，都不需要」）：`_sub_table` 不再渲染 `note` 段（一处覆盖 4.1~4.6）；四章章节说明、比分精选/大胆档表前表后说明、第五节积分榜来源、前日回顾的口径解释句、卡片让球分档说明句均删。纯来源/图例/注类小标注（`.league-src/.inj-src/.std-legend/.parlay-note`，共 56 处）用 CSS `display:none` 统一隐藏。**保留**：历史底蕴荣誉 notes（11 段数据）、前日回顾命中统计（10 段数字）、`cmp-note`/`league-note`/`pred-note` 结论、`fold-hint` 折叠条提示。
- **4.2 比分预测表 11-08 起 9 列**（去掉「可能进球(主)/(客)」两列，`_mode_h/_mode_a` 变量已删），表头=编号/主队/客队/预期进球(主/客)/比分预测/比分双档/±1球覆盖/Top3覆盖/可信度。
- **返回顶部按钮** `#backTop`：CSS/HTML/JS 都在 `TOC_BLOCK`/`FOLD_JS`（右下角圆形，滚动>400px 才显示，平滑回顶，尊重 reduced-motion，打印隐藏）。⚠️ `right:14px;bottom:22px` 被 `toc-toggle` 占用 → ≤1399px 时 `bottom:78px` 叠在目录按钮上方，≥1400px（目录按钮隐藏）自动落回 22px。
- 三层折叠：① 每场卡片只常驻「卡头+队名+赔率」与「🎯比分与方向预测」两块，中间 11 项（排名/H2H两卡/底蕴/交锋/战绩/红彩4块/伤停/冷门/让球）按原序合成一条 `mid_fold`（用户截图指定的形态）；② `_sub_table(..., fold=True)` 用于 4.2~4.6，**4.1 常驻**；③ 第五节 h2 常驻、正文折叠。**所有前日回顾在装配层统一走 `_wrap_recap()` 折叠**（3 类渲染器 / 10 个块），嵌套在汇总表折叠内时用 `.fold-body details.fold.fold-recap` 去外框。
- TOC 联动：点目录项自动展开所在 `details.fold`；`spy()` 跳过 `offsetParent===null` 的隐藏标题，避免高亮到折叠内项。
- ⚠️ 折叠只减可见高度、不减文件体积（817KB→834KB，多 17KB 是折叠壳）；判据用「可见区是否还有回顾表格」而不是文件大小。
- 榜源四级链：7M→腾讯 `qq_standings.json`（limit=50）→Fox `fox_standings.json`（SSR 正则 `<table id="live-standings-table-N">`，bifrost 恒 401）→UEFA `uefa_standings.json`（本机 timeout，用 WebFetch 落盘）。腾讯/Fox/UEFA 走 `std_league_card()`；分组赛 `std_group_card()` 只展开本日队小组；收官（场次齐平且≥3）不做名次模拟。腾讯赛事 ID：欧冠5/英超8/意甲21/德甲22/西甲23/法甲24。
- ⚠️ **7M 榜全是港澳台译名**（飛燕諾/阿積士/阿仙奴/車路士/巴塞隆拿），且行内 `name`=繁体港译、`name_zh`=简体港译（飞燕诺/阿积士）；渲染层原优先读 name_zh → 只靠 difflib 匹配（繁简 0 相似）→ 排名大面积缺失、榜上显示港译。唯一归一处 `standings_alias.py::cn()`（11 联赛 200 队港译→大陆简称，幂等），三处必须都过：`_fetch_league_data` 落盘前、`_gen_report._std_teams`+`_qq_team`、`_build_today_extras` 读榜后。opencc 只能繁→简，解决不了港译人名。master 正本在 `tools/prediction/standings_alias.py`。
- ⚠️ **7M 会把两段榜拼进同一组数组**（芬超：12 队先 22 轮常规赛再分组，`f_sds_tn` 给 24 项 = 25 轮总榜 + 22 轮常规赛榜），`parse_standing` 顺序编号 → 同队出现两次、名次排到 24、「高亮=本日参赛队」两处都亮。修法：按 `tid` 去重、保留 `p`（已赛场次）最多那行并重排名次（`_fetch_league_data.parse_standing`；master 同名补丁 `a67ac654`）。判据：`len(teams)==len({tid})`；正常联赛 12/16/18/20 行。
- 第三节序：队名+排名 → 赔率三格 → 积分排名·赛事 → H2H 两卡 → 历史底蕴 → 历史交锋+近期战绩（始终并列）→ 伤停与赛前分析 → 冷门/让球 → 比分与方向。入口 `std_rows(lg)`/`std_of(team,lg)`。
- 文案红线：不写「怎么看表」说明句；缺口用最短一句（`暂无交锋记录`）。窄屏 `@media(max-width:640px)` 用 `minmax(0,1fr)`。

## 赛前信息：阵容/伤停/天气/时间
- 阵容主源 lineupstoday.com（`_fetch_lineups.py`→lineups.json），URL `/<league>/<home-slug>-<away-slug>-<DD-MM-YYYY>/`，slug 表 `_RAW_TEAMS`。⚠️ 表存全称、报告用简称，查不到静默 skip（unmapped）→ 欧战新军补别名；改表同步 master `fetch_lineups.py`。区块 id：`opstelling`（ov-veld__speler）、`absenties`（li.ov-absentie），按 id 切块别按 h2；赛后页无 `absenties`；`is-twijfel`=存疑；「Not in the squad」丢弃。
- `injury_html()` 优先 lineups.json（按 matchNumStr）→ 阵型徽标+缺阵数+`<details class="inj-xi">`；无数据回退 injuries.json。`_ensure_side_data` 顺序：阵容→赛马会→天气→伤停兜底→开赛时间（jobs 3 元组）。
- 天气 `_fetch_weather.py`→weather.json（Open-Meteo，18–23 时，bad≥35km/h 或降雨≥70%）。**读 `_calc_result.json` 的 today → 必须在步骤3 之后跑**（同 `_fetch_referee.py`）。缺场次=TEAM_CITY/CITY_ZH 无该队，补两表即 100%；脚本在 gh-pages 被跟踪、master 正本常更旧 → 整文件 cp。
- 开赛时间：`_fetch_match_times.py`→match_times.json，源=网易竞彩赛程 `matchList/1?days=YYYY-MM-DD 12:00:00` 的 `matchTime`，抓 date±1 合并、按 `jcNum` 建表。卡片 `match-time` 后紧 `<span class="kickoff">` 再天气；入口 `kickoff_of(num)`；加载须校验 date==TODAY（编号每周复用）。
- ⚠️ 红彩 matchId 会指向旧场次（脚本只按 matchId 调接口、不校验队名）。每次跑完核对 `hongcai.json` 的 home/away 与 matches_data，错配移入 `missing`；`_fetch_hongcai.py` 重跑会写回，matlas 环节后再剔。简称差异（斯达/特尔斯达、国际图/国际图尔）属别名。
- 实测不可用勿再试：Transfermarkt 405、premierinjuries 403、Sports.ru 403、OTempo 超时、premierleague.com JS、百度体育 SPA。

## 复盘/诊断
- 六指标：方向 / 方向双选 / 比分单点 / 比分双档 / 半全场首选 / 总进球众数 / λ偏差。连续多日方向<50% 或 λ偏差>0.2 → 提示重拟合。查准度 `daily_diag.py --days 10` 或 `gen_review.py --kpi`。
- 累计（599 场 since 09-08）：方向 57.8%/双选 81.0%/单点 10.2%/双档 21.2%/半全 34.9%/总进球 20.7%。
- ⚠️「单点约 15%」是 4036 场旧口径，近期实测 10~11%。⚠️ 杯赛不降权（61.3% > 联赛 56.3%）。⚠️ <300 场不调参。对标球小策 62% 是双选口径，同口径六项我们赢五项。

## 赛果补录定时任务（每日 08:00）
- 入口 `_sync_results.py`（master `tools/prediction/sync_results.py`，细则见该 automation 的 memory.md）：对齐远端 → `--no-push --results-only` → `[变更判定]` → 0/0 不推 → `commit -- pathspec` → push。
- ⚠️ 不能直接跑 `update_odds_net.py --results-only`（`push_to_gh_pages()` 硬要求 master 分支）。⚠️ `existing_results` 必须优先读 results_data.json（26 字段），读 index.html 的 `const RESULTS` 会静默丢 3242 条让球/比分盘/总进球/半全场。⚠️ 变更判定须 `_norm()` 归一。
- 待办：归档仍有 1637 条带「让球」记录可回填 results_data.json。

## 兄弟项目 Matlas（C:\Users\Jin\matlas，零 import）
- 定位：jinbet=算，Matlas=发（per-match 落地页、留档、llms.txt/sitemap/Schema.org）。唯一耦合=`matlas/models.py` 契约 v1.0。仓库 github.com/Jinbigbig/matlas（SSH）：`main`=源码+数据（`_site/` 不进 main）、`gh-pages`=产物。发布 `TMPDIR=/c/tmp/matlas-trash bash publish.sh`（可 `SKIP_BUILD=1`），勿手工混提交。
- 顺序：`import_jinbet.py` → `_restore_extras.py`（dry-run→`--apply`→复核 0，脚本在 `C:/Users/Jin/_matlas_tools/`，不能留仓库内）→ `python -m matlas.fetch_squads` → `python -m matlas.enrich_squads` → `build.py --strict` → publish。
- 线上：`jinbigbig.github.io/matlas/` + `matlas.app.workbuddy.host/?sharecode=…`（裸路径 403）。当日页 URL=`/matlas/days/<date>.html`。域名只在 `config.DEFAULT_BASE_URL`。红线落成 `matlas/rules.py`（`--strict` 非零退出）；`prob_tag()` 唯一渲染器。
- ⚠️ `import_jinbet.py` 有损：清空历史日 injuries/weather/form_net/mood → 必须事后 restore，否则全删。`_restore_extras.py` 对当日新增文件报 `Expecting value: line 1 column 1` 属正常 skip。
- ⚠️ `publish.sh` 护栏：`data/`（含 `assets/logo/`）以外改动直接拒发布 → 如实报告，禁在 main 提交或改源码。11-08 已加 `[4.5/4] 同步 main`（被拒只警告不阻断）。
- 球员情报源=球小策 `player-rankings` 的 `ABV2_DC.nonce` + admin-ajax `abv2_dc_rankings`（nonce 每次现取，写死即 403 `-1`）。对外仅 6 项（GIM/OTI/DII/状态/稳定度/疲劳）；球员名不可跨源匹配。渲染 `pages.py::_squad_panel`，每队 ≥8 人才出；评分走普通数字，不能过 `pct` 类。
- 详情页序：结论→基本面→人员→市场推演→环境；「留档核验」整块删除（`_ledger`→`_settled_panel` 只留赛果+四维命中）。
