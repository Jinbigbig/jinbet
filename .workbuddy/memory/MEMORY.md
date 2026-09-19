# JinBet 项目长期笔记（精简版，细节见 automations/<id>/memory.md）

## 流水线（顺序不可乱）
0. `git show master:update_odds_net.py > update_odds_net.py` → 先 `--no-push` 再 `--no-push --results-only`（顺序错→ODDS 单引号 JS）。判据 `[DEDUP-ALIGN]`；跑前清 `_data_batch*.json`。
1. `mkdir -p predictions/<date>` → `_local_prepare.py`（0 场=无赛，结束）。
2. `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py`（chain 判据「市场混合(」+「比分矩阵对齐发布1X2」，路线图 ON·生效/ON·观察，Platt 已拟合）。
4. `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`（有变化重跑报告并提交 selection_tuning.json）。
5. 索引更新 → `grep -c data-page-node-id index.html` >0 才 checkout → commit 只推 gh-pages。
- 提交**严禁 `git add -A`**（会把工作盘千计 `_` 临时文件/备份/pycache 入裤，09-19 踩过，靠二次 rm --cached 清理）；用 `git add -u` + 显式 add。

## 分支与推送
- origin=SSH 免交互；禁 GITHUB_TOKEN/代理。只信 `git ls-remote`；推送成败只看 ls-remote。禁 force。
- rebase 用 `--no-fork-point <ls-remote 真实SHA>`；`git rebase --no-fork-point <SHA> origin/gh-pages` 会切到 detached 重放 origin（无操作），**正确写法是不带第二个参数**在 gh-pages 上执行。
- 撞死→`reset --hard <云端SHA>` → 恢复本地文件 → 单提交推。untracked overwrite 冲突别 rebase/abort 兜圈子（会删 untracked 数据）。
- bash PATH 偶坏 → `export PATH=/c/Users/Jin/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH`。

## 云端正本布局
- master `tools/prediction/`=全部脚本正本（101 个 .py，**文件名去 `_` 前缀**，gitignore 对 `_` 任意层级忽略）；master 根：update_odds_net.py + platt_params.json/league_profile.json（重拟合后必刷）。master 副本有 `_repo_root()` 自适应，**别用本地文件直接覆盖**。
- gh-pages=数据运行态（predictions/、odds_data/results_data、results_history/、odds_history/、scripts/matches_data.json、_calc_result.json、v34_state.json、strength_db.json、selection_tuning.json）+ score_engine.py/selection_algo.py。
- 新增脚本：工作盘 `_foo.py` ↔ master `tools/prediction/foo.py`（LF；改掉 `_xxx` 引用）两处同步。

## 队名归一 / 别名行（最贵的坑）
- canonical=官方简称（沃夫斯堡、布城、奥斯KFUM、卡塔尔23、达姆施塔…）；长名是别名，缺映射补 `RESULT_TEAM_NAME_MAP` 别手工删。
- 同编号双行→该场丢让球盘/比分盘/评级历史。排查：matches_data 行数>场次、_calc_result 该场 rq 空。修完必重跑步骤 1→4。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛 w=0.25；score_mix.w=0.3；市场权重动态 `league_market_w`（0.65~0.95）；改市场混合必重拟合 platt。保险丝 MAX_TOTAL=4.20/MIN_TOTAL=1.60/MAX_SINGLE=3.20/MIN_SINGLE=0.18/ZF_CAP=1.0/LEAGUE_EB_K=40。SCORE_ALIGN 勿回退；冷启动不进比分精选。星级阈值 0.44/0.50/0.57/0.66。
- 五模块：BRIER_OPT/KALMAN ON·生效；HEDGE ON·观察（apply=False 故意）；CLV/DRIFT 监控。DRIFT 报 league_baselines 漂移（德乙/韩职/荷甲）连续多日 → 提示离线重拟合。

## 已否决（勿再启用）
比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS；市场权重>0.85、平局权重缩放、λ缩放、象限限制、非平局优先、爆冷过滤、换选取目标。**单点/方向已贴天花板，提升只能扩覆盖或加场次。**

## 比分口径与长期真值（2478 场）
- 头条=top_scores[0] 联合众数；双档=[1:3]；λ≤2.6 单点最值。方向 51.21%、单点 15.13%、双档 24.01%、前三 39.14%、±1球 67.2%；头条为平局比分 66%。单日 15 场单点期望 2.3 场是天花板不是故障；**勿向用户反复提示此点**。两队 λ 同落 [1,2) 必然头条 1:1（押 1:1 占 39%，命中 16.63%>盲猜），五连 1:1 属正常形态。

## 两档（selection_algo 唯一实现）
- 唯一入口 `SA.split_boards`；_gen_report/_optimize_selection 只调 SA.rank_pk/rank_bold、SA.pk_result/bd_result，禁另写排序。TIER_PK=6/TIER_BD=4；档数=10 场 1 档每 +8 场 +1 档（按非冷启动场数）。
- 生产值：bd_total_shift=-1/bd_min_total=3(09-19 采纳)/bd_gap=1/bd_exclusive=1/bd_lean_src='engine'。护栏：改善≥0.3pp、天数<5 保留默认。`bd_tuple` 必须 2 元组。快照必落盘 cold/data_n。

## 三引擎（互不影响，09-18 定稿）
- A=_calc_engine（胜平负，4.1：倾向/方向可信度/让球盘/让球可信度/冷门）；B=score_engine（比分，4.2：可能进球、可能比分1/2+概率；DEFAULT 含 prob_temp=1.20，market_mix=0.70 已证有效勿降）；C=selection_algo（4.x 两档）。章节：4.1 胜负/4.2 比分/4.3 进球/4.4 让球/4.5 冷门/4.6 大比分。
- 可信度词表全站统一：**可用 / 慎用 / 别跟**（+数据不足）；让球分级唯一实现 `rq_grade(ev,conf)`。
- 红线：改 `_gen_report.py` 改完先 grep 源码再重跑；公开页 grep「用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar」须为空。

## 复盘/诊断
- 三指标：方向/双档/λ偏差；连续多日方向<50% 或 λ偏差>0.2 → 提示重拟合。用户问准不准 → `python daily_diag.py --days 10`。回测逐场档 `_bt_rows2.json`（master 同名）。
- 联赛形势源=7M standing.js（id 表见 automation 记忆），新队名补 `league_match.ALIAS`。
