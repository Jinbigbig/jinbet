# JinBet 项目长期笔记

## 每日流水线（顺序不可乱）
0. `git show master:update_odds_net.py > update_odds_net.py` → **先** `--no-push` **再** `--no-push --results-only`（顺序错→ODDS 单引号 JS）。判据=日志 `[DEDUP-ALIGN]`；跑前清陈旧 `_data_batch*.json`。
1. 首跑当日先 `mkdir -p predictions/<date>`，再 `_local_prepare.py`（0 场=今日无赛，直接结束）。
2. `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py`（chain 含「市场混合(」+「比分矩阵对齐发布1X2」，路线图 ON·生效/ON·观察，Platt 已拟合）。
4. `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`（有变化则重跑报告并把 selection_tuning.json 入 commit）。
5. 更新 predictions/index.html 索引 → `grep -c data-page-node-id index.html` 仅 >0 时 `git checkout -- index.html` → commit 只推 gh-pages。
- 引擎/脚本改动走 worktree 同步 master（路径 C:/ 风格；worktree 用 `--detach <真实SHA>`，先 prune）。`_gen_report.py`/`_optimize_selection.py` 是 `_` 前缀工作盘专属，master 无正本；其依赖 `selection_algo.py` 必须入库（gh-pages 根 + master tools/prediction/）。master `tools/prediction/calc_engine.py` 是另一份（`_repo_root()` 路径），改引擎须两处同步文本补丁。
- 提交用 `git add -u` + 显式 `git add predictions/<date>`，避免入库 `_` 临时文件。

## 分支与推送
- origin=SSH 免交互；禁 GITHUB_TOKEN/HTTP 代理。**只信 `git ls-remote`**（remote-tracking ref 被并发覆写）。判推送只看 ls-remote。
- ❗rebase 必须 `--no-fork-point <ls-remote 真实SHA>`（reflog 基点可能陈旧）。推 `git push origin HEAD:refs/heads/gh-pages`，禁 force。被拒→fetch 真实 SHA + `rebase -X theirs`（数据文件冲突自动留本地新数据）；撞死→`reset --hard <云端SHA>` 重跑全链单提交推。
- bash PATH 偶坏 → `export PATH=/c/Users/Jin/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH`；临时文件写仓库内（/c/tmp 不持久）。

## 队名归一
- canonical=短名；SCHEDULE 双行=RESULT_TEAM_NAME_MAP 缺映射，先查表别手工删。当日盘口只认 index.html `YYYY-MM-DD_主_客` 键。编号不符先怀疑竞彩重编号（已修），别改映射表。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛进球环境 w=0.25；score_mix.w=0.3；EWMA(0.25)+MAD；基础λ窗口 N=25/DECAY=0.96；市场权重=`league_market_w(league)` 动态（50%→0.80，±2pp→±0.05，夹 0.65~0.95）。**改市场混合必重拟合 platt_params.json**（已入库）。
- 保险丝：MAX_TOTAL=4.20/MIN_TOTAL=1.60/MAX_SINGLE=3.20/MIN_SINGLE=0.18/ZF_CAP=1.0/LEAGUE_EB_K=40，勿调高。SCORE_ALIGN 三象限缩放到发布 1X2，勿回退。冷启动场不进比分精选。
- 星级=Platt 后 max(1X2)，阈值 0.44/0.50/0.57/0.66。五模块：BRIER_OPT/KALMAN ON·生效，HEDGE_ENSEMBLE ON·观察（apply=False 故意），CLV/DRIFT 只监控。平局 boost `0.25*exp(-|λh-λa|/0.45)`。
- ✅09-16 修：fit_platt_params 已改为拟合内调动态市场权重。

## 市场结论 / 已否决
- 纯市场去水 1X2 > 生产 > 纯模型；平均返还率 88.56%，按市场买必输。二级盘 alpha：让球✅｜总进球✅不稳｜比分❌｜1X2❌；二级盘输入用未混市场 λ，`|让球|≥3`/分歧>25pp/无锚→勿跟。大比分市场系统性高估，只观察。
- 已否决（勿再启用）：比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS。

## 数据修复史
- 赛果库主客颠倒已全量清理（4624→3059）；归档污染每次步骤0 复发，靠 `align_results_history_to_official()` 自动对齐；唯一锚=体彩官方赛果 API，日期启发式 100% 不可靠。改数据后必 build_league_profile → 重拟合 platt → 重跑引擎。
- 1X2 缺失用比分盘反推（31 档去水），仅限当日新鲜比分盘；09-01 及更早禁回填。

## 比分口径
- 头条=top_scores[0] 联合众数（不可大胆化）；双档=top_scores[1:3]；量级参考=round(λ)。基准：联合众数 14.94%、Top2 26.54%、±1球 67.24%；病灶=退化（65.8% 首选 1:1）。λ≤2.6 单点最值（18~22%），禁 k>1 追高；±1 邻域须去重格集合。

## 比分精选 / 大胆档（09-17 解耦定调）
- 唯一生产入口=`SA.split_boards`：比分精选先占位→大胆档只在剩余场选（同场不上两榜，bold 腿数<TIER_BD 属正常）。常量 TIER_PK=6/TIER_BD=4；档数=10 场 1 档每 +8 场 +1 档（N_TIER_BASE/STEP/TIER_MAX），按非冷启动场数算。
- ❗选取算法唯一实现=`selection_algo.py`；`_gen_report.py`/`_optimize_selection.py` 只调 SA.rank_pk/SA.rank_bold、命中判 SA.pk_result/SA.bd_result，禁另写排序。回放也必须走 SA（09-17 前优化器自写排序致 4/12 天与生产不同）。
- 选场≠展示：选场用引擎口径 `pk_quality`（含市场信息，更适合选场）；展示由各板块自算（自算分布更适合双档：200 场 17.5% vs 引擎 11.5%）。比分精选自带 `pk_dist`（引擎 λ 独立泊松→自己缩放到发布 1X2）；大胆档自带 `bd_ref`（量级档=象限内 `max(bd_min_total, round(λ总)+bd_total_shift)` 最高概率格；极限档=再 +bd_gap）。生产值：bd_total_shift=-1/bd_min_total=2/bd_gap=1/bd_exclusive=1/bd_lean_src='engine'。
- `bd_tuple` 必须 2 元组（质量分, λ总）——`_gen_report` 解包依赖，3 元组会崩。引擎 hit_pick/band_scores 只服务报告正文与 gen_review。
- 结构参数必须大样本定（12 天回放曾把 shift=+1 选最优，178 天证伪最差）；网格已限 shift∈{-1,0}。护栏：改善≥0.3pp 才采纳、可用天数<5 保留默认（连续保持默认属正常，勿放宽）。
- ❗快照必须落盘 cold/data_n（09-17 修）；09-16 及更早快照无法回溯。报告「前日回顾」按当前调参重算，非当日实发口径。
- 大样本工具 `_bd_bigsample.py`/`_bd_indep_probe.py` 均工作盘探针、被 gitignore。

## 报告红线
- 公开页三不落：方法论/口径说明、回测统计量、私下对话与脚本名。复查 grep「用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar」须为空。

## 第七节 联赛形势（7M）
- 源 `data.7m.com.cn/matches_data/{id}/big/standing.js`；id：英超92/西甲85/德甲39/意甲34/法甲93/荷甲99/葡超88/瑞超103/芬超105/挪超104/巴甲160/日职102/日乙347/法乙171/意乙95/西乙96/德乙140。美职/亚冠精英/亚运男足/英冠/英联赛杯/解放者杯/欧冠/欧联/欧协联无 id → UNAVAILABLE。
- 新联赛/队名先补 `league_match.ALIAS`（简→繁异译，如 巴列卡诺→華歷簡奴）。

## 复盘
- 三指标=方向命中率/比分双档命中率/λ总进球偏差。连续多日方向<50% 或 λ偏差>0.2 → 提示离线重拟合（market_calib/Platt）。Brier 差另跑 review_market --skip-audit（非每日强制）。
