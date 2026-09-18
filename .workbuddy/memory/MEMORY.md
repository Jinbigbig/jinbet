# JinBet 项目长期笔记

## 每日流水线（顺序不可乱）
0. `git show master:update_odds_net.py > update_odds_net.py` → **先** `--no-push` **再** `--no-push --results-only`（顺序错→ODDS 单引号 JS）。判据=日志 `[DEDUP-ALIGN]`；跑前清陈旧 `_data_batch*.json`。
1. 首跑当日先 `mkdir -p predictions/<date>`，再 `_local_prepare.py`（0 场=今日无赛，直接结束）。
2. `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py`（chain 含「市场混合(」+「比分矩阵对齐发布1X2」，路线图 ON·生效/ON·观察，Platt 已拟合）。
4. `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`（有变化则重跑报告并把 selection_tuning.json 入 commit）。
5. 更新 predictions/index.html 索引 → `grep -c data-page-node-id index.html` 仅 >0 时 `git checkout -- index.html` → commit 只推 gh-pages。
- 引擎/脚本改动走 worktree 同步 master（路径 C:/ 风格；worktree 用 `--detach <真实SHA>`，先 prune）。**09-18 起全部脚本在 master `tools/prediction/` 有正本**（101 个 .py），改任何脚本都要同步两处：工作盘 `_xxx.py` ↔ master `tools/prediction/xxx.py`（详见「云端正本布局」）。注意 master 副本做过**仓库根自适应**（`BASE = dirname(__file__)` → `_repo_root()` 向上找 `results_history/`），**别用本地文件直接覆盖**，否则运行时找不到路径基准。
- 提交用 `git add -u` + 显式 `git add predictions/<date>`，避免入库 `_` 临时文件。

## 分支与推送
- origin=SSH 免交互；禁 GITHUB_TOKEN/HTTP 代理。**只信 `git ls-remote`**（remote-tracking ref 被并发覆写）。判推送只看 ls-remote。
- ❗rebase 必须 `--no-fork-point <ls-remote 真实SHA>`（reflog 基点可能陈旧）。推 `git push origin HEAD:refs/heads/gh-pages`，禁 force。被拒→fetch 真实 SHA + `rebase -X theirs`（数据文件冲突自动留本地新数据）；撞死→`reset --hard <云端SHA>` 重跑全链单提交推。
- ❗rebase 报 `untracked working tree files would be overwritten by checkout`（典型：外部 data 提交把 `odds_history/*.json`/`results_history/*.json` 纳入跟踪，而本地是 untracked）→ **别 rebase/abort 兜圈子**：abort 的 `reset --hard` 会把这些 untracked 文件直接删掉、并让 `.workbuddy/memory/2026-09-*.md` 显示为已删除。正确动作：`cp 目标文件 → git reset --hard <ls-remote 真实SHA> → cp 回去 → 单提交 → push`，事后 `git checkout -- .` 恢复被删的 tracked 日志。
- bash PATH 偶坏 → `export PATH=/c/Users/Jin/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH`；临时文件写仓库内（/c/tmp 不持久）。

## 云端正本布局（09-18 全量纳管，勿再留「仅本地」文件）
- **master `tools/prediction/`** = 全部脚本正本（101 个 .py，文件名**去 `_` 前缀**：`_calc_engine.py`→`calc_engine.py`、`_gen_report.py`→`gen_report.py`、`_optimize_selection.py`→`optimize_selection.py`…）。**去 `_` 不是审美**：master `.gitignore` 对 `_calc_engine.py`/`_gen_report.py`/`_local_prepare.py` 做**任意层级**匹配，带下划线会被静默忽略。同目录放数据资产：`bt_rows2.json`、`dir_rows.json`、`official_results_cache.json`、`league_data.json`、`club_pedigree.json`。
- **master 根**：`update_odds_net.py`（步骤 0 用 `git show master:update_odds_net.py` 取）、`platt_params.json` + `league_profile.json`（**校准参数快照，重拟合后必须刷 master**，否则回退即精度回退）。`odds_data.json`/`results_data.json` 在 master 根是旧快照，活数据以 gh-pages 为准。
- **gh-pages**：数据与运行态（`predictions/`、`odds_data.json`、`results_data.json`、`results_history/`、`odds_history/`、`scripts/matches_data.json`、`_calc_result.json`、`v34_state.json`、`strength_db.json`、`selection_tuning.json`、`market_calib.json`、`drift_baseline.json`）+ `score_engine.py`/`selection_algo.py`（脚本运行处，gen_report 直接 import）。
- **master `tools/archive/workbench_20260918.tar.gz`** = 工作盘非脚本产物快照（215 文件/4.49MB：探针缓存、旧报告、校准与数据备份、诊断页、日志）。重大变更后重打一份新的、保留旧的。
- **新增脚本流程**：工作盘写 `_foo.py` → 复制到 master `tools/prediction/foo.py`（LF；同步改掉文件内对 `_xxx.py` 的引用与 `import _xxx`）→ push master。**别只留工作盘。**
- 已**故意不纳管**：`_verify_homeaway.py`（被 master `verify_homeaway.py` 取代）。

## 队名归一
- canonical=短名（**results_history / ODDS 键 / SCHEDULE 三处统一用官方简称**：沃夫斯堡、布城、奥斯KFUM、卡塔尔23、达姆施塔。长名如 沃尔夫斯堡/布里斯托尔城/奥斯陆KFUM/卡塔尔亚足 一律视为别名）。
- ❗**同编号多行（别名行）是本项目最贵的坑**：SCHEDULE 同时出现「简称行（带赔率/让球/比分盘/matchId 5498xxx）」与「长名行（2041xxx 旧ID，赔率与战绩全空）」，下游 `{m["matchNumStr"]: m}` 按「后写胜」保留空行 → 该场**同时丢掉让球盘、比分盘、球队评级历史**。症状：报告 4.1 显示「无让球盘」、比分引擎 λ 退化到 1:1。
  - **排查**：`matches_data.json` 行数 > 实际场次（如 18 vs 14）；`_calc_result.json` 中该场 `rq` 为空。
  - **防护（09-18 已加，勿删）**：① `update_odds_net.RESULT_TEAM_NAME_MAP` 补别名映射（源头消除）；② `calc_engine._odds_richness` 按赔率完整度择行（1X2>让球>比分盘>战绩）；③ `local_prepare.py` SCHEDULE 去重 + ODDS 键容错匹配（master `tools/prediction/local_prepare.py` 已有正本）。
  - **修完必重跑步骤 1→4**（不是重跑报告就够：让球来自引擎 A、比分盘与评级来自引擎 B 的输入）。
- SCHEDULE 双行根因=`RESULT_TEAM_NAME_MAP` 缺映射或 identity 映射→先查映射表别手工删。当日盘口只认 index.html `YYYY-MM-DD_主_客` 键。编号不符先怀疑竞彩重编号（已修），别改映射表。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛进球环境 w=0.25；score_mix.w=0.3；EWMA(0.25)+MAD；基础λ窗口 N=25/DECAY=0.96；市场权重=`league_market_w(league)` 动态（50%→0.80，±2pp→±0.05，夹 0.65~0.95）。**改市场混合必重拟合 platt_params.json**（已入库）。
- 保险丝：MAX_TOTAL=4.20/MIN_TOTAL=1.60/MAX_SINGLE=3.20/MIN_SINGLE=0.18/ZF_CAP=1.0/LEAGUE_EB_K=40，勿调高。SCORE_ALIGN 三象限缩放到发布 1X2，勿回退。冷启动场不进比分精选。
- 星级=Platt 后 max(1X2)，阈值 0.44/0.50/0.57/0.66。五模块：BRIER_OPT/KALMAN ON·生效，HEDGE_ENSEMBLE ON·观察（apply=False 故意），CLV/DRIFT 只监控。平局 boost `0.25*exp(-|λh-λa|/0.45)`。
- ✅09-16 修：fit_platt_params 已改为拟合内调动态市场权重。

## 市场结论 / 已否决
- 纯市场去水 1X2 > 生产 > 纯模型；平均返还率 88.56%，按市场买必输。二级盘 alpha：让球✅｜总进球✅不稳｜比分❌｜1X2❌；二级盘输入用未混市场 λ，`|让球|≥3`/分歧>25pp/无锚→勿跟。大比分市场系统性高估，只观察。
- 已否决（勿再启用）：比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS。
- 09-18 新增否决（均 2478 场 walk-forward / 近 10 天回放实测，全部 ≤ 现状）：市场权重 0.90/0.95/1.00（51.09/51.17/51.33% vs 现状 51.21%，噪声内）；平局权重×0.9/×0.8（15.09/15.13% vs 15.13%）；λ 总量 ±5%/+10%（14.77/14.65%）；候选限制在预测象限（14.49%）；优先非平局比分（12.99%，明显差）；剔除高爆冷风险场次（精选 30.6%→20.0%）；换比分选取目标（头条概率/前三合计/λ最低 25~30% vs 现状 33.3%）。**结论：单点与方向都已贴天花板，任何调参均为过拟合；提升只能靠扩覆盖（前 4 档 47.7%、前 6 档 59.8%）或加场次。**

## 数据修复史
- 赛果库主客颠倒已全量清理（4624→3059）；归档污染每次步骤0 复发，靠 `align_results_history_to_official()` 自动对齐；唯一锚=体彩官方赛果 API，日期启发式 100% 不可靠。改数据后必 build_league_profile → 重拟合 platt → 重跑引擎。
- **09-18 二次对锚**：全库仍整体反序（235 文件），用项目自带 `dedup_results_history.py --apply --no-net` 修复：4635→3104 场，主胜/平/客胜 **42.6/26.3/31.2%**、场均 1.57/1.29（标准主场优势），备份 `_hist_backup_2026-09-18/`。**自检基准：主胜应 > 客胜约 10pp**；若主客近似相等或客胜更高 → 库又被反序写入。
- 1X2 缺失用比分盘反推（31 档去水），仅限当日新鲜比分盘；09-01 及更早禁回填。

## 比分口径
- 头条=top_scores[0] 联合众数（不可大胆化）；双档=top_scores[1:3]；量级参考=round(λ)。λ≤2.6 单点最值（18~22%），禁 k>1 追高；±1 邻域须去重格集合。
- **长期真值（2478 场 walk-forward，09-18 实测）**：方向 51.21%（纯市场去水 51.94%，Brier 0.19862 vs 0.19766）；单点 **15.13%**（自称 15.2，校准完美）；双档 **24.01%**；前三累计 **39.14%**；±1球邻域 **67.2%**（前六累计 59.8%/±1球 89.6%）。头条为平局比分占 66%（长期）。→ 单日 15 场的比分单点期望仅 2.3 场，**"每天不到 3 场"是天花板不是故障**；连续多日单点<10% 才需怀疑漂移。

## 比分精选 / 大胆档（09-17 解耦定调）
- 唯一生产入口=`SA.split_boards`：比分精选先占位→大胆档只在剩余场选（同场不上两榜，bold 腿数<TIER_BD 属正常）。常量 TIER_PK=6/TIER_BD=4；档数=10 场 1 档每 +8 场 +1 档（N_TIER_BASE/STEP/TIER_MAX），按非冷启动场数算。
- ❗选取算法唯一实现=`selection_algo.py`；`_gen_report.py`/`_optimize_selection.py` 只调 SA.rank_pk/SA.rank_bold、命中判 SA.pk_result/SA.bd_result，禁另写排序。回放也必须走 SA（09-17 前优化器自写排序致 4/12 天与生产不同）。
- 选场≠展示：选场用引擎口径 `pk_quality`（含市场信息，更适合选场）；展示由各板块自算（自算分布更适合双档：200 场 17.5% vs 引擎 11.5%）。比分精选自带 `pk_dist`（引擎 λ 独立泊松→自己缩放到发布 1X2）；大胆档自带 `bd_ref`（量级档=象限内 `max(bd_min_total, round(λ总)+bd_total_shift)` 最高概率格；极限档=再 +bd_gap）。生产值：bd_total_shift=-1/bd_min_total=2/bd_gap=1/bd_exclusive=1/bd_lean_src='engine'。
- `bd_tuple` 必须 2 元组（质量分, λ总）——`_gen_report` 解包依赖，3 元组会崩。引擎 hit_pick/band_scores 只服务报告正文与 gen_review。
- 结构参数必须大样本定（12 天回放曾把 shift=+1 选最优，178 天证伪最差）；网格已限 shift∈{-1,0}。护栏：改善≥0.3pp 才采纳、可用天数<5 保留默认（连续保持默认属正常，勿放宽）。
- ❗快照必须落盘 cold/data_n（09-17 修）；09-16 及更早快照无法回溯。报告「前日回顾」按当前调参重算，非当日实发口径。
- 大样本工具 `bd_bigsample.py`/`bd_indep_probe.py`（原 `_` 前缀）09-18 已纳管 master `tools/prediction/`。

## 三引擎架构（09-18 定稿，互不影响）
- **A=胜平负**：`_calc_engine.py`（V3.4，λ+Platt+SCORE_ALIGN）→ 报告 **4.1 胜负预测**（编号/主队/客队/倾向/方向可信度/让球盘/让球判读/冷门）。已**去掉**命中比分与双档列。
- **B=比分**：`score_engine.py`（独立新建，只读赛果库+当日赔率/比分盘，**不读 A/C 任何内部状态**）→ 报告 **4.2 比分预测**（预期进球主/客、双方各自最可能进球数+概率、最可能比分+概率、±1球/Top3 覆盖、可信度）。
- **C=两档**：`selection_algo.py`（比分精选/大胆档，见下节）。
- 已实测：改 B 的 λ3/market_mix → 4.1 完全不变；改 C 的 bd_total_shift/pk_degen_down → 4.1、4.2 均不变。
- 报告章节已重编号：4.1 胜负预测 / 4.2 比分预测 / 4.3 进球数 / 4.4 让球盘 / 4.5 冷门 / 4.6 大比分。
- 引擎 B 实现：**双变量泊松**（Karlis–Ntzoufras 共同分量 λ3：X=Y1+Y3, Y=Y2+Y3）+ 主客分拆攻防评级（指数衰减 半衰期120天、向 1.0 收缩 k=4、Gauss-Seidel 对手强度）+ λ 由市场 1X2 去水一维反解分配 + 竞彩比分盘去水分布按 70% 融合 + 蒙特卡洛 2 万次校验解析网格。
- 引擎 B `DEFAULT`：`half_life=120, k_shrink=4, opp_adj=1, score_w=0.50, lam3=0.08, tau 全关, market_mix=0.70, max_goal=8, mc_n=20000, league_eb_k=40`。**`market_dist()` 只取 LISTED（0:0~5:5），必须排除「胜其他/平其他/负其他」**（否则 `int()` 抛错且与网格重复计数，尾部交给模型补）。`bd_tuple`/`top_scores` 口径不变。
- 引擎 B 实测（2478 场 walk-forward）：Top1 **13.88%** / Top3 34.26% / ±1球 66.18% / 1X2 51.61%，**未超基线**（基线经 1X2 校准被结构抬升），但完全独立符合"重做一套"要求；lam3/tau 扫描均在噪声内 → 取小值/关闭，勿再调。
- ✅ 09-18 配置复核（1248 场含比分盘）：**当前配置已是最优**——生产（引擎 λ + 70% 市场融合）Top1 **16.43%** / Top3 37.98% / ±1球 68.91%，优于「改用市场隐含 λ」(14.90%) 与「市场权重 100%」(14.90%)。λ 总量无系统性偏差（引擎λ总/市场隐含λ总 中位 **0.981**、均值 0.964、P10 0.649/P90 1.247）。→ 再调 score_w/market_mix 是过拟合。
- 落盘：gh-pages `66ed89f`(score_engine.py) → `e51ac27`(报告 4.1 拆分) → `562624d`(赛果库对锚) → `fc155d5`/`09eaf8b`(别名行事故修复)；master `ed5735f`(引擎B) → `9711c15`(别名行修复) → `2b7ecc5`/`c2ccdec`(全量纳管+归档)。离线资产 09-18 已入库：`tools/prediction/fit_score_engine.py` + `bt_rows2.json`（重拟合引擎 B 直接跑，不用重建）。
- 用户偏好：**不要反复提示"比分准确率天花板"** —— 已知悉，按要求做并尽力提升即可。

## 报告红线
- 公开页三不落：方法论/口径说明、回测统计量、私下对话与脚本名。复查 grep「用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar」须为空。

## 第七节 联赛形势（7M）
- 源 `data.7m.com.cn/matches_data/{id}/big/standing.js`；id：英超92/西甲85/德甲39/意甲34/法甲93/荷甲99/葡超88/瑞超103/芬超105/挪超104/巴甲160/日职102/日乙347/法乙171/意乙95/西乙96/德乙140。美职/亚冠精英/亚运男足/英冠/英联赛杯/解放者杯/欧冠/欧联/欧协联无 id → UNAVAILABLE。
- 新联赛/队名先补 `league_match.ALIAS`（简→繁异译，如 巴列卡诺→華歷簡奴）。

## 复盘
- 三指标=方向命中率/比分双档命中率/λ总进球偏差。连续多日方向<50% 或 λ偏差>0.2 → 提示离线重拟合（market_calib/Platt）。Brier 差另跑 review_market --skip-audit（非每日强制）。
- **用户问"最近准不准/是不是算法坏了"→ 直接跑 `python daily_diag.py --days 10`**（工作盘根，无 `_` 前缀）。输出逐日命中（方向/单点/双档/两档）+ 1X2 校准 + 模型 vs 纯市场，并自动并列长期基准。判读：与长期基准差在 2σ 内 = 样本波动，不是漂移。
- **「方向/倾向」在公开报告里的 5 处体现**（无单独叫「方向」的栏位，正式名叫「倾向」）：①第三节逐场卡片「XX倾向｜最可能比分」；②第四节 4.1 表第 4 列「倾向」（=`主胜 43.8%`，**百分比是模型给该方向的概率=把握度，不是命中率**，此列即统计口径来源）；③核心策略「星级 = 胜平负方向的确定性」；④方向串关推荐（以倾向为腿）；⑤第二节模型胜平负三率分布图。线上 `https://jinbigbig.github.io/jinbet/predictions/<date>/`。
- 方向口径 = 1X2 三项取概率最大（`SA.direction_key`，不含让球）。**判读用把握度分档**：最大概率 ≥50% 档长期可用（近 10 天 90 场 72.2%），40~50% 档不可信（43 场仅 39.5%，低于抛硬币）。**平局是结构性失血点**：实际平局占 22%，模型只报 2% 平（召回 ~6%），32/60 错判来自此；剔除平局后胜负有 90/118=76.3%。
- 明细核对：`_dir_detail.py`（出 `_dir_rows.json`）+ `_gen_dir_page.py`（出 `diag_dir_<date>.html`，逐场含错判可筛选）。窗口内有赔率的场次口径：模型 65.4% vs 纯市场去水 73.1%（52 场，样本小）。
- 回测逐场档留着做离线 A/B，不必重跑引擎：`_bt_rows2.json`（2478 场，引擎 B 的输入；master 同名 `bt_rows2.json`）、`_bt_rows.json`（旧版 1X2 档）。重跑方式：`<repo>/tools/prediction/` 放 `calc_engine.py` + `_bt.py`(=`backtest_v34.py` 复制，REPO 自动解析为 repo 根)，cwd=repo 根执行；环境变量 `BT_MARKET_W` 可强制市场权重。跑完删 `tools/`（gh-pages 树内不应留）。
