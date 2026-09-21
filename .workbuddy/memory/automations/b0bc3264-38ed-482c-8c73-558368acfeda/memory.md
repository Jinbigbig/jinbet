# 自动化 b0bc3264 执行记忆（JinBet 每日流水线）

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
