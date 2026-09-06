# JinBet 项目长期记忆

## 项目概述
- **JinBet** — 竞彩足球投注记录与分析工具
- 在线地址: https://jinbigbig.github.io/jinbet/
- GitHub 双分支: master(源码) / gh-pages(部署)
- 技术栈: 纯 HTML/CSS/JS 单文件应用 + Python 标准库脚本 + GitHub Actions CI

## 架构要点
- `index.html` — 主应用，5种玩法(胜平负/让球/比分/总进球/半全场)，localStorage 存储
- 赔率数据从网易体育 (sports.163.com) 抓取
- CI: `.github/workflows/daily-update.yml` — 每日自动更新赔率
- AI 预测: `prediction.html` + `predictions/` 按日期归档

## 关键脚本
| 脚本 | 用途 |
|------|------|
| `fetch_odds.py` | 抓取赔率 → odds_data.json |
| `update_odds_net.py` / `update_163_odds.py` | 抓取 + 注入 HTML |
| `push_bets.py` | 推送投注记录到 gh-pages |
| `clear_bets.py` | 清空线上投注 (需输入YES) |
| `odds_proxy.py` | 本地 CORS 代理 |

## 版本规范
- version.txt 用时间戳格式 (如 20260905082429)，用于 CI 刷新检测
- `APP_VERSION` 常量更新会触发旧 localStorage 数据自动清除
- localStorage keys 必须含版本号，更新时需写迁移代码保留投注记录

---

## 环境约束（2026-09-05 确立，操作前必读）

### 网络代理
- 环境变量 `http_proxy/https_proxy = http://127.0.0.1:53311` **访问 GitHub 返回 502**，不可用
- 可用通道：**`http://127.0.0.1:7897`**
- 用法（临时指定，不污染用户配置）：
  `git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 fetch origin`

### Git 远端引用（高危陷阱）
1. **`git fetch <remote> <refspec>` 不更新 remote-tracking refs**，只写 `FETCH_HEAD`。
   曾因此读到 7-21 的陈旧缓存，误判"云端比本地旧"，险些把本地新版降级。
   → 校验云端真实版本必须以 **`.git/FETCH_HEAD`** 为准，不要信 `origin/xxx`。
2. **本环境无法写入 `refs/remotes/`** —— `git update-ref` 返回成功但磁盘内容不变。
   → 直接对 commit SHA 操作：`git reset --hard <sha>` / `git branch -f master <sha>`。
   → 副作用：`git status -sb` 会显示虚假的 `[ahead N, behind M]`，属显示问题，内容已同步。
3. **`reset --hard` 大批量更新后必须复查 `git status`**：可能部分文件未落盘（表现为 `D`），
   需 `git checkout -- .` 补回。不能只看命令退出码。
4. 判断版本新旧要同时看 `%ad`(author date) 和 `%cd`(committer date)。

### 强制同步标准流程（以云端为准）
```bash
git branch backup-ghpages-local-$(date +%Y%m%d_%H%M%S)   # 先备份
git -c http.proxy=http://127.0.0.1:7897 fetch origin      # 不带 refspec
head -3 .git/FETCH_HEAD                                   # 取真实云端 SHA
git reset --hard <云端SHA>
git clean -fd                                             # 以云端为准时
git checkout -- .                                         # 补回漏落盘的文件
git status --short                                        # 必须为 0 项
```

---

## 项目硬约束

### 分支管理
- **gh-pages** (生产/商店): 仅静态文件 (index.html, odds_data.json, .nojekyll, predictions/, version.txt, favicon*)
- **master** (开发/工厂): 所有源码、Python脚本、CI配置、测试、tools/、文档
- 开发改 master → CI 自动同步到 gh-pages
- 推送前必须 `git pull --rebase` 避免分叉
- 禁止 force push；保留 2026-07-23/25/26 的原始 prediction 报告
- **`predictions/` 只归 gh-pages，master 不同步**（2026-09-06 明确）：
  finish.sh 只推 gh-pages，CI(daily-update.yml) 全程不碰 predictions/，
  master 上有无报告对 CI 零影响。"双向同步"仅指 CI 搬运的 index.html/odds_data.json/
  version.txt/odds_history/results_data.json/results_history/

### HTML / 前端
- 必须包含 Cache-Control / Pragma / Expires meta 标签
- Favicon 多格式 (ICO+PNG+SVG)；Safari 需 `rel="shortcut icon"` 并优先 PNG
- 移除 apple-touch-icon（会导致 Safari 失败）
- 页脚版本号用 APP_VERSION 变量动态设置 (id='appVersion')
- localStorage keys 禁止硬编码
- getOddsForMatch 支持多种 key 格式: 'date_home_away', 'date_home vs away', 'home vs away'
- aiCurrentMatches 必须含 league 字段，与 SCHEDULE 字段一致

### Python / CI
- docstring 只写功能描述，不含版本历史和用法
- GitHub Actions 从 master 运行，推送静态文件到 gh-pages
- .DS_Store 必须被 gitignore

### Git 规范
- commit 格式: `type(scope): 中文描述`，type 含 feat/fix/data/style/ci/report
- README.md 必须含文件说明表；CHANGELOG.md 存版本历史

### 经验教训
- Emoji ⚽ 内联 SVG 会导致编码问题
- Favicon 缓存极持久，需提供清缓存说明
- 绝对路径在子目录部署会 404
- 导入时 game 对象缺 match 字段会显示 undefined
- 未暂存修改时切分支会导致 CI 失败
- **`git clean -fd` 会删除未提交文件且无法从 git 恢复**，执行前先确认损失面
