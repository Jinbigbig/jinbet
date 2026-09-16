# JinBet 项目长期笔记（精简版；详细历史见 automations/b0bc3264/memory.md）

## 每日流水线（顺序不可乱）
0. **最先**：`git show master:update_odds_net.py > update_odds_net.py` → `python update_odds_net.py --no-push` **再** `--no-push --results-only`（顺序错→ODDS 变单引号 JS，`_local_prepare` 报「赔率 0/N」）。步骤0 会自动跑官方锚对齐（`align_results_history_to_official`），无需手工 dedup。
1. `_local_prepare.py` 2. `_build_today_extras.py` 3. `_fetch_league_data.py`（跑报告前，生成 league_data.json 供第七节积分榜）3.5 `_calc_engine.py`（查 chain 含「市场概率混合(」「比分矩阵对齐发布1X2」、路线图有 **ON·生效/ON·观察** 字样、Platt 已拟合）4. `_gen_report.py` 4.5 `gen_review.py --date <昨日>` 4.6 `_optimize_selection.py`（回放历史刷新 selection_tuning.json，供次日报告；**已挂进 14:00 定时自动化**，幂等、无改善不动文件）5. 更新 predictions/index.html 索引 → commit 只推 gh-pages（fetch+rebase，禁 force）。
- ⚠️ 引擎读根目录 `_data_batch{1..6}.json` 覆盖注入当日比赛——旧批撞车会污染预测，跑前确认无陈旧批（已备份 `_data_batch_backup_20260912/`）。
- ⚠️ 首跑当日先 `mkdir -p predictions/<date>`（目录缺失→`dump_prediction_snapshot()` 静默跳过→gen_report FileNotFoundError）。
- 引擎/脚本改动走 worktree 同步 master（路径必须 `C:/` 风格，用 `git worktree list` 查真实路径）；predictions/ 只归 gh-pages；V3.4 状态文件（strength_db/v34_state/drift_baseline/clv_log.json）属 gh-pages。新脚本勿用 `_` 前缀入库（.gitignore 任意层级匹配）；master 正本放 `tools/prediction/`。

## 分支与推送 / 协作风险
- origin=SSH 免交互（`git@github.com:Jinbigbig/jinbet.git`）；禁 GITHUB_TOKEN/HTTP 代理。**只信 `git ls-remote`**（本地 `origin/*` remote-tracking ref 常被另一会话覆写/指到起始态仓库）。
- gh-pages 远端常有 CI/外部作业追加数据提交：推送被拒→`git fetch origin gh-pages` + `git rebase origin/gh-pages`；撞数据文件冲突直接用 `git reset --hard <云端真实SHA>` 重跑全链后单提交推送。
- 判推送结果只看 ls-remote（曾被 SIGTERM 的 push 实际成功；SSH 偶发超时重试即可）。
- 根 index.html 3.4MB 程序生成：仅 IDE 注入 `data-page-node-id` 时才 `git checkout -- index.html`（否则会丢数据更新）。
- 环境坑：bash PATH 偶坏（`dirname: command not found`）→ `export PATH=/c/Users/Jin/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH`；`/c/tmp` 不跨调用持久（临时文件写仓库内）；`git stash` 常读不出 refs/stash → 用 `cat .git/refs/stash` 取 SHA 再 checkout。

## 队名归一 / 重复场次
- canonical=短名。SCHEDULE 双行根因=`RESULT_TEAM_NAME_MAP` 缺映射或存在 identity 映射（全名→全名）→**先查映射表别手工删**。已补：基多体大/拉普大学/莱红牛/曼联/哈马费萨/埃沃斯堡/拜仁/中国女/中国港女。改后重跑步骤0 须看到「合并后清理 N 场重复」。
- 当日盘口只认 index.html `YYYY-MM-DD_主_客` 键；odds_data.json 无日期键会被历史污染。
- 竞彩开售后会重编号（预排号→正式号）→ `update_odds_net.py` 已修：在售编号覆盖滞后值 + main() 编号刷新（今日及以后）+ 赔率报到新值即覆盖。**编号与官方不符先怀疑重编号，别改映射表。** 残留：SCHEDULE.matchId 仍可能是赛果API旧 id（展示无影响）。

## 引擎（勿回退）
- λ=期望值口径。市场权重 = `league_market_w(league)` 动态（按联赛市场去水准确率：50%→0.80，每 ±2pp→±0.05，夹紧 0.65~0.95）；联赛进球环境 w=0.25；**score_mix.w 真相=0.3**（线上真实值，注释/旧记忆误写 0.5）；EWMA(0.25)+MAD；基础λ窗口 N=25/DECAY=0.96。
- λ 保险丝 MAX_TOTAL=4.20/MIN_TOTAL=1.60/MAX_SINGLE=3.20（触顶=过激进勿调高）；`MIN_SINGLE=0.18`（单队 λ 下界，反解内夹紧、总量守恒）、`ZF_CAP=1.0`（零封修正只削弱不放大）、`LEAGUE_EB_K=40`（联赛基线经验贝叶斯收缩）。三者有 4036 场对照（`score_floor_probe.py`/`clean_sheet_floor_scan.py`）。
- 引擎输出 `data_n`{home,away} 与 `cold`；报告侧冷启动场次不进「比分精选」、可信度显示「数据不足」。
- SCORE_ALIGN（第七步D）：比分矩阵三象限缩放到已发布 1X2，勿回退。
- **星级=胜平负倾向确定性**（Platt 后 max(1X2)，阈值 0.44/0.50/0.57/0.66）。旧「星级=比分众数概率」已弃。
- V3.4 五模块已接线（`main()` 日频调用）：`BRIER_OPT` ON·生效（每 7 天最多一次 walk-forward，改善≥0.3% 且落 0.60~0.85 才采纳→`v34_tuned.json`）；`KALMAN_STRENGTH` **ON·生效**（修正点在第三步C=市场混合前模型侧 λ）；`HEDGE_ENSEMBLE` **ON·观察**（apply=False，只记录不改预测，属**故意**非 bug）；`CLV_TRACK`/`DRIFT_MONITOR` ON（只监控）。另：平局 boost `0.25*exp(-|λh-λa|/0.45)`（Platt 后 / SCORE_ALIGN 前）。
- `platt_params.json` 已纳入版本管理（n=1981）。改市场权重或市场混合方式后须重拟合。
- ✅ **权重口径不一致（2026-09-16 已修复）**：原 `fit_platt_params` 按固定 `MARKET_W=0.80` 拟合，而 `calc_match` 用动态 `league_market_w`（夹紧 0.65~0.95）→ 偏离 0.80 的联赛 Platt 校准错配。已改为 fit 内 `league_market_w(league)`。回测（2462 场 walk-forward 01-30→09-09）：准确率 51.10%→51.26%、Brier 0.19857→0.19850、LogLoss 1.00429→1.00371，平局行命中 43.9%→44.2%，一致小幅改善。

## 二级盘 / 市场结论
- 二级盘（market_calib.json）输入须用未混市场 λ（lam_h_B/lam_a_B）；置信门槛 `|让球|≥3`/分歧>25pp/无1X2锚点→低置信「勿跟」。
- 纯市场去水 1X2 最优 > 生产 > 纯模型；市场已吞掉基本面，别再补。平均返还率 88.56%→按市场买必输。二级盘 alpha：让球✅｜总进球✅不稳｜比分❌｜1X2❌。大比分（6+/7+）市场系统性高估，只观察不推荐。

## 已回测否决（勿再试）
比分盘/总进球盘并入网格、λ 线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS。判 alpha 看样本外 Brier+分月稳定。

## 数据修复史（要点）
- 赛果库曾主客全颠倒（`fetch_163_results` 主客反序双写）；2026-09-10 修源头；**2026-09-14 全量清理**（`dedup_results_history.py` v2）：跨日孪生 1531 对 + 单条反转 1244 条，4624→**3059**；主客分布 35.0/26.4/38.6→**42.4/26.4/31.3**；官方锚同向率 100%。下游重建 `league_profile.json`（3058 场、基线 2.8506、39 联赛、score_mix.w 仍 0.3）+ 重拟合 platt（n 1981）。
- ❗**复发已修（master 319a949）**：步骤0 的 `archive_results()` 会把反序写回 → 新增 `align_results_history_to_official()` 自动对齐，**以后跑步骤0 自愈**。实况：**归档污染每次步骤0 都会重新出现**（2026-09-16 第三次复发，4602 条/1531 组重复 → 自愈后 3086 条/0 重复/主客 42.6-26.3-31.2），判据=日志有 `[DEDUP-ALIGN]` 行；无该行说明 `dedup_results_history.py` 找不到（根目录或 `tools/prediction/` 放一份即可）。
- ❗**教训**：「保留较早/较晚日期副本」等日期启发式 100% 不可靠；唯一锚=体彩官方赛果 API；自检看主客分布是否恢复主场优势。
- 改数据后必 `build_league_profile.py` → 删/重拟合 platt_params.json → 重跑引擎。
- **1X2 缺失用比分盘反推**（`_local_prepare.py`）：31 档去水按主/平/客聚合，仅当日新鲜比分盘（09-03 起方向一致率 100%）；09-01 及更早禁回填。

## 比分口径（头条=联合众数，双档=第2/第3可能比分）
- 头条=`top_scores[0]` 联合众数；**不可"大胆化"**（argmax 是单场命中最优解，任何 λ 分档下众数都赢）。「量级参考」列=round(λ) 仅参考。
- 双档=`top_scores[1]`+`top_scores[2]`（模型排序第 2、第 3 可能比分，2026-09-16 起由"稳档(众数)+胆档(λ取整)"改为纯次优双档）；文案「长期双档命中约 20%」（4036 场：Top2 11.6%+Top3 8.9%≈20.5%）。复盘 `gen_review.predict_scores()` 的 `band` 同步取 `ts[1:3]`。
- 另有「🔥 大胆档」板块（独立计算：按「量级档/极限档」模型概率排序，取第一档前 4 场）。
- 基准（4036 场）：联合众数 14.94% ＞ floor(λ) 13.85% ＞ round(λ) 13.06% ＞ 常数 1:1 12.93%（McNemar p<0.001）；阶梯 Top1 14.94/Top2 26.54/Top3 35.48/±1球 67.24%。
- 病灶=退化（65.8% 首选 1:1）→ 必须挑场次：「🎯 今日比分精选」按质量（命中比分概率×λ质量系数）取第一档前 6 场。
- λ≤2.6（约 1/3 场）单点 18~22% 最值得看比分；9 月 λ 3.05~3.13 异常高，**严禁 k>1 追高**。
- ⚠️ 算 ±1 球邻域禁用 `sum(g[max(0,h+da)])`（边界重复计数），须用去重格集合。
- 提升只在「分布/新信息源」，调因素（坐标上升）实证过拟合死路。

## 比分精选 / 大胆档 分档数量与每日优化（2026-09-16 定调）
- 分档常量（`_gen_report.py`）：`TIER_PK=6`（比分精选每档）、`TIER_BD=4`（大胆档每档）；**档数规则=以 10 场为基准 1 档，每多 8 场加 1 档**：`N_TIER_BASE=10`、`N_TIER_STEP=8`、`TIER_MAX=5`（上限护栏）。即 10场→1档/6+4、18→2档/12+8、26→3档/18+12、34→4档/24+16、42→5档/30+20。档数按**非冷启动**场次数算（今日 17 场中有 2 场冷启动 → 15 场 → 1 档）。
- **第一档准确率优先**：两档各自按质量降序，第一档取质量最高的 6/4 场，第二档取次优增量（表格内有「第二档」分隔行）；冷启动场次一律排除。
- 两档**独立计算**：比分精选质量 = 命中比分概率 × λ 质量系数（低 λ 命中率高，见 score_cred 表）+ 1:1 退化降权；大胆档质量 = max(极限档概率, 量级档概率)，可设 `bd_lambda_min` 排除过低 λ。两档互不以对方为输入。
- 每日优化：新增 `_optimize_selection.py`（步骤 4.6，跑在 `gen_review.py` 之后）回放历史 pred_snapshot + 实际赛果，网格搜索上述旋钮，改善 ≥0.3pp 才采纳、可用天数 <5 则保留默认，写入 **`selection_tuning.json`**（不带下划线故可入库，被 `_gen_report.py` 读取）。首跑 11 天历史无改善→保持默认（防小样本过拟合）。
- ⚠️ `_gen_report.py` / `_optimize_selection.py` 是 `_` 前缀，被 .gitignore 任意层级忽略，只存在于工作盘（master 目前无 tools/prediction/ 正本）；改这两个脚本后**只需重跑报告+推 gh-pages**，不必同步 master。

## 报告呈现纪律（红线）
- 公开页**三不落**：方法论/口径说明、回测统计量（χ²/Brier/McNemar/样本量）、私下对话引用与脚本名。只留「今日可执行结论」+ 量级基准（单点~15%/双档~20%/±1球~67%）。
- 章节标题不带解释性括号。脚本注释去个人化。
- 复查：`grep -E "用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar" predictions/<date>/index.html` 须为空。

## 第七节 联赛形势（7M）
- 数据源 `data.7m.com.cn/matches_data/{id}/big/standing.js`。脚本：`_fetch_league_data.py`、`_league_match.py`（简→繁映射，未匹配显示「排名—」）。
- 联赛 id：英超92/西甲85/德甲39/意甲34/法甲93/荷甲99/葡超88/瑞超103/芬超105/挪超104/巴甲160/日职102/日乙347/法乙171/意乙95/西乙96/德乙140。**美职(MLS)、亚冠精英、亚运男足、英冠、英联赛杯、解放者杯 7M 无对应赛季 id**（2026-09-15 用 `_7m_scan.py` 扫 id 1-260 + 600-1000 确认英冠亦无，勿编造）；这些联赛在 `league_match.UNAVAILABLE` 中列明，报告显示说明替代。
- 排名反填：`_build_today_extras.py` 除回收旧报告外，另从 `league_data.json` 用 `match_team_strict()`（只认精确+ALIAS，关闭子串回退）反填 home_rank/away_rank。**新增联赛/新队名务必先补 `league_match.ALIAS`（简→繁异译，如 巴列卡诺→華歷簡奴、西班牙人→愛斯賓奴、皇马→皇家馬德里），否则排名全「—」**；`_SIMP2TRAD` 只覆盖差异字，不能处理异译。已修正错误条目 `赫塔费`（曾误指 華歷簡奴＝巴列卡诺，应为 加泰）。巴甲 20 队已于 2026-09-16 全部补齐（博塔弗戈→保地花高、格雷米奥→甘美奧、帕梅拉斯→彭美拉斯、巴竞技→帕拉尼恩斯、米竞技→明尼路、布拉干RB→巴拉干天奴、里莫→瑞模貝雷PA 等）。
- `UNAVAILABLE` 已含 欧冠/欧联/**欧罗巴**/欧协联（均为杯赛赛制说明）→ 报告显示「杯赛赛制无联赛积分榜」而非「获取失败」。

## 复盘（步骤4.5）
- `gen_review.py --date <昨日>` → `predictions/<当日>/review_<昨日>.html`，覆盖全部场次（不依赖赔率）；回复列「复盘三指标」=方向命中率/比分双档命中率/λ总进球偏差。连续多日方向<50% 或 λ偏差>0.2 → 提示离线重拟合。
- Brier 差另跑 `tools/prediction/review_market.py --date <昨日> --skip-audit`（非每日强制）。
