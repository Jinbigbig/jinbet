# JinBet 长期笔记（细则见 automations/<id>/memory.md）

## 流水线（顺序不可乱）
0. `git show $(git ls-remote origin master|cut -f1):update_odds_net.py > update_odds_net.py` → `--no-push` 再 `--no-push --results-only`（顺序错→ODDS 单引号 JS）。判据 `[DEDUP-ALIGN]`；跑前清 `_data_batch*.json`。
1. `mkdir -p predictions/<date>` → `_local_prepare.py`（0 场=无赛）。
2. `_build_today_extras.py` → `_fetch_league_data.py` → `_calc_engine.py`（链路标记只在 stdout：grep `MARKET_BLEND_PROB|SCORE_ALIGN|ON·生效|ON·观察`，实际文案「市场概率混合已启用(V3.2)」「比分矩阵对齐发布的 1X2 已启用(V3.3)」，**旧串「市场混合(」已不存在**）。
4. `_gen_report.py` → `gen_review.py --date <昨日>` → `_optimize_selection.py`。
5. 索引 → 根 index.html 有 `data-page-node-id` 才 checkout → 只推 gh-pages。**严禁 `git add -A`**。

## 分支与推送
- origin=SSH；只信 `git ls-remote`（本地 `origin/*` 恒滞后，取文件用 `git show $(git ls-remote origin <br>|cut -f1):路径`）；禁 force/GITHUB_TOKEN。
- gh-pages `git rebase --no-fork-point <云端SHA>`（**不带第二参数**）；撞死→`reset --hard <云端SHA>`+`checkout <好提交> -- .`+单提交推；续须 `GIT_EDITOR=true`。
- 推 master 用 worktree：`git worktree add --detach "C:/Users/Jin/_wt_master" <SHA>`（**须 C:/ 风格**）→覆盖→commit→`push origin HEAD:refs/heads/master`→`worktree remove --force`。
- ⚠️ `reset --hard` 会删掉被跟踪的 root `_` 脚本与 league_data.json → 先 `git tag -f backup_<日期>_pre <本地提交>`，事后 `git show backup_<日期>_pre:<路径> > <路径>` 恢复。
- ❗❗ `reset --hard` **会抹掉 `.workbuddy/memory/` 已跟踪未提交改动** → 记忆写完必须随当日 commit 入库（chore 前缀）。
- ⚠️ `git show <ref>:路径` 若 ref 未 fetch 会 fatal 且**已把目标截成 0 字节** → 先 `git fetch origin master` 再 show。

## 云端正本布局
- master `tools/prediction/`=脚本正本（去 `_` 前缀）+ 根 update_odds_net.py/platt_params.json/league_profile.json；这几支实为 **LF**；`gen_report` 有 5 处去下划线须保留。
- ⚠️ `tools/prediction/gen_report.py` 已**落后**（无 CUP_EXTRA 杯赛卡/第六节未改名）→ 本地 `_gen_report.py` 最新，**勿用 master 副本覆盖本地**。
- `_league_match.py` 内容自洽 → 改 ALIAS 后直接 `cp` 到 master `tools/prediction/league_match.py`。
- gh-pages=数据运行态（predictions/、odds_data/results_data、results/odds_history/、scripts/、_calc_result.json、v34_state.json、strength_db.json、selection_tuning.json）+ **仅 root** 的 score_engine.py/selection_algo.py/score_pick_optimize.py。root `_` 脚本 gh-pages 未跟踪 → 只同步 master。

## 队名归一 / 别名行（最贵的坑）
- canonical=官方简称（沃夫斯堡、布城、奥斯KFUM、卡塔尔23…）；缺映射补 `RESULT_TEAM_NAME_MAP`，别手工删。
- 同编号双行→丢让球/比分盘与评级历史；查 matches_data 行数>场次、_calc_result 该场 rq 空；修完重跑 1→4。

## 引擎 V3.4（勿回退）
- λ=期望值；联赛 w=0.25；score_mix.w=0.3；市场权重动态 `league_market_w` 0.65~0.95；改市场混合必重拟合 platt。保险丝 MAX_TOTAL4.2/MIN_TOTAL1.6/MAX_SINGLE3.2/MIN_SINGLE0.18/ZF1.0/EB_K40。SCORE_ALIGN 勿回退；冷启动不进比分精选。星级 0.44/0.50/0.57/0.66。
- 五模块：BRIER_OPT/KALMAN ON·生效；HEDGE ON·观察（apply=False 故意）；CLV/DRIFT 监控。
- **已否决勿再启用**：比分盘/总进球盘入网格、λ线性混合、偏差查表+收缩、联合校准1X2、大球导向、象限守恒、Dixon-Coles τ、isotonic/温度缩放、赛事专属战绩、VENUE_H2H、BTTS、REST_DAYS、市场权重>0.85、平局权重缩放、λ缩放、非平局优先、爆冷过滤。**单点/方向已贴天花板，只剩扩覆盖或加场次。**
- 比分**推演过程不进公开页**：`match_card()` 不挂 `chain_table()`，不留「λ=…→校准后 λ×…」「零封修正 ×…」推演行；「比分是怎么推出来的」须 0 命中。

## 比分口径（09-22 定稿）
- 首选唯一实现 `score_engine.headline_reorder`：带 `mkt`（比分盘去水）→ argmax[log p_比分盘+0.3·log p_模型]，**不要求与方向同象限**；无 mkt 退回旧 gap 规则。同日同比分上限 `head_day_cap=4`。
- ⚠️ **禁止重排 `top_scores` 位次**（恒纯概率降序）；首选另存 `headline`。跨象限设计允许：卡片渲染 `hm_mark`，**别写「方向倾向内的首选比分」**。
- ⚠️ 落位必须走**引擎B**候选格：`_apply_headline_plan(out,TODAY,raw)`→`_headline_cells`（`engine_asof()+predict()`，不可用才退 top_scores）。
- 双档=除首选外概率最高的两个。长期：方向 51.2%、单点 ~15%、双档 ~24%、前三 39.1%。单日 15 场单点期望 2.3 场是天花板，**勿反复向用户提示**。

## 两档（selection_algo 唯一实现）
- 唯一入口 `SA.split_boards`；只调 `SA.rank_pk/rank_bold`、`pk_result/bd_result`。TIER_PK=6/TIER_BD=4；档数=10 场 1 档、每 +8 场 +1 档，按当日全部非冷启动场次算、两榜同档数。
- 生产值：bd_min_total=3、bd_gap=1、bd_exclusive=1、bd_lean_src='engine'。护栏：改善≥0.3pp、天数<5 保留默认。`bd_tuple` 必须 2 元组。

## 三引擎 / 渲染纪律
- A=_calc_engine（4.1 胜负/4.4 让球/4.5 冷门）；B=score_engine（4.2 比分，prob_temp=1.20、market_mix=0.70 勿降）；C=selection_algo（两档）；另 4.3 进球/4.6 大比分。
- **半全场（2026-10-22 起常态）**：引擎 `htft_analysis`（半场 λ=全场×0.45 `HALF_SHARE`，上下半场独立泊松 9 格，**纯模型不吃市场**）；每场 `htft` 字段入 `_calc_result`+快照；报告=卡片「总进球倾向」下方「半全场」行（top3 `_conf_tag`+半场倾向）+ 4.3 表末列；引擎未产出时自动省略。**复盘已接入（2026-10-26）**：`_gen_report._recap_htft()` 在 4.3 表下挂「半全场预测落地」，`gen_review` 加「半全场」列；老快照无 `htft` 字段时按当时 λ 调 `_calc_engine.htft_analysis` 复算（84/84 实测与引擎输出一致）。半全场概率尺度独立 → 渲染用 `HTFT_HI=40 / HTFT_MID=26`，别用默认 60/45（否则九宫格全判灰）。
- 词表统一 **可用/慎用/别跟**；让球分级唯一实现 `rq_grade(prob,conf)`（≥50% 且置信非低 可用 / ≥42% 慎用 / 其余别跟）。回顾表用 `_rq_grade/_rq_tag/_rq_cell`；快照无 rq 置信度 → `_rq_conf_of(hc)` 按 |让球| 还原（1 高/2 中/≥3 低）。
- **概率唯一渲染器 = `_conf_tag(p,nd=1,hi=60,mid=45)` → `<span class="pct pct-hi|pct-mid|pct-lo">`**（默认 ≥60 绿/45~60 橙/<45 灰）。`_gen_report.py` 禁手写裸百分比 span。`_conf_tag`/`_conf_bucket`/`_conf_split`/`_star_txt` 必须定义在 `build_league_sec` **之前**。半全场（九宫格）与半场倾向传 `hi=40,mid=26`。
- **4.1 胜负表「备选方向」列（2026-10-26 起）**：`op2*100 < 50`（方向可信度未达「可用」）时渲染三率第二高者+概率，否则「—」。回测 599 场：<45% 档 单选 43%→双选 73%（+30pp）、45-50 档 56%→82%、≥60 档 69%→88%，**增益低置信最大**。⚠️ 双选是三选二，随机基线 67%，对外必须并列展示且注明基线，**禁止拿双选当准确率**。
- 红线：公开页 grep「用户|你说|定调|目标函数|口径一致性|偏差归因|probe|χ²|Brier|argmax|McNemar」须空。

## 报告布局（2026-10-22 定稿）
- 章节序：一总览/二市场信心/三逐场/四预测汇总/**五联赛与杯赛形势**/六核心策略与风险提示/动态校准/今日比分精选/大胆档（`{league_sec}` 在 `{strategy_sec}` 之前）。
- 第五节：**左积分榜、右形势分析**；积分榜**完整表格常驻**（禁色块/折叠，`std_chips()` 已删）。唯一渲染器 `std_table()`；外层 `.league-overview-grid` **单列**，分栏只在卡内（`.lg-split` 1fr 1fr，≤900px 单列）。
- 「关键线」「历史补跑说明」每赛事说一次（`_zone_line()`/`_past_note()` 挂右栏顶部），**禁止逐场重复**。
- 榜源四级链：7M（各国联赛）→ 腾讯 `qq_standings.json`（欧冠等，须 `limit=50`）→ Fox `fox_standings.json`（解放者杯/欧罗巴，SSR 正则解析 `<table id="live-standings-table-N">`，bifrost 恒 401 别试）→ UEFA `uefa_standings.json`（欧协联，`_fetch_uefa_standings.py` 解析 uefa.com 官方页；**本机直连 uefa.com 两域名恒 read timeout**，失败保留原文件，刷新走 WorkBuddy WebFetch 通道抓官方页后落盘）。腾讯/Fox/UEFA 用 `std_league_card()`；分组赛用 `std_group_card()` 只展开本日队所在小组。小组赛收官（场次齐平且≥3）不做名次模拟，改给组内名次+出线结论。腾讯赛事 ID（1-399 全扫描实证）：欧冠5/英超8/意甲21/德甲22/西甲23/**法甲24（18 是无效 ID，已修）**。
- 第三节逐场序：队名+排名 → 赔率三格 → 积分排名·赛事（3列）→ H2H 两卡 → 历史底蕴 → **历史交锋+近期战绩（始终并列）** → 伤停与赛前分析 → 冷门/让球 → 比分与方向。榜位唯一入口 `std_rows(lg)`（7M→腾讯→Fox）与 `std_of(team,lg)`；`rank_of` 已改走它。底蕴表头「队名（国家）」；两国相同则维度名加「（国名）」。
- 文案红线：**不写「怎么看表」的说明句**；数据缺口用最短一句（如 `暂无交锋记录`）。
- 窄屏 `@media(max-width:640px)`：`.form-grid`/`.odds-grid` 用 `minmax(0,1fr)`。

## 赛前信息：阵容/伤停 + 天气
- 主源 lineupstoday.com（`_fetch_lineups.py`→lineups.json）：URL 拼法 `/<league>/<home-slug>-<away-slug>-<DD-MM-YYYY>/`，slug 映射在 `_RAW_TEAMS`。⚠️ **映射表存全称、报告用简称，精确查表查不到会静默 skip（reason=unmapped，miss 里 None 即缺的 slug），报告表现为「暂无公开伤停」**——欧战新军必须补简称别名（10-23 补了格风暴/波兹南/萨迪纳摩/克里特/贝西克塔/利勒斯特，命中 6/12→12/12）。`_RAW_TEAMS` 改动须同步云端 master `tools/prediction/fetch_lineups.py`。区块 id 荷兰语：`opstelling`（阵容，ov-panel ov-elftal + ov-veld__speler）与 `absenties`（伤停，li.ov-absentie），按 id 切块别按 h2。
- 坑：赛后页无 `absenties`（须赛前抓）；`ov-veld__speler` 带 `is-twijfel` 后缀；赛后 em 是「阵型 · 主教练」；英文队名取 JSON-LD SportsEvent 不可用 slug 反查；「Not in the squad」丢弃。单页 2–15s 偶发 SSL 失败重试 1 次；发现场次靠联赛页/拼 URL，别依赖 sitemap。
- 渲染：`injury_html()` 优先 lineups.json（按 matchNumStr）→ 阵型徽标+缺阵数+`<details class="inj-xi">` 折 11 人首发；无数据才回退 injuries.json。天气 `_fetch_weather.py`→weather.json（Open-Meteo，18–23 时，bad≥35km/h 或降雨≥70%）。**天气脚本读 `_calc_result.json` 的 today → 必须在步骤3 之后跑**，步骤2.6 阶段跑会取到昨日日期（`_gen_report` 内 `_ensure_side_data` 会重取，故报告正确）。`_ensure_side_data()` 顺序：阵容→香港赛马会→天气→伤停兜底（`_fetch_injuries.py`）→开赛时间。jobs 是 `(tag, script, extra_args)` 3 元组。
- **开赛时间（10-23 起常态）**：`_fetch_match_times.py`→match_times.json，源=网易竞彩赛程 `matchList/1?days=YYYY-MM-DD 12:00:00` 的 `matchTime`（毫秒/北京时间）；抓 date±1 天合并，按 `jcNum` 建表，label 相对 date（同日 `HH:MM` / 次日 `次日 HH:MM`）。卡片位置：`<span class="match-time">{TODAY}</span>` 后紧跟 `<span class="kickoff">`，再是天气。唯一入口 `kickoff_of(num)`；**加载时必须校验 match_times.json 的 date==TODAY**（编号每周复用，跨日脏数据会挂错场）。体彩 `getUniformMatchResultV1.qry` 只有 matchDate 无时分秒，别用它取时间。
- **实测不可用勿再试**：Transfermarkt 405、premierinjuries 403、Sports.ru 403、OTempo 超时、premierleague.com JS 渲染、百度体育 SPA。

## 复盘/诊断
- **六指标（2026-10-26 起）**：方向 / 方向双选 / 比分单点 / 比分双档 / 半全场首选 / 总进球众数 / λ偏差。连续多日方向<50% 或 λ偏差>0.2 → 提示重拟合。问准不准 → `python daily_diag.py --days 10` 或 `python gen_review.py --kpi`。联赛形势源=7M standing.js，新队名补 `league_match.ALIAS`。
- **`gen_review` 累计实测（599 场 since 09-08）**：方向 57.8% / 方向双选 81.0% / 单点 10.2% / 双档 21.2% / 半全场首选 34.9% / 总进球众数 20.7%。
- **同口径实测（658 场，09-05→10-25，快照×results_data 关联重算）**：方向 55.9% / 比分首选 11.2% / 比分双选 21.0% / 总进球首选 19.0%·前二 38.4% / **半全场首选 33.7%·前二 52.1%·前三 65.0%（校准比 0.97 健康）**。半全与总进球**已于 2026-10-26 接入 `gen_review` 常规复盘**。
- ⚠️ **「单点约 15%」文案与实测不符**：15% 来自 4036 场旧口径回测，近期实测 10.2%（599 场）/ 11.2%（658 场）。**勿直接引用 15%**，需另案校准文案。
- ⚠️ **杯赛不要降权**：实测杯赛/洲际 173 场方向 61.3% > 联赛 426 场 56.3%，与"杯赛爆冷多"的直觉相反。
- ⚠️ **短窗口会骗人**：半全前二只看 10-22~10-25 的 83 场会得 36.1%（期望 52.9%，比值 0.68），那是 4 天冷段。**少于 300 场不要据此调参**。
- **对标球小策（qiuxiaoce）**：它宣称的 62% 是**方向双选任一命中**口径；拆开是单选 53.9% / 双选 62.1%，且低置信场次双选占比 56.6%（47.2% 单选→63.2% 双选）。同口径下六项里我们赢五项、差一项在噪声内，**方向 +2.0pp（z≈0.61）与五大联赛 +4.5pp（z≈0.88）均不显著**。它的 xG/xGOT/OTI/GIM/DII 与 λ 参数一律不外泄，只可学框架（三档分级/情报否决/双选档），不可复刻。详见 `2026-10-26.md`。
- **HALF_SHARE（当前 0.45）扫描有内部峰在 0.30~0.35（前二 +2.0pp）**，但≈1 个标准误，**未达显著，暂不改**；要改须先做逐日交叉验证。
## 赛果补录定时任务（每日 08:00）
- 入口 `_sync_results.py`（master `tools/prediction/sync_results.py`，LF）：**[0/3] 对齐远端基线** → `--no-push --results-only` 落盘 → 读 `[变更判定]` → 0/0 跳过不推 → `git add` 5 路径 + `commit -- pathspec`（index.html/results_data.json/results_history/odds_history/version.txt）→ push（被拒才 `rebase --autostash`）。
- **⚠️ 根因与根治（10-26）**：本地克隆恒落后远端当天 3 次「自动更新赔率+赛果」提交，若在旧基线算完再推 → non-fast-forward → rebase 要把补录 diff 重放到远端，两侧同改 index.html/results_data.json/results_history/ → JSON 无法合并 → **连续 10-24/25/26 退出码 1**。根治=`align_to_remote()` 放在抓取之前：fetch → 纯落后则 `merge --ff-only`（脏文件挡住退 `reset --keep`）→ 分叉且本地提交**全是** `data: 赛果补录` 则 `reset --keep` 回远端基线**重算**（赛果幂等，不丢数据）→ 分叉含人工数据提交则退出码 2 交人工，绝不自动丢弃。
- ⚠️ commit 必须带 pathspec + 提交后 `git reset -q`：否则索引里残留的 `odds_data.json` 等会被一起提交（曾出现）。
- ⚠️ 不能直接跑 `update_odds_net.py --results-only`：`push_to_gh_pages()` 硬要求当前分支 master，而仓库日常在 gh-pages 且本地 master 落后云端 126 提交。
- ⚠️ `existing_results` **必须优先读 results_data.json**（26 字段）。历史实现读 index.html 的 `const RESULTS`（`update_html_results()` 只写 15 字段）→ 写回时静默降级历史条目（实测 3242 条丢让球/比分盘/总进球/半全场）。
- ⚠️ 变更判定必须 `_norm()` 归一：index.html 里数字是字符串 `'4.05'`，API 是数字 `4.05`，直比恒不等（曾每天误报 109 条更新）。
- 待办：归档里仍有 1637 条带「让球」的完整记录可回填 results_data.json，等确认。

## 兄弟项目 Matlas（C:\Users\Jin\matlas，与 jinbet 零 import）
- 定位：jinbet=算（引擎/回测/调优），Matlas=发（per-match 落地页、留档核验、llms.txt/sitemap/Schema.org）。唯一耦合=`matlas/models.py` 数据契约 v1.0（`Match.from_dict`），jinbet 侧映射等用户指示。
- 仓库 github.com/Jinbigbig/matlas（SSH）。`main`=源码+数据（`_site/` 不进 main）、`gh-pages`=构建产物（含 .nojekyll）。发布走 `./publish.sh`（strict 构建→临时目录→强推 gh-pages），勿手工混提交。
- 线上：GitHub Pages `jinbigbig.github.io/matlas/` + 内置通道 `matlas.app.workbuddy.host/?sharecode=…`（裸路径 403）。域名只在 `config.DEFAULT_BASE_URL` 一处；内链按页深用相对前缀。
- 红线落成 `matlas/rules.py` 构建期自检（`build.py --strict` 非零退出）；`prob_tag()` 唯一渲染器；`Match.fingerprint()` 赛前字段指纹=不可篡改台账。
- 未决等指示：接 jinbet V3.4 引擎、赔率/7M/腾讯/Fox 抓取、SCORE_ALIGN、让球分级、冷门过滤、球小策对照源上页。
