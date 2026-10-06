# 自动化 b0bc3264 执行记忆（JinBet 每日流水线）

## 2026-10-06（14:00 常规流水线）— 全链跑通，12 场
**结果**：全链跑通，**12 场**（周二001–012：国际赛 x3 / 欧国联 x8 / 美职 x1；赔率 12/12；冷启动 2 场 002/010）→ 非冷启动 10 场 → **1 档**：比分精选 6 场（009/005/006/003/007/004）、大胆档 4 场（008/011/012/001）；串关 4 组（方向 A/B + 信心 A/B，冷门 A/B 复用）。gh-pages 单提交（ls-remote 核验）。master 未动（`f9fb275`，今日无脚本改动）。
- ❗**并发提交处置**：本地 HEAD `33b3a68`（两个非 JinBet 渲染器提交：`ad37d02`「report: 2026-10-05」把已发布 JinBet 10-05 页从 1801 行压到 432 行；`33b3a68`「report: 2026-10-06」生成 876 行同日期页；二者均只跟踪 `_calc_result.json`）→ `git tag -f backup_20261006_pre 33b3a68` + `git reset --hard 11e3132`（云端）。因两页日期分别=已有 JinBet 报告日(10-05)与本次产出日(10-06)，**不保留**，避免覆盖 JinBet 正版页。
- 步骤0 `[DEDUP-ALIGN]` 生效（235/261，写盘 261，备份 `_hist_backup_2026-10-06`）；无陈旧 batch；ODDS 3181 / results_data 3282（回填更新 3108、新增 0）。
- 步骤2：H2H 0/12、近期 10/12、主客场 8/12、排名 0/12、新闻 0/12；步骤2.5 仅美职（7M 459，实为 USL）1 联赛（国际赛/欧国联无 7M 映射）。
- 步骤3 链路标记齐全：Platt n=**2231**、MARKET_BLEND_PROB ON、SCORE_ALIGN ON、BRIER_OPT/KALMAN/CLV/DRIFT ON·生效、HEDGE ON·观察。
- 步骤4.5 复盘 **10-05（7 场）**：方向 **5/7=71%**、单点 0/7=0%、双档 1/7=14%、λ偏差 **+0.80**（n=7；前次可核算日 09-30 为 +1.02，符号同向但中间 10-01~10-04 无核算基数 → 暂不触发重拟合，继续观察）。
- 步骤4.6 **与上一版一致（无新采纳）**：10 旋钮完全未变（bd_total_shift=-1 / bd_min_total=3 / pk_degen_down=0.9 / pk_lambda_caps=[2.6,3.0,3.0]…）；仅 `_meta` tuned_at 10-05→10-06、days 22→23、指标刷新（pk base 59.13→59.57、bd base 27.17→33.91、bd holdout 17.86→27.86）。optimizer 仍打 adopt=True 勿误读。内容有变化 → 重跑报告 + 提交 selection_tuning.json。
- DRIFT_MONITOR 连续第 **15** 日 `league_baselines` 漂移（亚冠精英 51.97% / 德乙 50.0% / **日联赛杯 50.0%**（英联赛杯已退出名单））→ 已在回复提示离线重拟合 market_calib/Platt。
- 根 index.html 无 `data-page-node-id`（grep=0，未 checkout）；报告红线 grep 0、复盘页红线 grep 0。predictions/index.html 插入 10-06 行（12 场 / 国际赛 x3 + 欧国联 x8 + 美职 x1）。

## 2026-10-05（14:00 常规流水线）— 全链跑通，7 场
**结果**：全链跑通，**7 场**（周一001–007 全部欧国联；赔率 7/7，无冷启动/无别名行）。档数 **1 档** → 比分精选 6 场 / 大胆档 1 场（003 罗马尼亚vs瑞典）；串关 4 组。gh-pages 单提交（ls-remote 核验）。master 未动（`f9fb275`，今日无脚本改动）。
- **无并发分叉**：本地 HEAD == 云端 `cc500f2`（0/0）→ 直接追加单提交，无需 tag/reset。
- 步骤0：`[DEDUP-ALIGN]` 生效（235/260，写盘 260，备份 `_hist_backup_2026-10-05`）；无陈旧 batch；ODDS 3168 / results_data 3275（更新 3101、新增 0）。
- 步骤2：H2H 0/7、近期 7/7、主客场 6/7、排名 0/7；步骤2.5 欧国联无 7M 映射 → league_data 0 联赛（正常）。链路标记齐全，Platt n=2223。
- 步骤4.5 **无复盘**：`predictions/2026-10-04/pred_snapshot.json` 不存在 → 打印「无快照」跳过（10-02 起连续第 4 日无 JinBet 报告 → 无复盘三指标）。
- 步骤4.6 **保持默认**（10 旋钮全未变；仅 `_meta.tuned_at` 10-04→10-05，`days_used` 仍 22）。optimizer 仍打 adopt=True 勿误读。内容有变化 → 重跑报告 + 提交 selection_tuning.json。
- 根 index.html 无 `data-page-node-id`（grep=0，未 checkout）；报告红线 grep 0。记忆随本次 chore 提交入库。
- DRIFT_MONITOR 连续第 **14** 日 `league_baselines` 漂移（亚冠精英 51.97% / 德乙 50.0% / 英联赛杯 18.03%）→ 已在回复提示离线重拟合 market_calib/Platt。
- predictions/index.html 的 commited 版本本就含 IDE 注入的 `data-page-node-id`（10 处）——与根 index.html 不同，**该文件历史上已被注入且已入库，正常**，只需插入当日行。

## 2026-10-04（14:00 常规流水线）— 当日无在售赛事
**结果**：今日 **0 场** → 步骤1 后按规程终止（2/2.5/3/4 未执行），**无报告链接、无串关、无档位**。gh-pages 单提交（见下，ls-remote 核验）。master 未动。
- ❗**0 场已三源互证，勿再当提取故障排查**：① `_local_prepare.py` 从 SCHEDULE 提取 0 场（SCHEDULE 最新日期止于 2026-10-01）；② 体彩竞彩计算器 API 返回 `vtoolsConfig.offLineStopMessage = 抱歉，本彩种已停止销售`、matchInfoList 空；③ 500.com `trade.500.com/jczq/?date=2026-10-04` 显示「暂无赛事信息」。另：体彩赛果 API 在 09-29~10-05 区间仅返回 23 场（全 ≤09-30），10-01 起全 0；**网易竞彩 API 对近期所有日期返回空 → 网易主源已失效**。
- 步骤0：正本取 `git ls-remote origin master` = `f9fb275`（本地 master 引用不可信）；本轮**未见 `[DEDUP-ALIGN]` 行**（脚本已换成 f9fb275 版，行为正常，勿误判为缺文件）；无陈旧 batch；ODDS 3161 条、归档 87 日期。
- 步骤4.5 复盘 10-03：`predictions/2026-10-03/pred_snapshot.json` 缺失 → 打印「无快照…（该日可能未生成报告）」跳过；**无复盘三指标可报**。
- 步骤4.6 **保持默认**（10 旋钮全未变；仅 `_meta.tuned_at` 10-02→10-04，`days_used` 仍 22 —— 10-01~10-03 无新赛果可核算）。optimizer 仍打 adopt=True 勿误读。内容有变化 → 随本次 chore 提交 selection_tuning.json。
- ❗传 4 状态（**与 10-02 不同，本次不丢弃**）：本地 gh-pages 有两个**非 JinBet 流水线**的未推送提交 —— `21a7771`「report: 2026-10-03」实为 **北单 27 场深度分析报告**（标题含「北单」，非竞彩）；`9de6547`「report: 2026-10-04」实为「AI 足球预测报告 · 2026-10-04」16 场、**无串关推荐/比分精选/大胆档小节** → 非 JinBet 渲染器。处置 = `git tag backup_20261004_pre 9de6547` + `git reset --soft 21a7771`（保留两页与索引行，避免毁掉并行作业成果）→ 与数据刷新合为一条 chore 提交推 gh-pages。两页红线 grep 均 0。
- 根 index.html 无 `data-page-node-id`（grep=0，未 checkout）；记忆随本次 chore 提交入库（防次日 reset 回退）。

## 2026-10-02（14:00 常规流水线）— 当日无在售赛事
**结果**：今日 **0 场**（`_local_prepare.py` 对 2026-10-02 从 SCHEDULE 提取 0 场；Trae Work 并行页面标题「2026年10月2日 足球新闻汇总报告（当日无竞彩在售场次）」双证）→ 按规程终止预测报告链（步骤 2/2.5/3/4 均未执行），未生成 `predictions/2026-10-02/index.html` → **无报告链接、无串关、无档位**。master `ce309b9 → f9fb275`（gen_review 修复，ls-remote 核验）；gh-pages 单提交见下。
- 并发作业：本地 HEAD `4d62aac`（今日早版报告，父=云端 `1739e04`，仅跟踪 index.html/odds_data/predictions，**未跟踪 root `_` 脚本**）→ `tag backup_20261002_pre` + `reset --hard 1739e04` + 重跑。**该早版本身就是「当日无竞彩在售场次」空页 → 0 场是真无赛事，不是提取失败。**
- 步骤0 `[DEDUP-ALIGN]` 生效（235/257，写盘 257，备份 `_hist_backup_2026-10-02`）；无陈旧 batch；ODDS 3161 / results_data 3275（回填更新 3101 条、新增 0）。`dedup_results_history.py` 在根目录。
- 步骤4.5 复盘 10-01：预测 1 场（周四001 美职 纽约红牛 vs 圣路易城），**赛果到 0 场** —— `results_data.json` 最新日期仅到 `2026-09-30`，该场官方结果尚未归档 → 复盘三指标 **0/0**（无核算基数）、λ偏差 +0.00。页面仍输出累计基准（23 比赛日 / 311 场：方向 58.8%、单点 12.2%、双档 18.6%）。**赛果缺档 ≠ 引擎失手，勿据此判定方向连击。**
- 步骤4.6 **保持默认**（10 旋钮全未变；仅 `_meta.tuned_at` 10-01→10-02，`days_used` 仍 22 —— 因 10-01 无赛果，可核算天数未增长）。optimizer 仍打 adopt=True 勿误读。
- **修复 gen_review.py 两处 0 赛果边界 bug（新增，已同步 master）**：① `misses` 为空即断言「方向全部命中」→ 0 赛果日误报，改为 `nres==0` 时输出「赛果尚未归档（0 场可核算）；官方结果更新后本页自动补算。」；② 逐场行对无赛果场次渲染 ✘（误示失手）→ 改为灰色 ⏳。落盘 master `tools/prediction/gen_review.py`（该文件 master 为 **LF**、工作盘为 CRLF → 须先做 CRLF→LF 行尾归一，否则整文件行尾 churn）。
- 根 index.html 无 `data-page-node-id`（grep=0，未 checkout）；复盘页红线 grep 命中 0。
- 记忆随本次 chore 提交入库（防次日 reset 回退）。

## 2026-10-01（14:00 常规流水线）
**结果**：全链跑通，**1 场**（赔率 1/1，无冷启动/无别名行）。gh-pages `9eda23a → 待核验`；master 未动（今日无脚本改动，`4b887f9`）。红线 grep 报告与复盘页均 0；根 index.html 无 `data-page-node-id`（未 checkout）。
- 并发作业：本地 HEAD `2611c77`（今日早版报告，父=云端 9eda23a，**未跟踪 root `_` 脚本**，只改 index.html/数据/predictions）→ `tag backup_20261001_pre` + `reset --hard 9eda23a` + 重跑全链单提交。注意该早版把 root index.html 删了 9.6 万行（`-96928`），reset 回云端后由步骤0 重建，正常。
- 步骤0 `[DEDUP-ALIGN]` 生效（235/256，写盘 256 文件，备份 `_hist_backup_2026-10-01`）；无陈旧 batch；ODDS 3161 / results_data 3275（更新 3103 条、新增 0）；`dedup_results_history.py` 在根目录。
- 1 场：周四001 美职 纽约红牛 vs 圣路易城。步骤2.5 美职(7M 459，实为 USL) 1 联赛；H2H 0/1、近期 1/1、主客场 0/1、排名 0/1。
- 头条 `1:2` 9.3%（与 `top_scores[0]` 1:1 13.2% 跨象限，设计允许）；快照/`_calc_result`/报告三处首选一致（报告渲染 `1-2`）。方向 客胜 56.5%、星级 3、让球 +1·让球负 EV 1.028、冷门 中 42.2%、λ总 3.05。
- 1 场 → **0 档**（比分精选/大胆档均 0 场）、**串关 0 组**。前日回顾：09-30 两场比分精选均 ❌ 未中（实际 2-1 / 1-1）。
- 复盘 09-30（2 场）：方向 **1/2=50%**、单点 0/2=0%、双档 0/2=0%、λ偏差 **+1.02**（n=2；昨日 -0.10 → 反号，不触发重拟合）。
- 4.6 **保持默认**（10 旋钮全未变，仅 `_meta.tuned_at` 09-30→10-01 / days 保持 22；optimizer 打 adopt=True 勿误读）→ 内容有变化仍重跑报告；无真实参数变更。
- DRIFT_MONITOR 连续第 **13** 日 `league_baselines` 漂移（亚冠精英 51.97% / 德乙 50.0% / 英联赛杯 18.03%）→ 已在回复提示离线重拟合 market_calib/Platt。
- 记忆已随 report 提交入库（防次日 reset 回退）。

## 2026-09-30（14:00 常规流水线）
**结果**：全链跑通，2 场（赔率 2/2，无冷启动/无别名行）。gh-pages `92321cb → 4dad411`（ls-remote 核验，快进）；master 未动（今日无脚本改动，`9886e71`）。线上报告/复盘/索引/selection_tuning 破缓存全 200（新页首次 404 → 等 45s 转 200）；红线 grep 报告与复盘页均 0。
- 并发作业：本地 HEAD `657a70c`（今日早版报告，父=云端 92321cb，**无未提交改动**，只跟踪 `_calc_result.json`）→ `tag backup_20260930_pre` + `reset --hard 92321cb` + 重跑全链单提交。**注意**：该早版提交把 `odds_data.json` 删了 8 万行（云端→早版 diff 显示 -80338），reset 回云端后由步骤0 重建，正常。
- 步骤0 `[DEDUP-ALIGN]` 生效（235/255，255 文件写盘）；无陈旧 batch；ODDS 3162 / results_data 3273（回填更新 3102 条、新增 0）；`dedup_results_history.py` 在根目录。
- 2 场：周三001/002 亚运男足（韩国亚vs中国亚、乌兹别亚vs日本亚）。步骤2.5 亚运男足无 7M 映射 → league_data 0 联赛（正常）；H2H≥3 场 0/2、近期状态 2/2、排名 0/2。
- 头条口径 2/2、变更 1 场（002 乌兹别亚vs日本亚 → 0:2，跨象限；001 保持 2:0）；`top_scores` 纯概率降序 2/2。卡片「比分双档」概率（18.0/12.4）高于快照 top_scores（14.3/11.1）属 prob_temp=1.20 重归一后的显示口径，非不一致。
- 串关 2 组（方向 A 2串1 @1.69 / 53.5%；信心 A 比分腿 001 2-0 × 002 0-2 @32.50）。前日回顾：方向串关 A/B **均 ✅ 全中**。
- 复盘 09-29（15 场）：方向 **13/15=87%**、单点 5/15=33%、双档 4/15=27%、至少一项 93%、λ偏差 **-0.10**（n=15，阈值内；昨日 -0.98 → 反号不连续）。方向 ≥50% 连续第 2 日、λ偏差连续 2 日在阈内 → 不触发重拟合。
- 4.6 **采纳新参数**：`bd_total_shift 0→-1`、`pk_degen_down 1.0→0.9`（pk base 59.55→60.00 adopt；bd base 28.41→35.45、**holdout 25.71→37.86 同步改善** → 真采纳，非回退默认）；days 21→22。内容变化 → 重跑报告 + 提交 selection_tuning.json。
- DRIFT_MONITOR 连续第 **12** 日 `league_baselines` 漂移（亚冠精英 51.97% / 德乙 50.0% / 英联赛杯 18.03%）→ 已在回复提示离线重拟合 market_calib/Platt。global_goals/home_away_ratio 仍稳定。
- 记忆已随 chore 提交入库（防次日 reset 回退）。

## 2026-09-29（14:00 常规流水线）
**结果**：全链跑通，15 场（赔率 15/15，无冷启动/无别名行）。gh-pages `e94de92 → 449aa18`（ls-remote 核验，快进）；master 未动（今日无脚本改动）。线上报告/复盘/索引/selection_tuning 破缓存全 200；红线 grep 0（报告与复盘页均 0）。
- 并发作业：本地 HEAD 为 12:49 的早版报告 `244dbfa`（父=云端 e94de92，只跟踪 `_calc_result.json`，**未跟踪 root `_` 脚本**）→ `tag backup_20260929_pre` + `reset --hard e94de92` + 重跑全链单提交。**本地 master 分支停在 897636a（behind 55）→ 取正本须用 `git ls-remote origin master` 的 SHA（本次 6a5d078），不可用本地 `master:` 引用。**
- 步骤0 `[DEDUP-ALIGN]` 生效（235/254，6 行）；无陈旧 batch；ODDS 3160 / results_data 3258；`dedup_results_history.py` 在根目录（tools/prediction/ 无）。
- 15 场：周二001–015 亚运女足 x2 / 国际赛 x2 / 日联赛杯 x4 / 欧国联 x7。步骤2.5 四联赛全无 7M 映射 → league_data 0 联赛（正常）；排名注入 0/15，H2H≥3 场 0/15。
- 头条口径 15/15、`top_scores` 纯降序 15/15；分布 2:0 x4 / 1:0 x3 / 0:2 x3 / 1:2 x3 / 1:1 x2 / 2:1 x1（1:1 未超 cap）。串关 4 组（方向 A/B + 信心 A/B，冷门 A/B 复用）。前日回顾读 09-28 页：3 组串关全中 1 组。
- 复盘 09-28（8 场）：方向 3/8=38%、单点 0/8=0%、双档 2/8=25%、λ偏差 **-0.98**（n=8；符号 -0.39/+0.70/-0.98 不连续 → 不触发重拟合）。
- 4.6 **采纳新参数**：`bd_total_shift -1→0`、`bd_min_total 2→3`（optimizer 报 bd base 26.43→36.43、**holdout 25.71→35.71 也改善** → 本次是真采纳，非回退默认）；pk 旋钮未变。内容变化 → 重跑报告 + 提交 selection_tuning.json。
- DRIFT_MONITOR 连续第 11 日 `league_baselines` 漂移（亚冠精英 51.97% / 德乙 50.0% / 英联赛杯 18.03%）→ 已在回复提示离线重拟合 market_calib/Platt。
- 记忆已随 chore 提交入库（防次日 reset 回退）。

## 2026-09-28（14:00 常规流水线）
**结果**：全链跑通，8 场（赔率 8/8，无冷启动）。gh-pages `4e4993b → 待核验`；master 未动（今日无脚本改动）。红线 grep 0。
- 并发作业：本地 HEAD 为今早早版报告 `c77c1bd`（父=云端 4e4993b，只跟踪 `_calc_result.json` 一个 `_` 文件，无 root 脚本风险）→ `tag backup_20260928_pre` + `reset --hard 4e4993b` + 重跑全链单提交。
- 步骤0 `[DEDUP-ALIGN]` 生效（6 行）；无陈旧 batch；ODDS 3145 / results_data 3250。
- 8 场：国际赛 x2 / 欧国联 x6。步骤2.5 两联赛均无 7M 映射 → league_data 0 联赛（正常）；排名注入 0/8。
- 头条口径 8/8；1:1 恰 4 场（= head_day_cap）。calc/snapshot/报告首选比分 8/8 一致（报告用短横线 `2-0` 格式，核对时注意别拿 `2:0` 比）。
- 复盘 09-27（9 场）：方向 6/9=67%、单点 11%、双档 22%、λ偏差 **+0.70**（n=9；与前日 -0.39 反号 → 不触发重拟合）。
- ❗4.6 **本次有大变化**：`bd_total_shift 0→-1`、`bd_min_total 3→2`（大胆档回退默认）；比分精选旋钮未变。原因：留出段（末 6 日）四个候选格目标值全为 30.00（逐日命中互换后聚合相等）→ `full-base≥0.3 且 hold-hold_base≥0.3` 恒不成立 → 脚本按设计「无候选满足就保留默认」写默认值。**注意**：脚本 `out = dict(DEFAULT_TUNING)` 起步，不继承上一版已采纳值，因此「未再确认」= 回退默认，这是设计行为（全样本上 shift=0/mt=3 为 34.75 vs 默认 27.75，属样本内差异）。内容变化 → 重跑报告 + 提交 selection_tuning.json。
- DRIFT_MONITOR 连续第 10 日 `league_baselines` 漂移（亚冠精英 51.97% / 德乙 50.0% / 英联赛杯 18.03%）→ 已在回复提示离线重拟合 market_calib/Platt。

## 2026-09-27（14:00 常规流水线）
**结果**：全链跑通，9 场（赔率 9/9，无别名行/无冷启动）。gh-pages `ee03b34 → 3f96885`（ls-remote 核验，快进）；master 未动（今日无脚本改动）。线上报告/复盘/索引/selection_tuning 全 200（新文件首次 404 属 Pages 部署延迟，等 60s 转 200）；红线 grep 0。
- 并发作业处置：本地未推送 `dd58cc7`（09-27 早版报告，基于 f954215，**未跟踪 root `_` 脚本**——只跟踪 `_calc_result.json` 数据文件）与云端 ee03b34（3 个 09-26 数据提交）分叉 → `git tag -f backup_20260927_pre dd58cc7` + `reset --hard ee03b34` + 重跑全链单提交。reset 前可 `git ls-tree <db> --name-only | grep '^_'` 预判是否需事后恢复脚本。
- ❗❗ **本次 reset 的真损失在记忆文件**：`.workbuddy/memory/` 被 gh-pages 跟踪，而 MEMORY.md 的 09-26 增补与 automation memory 的 09-26 条目都是「已跟踪未提交」的工作区改动 → `reset --hard` 直接回退。事后按会话初始读到的原文逐条恢复。**教训：记忆写完必须 `git add .workbuddy/memory` 并随当日或次日 chore 提交入库。**
- 步骤0 `[DEDUP-ALIGN]` 生效（235/252）；无陈旧 batch；ODDS 3136 / results_data 3241。
- 9 场：韩职 x1 / 国际赛 x1 / 荷乙 x1 / 欧国联 x5 / 美职 x1。步骤2.5 取到 2 联赛（美职/荷乙）；排名注入 0/9（无 7M 队名映射）。
- 头条口径覆盖 9/9：1:1 / 1:1 / 2:1 / 2:1 / 1:2 / 2:1 / 2:1 / 1:1 / 1:2（1:1 恰 3 场，未超 head_day_cap=4）。
- 报告 9 场卡片 / 串关 4 组（方向 A/B + 信心 A/B，冷门 A/B 复用信心腿）。前日回顾读 09-26 已发布页：8 组串关全中 2 组（方向B/方向C 全中）。
- 复盘 09-26（24 场）：方向 18/24=75%、单点 3/24=12%、双档 3/24=12%、至少一项 75%、λ偏差 **-0.39** 球/场（单日超阈但与前后几日符号不一致 → 不触发重拟合）。
- 4.6：**保持默认**（10 旋钮完全未变，仅 `_meta` 刷新 days 18→19 / tuned_at / 指标；optimizer 打 adopt=True 勿误读）。内容变化 → 重跑报告 + 提交 selection_tuning.json。
- DRIFT_MONITOR 连续第 9 日 `league_baselines` 漂移（亚冠精英 51.97% / 德乙 50.0% / 英联赛杯 18.03%）→ 已在回复提示离线重拟合 market_calib/Platt。
- ⚠️ 步骤3 链路标记真实文案 = `MARKET_BLEND_PROB ON  市场概率混合已启用(V3.2)` + `SCORE_ALIGN ON  比分矩阵对齐发布的 1X2 已启用(V3.3)`，**旧串「市场混合(」「比分矩阵对齐发布1X2」已 grep 不到** → 按 `MARKET_BLEND_PROB|SCORE_ALIGN|ON·生效` 核。

## 2026-09-26（14:00 常规流水线）
**结果**：全链跑通，25 场（赔率 25/25，无别名行）。gh-pages `1588e1c → f954215`（ls-remote 核验，快进）；master `ee1a7a4 → ecdc6d2`。线上报告/复盘/索引/selection_tuning 全 200，红线 grep 0。
- 并发作业处置：本地未推送 `05f3996`（09-26 早版报告，无快照/复盘，且**把 root `_` 脚本与 league_data.json 纳入跟踪**）→ `git tag -f backup_20260926_pre 05f3996` + `reset --hard 1588e1c`。
- **❗新踩坑**：`reset --hard` 会把并发提交已跟踪的 `_gen_report.py / _fetch_league_data.py / _league_match.py / league_data.json` **从磁盘删除** → 必须 `git show backup_<tag>:<路径> > <路径>` 逐个恢复（本次 4 个）。以后先打 tag 再 reset。
- 步骤0 `[DEDUP-ALIGN]` 生效（235/251）；无陈旧 batch；ODDS 3131 / results_data 3217。
- 25 场：亚运男足 x2、日乙 x5、欧国联 x7、荷乙 x2、国际赛 x2、美职 x7。步骤2.5 取到 3 联赛（日乙/美职/荷乙）；**美职 7M id 459 实为 USL，报告按 UNAVAILABLE 只出说明、不落表**（正常，勿当 bug）。
- **新增 ALIAS（`_league_match.py`）**：新潟天鹅→新潟天鵝、甲府风林→甲府風林、赫拉克勒→荷华高斯、罗达JC→洛达、瓦尔韦克→RKC华域克 → 排名注入 3/25→7/25（14 队）；已同步 master `tools/prediction/league_match.py`（master 原副本缺 荷乙/ALIAS 补充）。
- 引擎 25 场全算完；头条口径覆盖 25/25、变更 20 场；快照/报告首选比分逐场比对 **25/25 一致**。档数 2 档 → 比分精选 12 场（6+6）；串关 5 组。
- 复盘 09-25（13 场）：方向 7/13=54%、单点 15%、双档 15%、λ偏差 +0.16 → 阈值内。
- 4.6：**保持默认**（10 旋钮全未变，仅 `_meta` 刷新 days 17→18 / tuned_at；optimizer 打 adopt=True 勿误读）；内容变化 → 重跑报告 + 提交 selection_tuning.json。
- DRIFT_MONITOR 连续第 8 日 `league_baselines` 漂移 → 回复提示离线重拟合 market_calib/Platt。
- 未同步 master 的其他脚本：`tools/prediction/gen_report.py` 已落后本地（无 CUP_EXTRA 杯赛卡）→ **勿用 master 副本覆盖本地 `_gen_report.py`**。

## 2026-09-24（14:00 常规流水线）
**结果**：全链跑通，8 场（赔率 8/8，无别名行）。gh-pages `978d04a → a8bd000`（ls-remote 核验，无 rebase）；线上报告/复盘/索引均 200（**本次 Pages 延迟更久：连续 404 约 2 分钟才转 200**，勿因两次 404 就判失败，用 `git ls-tree` 先确认云端文件在）；红线 grep 0。无脚本改动 → 未同步 master。
- ❗本地已有并发作业的未推送提交 `d75721a`（09-24 早版报告+odds，基于 635d074），与云端（978d04a = 3 个 09-23 数据提交）**分叉** → 处置 = `git tag backup_20260924_pre d75721a` 备份后 `git reset --hard 978d04a` + 重跑全链单提交，直接快进推送（比 09-19 的 `checkout -- .` 更省事，因当日数据全部要重算）。
- 步骤0 `[DEDUP-ALIGN]` 生效（235/249，6 行）；无陈旧 batch；步骤0b 回填 ODDS 3032 条 / results_data 3196 条（备份 `_hist_backup_2026-09-24`）。
- 8 场：001-003 国际赛（日本vs乌拉圭、韩国vs厄瓜多尔、中国vs马尔代夫）、004-008 欧国联（科索沃vs爱尔兰、葡萄牙vs威尔士、荷兰vs德国、塞尔维亚vs希腊、挪威vs丹麦）。003 冷启动（缺近期战绩）；步骤2.5 两联赛均无 7M 映射 → league_data 0 联赛（正常）；排名注入 0/8。
- 头条口径 8/8：1:0 / 1:1 / 4:0 / 1:1 / 2:0 / 1:1 / 1:1 / 2:1（1:1 恰 4 场 = `head_day_cap` 上限）；快照/报告一致，`top_scores` 仍纯概率降序。
- 档数：8 场、非冷启动 7 → **1 档**；比分精选 6 场（005/002/001/007/004/008，003 冷启动未纳入）、大胆档 1 场（006 荷兰vs德国：稳档1-1 / 量级1-3 / 极限2-3）、串关 6 组（方向A/B、信心A/B、冷门A/B）。
- 复盘 09-23（3 场）：方向 2/3=67%、单点 0/3=0%、双档 2/3=67%、λ偏差 **+0.82**（n=3）。方向 ≥50% 连续第 3 日；λ偏差由负转正（09-21 -3.25、09-22 -1.34、09-24 +0.82）→ 非同向连续，继续观察。
- 4.6：**保持默认**（10 旋钮完全未变，仅 `_meta.tuned_at` 09-23→09-24；optimizer 仍打 adopt=True，勿误读）。内容有变化 → 重跑报告 + 提交 selection_tuning.json。
- 提交 `git add -u` + 显式 add（249 文件）；根 index.html 无 `data-page-node-id`（grep=0，未 checkout）。predictions/index.html 补 09-24 行（8 场 / 国际赛 x3 + 欧国联 x5）。
- 趋势：DRIFT_MONITOR 连续第 6 日 `league_baselines` 漂移（亚冠精英 51.97% / 德乙 50.0% / 英联赛杯 18.03%）→ 已在回复提示离线重拟合 market_calib/Platt。

## 2026-09-23（14:00 常规流水线）
**结果**：全链跑通，3 场（赔率 3/3，无别名行）。gh-pages `5e27fdb → 待核验`；红线 grep 0。
- ❗**本地已有并发作业（Trae Bot 12:46）的未推送提交 3fb1f01**（09-23 早版报告+odds），落在云端 HEAD 之上无分叉 → 处置=`git reset --soft 5e27fdb` 后重跑全链再单提交，避免两条同名 report 提交。推送仍须先 `ls-remote` 取真实 SHA。
- 步骤0 `[DEDUP-ALIGN]` 生效（6 行）；无陈旧 batch。**注意**：`chain` 字段在 `_calc_result.json` 里并不存在（顶层只有 calibration/matches/today）→ 链路标记只在 `_calc_engine.py` 的 stdout 日志里核对（`grep '市场混合\|SCORE_ALIGN\|ON·生效' _s3.log`），**别去 HTML/snapshot 里找**（公开页按红线本就不该有方法论）。
- 3 场：001/002 亚运男足（中国亚vs阿联酋亚、日本亚vs泰国亚）、003 美职（西雅图vs盐湖城）。步骤2.5 亚运男足无 7M 映射 → league_data 仅美职 1 联赛（正常）。
- 头条口径 3/3 覆盖、2 场变更（001→1:1 15.3%、003→2:1 11.9%；002 保持 2:0）。快照/`_calc_result` 一致，`top_scores` 仍纯概率降序。**比分精选仅 1 场**（003，001/002 缺近期战绩未纳入）；**大胆档 0 场**；**串关 0 组**（3 场、高信心仅 1 场 + 高风险 2 场，从严后不成立）。
- 复盘 09-22（4 场）：方向 3/4=75%、单点 1/4=25%、双档 0/4=0%、λ偏差 **-1.34**（n=4）。方向 <50% 连击已中断（09-21 100%/n=1、09-22 75%）；λ偏差连续两日偏低但样本极小（09-21 n=1 -3.25、09-22 n=4 -1.34），EWMA 比值 0.996 正常。
- 4.6：**保持默认**（10 旋钮完全未变，仅 `_meta` 刷新 base 59.38→60.00 / tuned 60.62→61.25 / tuned_at；optimizer 仍打 adopt=True，勿误读）。内容有变化 → 重跑报告 + 提交 selection_tuning.json。
- 提交用 `git add -u` + 显式 add；根 index.html 无 `data-page-node-id`（grep=0，未 checkout）；`predictions/index.html` 的 09-23 行（3 场 / 亚运男足 x2 + 美职 x1）由并发提交带入且核对无误。
- 趋势：DRIFT_MONITOR 连续第 5 日 `league_baselines` 漂移（亚冠精英 51.97%/德乙 50.0%/英联赛杯 18.03%）→ 已在回复提示离线重拟合 market_calib/Platt。

## 2026-09-22（14:00 常规流水线）
**结果**：全链跑通，4 场（赔率 4/4，无别名行）。gh-pages `c02ad64 → 6ac6872`（ls-remote 核验），线上报告/复盘/索引/selection_tuning 全 200（首次 404 = Pages 部署延迟，**等 50 秒重试即 200**），红线 grep 计数 0。
- 步骤0 `[DEDUP-ALIGN]` 生效（235/247）；无陈旧 batch；复跑 results-only 落文件后 grep 才看到 DEDUP 行（tail 会截掉）。
- 4 场：001 韩国亚vs沙特阿拉伯（亚运男足）、002/003/004 英锦标赛。步骤2.5 两联赛均无 7M 映射 → league_data 0 联赛（正常）。
- 头条口径 4/4 覆盖、2 场变更（002/004→2:1）；快照 `headline` 与报告三处一致，`top_scores` 仍纯概率降序（属设计）。串关 2 组。
- 复盘 09-21：仅 1 场（中国女 5:1 菲律宾女），方向 1/1=100%、单点/双档 0/1、λ偏差 -3.25（单场极端，n=1）。偏差符号 = 预测 − 实际。
- 4.6：**保持默认**（10 旋钮未变，仅 `_meta` 刷新 tuned_at/ pk 指标；optimizer 仍打 adopt=True，勿误读为「采纳新参数」）；内容有变化 → 重跑报告 + 提交 selection_tuning.json。
- **❗本次无 rebase**：本地 HEAD 已在云端之上（前一提交 8520597 = 昨晚生成的旧版 09-22 报告，3 场未推）→ 追加提交后直接快进推送。推送前 `ls-remote` 仍为 c02ad64 未变。
- 提交 `git add -u`（252 文件）+ 本次提交已含 predictions/2026-09-22 三件套与 predictions/index.html（索引 09-22 行手工从 3 场改为 4 场 / 亚运男足 x1 + 英锦标赛 x3）；根 index.html 无 `data-page-node-id`（未 checkout）。
- 趋势：方向命中率连续两日 <50%（09-19 43%、09-20 46%）；DRIFT 连续第 4 日 `league_baselines` 漂移 → 已在回复提示离线重拟合 market_calib/Platt。

## 2026-09-20（14:00 常规流水线）
**结果**：全链跑通，30 场（赔率 30/30，无别名行/重复对）。gh-pages `e7d4e95 → 1fe3188`（ls-remote 核验），线上报告/复盘/selection_tuning 均 200，红线 grep 为空。
- 步骤0 `[DEDUP-ALIGN]` 生效（235/245）；无陈旧 batch；复跑 results-only 落日志验证 DEDUP 行（tail 会截掉该行，**必须落文件再 grep**）。
- 复盘 09-19：方向 13/30=43%、单点 7%、双档 20%、λ偏差 +0.33（单日超阈；09-18 为 -0.09，非持续，未触发重拟合，继续观察）。
- DRIFT 第 3 日 league_baselines 漂移（德乙 50%/韩职 16.67%）→ 已回复提示离线重拟合 market_calib/Platt。
- 4.6：**参数旋钮全部未变**，仅 `_meta` 随 15 天窗口刷新（pk 60.67 vs base 59.33、bd 38.0 vs 29.67 均为既有参数再确认）；重跑报告+提交 selection_tuning.json。
- rebase 冲突照例 3 文件（index.html/odds_data.json/results_data.json），`--theirs` 一次通过。
- league_data.json 历来不入库（untracked，保持）。

## 2026-09-18（晚6：009–013 五连 1:1 质疑 → 引擎 B 概率校准，非流水线）
**触发**：用户「009-013，五场1：1，从概率学上说，可能性低到不可能发生」。
**核查（重要，下次同类质疑照此回答）**
- **不是 bug**：联合分布众数 = (λh 格, λa 格)，两队 λ 同落 [1,2) 就必然给 1:1；1248 场样本押 1:1 占 **39.0%**，与基础频率 12.79% 无矛盾。
- **不是噪音**：押 1:1 命中 **16.63%** ＞ 盲猜 12.79%。
- **要点**：必须区分「预测同分」与「结果同分」——五场实际全 1:1 概率 ≈1.4e-5（用户直觉对），但报告从未如此声称，单点只有 10~13%。五场与可能比分2 的差距 0.6~3.3pp（四场 1pp 内）→ 是贴脸并列，不是自信判断。
- **market_mix=0.70 被反证有效**：融合 vs 纯模型模态分歧 41.3%（515/1248），分歧场融合 14.56% ＞ 纯模型 12.62% → 勿下调。
**真缺陷 + 修法**：引擎 B 申明概率全线低报（申明/实际：头条 11.76/16.43、Top3 31.68/37.98、±1球 62.91/68.91）。新增 `DEFAULT prob_temp=1.20`，`predict()` 在 `blend_market` 后按 `p^T` 重归一。单调 → 1248/1248 场选取不变、1X2 未受影响；修后 ±1球 68.75%（实际 68.91%）。γ 定标法：前半段拟合、后半段样本外（Brier −0.29%/LogLoss −0.49%）。
**落盘**：gh-pages `1779d87`、master `bde0ab7`。**下次要点**：① 诊断"申明是否失准"看「申明 vs 实际」对照表，别看 Brier 单指标；② master 版 `score_engine.py` 是 **CRLF**，写入时须转回 CRLF 否则整文件行尾 churn；③ Edit 又出现一次「回报成功但源码未变」（DEFAULT 块），靠 `grep -n prob_temp`（应命中 2 处）抓到 → 改完必 grep 复核。

## 2026-09-18（晚4：报告措辞/列名改造，非流水线）
**触发**：用户「让球判读改成让球可信度（下面用可用慎用）；最可能比分改成可能比分1/可能比分2（预测两个）；可信度描述也用可用慎用；最可能进球改成可能进球」。
**做法**：只改渲染脚本 `_gen_report.py` → 重跑 `_gen_report.py` → 推 gh-pages；再同步 master `tools/prediction/gen_report.py`（须去下划线：`_optimize_selection.py`/`_calc_engine.py`/`import _league_match`）。
**要点（下次改报告措辞直接照做）**
- 词表全站统一 **可用 / 慎用 / 别跟**（+ 数据不足）。让球分档唯一实现 = 新增 `rq_grade(ev, conf)`（4.1 表与逐场卡片共用）：EV≥1.10 且置信≥中 可用 / EV≥1.00 慎用 / 其余别跟。
- 4.2 列：可能进球(主)/(客)、可能比分1、可能比分2（各附概率，原独立「概率」列并入格内，列数仍 11）；4.1 列 7 改「让球可信度」。
- 踩坑：`txt, cls = rq_grade(...)` 顺序别写反（写成 `cls, txt` 会在页面出现字面量 `tag-red`）；两次 Edit 回报成功但源码未变 → **改完必须 grep 源码 + 生成后 grep 旧词**（验收：`让球判读`/`最可能比分`/`不可信`/`有偏离` 计数须为 0）。
**落盘**：gh-pages `a333f50`、master `024e10d`；线上已复核。

## 2026-09-18（晚3：工作盘脚本/资产全量纳管到 master，非流水线）
**触发**：用户「`_local_prepare.py` 需要纳管，另外其他的文件也要放到云上」。
**做法（可复用）**：逐文件比对不能只按文件名 —— master 副本做过**仓库根自适应**（`BASE=dirname(__file__)` → `_repo_root()` 向上找 `results_history/`）。先「去自适应」再 diff，才能区分「真旧」与「仅路径改造」。本次 46 个完全一致、6 个仅路径差异（master 更健壮，不动）、仅 2 个真需同步。
**动作**：master `tools/prediction/` 补 47 个脚本（去 `_` 前缀）→ 该目录现 101 个 .py；`gen_report.py` 覆盖为今日三引擎版；`local_prepare.py` 用逆变换重建（保留 `_repo_root()` + 今日去重/容错）；补 `bt_rows2.json`/`dir_rows.json`/`official_results_cache.json`/`league_data.json`；刷 master 根 `platt_params.json`(→09-18/n=2020) 与 `league_profile.json`；`tools/archive/workbench_20260918.tar.gz` 收工作盘其余产物（4.49MB/215 文件）。101 个脚本 py_compile 全通过。
**落盘**：master `2b7ecc5` → `c2ccdec`（ls-remote 核验）。
**下次要点**：① 新增脚本一律「工作盘 `_foo.py` ↔ master `tools/prediction/foo.py`」两处同步，**带 `_` 前缀会被 master `.gitignore` 任意层级忽略**；② 同步时须把文件内 `_xxx.py` 引用与 `import _xxx` 一起去下划线；③ master 副本的 `_repo_root()` 改造**别用本地文件直接覆盖**；④ 重拟合 `platt_params.json`/`league_profile.json` 后要刷 master 根的快照。

## 2026-09-18（晚2：修复上游别名行——4 场丢让球盘/比分盘）
**触发**：用户反馈「003/004/012 明明有让球盘却说没有；引擎B的比分还是原来的」。
**根因**：`scripts/matches_data.json` 18 行而真实 14 场 —— SCHEDULE 同场生成「官方简称行（带赔率/让球/比分盘/matchId 5498xxx）」+「长名行（2041xxx，赔率与战绩全空）」两行，`_calc_engine.py` 用 dict 覆盖后写胜 → 保留空行 → 该场同时丢让球盘（4.1 显示「无让球盘」）+ 比分盘 + 球队评级历史（引擎 B 退化成 1:1）。核对 results_history：沃夫斯堡 20 场 / 布城 6 / 奥斯KFUM 11 → **官方简称才是 canonical，长名是污染**。
**处置**：① 删 4 行空别名行；② `RESULT_TEAM_NAME_MAP` 补 5 条映射（沃尔夫斯堡→沃夫斯堡、达姆施塔特→达姆施塔、布里斯托尔城→布城、奥斯陆KFUM→奥斯KFUM、卡塔尔亚足→卡塔尔23）；③ `calc_engine` 新增 `_odds_richness` + 同编号择行保护；④ `_local_prepare.py` SCHEDULE 去重 + ODDS 键容错；⑤ 重跑引擎 A + 报告。
**结果**：001 43.8%→64.7%、003 42.8%→47.9%、004 46.7%→65.6%、012 39.7%→51.7%，4.1 全部有让球盘；引擎 B 与市场比分盘头条 12/14 一致。落盘 gh-pages `fc155d5`、master `9711c15`。
**引擎 B 配置复核**：1248 场含比分盘 → 生产 Top1 16.43% > 换市场隐含λ 14.90%；λ总/市场λ总 中位 0.981（无偏）→ 参数已最优，勿再调。
**下次排查要点**：`matches_data.json` 行数 > 实际场次 = 别名行污染；`_calc_result.json` 某场 `rq` 为空同理。修完必须**重跑步骤 1→4**（让球来自引擎 A、比分盘与评级是引擎 B 的输入）。

## 2026-09-18（晚：三引擎解耦重构，非流水线）
**用户需求**：重做一套按双方进球联合分布预测比分的引擎；现有引擎继续算胜平负、4.1 拆出「让球+判读」并去掉命中比分/双档；最终三套引擎互不影响。
**交付**：新建 `score_engine.py`（引擎 B，双变量泊松 λ3 + 主客分拆攻防评级 + 市场 1X2 反解分配 λ + 比分盘 70% 融合 + 2 万次蒙特卡洛）；`_gen_report.py` 拆 4.1/新增 4.2，原表顺延 4.3~4.6；引擎 A/C 未动。报告章节现为 4.1 胜负预测 / 4.2 比分预测 / 4.3 进球数 / 4.4 让球盘 / 4.5 冷门 / 4.6 大比分。
**关键数字**：引擎 B（2478 场 walk-forward）Top1 13.88% / Top3 34.26% / ±1球 66.18% / 1X2 51.61%；参数 `half_life=120,k_shrink=4,opp_adj=1,score_w=0.50,lam3=0.08,tau关,market_mix=0.70,max_goal=8,mc_n=20000,league_eb_k=40`。互不影响已实测（改 B 的参数只动 4.2；改 C 的参数 4.1/4.2 都不动）。
**顺带修复**：`results_history` 235 文件主客整体反序 → `dedup_results_history.py --apply --no-net` 修复（4635→3104，主胜 42.6%/平 26.3%/客胜 31.2%）。
**落盘**：gh-pages `66ed89f → e51ac27 → 562624d`（ls-remote 核验一致）；master `ed5735f`（`tools/prediction/score_engine.py`）。线上报告 200，红线 grep 为空。
**复用要点**：① 公开页「今日比分精选」表的「命中比分/双档」列属引擎 C，**不是**要删的 4.1 列，勿误删；② 引擎 B 的 `market_dist()` 只取 0:0~5:5，务必排除「胜其他/平其他/负其他」；③ 用户明确要求**不要反复提示比分准确率上限**；④ 临时脚本 `_fit_score_engine.py`/`_bt_rows2.json` 留工作盘做离线 A/B。

## 2026-09-18（晚：准确率质疑专项诊断，非流水线）
**触发**：用户问「最近有预测对的么？算法是不是有问题？平均 3 场都预测不到？必须改良」。
**结论**：非故障。近 10 天方向 92/152=60.5%（长期 51.2%）、单点 11.8%（长期 15.1%）、双档 15.8%（长期 24.0%）；单点每天期望本就只有 2.3 场。近 10 天偏低是因该时段极端高比分（3.31 球/场 vs 长期 2.86）。
**证据**：1X2 校准 ±3pp 内；比分自称/实际吻合（长期 15.2% vs 15.1%）；2478 场回测里模型 51.21% ≈ 市场去水 51.94%。8 组改良尝试（市场权重/平局权重/λ 缩放/象限限制/非平局优先/爆冷过滤/选取目标）全部 ≤ 现状 → 不做任何参数改动。
**交付**：`diag_2026-09-18.html` 诊断报告（present_files）、新增 `daily_diag.py`、保留 `_bt_rows.json`。未改引擎/发布页；扩覆盖方案待用户选。
**复用要点**：回测可在 `<repo>/tools/prediction/` 放 `calc_engine.py`+`_bt.py` 后 cwd=repo 根跑（约 25 秒/次，`BT_MARKET_W` 可覆盖市场权重），跑完删 `tools/`。

## 2026-09-18（常规流水线）
**结果**：全链跑通，gh-pages `752a0fc → 46feb0f`（ls-remote 核验），线上报告/复盘页均 200。
- 当日 14 场（提取 18 场含队名变体行），冷启动未见异常 → 档数按非冷启动算。链路标记齐全（Platt n=2020、MARKET_BLEND_PROB ON、SCORE_ALIGN ON、路线图全在）。步骤0b `[DEDUP-ALIGN]` 照例生效（235/243）。
- 复盘 2026-09-17：方向 7/11=64%、单点 9%、双档 9%、λ偏差 -0.30 球/场（λ偏差连续两日 >0.2？09-16 为 -0.07，09-17 为 -0.30 —— 单日超阈，暂不触发重拟合，继续观察）。
- DRIFT_MONITOR 报 `league_baselines` 漂移（德乙 50%/韩职 16.7%/荷甲 15.4%）→ 引擎自提示离线重拟合 market_calib/Platt，已在回复中告知用户。
- 4.6 优化：13 天，base=best → 保持默认（仅 `_meta` 刷新，已提交）。
- rebase 冲突 3 个数据文件（index.html/odds_data.json/results_data.json），按 `git checkout --theirs` 取本地新数据一次通过。
- 首次 curl 线上 404 属 Pages 部署延迟，等 45 秒后全部 200。
- 已先按要求精简 MEMORY.md（原文件超 3000 字符被截断注入）。

## 2026-09-17（下午追加：选取口径修复）
**触发**：用户反馈「两档命中率太差，有没有按历史重算」。
**结论**：优化器每天都在跑，但回放**自写排序且不排冷启动** → 与生产不是同一算法（4/12 天选出场次不同），且 λ 门槛网格只到 2.0（真实改善在 2.4~3.2）→ 必然天天报「保持默认」。
**修复**：`_optimize_selection` 改调 `SA.rank_pk/SA.rank_bold`；`bd_lambda_min` 语义改「λ 达标优先」（未达标 −1000 让位，档位不塌缩）；网格放宽。→ **采纳 bd_lambda_min=3.0**（目标 16.25→28.75）。比分精选保持默认（12 天 31.9%，已优于 ~20.5% 基准）。
**真命中率参考（12 天第一档）**：比分精选 23/72=31.9%（含双档）；大胆档 5/48=10.4% → 修后 14.6%、命中日 3/12→6/12。
**落盘**：gh-pages `4844b06`；master `e2ce110`（新增 `tools/prediction/selection_algo.py` 正本）。线上 200 已核验。

**❗今日新踩的坑（下次务必照做）**
- `git rebase` 会因远端 force-update 后的 reflog 走 `--fork-point` 取到陈旧基点（曾致 247 提交误重放 + 卡冲突）→ **一律 `git rebase --no-fork-point <ls-remote 真实SHA>`**；推 `git push origin HEAD:refs/heads/gh-pages`。
- `origin/*` remote-tracking ref 会被并发会话覆写（本次被写回 b119ac2）→ 基点只信 `git ls-remote`。
- worktree 在并发下 admin 目录会消失 → 先 `git worktree prune`，用 `git worktree add --detach <path> <真实SHA>`。
- `bd_tuple` 必须保持 **2 元组**（`_gen_report.py` 用 `(-x[0], -x[1])` + `_is_cold(x[2])` 解包），返回 3 元组会连环崩。
- ⚠️ 报告「前日回顾」是按**当前**调参重算的，不是当日实发口径；调参后历史回顾数字会跟着变（读数字别当发布记录）。

## 2026-09-17（上午·常规流水线）

**结果**：全链跑通，gh-pages `a6aab19 → b25d7fe`（ls-remote 核验），线上报告/复盘页均 200。
- 当日 11 场、冷启动 2 场 → 1 档（比分精选 6 / 大胆档 4）。链路标记齐全（市场混合/SCORE_ALIGN/Platt n=2010）。
- 复盘 2026-09-16：方向 8/16=50%、单点 12%、双档 6%、λ偏差 -0.07。
- 4.6 优化：12 天，base=best → 保持默认（仅 `_meta` 刷新，已提交）。
- 步骤0b `[DEDUP-ALIGN]` 生效（235/242 文件），归档污染照例复发并自愈。

**本次新学到的操作要点（下次照做）**
- 远端 gh-pages 可能已有外部数据提交（本次 a6aab19「data: 自动更新赔率+赛果」）→ **先 `git fetch origin gh-pages` + `git rebase -X theirs origin/gh-pages`**（`-X theirs` 在 rebase 语义下=优先本地新数据，可无冲突自动解决数据文件；远端独有改动如 version.txt 会被保留）。本次一次通过，无需 reset --hard 重跑全链。
- 校验链路标记时，chain 里市场混合的**实际文案是「市场混合(」**（内含「80%概率混合(总量守恒)」），不是「市场概率混合(」；判据按「市场混合(」+「比分矩阵对齐发布1X2」两条。
- 提交用 `git add -u` + 显式 `git add predictions/<date>`，避免把工作盘大量 `_` 前缀临时文件（未忽略、真 untracked）一并入库。

## 2026-09-16（首录）
**任务**：比分精选/大胆档改「分档展示 + 倍数递增 + 独立计算 + 每日自动优化」。

**做了什么**
- `_gen_report.py`：两档改为分档选择。常量 `TIER_PK=6`（比分精选每档）、`TIER_BD=4`（大胆档每档）；**档数规则 = 以 10 场为基准 1 档、每多 8 场加 1 档**（`N_TIER_BASE=10`、`N_TIER_STEP=8`、`TIER_MAX=5`，按非冷启动场次数算）：10→1档(6/4)、18→2档(12/8)、26→3档(18/12)、34→4档(24/16)、42→5档(30/20)。代码支持任意 N 档（每档前插「第N档」分隔行，切片不足则该档不出现）。
  - 两档独立排序：比分精选 = 命中比分概率 × λ质量系数（低 λ 更准）+ 1:1 退化降权；大胆档 = max(极限档概率, 量级档概率)，弃用旧的「量级与头条总进球差」口径。
  - 第一档取质量最高的 6/4（准确率优先），第二档取次优增量；表格内插「第二档」分隔行。前日回顾复用同一套分档排序。
- 新增 `_optimize_selection.py`：**每日步骤 4.6（跑在 `gen_review.py` 之后）**。回放历史 pred_snapshot + 实际赛果，网格搜索质量旋钮，改善≥0.3pp 才采纳、可用天数<5 保留默认，写 `selection_tuning.json`（被报告读取）。

**验证**：今日 17 场<20 → 只出第一档 6/4；临时把阈值降到 10 复测得 12/8 + 分隔行（倍数递增正确），已还原。红线 grep 为空。首跑优化器：11 天历史无改善 → 保持默认（预期内）。

**落盘**：gh-pages `2049ec8 → 0de7375`（ls-remote 核验）。线上报告 / selection_tuning.json 均 200。

**待办/注意**
- `_gen_report.py`、`_optimize_selection.py` 为 `_` 前缀被 gitignore 忽略，只在工作盘；master 当前**无** `tools/prediction/` 目录 → 改这两个脚本只需重跑报告 + 推 gh-pages。
  - ⚠️ 已过时（2026-09-18 起）：master `tools/prediction/` 已是全部脚本正本（`gen_report.py`/`optimize_selection.py` 等，去 `_` 前缀）。改脚本必须两处同步。
- 每日跑完 `gen_review.py` 后记得执行 `_optimize_selection.py`，否则选取参数不会随复盘进化。
- 若用户觉得「比赛很多」的门槛 20 场偏高/偏低，调 `N_TIER2` 即可；要第三档则同时提 `TIER_MAX`。

## 2026-09-19（14:00 常规流水线）
**结果**：全链跑通，30 场（赔率 30/30）。gh-pages `8e17078 → 13d93da → 9e3d1ca`（ls-remote 核验），线上报告/复盘/selection_tuning 均 200，红线 grep 为空。
- 步骤0 `[DEDUP-ALIGN]` 生效（235/244）；无陈旧 batch 文件；matches_data 无别名行（防护正常）。
- 复盘 09-18：方向 7/14=50%、单点 14%、双档 29%、λ偏差 -0.09（阈值内）。
- 4.6：比分精选保持默认；**大胆档采纳 bd_min_total 2→3**（30.71→32.50），重跑报告+提交。
- DRIFT 连续第 2 日 league_baselines 漂移（德乙/韩职/荷甲）→ 回复中提示离线重拟合。

**❗新踩坑（下次照做）**
- `git rebase --no-fork-point <SHA> origin/gh-pages` 带第二参数会把 HEAD detached 到 origin 做空操作、本地提交不动 → **rebase 时不带第二个参数**，在 gh-pages 上 `git rebase --no-fork-point <SHA>`。
- 本地曾出现外部作业（Trae Bot 13:52）的未推送提交 a0bbeab（同日早版报告+odds），与远端分叉致 rebase 冲突 → 处置=`reset --hard <云端SHA>` + `git checkout <本地好提交> -- .` + 单提交推。**但严禁 `git add -A`**——本次把 2147 个 `_` 临时文件/备份/pycache 误入裤，靠二次 `git rm -r --cached`（保留 predictions/2026-09-19、odds_history、results_history 五项）清理（9e3d1ca）。提交永远 `git add -u` + 显式 add。
- MEMORY.md 已精简至约 3000 字符（此前超限被截断）。

## 2026-09-19（20:30 头条比分口径改造，非流水线）
**触发**：用户「连续12场预测1:1？？？」→「我不需要这种数学概率，我不要这种众数分布」。
**结论**：众数口径结构性退化（两队 λ 同落 [1,2) → 首选恒 1:1，长期占 56%），已改为**倾向象限内优选**。
- 唯一实现 `score_engine.headline_reorder(top, gap=5.0, dir_key)`；`DEFAULT.head_gap=5.0`。规则：众数为平局比分且领先「倾向象限内最高概率比分」<5pp → 顺延；倾向=平局保留 1:1。**直接重排 top_scores 位次**，故报告 4.2 列、SA.hit_pick、SA.band_scores 全部自动跟随（无需改 _gen_report/selection_algo）。
- 实测（2478 场，probe 已入 master `headline_rule_probe.py`）：象限+gap5 = **15.58%**、1:1→24%（众数 15.13%/56%）；gap6 15.05、gap7 14.57、gap10 13.44 → 取 5。纯非平局顺延(gap5) 15.54% 但 36% 场次与倾向矛盾 → 弃用。
- ❗坑：`_calc_engine.py` 自己重建快照 top_scores（不经引擎 B），必须在该处也调用同一函数（`_headline_rank(top, dir_key)`，dir_key 取引擎 A 倾向），否则报告变了、快照没变。
- 今日效果：1:1 26/30 → 5/30。落盘 gh-pages `d12fe5b→fba2ce1`、master `7f1d7d0→f3f7c96→b58204b`。
- ❗并发作业提示：master 与 gh-pages 都有外部自动化在推（master 出现 09-19 09:19 数据提交、gh-pages 被推到 d12fe5b）→ 推送前必须重新 `ls-remote` 取真实 SHA 并 fetch（本地 tracking ref 会滞后，直接 rebase 会报 invalid upstream）。

## 2026-09-19（21:00 修复「比分列颠倒」，非流水线）
**触发**：用户「你把可能比分1和2颠倒了一下？？？1:1都在比分2里显示了」。
**根因**：20:30 改造时**直接重排了 `top_scores` 位次**，使「可能比分1/2」不再是概率降序（001 场 11.7% 在左、12.0% 在右）。
**定稿口径（勿回退）**：
- `top_scores` **恒为联合分布纯概率降序**（口径事实）；首选另存 `headline`（快照字段）/`SA.headline_pick(cells, direction_key(m))` 现算。规则实现唯一 = `score_engine.headline_reorder`（gap=5.0）。
- 双档 = **除头条外概率最高的两个**（`SA.band_scores`）。
- 报告 4.2 列：`可能比分1/可能比分2` → `比分预测` + `比分双档`；卡片「命中比分」→「比分预测」文案同步。
**实测（新增探针，已入 master tools/prediction/）**：
- `band_rule_probe.py`（2478 场）：象限内排序 首选14.21/双档15.78/前三29.98 ≪ 纯概率 15.13/24.01/39.14 → 象限口径**不可**用于比分列/双档。
- `pk_head_probe.py`（回放 225 场，复用 `_optimize_selection` 回放）：比分精选榜头条改同口径后 头条 11.11%→8.89%、双档 17.33%→19.56%、**并集不变 28.44%**、1:1 63%→14%。
**今日效果**：1:1 占比 4.2 首选 26/30→1/30；比分精选榜 18/18→6/18；大胆档 0/4。
**连带**：口径变更后重跑 4.6，`selection_tuning.json` 采纳 pk（`pk_degen_down` 0.85→1.0、caps 3.4→3.0）与 bd（`bd_total_shift` -1→0）。
**落盘**：gh-pages `6883217→d38d942`；master `b58204b→43be6da`。
**❗踩坑**：
- master 副本是 **CRLF**，逐段替换式同步必须先按行尾归一，否则锚点 0 命中（本次已改为自动识别）。
- GitHub Pages **CDN 会返回旧缓存**（本次拿到另一作业的 V3.3 版报告）→ 核验线上务必带 `?v=$(date +%s)` 破缓存，否则会误判成「没生效/被覆盖」。
- 并发作业（Trae Bot）也在写同一个 `predictions/<date>/index.html`，推送前照例先 `ls-remote` 取真实 SHA。

## 2026-09-19（22:00 大胆档档数 + 串关前日回顾，非流水线）
**触发**：用户「1 大胆档没按比赛数量灵活增数量。2 串关推荐下加前日回顾。」
**修复1（档数）**：`rank_bold` 原按「精选占位后剩余池」自算档数（30 场→剩 12→num_tiers=1→仅 4 场），与报告文案自相矛盾。改 `split_boards` 统一按**当日全部非冷启动场次**算档数并传给两榜（rank_pk/rank_bold 新增 `n_tiers` 形参，默认 None 保持旧行为，故所有探针不受影响）。效果 30 场：精选 18（不变）、大胆 4→11（3 档 4+4+3）。4.6 优化器只评第一档 → 无需重跑。
**新增2（前日回顾）**：报告「五、核心策略」的串关推荐下方新增 `📅 前日回顾`（`_gen_report._build_parlay_recap()`，占位符 `<!--RECAP_PARLAY-->`）：解析**昨日已发布 index.html** 的串关表（方向/信心/冷门）逐腿核对赛果（`_lookup_actual`），逐腿 ✅/❌ + 实际比分，整组「✅ 全中 / ❌ 挂 N 腿 / ⏳ 待赛果」，末行给「共 N 组、全中 M 组 + 当日单场战绩（复用 `gen_review.day_rows/tally`）」。**刻意读昨日 HTML 而非重算**：口径迭代不污染历史串关回顾；昨日无报告/无串关表时输出说明行。
**落盘**：gh-pages `e7a40b6→2b68ac3`；master `43be6da→15aefde`。红线 grep 空；线上 472315 字符已复核。
**❗踩坑**：`_gen_report.py` 的词组拼接易出「方向串关串关 A」类重复 → 标签直接用昨日原表组名（方向串关/信心串关/冷门串关 + A-D），不要再手工拼「串关」。MEMORY.md 二次超限（4315→已压至 ~3.1k）。

## 2026-09-20（19:45 修复第六节繁体字，非流水线）
**触发**：用户「六、当日赛事联赛形势里面还是繁体字」。
**根因**：`_fetch_league_data.py` 简体字段（name_zh/season_zh/note_zh）设计上用 opencc(t2s) 生成，运行环境无 opencc → 静默回退繁体直出。
**修法（不引入 opencc 依赖）**：`_league_match.py` 新增 `_TRAD2SIMP` 字表 + `ALIAS_REV`（ALIAS 反查，港译还原大陆译名：拿玻里→那不勒斯、巴塞隆拿→巴萨）+ `to_simp()`；fetch 回退改调 `LM.to_simp`。顺带补 23+ 条 ALIAS（勒沃库森→利華古遜、马赛→馬賽、尼斯→奈斯、富勒姆→富咸、波尔图→波圖等），队名匹配 31/54→51/54（米亚尔比 7M 瑞超榜无此队，宁缺勿错；韩职无数据源）。
**连带修复**：此前「排名—」的队（亚特兰大/町田泽维/柏太阳神等）因 ALIAS 补齐而出现真实排名。
**落盘**：gh-pages `2cf82f2`、master `272b9f4`（league_match.py 直接 cp + fetch_league_data.py CRLF 锚点行级替换）。线上破缓存核验繁体关键词全 0。
**❗要点**：① master fetch_league_data.py 是**混合行尾**文件（CRLF 为主、个别 LF），锚点替换必须按行 splitlines(keepends=True) 定位；② rebase 若报 untracked 会覆盖（本次 odds_history/results_history 单文件），先备份移走再 rebase（备份在 _backup_20260920/）；③ 以后新增 7M 队名映射一律加 `_league_match.ALIAS`（展示名自动经 ALIAS_REV 反转为简体名，匹配与显示一处维护）。

## 2026-09-21（比分引擎口径收口，非流水线）
**结果**：master `0f66b3b → 96c1ecb`（ls-remote 核验，快进）；**gh-pages 无需改动**。
- 关键认知：`_calc_engine.py`/`_gen_report.py` 等 root `_` 脚本在 **gh-pages 并未跟踪**，其正本只在 master `tools/prediction/` → 改这类脚本只同步 master，不必推 gh-pages（gh-pages 仅跟踪 score_engine.py/selection_algo.py/score_pick_optimize.py 三个 root .py）。
- 本次修两处：① 头条落位的候选格改走**引擎B**（新增 `_headline_cells`，调用点 `_apply_headline_plan(out,TODAY,raw)`），此前用引擎A自己的比分矩阵 → 实测 3 场里 1 场首选分歧；② 卡片文案去「方向倾向内的首选比分」，并启用此前**从未渲染**的死变量 `hm_mark`（跨象限提示）。
- 操作要点（已入 MEMORY.md）：`origin/*` 本地跟踪引用会滞后（origin/master 停在 3b855cd 而真实是 0f66b3b）→ 取正本必须 `git show $(git ls-remote origin <br>|cut -f1):路径`；推 master 用 worktree，路径**必须写 `C:/...`**（写 `/c/...` 会被建成 `C:\c\...`）。
- 报告「串关推荐」下方有「📅 前日回顾」（占位符 `<!--RECAP_PARLAY-->`），读**昨日已发布** index.html 逐腿核赛果（不重算 → 不受口径迭代影响）；`_gen_report.py` 的词组拼接易出重复标签，标签直接用昨日原表组名。
- 09-22 报告已按新口径本地重生成（3 场：周二002=2:1 12.5%、周二003=1:1 12.5%、周二004=2:1 11.3%），快照/4.2/卡片三处概率一致、红线 grep 空；**未发布**，交明日 14:00 流水线。
