# JinBet 长期笔记（细则见 automations/<id>/memory.md）

## 流水线（顺序不可乱）
0. `git show master:update_odds_net.py > update_odds_net.py` → `--no-push` 再 `--no-push --results-only`（顺序错→ODDS 单引号 JS）。判据 `[DEDUP-ALIGN]`；跑前清 `_data_batch*.json`。
1. `mkdir -p predictions/<date>` → `_local_prepare.py`（0 场=无赛）。
2. `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py`（chain 判据「市场混合(」+「比分矩阵对齐发布1X2」）。
4. `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`。
5. 索引 → 根 index.html 有 `data-page-node-id` 才 checkout → 只推 gh-pages。**严禁 `git add -A`**。

## 分支与推送
- origin=SSH；只信 `git ls-remote`（本地 `origin/*` 会滞后 → 取文件用 `git show $(git ls-remote origin <br>|cut -f1):路径`）；禁 force/GITHUB_TOKEN。
- gh-pages `git rebase --no-fork-point <云端SHA>`（**不带第二参数**）；撞死→`reset --hard <云端SHA>`+`checkout <好提交> -- .`+单提交推；继续须 `GIT_EDITOR=true`。
- 推 master 用 worktree：`git worktree add --detach "C:/Users/Jin/_wt_master" <SHA>`（**须 `C:/...`**，`/c/...` 会建成 `C:\c\...`）→覆盖→commit→`push origin HEAD:refs/heads/master`→`worktree remove --force`。

## 云端正本布局
- master `tools/prediction/`=脚本正本（去 `_` 前缀）+ 根 update_odds_net.py/platt_params.json/league_profile.json。这几支脚本实为 **LF**；`gen_report` 有 5 处去下划线须保留。
- gh-pages=数据运行态（predictions/、odds_data/results_data、results/odds_history/、scripts/、_calc_result.json、v34_state.json、strength_db.json、selection_tuning.json）+ **仅 root** 的 score_engine.py/selection_algo.py/score_pick_optimize.py。**root `_` 脚本在 gh-pages 未跟踪** → 只同步 master；新增脚本两处同步。

## 队名归一 / 别名行（最贵的坑）
- canonical=官方简称（沃夫斯堡、布城、奥斯KFUM、卡塔尔23…）；缺映射补 `RESULT_TEAM_NAME_MAP`，别手工删。
- 同编号双行→丢让球/比分盘与评级历史；查 matches_data 行数>场次、_calc_result 该场 rq 空；修完重跑 1→4。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛 w=0.25；score_mix.w=0.3；市场权重 0.65~0.95；改市场混合必重拟合 platt。保险丝 MAX_TOTAL4.2/MIN_TOTAL1.6/MAX_SINGLE3.2/MIN_SINGLE0.18/ZF1.0/EB_K40。SCORE_ALIGN 勿回退；冷启动不进比分精选。星级 0.44/0.50/0.57/0.66。
- 五模块：BRIER_OPT/KALMAN ON·生效；HEDGE ON·观察（apply=False 故意）；CLV/DRIFT 监控。

## 已否决（勿再启用）
比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS、市场权重>0.85、平局权重缩放、λ缩放、非平局优先、爆冷过滤。**单点/方向已贴天花板，只剩扩覆盖或加场次。**

## 比分口径（09-22 定稿，取代 09-19 象限/众数规则）
- 首选唯一实现 `score_engine.headline_reorder`：带 `mkt`（比分盘去水）→ **argmax[log p_比分盘+0.3·log p_模型]**，**不要求与方向同象限**；无 `mkt` 退回旧 gap 规则。同日同比分上限 `head_day_cap=4`（`plan_headlines` 按日分配，治 1:1 刷屏）。
- 换规则理由：09-19 规则建在**失真旧底座**上（λ 中位偏差 0.56）。忠实重放 2478 场旧 12.39% vs 众数 13.88%；已发布 224 场 11.16% vs 12.50% → 旧规则净负。新口径单点 13.64%/双档 34.50%，留出段 13.93%/13.92%。底座 `_bt_rows3.json`+`score_pick_optimize.py`（`_bt_rows2.json` 失真勿用）。
- ⚠️ **禁止重排 `top_scores` 位次**（恒纯概率降序）；首选另存 `headline`（快照/`_calc_result` 同一份）。跨象限是设计允许：卡片渲染 `hm_mark`，**别再把文案写成「方向倾向内的首选比分」**。
- ⚠️ 落位必须用**引擎B**候选格：`_apply_headline_plan(out,TODAY,raw)`→`_headline_cells` 走 `score_engine.engine_asof()+predict()`（不可用才退 `top_scores`）。
- 双档=除首选外概率最高的两个。长期：方向 51.2%、单点 ~15%、双档 ~24%、前三 39.1%、±1球 67.2%。单日 15 场单点期望 2.3 场是天花板，**勿反复向用户提示**。

## 两档（selection_algo 唯一实现）
- 唯一入口 `SA.split_boards`；只调 `SA.rank_pk/rank_bold`、`pk_result/bd_result`。TIER_PK=6/TIER_BD=4；档数=10 场 1 档、每 +8 场 +1 档，**按当日全部非冷启动场次算、两榜同档数**。
- 生产值：bd_min_total=3、bd_gap=1、bd_exclusive=1、bd_lean_src='engine'。护栏：改善≥0.3pp、天数<5 保留默认。`bd_tuple` 必须 2 元组；快照必落盘 cold/data_n。

## 三引擎（互不影响）
- A=_calc_engine（4.1 胜负/4.4 让球/4.5 冷门）；B=score_engine（4.2 比分，prob_temp=1.20、market_mix=0.70 勿降）；C=selection_algo（4.x 两档）；另 4.3 进球/4.6 大比分。
- 可信度词表统一 **可用/慎用/别跟**；让球分级唯一实现 `rq_grade(ev,conf)`。
- 红线：公开页 grep「用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar」须空。

## 复盘/诊断
- 三指标：方向/双档/λ偏差；连续多日方向<50% 或 λ偏差>0.2 → 提示重拟合。问准不准 → `python daily_diag.py --days 10`。联赛形势源=7M standing.js，新队名补 `league_match.ALIAS`。
