# JinBet 项目长期笔记

## 每日流水线（顺序不可乱）
0. **最先**：`git show master:update_odds_net.py > update_odds_net.py` → `python update_odds_net.py --no-push` **再** `--no-push --results-only`（顺序错→ODDS 变单引号 JS，步骤1 报「赔率 0/N」）。0b 会自动跑官方锚对齐，判据=日志有 `[DEDUP-ALIGN]` 行（无该行=根目录缺 `dedup_results_history.py`）。跑前确认无陈旧 `_data_batch*.json`。
1. `_local_prepare.py`（首跑当日先 `mkdir -p predictions/<date>`，否则快照静默跳过→步骤4 FileNotFoundError）
2. `_build_today_extras.py` 3. `_fetch_league_data.py` 3.5 `_calc_engine.py`（查 chain 含「市场概率混合(」「比分矩阵对齐发布1X2」、路线图有 ON·生效/ON·观察、Platt 已拟合）
4. `_gen_report.py` 4.5 `gen_review.py --date <昨日>` 4.6 `_optimize_selection.py`（回放刷新 `selection_tuning.json`，幂等，无改善不动文件）
5. 更新 predictions/index.html 索引 → commit 只推 gh-pages（fetch+rebase，禁 force）。
- 引擎/脚本改动走 worktree 同步 master（路径必须 `C:/` 风格）；predictions/ 与 V3.4 状态文件属 gh-pages；master 正本放 `tools/prediction/`；新脚本勿用 `_` 前缀（.gitignore 任意层级匹配）。

## 分支与推送
- origin=SSH 免交互；禁 GITHUB_TOKEN/HTTP 代理。**只信 `git ls-remote`**（remote-tracking ref 会被并发会话覆写）。
- ❗**rebase 必须 `--no-fork-point` 且用 ls-remote 拿到的真实 SHA**（如 `git rebase --no-fork-point <sha>`）。远端被 force-update 后，rebase 的 `--fork-point` 会从 reflog 取到陈旧基点（曾把 b119ac2 当基点 → 误重放 247 个提交、卡在冲突）。推送用 `git push origin HEAD:refs/heads/gh-pages`。
- gh-pages 常有外部追加提交：被拒→fetch 真实 SHA + rebase；撞数据文件冲突→`reset --hard <云端真实SHA>` 重跑全链单提交推。
- 判推送只看 ls-remote（SIGTERM 的 push 实际可能已成功）。
- 根 index.html 3.4MB 程序生成：仅当 `grep -c data-page-node-id index.html` >0 才 `git checkout -- index.html`。
- 环境坑：bash PATH 偶坏 → `export PATH=/c/Users/Jin/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH`；`/c/tmp` 不跨调用持久（临时文件写仓库内）；`git stash` 读不出 refs/stash → `cat .git/refs/stash` 取 SHA。
- worktree：`git worktree add --detach <path> <真实SHA>`（先 `git worktree prune`；曾在并发下 admin 目录消失致 worktree 失效）。

## 队名归一
- canonical=短名。SCHEDULE 双行根因=`RESULT_TEAM_NAME_MAP` 缺映射或 identity 映射→先查映射表别手工删。改后重跑步骤0 须见「合并后清理 N 场重复」。
- 当日盘口只认 index.html `YYYY-MM-DD_主_客` 键；odds_data.json 无日期键会被历史污染。
- 竞彩开售后重编号（预排号→正式号）已修：在售编号覆盖滞后值 + main() 刷新。**编号与官方不符先怀疑重编号，别改映射表。** 残留：SCHEDULE.matchId 可能是赛果API旧 id（展示无影响）。

## 引擎 V3.4（勿回退）
- λ=期望值口径；联赛进球环境 w=0.25；`score_mix.w`=**0.3**（线上真实值）；EWMA(0.25)+MAD；基础λ窗口 N=25/DECAY=0.96。
- 市场权重=`league_market_w(league)` 动态（准确率 50%→0.80，每 ±2pp→±0.05，夹紧 0.65~0.95）。**改市场权重/混合方式后必须重拟合 platt_params.json**（n=1981，已纳入版本管理）。
- 保险丝：MAX_TOTAL=4.20 / MIN_TOTAL=1.60 / MAX_SINGLE=3.20（触顶=过激进勿调高）、MIN_SINGLE=0.18、ZF_CAP=1.0（零封只削弱）、LEAGUE_EB_K=40。
- SCORE_ALIGN（第七步D）：比分矩阵三象限缩放到已发布 1X2，勿回退。引擎输出 `data_n`/`cold`；冷启动场次不进比分精选、可信度显示「数据不足」。
- **星级=胜平负倾向确定性**（Platt 后 max(1X2)，阈值 0.44/0.50/0.57/0.66）。
- V3.4 五模块：BRIER_OPT ON·生效（每 7 天最多一次 walk-forward，改善≥0.3% 才采纳）、KALMAN_STRENGTH ON·生效、HEDGE_ENSEMBLE **ON·观察**（apply=False 是故意的）、CLV_TRACK/DRIFT_MONITOR 只监控。平局 boost `0.25*exp(-|λh-λa|/0.45)`（Platt 后 / SCORE_ALIGN 前）。
- ✅ 2026-09-16 修复：`fit_platt_params` 曾按固定 MARKET_W=0.80 拟合而 calc_match 用动态权重 → 已改为 fit 内调 `league_market_w`。回测准确率 51.10→51.26%、Brier 0.19857→0.19850。

## 市场结论 / 已否决
- 纯市场去水 1X2 > 生产 > 纯模型；市场已吞掉基本面。平均返还率 88.56%→按市场买必输。二级盘 alpha：让球✅｜总进球✅不稳｜比分❌｜1X2❌。二级盘输入须用未混市场 λ（lam_h_B/lam_a_B），`|让球|≥3`/分歧>25pp/无1X2锚点→低置信「勿跟」。大比分（6+/7+）市场系统性高估，只观察。
- 已回测否决：比分盘/总进球盘并入网格、λ 线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS。判 alpha 看样本外 Brier+分月稳定。

## 数据修复史
- 赛果库曾主客全颠倒；2026-09-14 全量清理（`dedup_results_history.py` v2）：4624→3059，主客分布 35.0/26.4/38.6→42.4/26.4/31.3，官方锚同向率 100%。
- ❗归档污染**每次步骤0 都会复发**（`archive_results()` 写回反序）→ master 319a949 新增 `align_results_history_to_official()` 自动对齐。自检看主客分布是否恢复主场优势。
- ❗教训：「保留较早/较晚日期副本」等日期启发式 100% 不可靠；唯一锚=体彩官方赛果 API。
- 改数据后必 `build_league_profile.py` → 删/重拟合 platt_params.json → 重跑引擎。
- **1X2 缺失用比分盘反推**（`_local_prepare.py`，31 档去水聚合）：仅限当日新鲜比分盘；09-01 及更早禁回填。

## 比分口径
- 头条=`top_scores[0]` 联合众数（**不可大胆化**）；双档=`top_scores[1]`+`top_scores[2]`；「量级参考」列=round(λ) 仅参考。复盘 `gen_review.predict_scores()` 的 band 同步取 `ts[1:3]`。
- 基准（4036 场）：联合众数 14.94% ＞ floor(λ) 13.85% ＞ round(λ) 13.06% ＞ 常数 1:1 12.93%；Top1/Top2/Top3=14.94/26.54/35.48%，±1球 67.24%。病灶=退化（65.8% 首选 1:1）→必须挑场次。
- λ≤2.6 时单点最值得看（18~22%）；**严禁 k>1 追高**。算 ±1 球邻域须用去重格集合（禁 `sum(g[max(0,h+da)])`，边界重复计数）。提升只在「分布/新信息源」，调因素=过拟合死路。

## 比分精选 / 大胆档（2026-09-16 定调，09-17 修口径）
- 常量（`selection_algo.py`）：`TIER_PK=6`/`TIER_BD=4`；档数=以 10 场为基准 1 档、每多 8 场加 1 档（`N_TIER_BASE=10`/`N_TIER_STEP=8`/`TIER_MAX=5`），按**非冷启动**场次数算。第一档准确率优先，冷启动场次一律排除。
- 两档独立计算：比分精选质量=命中比分概率×λ质量系数+1:1 降权；大胆档质量=量级档概率+极限档概率（由自带模型给出，见下条解耦说明）。
- ~~`bd_lambda_min` 语义=「优先满足」非「硬剔除」，最优 3.0~~ **已废弃（09-17 解耦改造时移除）**：它是借用的比分精选 λ 口径，与「两档互不关联」冲突，由大胆档自带模型的 `bd_total_shift` 承担激进程度。
- ❗**选取算法唯一实现 = `selection_algo.py`**；`_gen_report.py`（渲染）与 `_optimize_selection.py`（回放）一律 `import selection_algo as SA`，命中判定用 `SA.pk_result`/`SA.bd_result`。**回放选取也必须调 `SA.rank_pk`/`SA.rank_bold`**（09-17 前优化器自写排序、且不排冷启动 → 4/12 天选出的场次与生产不同，调参等于评估另一个算法）。
- **比分精选自带模型** `pk_dist`/`pk_ref`（09-17 补齐，与大胆档对称）：引擎 λ 独立泊松 → 自己三象限缩放到**已发布 1X2**（`pk_align_1x2=1`）→ 自己取头条/双档。**不读引擎比分矩阵**。
- ❗**选场口径 ≠ 展示口径**（用户 09-17 定义「单独计算」）：两档的**选场**一律取自今日引擎计算结果（`pk_quality` = 引擎口径命中比分概率 × λ 质量系数）；**展示的预测**由各板块自己算。`pk_tuple` = (自算头条, 自算概率%, λ总, **引擎把握度**)，排序只看第 4 项，前 3 项供渲染。`pk_result` 按展示口径判命中。
- `bd_tuple` 必须保持 **2 元组**（质量分, λ总量）：`_gen_report.py` 用 `key=lambda x: (-x[0], -x[1])` 且 `_is_cold(x[2])` 解包，改成 3 元组会连环崩。
- 引擎自身比分口径（`hit_pick`/`band_scores`）**只服务报告正文（总览/串关）与 gen_review 复盘**，不参与两档的预测与排序。
- 每日优化护栏：改善≥0.3pp 才采纳、可用天数<5 保留默认（防小样本过拟合；连续保持默认属正常，勿放宽）。
- ⚠️ `_gen_report.py`/`_optimize_selection.py` 只在工作盘（gh-pages 未跟踪、master `tools/prediction/` 里的 gen_report.py 是 09-05 旧版，勿混用）→ 改后只需重跑报告+推 gh-pages；但它们依赖的 `selection_algo.py` 必须入库（gh-pages 根 + master `tools/prediction/`）。
- **两块板块彻底解耦（2026-09-17 定调，用户要求「两档单独计算、互不关联」）**：
  - 唯一生产入口 = `SA.split_boards`：比分精选先占位 → 大胆档只在剩余场次中选取（**同一场次不上两榜**，低场次日 bold 腿数会 <TIER_BD，属正常）。
  - **大胆档自带模型** `bd_ref`：`bd_grid`(引擎 λ 独立泊松) + `bd_lean`(倾向，默认取引擎 1X2) → 量级档 = 象限内总球数 `max(bd_min_total, round(λ总)+bd_total_shift)` 的最高概率格；极限档 = 再 +`bd_gap`。**不读引擎比分矩阵**。
  - 参数：`pk_*`（比分精选）/ `bd_*`（大胆档）命名空间分离；`bd_lambda_min` 已退场（那是借用的比分精选口径）。生产值 `bd_total_shift=-1 / bd_min_total=2 / bd_gap=1 / bd_exclusive=1 / bd_lean_src='engine'`。
  - ❗**结构参数必须用大样本定，小样本只微调**：12 天回放曾把 `shift=+1` 选成最优，178 天/2462 场证伪它最差（+1 → 19.5%，-1 → 31.5%，-9.6pp）。优化器网格已限定 `shift∈{-1,0}`。
  - 大样本验证工具：`_bd_bigsample.py`（反解 λ 自 `_calib_backup_20260916/backtest_after.json`，2462 场）+ `_bd_indep_probe.py`（12 天回放对照）——均为工作盘探针，**被 gitignore，master 无正本**。
  - 效果：12 天回放 bold 10.4% → 22.7%（其中互斥贡献 +8.1pp）；大样本 29.5% → 31.5%；比分精选展示改自算后 12 天 23/72(31.9%, 命中日 11/12) → **26/72(36.1%, 命中日 12/12)**（选场不变，只换展示口径）。
  - ❗**排名信号与展示模型要分开评估**：比分精选若连选场也改用自算概率，12 天回放反而掉到 22/72 —— 引擎口径的把握度含市场信息，更适合选场；自算分布更适合出双档（200 场样本 双档 17.5% vs 引擎 11.5%）。
- ❗**快照必须落盘 `cold`/`data_n`**（2026-09-17 修）：`dump_prediction_snapshot` 此前不写这两字段 → `SA.is_cold()` 对全部历史快照恒 False → 优化器回放与报告「前日回顾」都把冷启动当正常场次排（报告正文不受影响，它读 `_calc_result.json`）。**09-16 及更早的快照已无法回溯**（根目录 `_calc_result.json` 每日覆盖），老回放仍属「冷启动盲」口径。
- ⚠️ master `tools/prediction/calc_engine.py` 是**另一份**（路径用 `_repo_root()`），曾滞后于工作盘 → 改引擎时要同步两处（worktree 里按同样文本打补丁，勿整体 cp）。2026-09-17 补同步了快照 cold 与动态市场权重两处。
- ✔️ 报告侧 `_conf_rank`/`_bold_rank` 是 `SA.pk_tuple`/`SA.bd_tuple` 的薄封装，**没有第二份排序实现**（排除冷启动靠 `SA.is_cold`）。
- ⚠️ 报告「前日回顾」是用**当前**调参重算的（`_bold_rank` 读今日 `_TUNING`），不是当日实际发布口径 → 命中数会随调参变化（09-17 改后 09-16 大胆档显示 1/4，而当日实发为 0/4）。读回顾数字时须知此口径。

## 报告呈现纪律（红线）
- 公开页**三不落**：方法论/口径说明、回测统计量（χ²/Brier/McNemar/样本量）、私下对话引用与脚本名。只留「今日可执行结论」+量级基准（单点~15%/双档~20%/±1球~67%）。章节标题不带解释性括号；脚本注释去个人化。
- 复查：`grep -E "用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar" predictions/<date>/index.html` 须为空。

## 第七节 联赛形势（7M）
- 数据源 `data.7m.com.cn/matches_data/{id}/big/standing.js`；脚本 `_fetch_league_data.py` + `_league_match.py`。
- 联赛 id：英超92/西甲85/德甲39/意甲34/法甲93/荷甲99/葡超88/瑞超103/芬超105/挪超104/巴甲160/日职102/日乙347/法乙171/意乙95/西乙96/德乙140。**美职/亚冠精英/亚运男足/英冠/英联赛杯/解放者杯 无 7M id**（勿编造），列入 `league_match.UNAVAILABLE`。
- 排名反填：`_build_today_extras.py` 用 `match_team_strict()`（只认精确+ALIAS）。**新联赛/队名务必先补 `league_match.ALIAS`**（简→繁异译，如 巴列卡诺→華歷簡奴、皇马→皇家馬德里），`_SIMP2TRAD` 不处理异译。已修正错误条目 `赫塔费`（应为 加泰）。
- 欧冠/欧联/欧罗巴/欧协联已入 UNAVAILABLE → 显示「杯赛赛制无联赛积分榜」。

## 复盘（步骤4.5）
- `gen_review.py --date <昨日>` → `predictions/<当日>/review_<昨日>.html`，覆盖全部场次。回复列「复盘三指标」=方向命中率/比分双档命中率/λ总进球偏差。连续多日方向<50% 或 λ偏差>0.2 → 提示离线重拟合。
- Brier 差另跑 `tools/prediction/review_market.py --date <昨日> --skip-audit`（非每日强制）。
