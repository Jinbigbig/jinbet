# JinBet 长期笔记（细则见 automations/<id>/memory.md）

## 流水线（顺序不可乱）
0. `git show master:update_odds_net.py > update_odds_net.py` → 先 `--no-push` 再 `--no-push --results-only`（顺序错→ODDS 单引号 JS）。判据 `[DEDUP-ALIGN]`；跑前清 `_data_batch*.json`。
1. `mkdir -p predictions/<date>` → `_local_prepare.py`（0 场=无赛）。
2. `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py`（chain 判据「市场混合(」+「比分矩阵对齐发布1X2」；路线图 ON·生效/ON·观察；Platt 已拟合）。
4. `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`（有变化重跑报告并提交 selection_tuning.json）。
5. 索引更新 → 根 index.html 被注入 `data-page-node-id` 才 checkout → commit 只推 gh-pages。
- 提交**严禁 `git add -A`**，用 `git add -u` + 显式 add。

## 分支与推送
- origin=SSH 免交互；禁 GITHUB_TOKEN/代理；只信 `git ls-remote`；禁 force。
- rebase 在 gh-pages 上 `git rebase --no-fork-point <云端真实SHA>`（**不带第二参数**）；撞死→`reset --hard <云端SHA>` + `checkout <本地好提交> -- .` + 单提交推。
- bash PATH：`export PATH=/c/Users/Jin/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH`。

## 云端正本布局
- master `tools/prediction/`=脚本正本（去 `_` 前缀；副本 `_repo_root()` 自适应、可能 CRLF，走锚点式同步，别直接用本地文件覆盖）；master 根 update_odds_net.py + platt_params.json/league_profile.json。
- gh-pages=数据运行态（predictions/、odds_data/results_data、results_history/、odds_history/、scripts/、_calc_result.json、v34_state.json、strength_db.json、selection_tuning.json）+ score_engine.py/selection_algo.py。
- 新增脚本：`_foo.py` ↔ master `tools/prediction/foo.py` 两处同步。

## 队名归一 / 别名行（最贵的坑）
- canonical=官方简称（沃夫斯堡、布城、奥斯KFUM、卡塔尔23、达姆施塔…）；缺映射补 `RESULT_TEAM_NAME_MAP`，别手工删。
- 同编号双行→该场丢让球/比分盘与评级历史；查 matches_data 行数>场次、_calc_result 该场 rq 空；修完重跑 1→4。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛 w=0.25；score_mix.w=0.3；市场权重 `league_market_w`（0.65~0.95）；改市场混合必重拟合 platt。保险丝 MAX_TOTAL=4.20/MIN_TOTAL=1.60/MAX_SINGLE=3.20/MIN_SINGLE=0.18/ZF_CAP=1.0/LEAGUE_EB_K=40。SCORE_ALIGN 勿回退；冷启动不进比分精选。星级阈值 0.44/0.50/0.57/0.66。
- 五模块：BRIER_OPT/KALMAN ON·生效；HEDGE ON·观察（apply=False 故意）；CLV/DRIFT 监控。

## 已否决（勿再启用）
比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS、市场权重>0.85、平局权重缩放、λ缩放、非平局优先、爆冷过滤。**单点/方向已贴天花板，只能靠扩覆盖或加场次。**

## 比分口径（09-19 定稿：不要众数分布）
- 首选唯一实现 `score_engine.headline_reorder(top, gap=5.0, dir_key)` + `head_gap=5.0`：众数为平局比分且领先「倾向象限内最高概率比分」不足 5pp → 顺延；倾向=平局保留 1:1。实测 15.58%（众数 15.13%）、1:1 占比 56%→24%；gap 6/7 更差。
- ⚠️ **禁止重排 `top_scores` 位次**：恒为纯概率降序；首选另存 `headline` 字段或 `SA.headline_pick(cells, direction_key(m))` 现算。09-19 重排曾致「可能比分1 概率<可能比分2」错位。
- 双档=除首选外概率最高的两个。长期基准：方向 51.2%、单点 15.1%、双档 24.0%、前三 39.1%、±1球 67.2%。单日 15 场单点期望 2.3 场是天花板，**勿反复向用户提示**。探针 `headline_rule_probe/band_rule_probe/pk_head_probe.py`。

## 两档（selection_algo 唯一实现）
- 唯一入口 `SA.split_boards`；_gen_report/_optimize_selection 只调 SA.rank_pk/rank_bold、SA.pk_result/bd_result，禁另写排序。TIER_PK=6/TIER_BD=4；档数=10 场 1 档、每 +8 场 +1 档，**按当日全部非冷启动场次算、两榜同档数**（09-19 修：曾按「精选占位后剩余池」算 → 30 场只出 4 场大胆档）。
- 生产值：bd_min_total=3、bd_gap=1、bd_exclusive=1、bd_lean_src='engine'。护栏：改善≥0.3pp、天数<5 保留默认。`bd_tuple` 必须 2 元组；快照必落盘 cold/data_n。
- 报告串关推荐下方有「📅 前日回顾」（`_gen_report._build_parlay_recap()`）：解析**昨日已发布 index.html** 的串关表逐腿核对赛果，不随口径迭代漂移。

## 三引擎（互不影响）
- A=_calc_engine（4.1 胜负/4.4 让球/4.5 冷门）；B=score_engine（4.2 比分，prob_temp=1.20、market_mix=0.70 勿降）；C=selection_algo（4.x 两档）；另 4.3 进球 / 4.6 大比分。
- 可信度词表统一 **可用/慎用/别跟**；让球分级唯一实现 `rq_grade(ev,conf)`。
- 红线：公开页 grep「用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar」须为空。

## 复盘/诊断
- 三指标：方向/双档/λ偏差；连续多日方向<50% 或 λ偏差>0.2 → 提示重拟合。用户问准不准 → `python daily_diag.py --days 10`。回测逐场档 `_bt_rows2.json`。
- 联赛形势源=7M standing.js，新队名补 `league_match.ALIAS`。
