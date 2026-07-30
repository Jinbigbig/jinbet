# JinBet 项目长期记忆

## 项目概述
- **JinBet** — 竞彩足球投注记录与分析工具
- 在线地址: https://jinbigbig.github.io/jinbet/
- GitHub 双分支: master(源码) / gh-pages(部署)
- 技术栈: 纯 HTML/CSS/JS 单文件应用 + Python 标准库脚本 + GitHub Actions CI

## 架构要点
- `index.html` (~6945行) — 主应用，5种玩法(胜平负/让球/比分/总进球/半全场)，localStorage 存储
- localStorage keys: `worldcup_bets_v737` (投注), `worldcup_odds_v738` (赔率)
- 赔率数据从网易体育 (sports.163.com) 抓取
- CI: `.github/workflows/daily-update.yml` — cron UTC 3:15 每日自动更新赔率
- AI 预测: `prediction.html` + `predictions/` 按日期归档

## 关键脚本
| 脚本 | 用途 |
|------|------|
| `fetch_odds.py` | 抓取赔率 → odds_data.json |
| `update_odds_net.py` | 抓取 + 注入 HTML + 更新 JSON (CI用) |
| `update_163_odds.py` | 完整版抓取 + 注入 |
| `push_bets.py` | 推送投注记录到 gh-pages |
| `clear_bets.py` | 清空线上投注 (需输入YES) |
| `odds_proxy.py` | 本地 CORS 代理 :51888 |

## 版本规范
- version.txt 用时间戳格式 (如 20260722043315)，用于 CI 刷新检测
- SemVer 从 7.90.0 开始，当前 7.96.2
- PATCH: bug修复/样式微调; MINOR: 新功能/修改; MAJOR: 重大调整/架构重构
- APP_VERSION 常量更新会触发旧 localStorage 数据自动清除；数据 schema 变更通过 key 版本号反映
- localStorage keys 必须含版本号 (如 jinbet_bets_7921)，更新时需写迁移代码保留投注记录

---

## 项目硬约束 (Hard Constraints)

### 分支管理
- **gh-pages** (生产/商店): 仅静态文件 (index.html, odds_data.json, .nojekyll, predictions/, version.txt, favicon*)，不含开发文件
- **master** (开发/工厂): 所有源码、Python脚本、CI配置、测试、tools/、文档
- 开发改 master → CI 自动同步到 gh-pages；手动推送先 commit master 再同步静态文件到 gh-pages
- 推送前必须 `git pull --rebase` 避免分叉导致推送失败
- 两个分支互相保持同步 (master↔gh-pages)
- 禁止 force push（会导致分支内容重复）；保持分支独立
- 保留 2026-07-23/25/26 的原始 prediction 报告

### HTML / 前端
- 必须包含 Cache-Control / Pragma / Expires meta 标签防止缓存
- Favicon 多格式 (ICO+PNG+SVG) 跨浏览器兼容；link 标签用相对路径
- Safari 需要 `rel="shortcut icon"`，优先 PNG（不支持 SVG）；移除 apple-touch-icon（会导致 Safari 失败）
- 页脚版本号用 APP_VERSION 变量动态设置 (id='appVersion')
- localStorage keys 用变量 (STORAGE_KEY_ODDS)，禁止硬编码
- getOddsForMatch 支持多种 key 格式: 'date_home_away', 'date_home vs away', 'home vs away'
- autoUpdateOdds 处理 '日期_主队_客队' 格式 (非 '主队 vs 客队')
- updateScheduleFromOdds: 从 oddsData[key].league 设联赛，国家队兜底 '国际赛'；新增比赛追加到 SCHEDULE，不删除已有
- loadAiSchedule: aiCurrentMatches 必须含 league 字段
- aiCurrentMatches 与 SCHEDULE 字段必须一致，否则联赛标签丢失

### Python / CI
- docstring 只写功能描述，不含版本历史和用法
- GitHub Actions 从 master 运行，推送静态文件到 gh-pages
- .DS_Store 必须被 gitignore

### Git 规范
- commit 格式: `type(scope): description`，type 含 feat/fix/data/style/ci/report，description 用中文
- README.md 必须含文件说明表；CHANGELOG.md 存版本历史

### 经验教训
- Emoji ⚽ 内联 SVG 会导致编码问题
- Favicon 缓存极持久，需提供清缓存说明
- 绝对路径在子目录部署会 404
- 导入时 game 对象缺 match 字段会显示 undefined
- 未暂存修改时切分支会导致 CI 失败
