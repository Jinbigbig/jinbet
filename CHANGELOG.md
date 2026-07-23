# Changelog

所有对本项目的显著变更都将记录在此文件。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 移除
- 🗑️ `index.html` 删除"数据存档"功能。原因：原功能不工作，需求不明确。
  - 顶部按钮 🗄 数据存档
  - 存档模态框（#archiveModal）整个 HTML 块
  - 13 个相关 JS 函数：`getBetGameDate`、`groupBetsByGameDate`、`openArchiveModal`、`renderCurrentBetsByDate`、`archiveSingleDate`、`archiveAllByGameDate`、`downloadArchiveFile`、`importArchives`、`renderSessionArchives`、`removeSessionArchive`、`viewArchiveDetail`、`showArchiveDetailModal`、`renderArchiveBetsTable`、`loadArchiveToCurrent`
  - 全局变量 `sessionArchives`
  - 净减 275 行
  - 保留"导入/导出投注"、"导入/导出赔率"功能（与存档功能独立）

### 修复
- 🐛 `index.html` 批量赛果录入的日期默认值从"次日"改为"当日"。原因：录赛果通常是给当天已结束的比赛补录结果。次日是开赛日而非赛果日。赔率管理和添加投注的默认值仍是次日（行为不变）。
- 🐛 `README.md` 在线访问地址修正为 `https://jinbigbig.github.io/jinbet/`（原 `782117977` 是从旧 README 沿用的错误值）

### 新增
- 📝 `README.md` 重写：补充目录结构、本地使用、数据备份说明
- 📋 `CHANGELOG.md` 新建
- 📦 `requirements.txt` 新建（当前仅使用标准库）
- 🛠️ `.editorconfig` + `.prettierrc` 新建，统一代码风格
- 📂 `tools/` 目录：8 个调试脚本从根目录迁入，硬编码 Windows 路径改为相对路径
- 📄 `tools/README.md` 新建，说明 tools 目录用途

### 变更
- 🗑️ `index.html` 中关于 `v7.28.html` 的引用全部移除
- 🗂️ 8 个一次性调试脚本从根目录移至 `tools/`：`analyze.py`、`check_html_games.py`、`check_html_games2.py`、`check_scores.py`、`check_scores2.py`、`fix_other.py`、`fix_update.py`、`fix_update2.py`
- 🧹 `init()` 中抽离 `fmt()` 日期格式化辅助函数，三个日期输入框分开设置默认值（赛果录入=当日，其他=次日）

## [7.56] - 2026-06-25

### 变更
- 🗑️ 删除 `v7.28.html`（合并到 `index.html`）
- 🔧 `index.html` 微调

## [7.52] - 2026-06-25

### 新增
- 🎉 项目初始化提交
- 📄 `index.html`（v7.52 完整版，含 5 种玩法）
- 🐍 `fetch_odds.py`（GitHub Actions 使用的赔率抓取脚本）
- 🐍 `update_163_odds.py`（完整版抓取 + 注入工具）
- 🐍 `odds_proxy.py`（本地 CORS 代理）
- 🤖 `.github/workflows/odds.yml`（每日 08:00 自动更新）
- 📄 `odds_data.json`（赔率数据）
- 🖥️ Windows 启动脚本：`run_update.bat`、`start_proxy.vbs`

---

## 版本号约定

版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（MAJOR.MINOR.PATCH）：
- **PATCH（补丁号）**：修复 bug、样式微调、小改动（如 7.90.1）
- **MINOR（次版本号）**：新增功能、修改功能、重要改进（如 7.91.0）
- **MAJOR（主版本号）**：重大调整、架构重构、数据 schema 变更（如 8.0.0）

当前版本：从 7.90.0 开始（原 v7.90 平滑过渡）

**特殊说明**：
- `version.txt` 保持时间戳格式，用于 CI 自动刷新检测，不受 SemVer 影响
- 数据 schema 变更通过 localStorage key 反映（如 `worldcup_bets_v737`），升级时会写迁移代码
