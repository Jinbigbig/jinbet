# JinBet 项目长期笔记（精简版；详细历史见 automations/b0bc3264/memory.md）

## 每日流水线（顺序不可乱）
0. **最先**：`git show master:update_odds_net.py > update_odds_net.py` → `python update_odds_net.py --no-push` **再** `--no-push --results-only`（顺序错→ODDS 变单引号 JS）。
1. `_local_prepare.py` 2. `_build_today_extras.py` 3. `_calc_engine.py`（查 chain 含「市场概率混合(」「比分矩阵对齐发布1X2」、V3 全 ON、Platt 已拟合）4. `_gen_report.py` 4.5 `gen_review.py --date <昨日>` 5. commit 只推 gh-pages（fetch+rebase，禁 force）。**新增**：跑 4 前先 `python _fetch_league_data.py` 生成 league_data.json（第七节积分榜用）。引擎/脚本改动走 worktree 同步 master，predictions/ 只归 gh-pages。
- ⚠️ 引擎读根目录 `_data_batch{1..6}.json` 覆盖注入当日比赛——旧批撞车会污染预测，跑前确认无陈旧批。
- ⚠️ 首跑当日先 `mkdir -p predictions/<date>`（快照目录缺失→gen_report 报错）。

## 分支与推送 / 协作风险
- origin=SSH 免交互；禁 GITHUB_TOKEN/HTTP 代理。**只信 `git ls-remote`**。
- **另一会话持续覆写 `refs/remotes/origin/*`**（本地 update-ref 不生效），并重建过一条陌生 master 历史（无 tools/prediction）。一切以 `git ls-remote origin <branch>` 为准；同步 master 先 `git reset --hard <真实SHA>`。
- 新脚本勿用 `_` 前缀入库（.gitignore 任意层级匹配）；master 正本放 `tools/prediction/`，本地副本带 `_`。
- 根 index.html 3.4MB 程序生成：仅 IDE 注入 `data-page-node-id` 时才 checkout（丢更新）；CI 撞车 `reset --hard <云端SHA>` 后重跑步骤0。

## 队名归一 / 重复场次
- canonical=短名。SCHEDULE 双行根因=`RESULT_TEAM_NAME_MAP` 缺/identity 映射→**先查映射表别手工删**。已补：基多体大/拉普大学/莱红牛/曼联/哈马费萨。
- 当日盘口只认 index.html `YYYY-MM-DD_主_客` 键；odds_data.json 无日期键会被历史污染。

## 引擎 V3.3（勿回退）
- λ=期望值口径。市场混合 MARKET_W=0.80（λ总量守恒，方向交市场、总量留模型）；联赛进球环境 w=0.25；**score_mix.w 真相=0.3**（非 0.5，线上真实值，注释/旧记忆误写 0.5）；Platt 须在市场混合后分布上拟合（改权重须删 platt_params.json 重拟合）；EWMA(0.25)+MAD；基础λ窗口 N=25/DECAY=0.96。
- λ 保险丝 MAX_TOTAL=4.20/MIN_TOTAL=1.60/MAX_SINGLE=3.20，触顶=过激进勿调高。
- SCORE_ALIGN（第七步D）：比分矩阵三象限缩放到已发布 1X2，勿回退。
- **星级=胜平负倾向确定性**（Platt 后 max(1X2)，阈值 0.44/0.50/0.57/0.66）。旧「星级=比分众数概率」已弃。

## 二级盘 / 市场结论
- 二级盘（market_calib.json）输入须用未混市场 λ（lam_h_B/lam_a_B）；置信门槛 `|让球|≥3`/分歧>25pp/无1X2锚点→低置信「勿跟」。
- 纯市场去水 1X2 最优 > 生产@0.80 > 纯模型；市场已吞掉基本面，别再补。平均返还率 88.56%→按市场买必输。二级盘 alpha：让球✅｜总进球✅不稳｜比分❌｜1X2❌。大比分市场高估只观察。

## 已回测否决（勿再试）
比分盘/总进球盘并入网格、λ 线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS。判 alpha 看样本外 Brier+分月稳定。

## 数据修复史
- 赛果库主客全颠倒已翻转；results_history 孪生去重；ODDS 反向孪生清。改后必 `build_league_profile.py`→删 platt_params.json→重跑引擎。
- **1X2 缺失用比分盘反推**（`local_prepare.py`）：31 档去水按主/平/客聚合，仅当日新鲜比分盘用（09-03 起方向一致率 100%）；09-01 及更早归档比分盘主客翻转，禁回填。

## 比分口径（2026-09-13 晚定稿：头条=联合众数，双档=稳档+胆档）
- 头条=联合众数（top_scores[0] 首个列出格）。**头条不可"大胆化"**：argmax 是单场命中最优解；
  条件实验只在"众数比 λ 总量小 ≥1.5 球"的最保守子集换期望，子集内仍 众数 14.0% ＞ 期望 9.1%
  （时间外 1620 场：众数 16.5% vs round(λ) 12.8%，−3.7pp）。任何 λ 分档/阈值下众数都赢。
- 双档=**稳档(众数) + 胆档(λ 期望取整)**，互补非同质（2026-09-13 晚起，取代"众数+次高众数"）。
  代价双档 27.6%→26.1%（−1.5pp）；收益含≥3球档 39%→69%。文案"长期双档命中约 26%"仍准。
- 新增「🔥 大胆档」板块（bold_sec，纯增量）：按量级档与头条总进球差取前 5 场，给量级档+极限档。
- 保守的量化：众数头条平均 1.89 球 vs 实际 2.83（偏差 −0.94）——这是分布单点的固有属性，非 bug。
- 旧「头条=期望值、弃众数」口径已于 09-13 早间废弃，勿回退；「量级参考」列保留为参考。
- **基准（4036 场 w=0.3）**：联合众数单点 14.94%＞floor(λ) 13.85%＞round(λ) 13.06%＞常数 1:1=12.93%（McNemar χ²=19.34 p<0.001，净多中 81 场）。阶梯 Top1 14.94/Top2 26.54/Top3 35.48/±1球 67.24%。
- **病灶=退化**：65.8% 场次首选 1:1；「🎯 今日比分精选」按自评概率排序（前3场单点~20%，取前3→49% 比赛日至少中1场）。
- **调因素实证死路**：坐标上升训练集+28→检验集−21。提升只在「分布/新信息源」。
- λ 分档：λ≤2.6（约 1/3 场）单点 18~22% 最值得看比分（阈值 2.6/3.5）；9 月 λ 3.05~3.13 异常高，**严禁 k>1 追高**。
- ⚠️ 算 ±1 球邻域禁用 `sum(g[max(0,h+dh)])`（边界重复计数虚高），须去重格集合。
- 模型校准偏保守（P(1:1) 自认12.11% vs 实际12.93%）→ 矩阵不动。

## 报告呈现纪律（2026-09-13 用户当面指出，红线）
- 公开页**三不落**：不落方法论/口径说明、不落回测统计量（χ²/Brier/McNemar/样本量）、不落私下对话引用（「用户定调/你说/为什么单列…」）。只留「今日可执行结论」+ 量级基准（单点~15%/双档~26%/±1球~67%，不留精确值）。
- 脚本注释同步去个人化（「用户定调」→「口径依据：」）。
- **章节标题一律不带解释性括号**（如「今日比分精选（重点关注这几场）」），解释性文字放正文或说明段。
- 改完复查：`grep -E "用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax" predictions/<date>/index.html` 须为空。

## 第七节 联赛形势（2026-09-13 接入 7M）
- 数据源 **7M 体育数据库** `data.7m.com.cn/matches_data/{id}/big/standing.js`（并行 JS 数组 f_sds_tn/mnum/mw/md/ml/mgs/mga/pt/memo）。
- 脚本：`_fetch_league_data.py`（抓 14 联赛→`league_data.json`）、`_league_match.py`（简体缩写队名→7M 繁体全名映射，覆盖 44/46，未匹配优雅显示「排名—」）。
- **联赛 id 映射**：英超92/西甲85/德甲39/意甲34/法甲93/荷甲99/葡超88/瑞超103/芬超105/挪超104/巴甲160/日职102/日乙347。**美职(MLS) 7M 未收录**（id459 实为 USL）→ 该联赛卡显示说明替代，勿编造。
- 卡片：积分榜全表（欧冠/欧联绿底、降级红底）+ 本日对阵积分影响（双方当前排名/分差，≤3 分标「卡位对话」）。未来赛程 7M 不含。
