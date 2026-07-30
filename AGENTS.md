# AGENTS.md - jinbet 项目约束

## 双分支架构

- `master` — 开发环境：源码、Python 脚本、CI 配置、测试脚本、工具目录、文档
- `gh-pages` — 生产环境：仅包含用户访问的静态文件（index.html, odds_data.json, .nojekyll, predictions/, version.txt, favicon.ico/png/svg），禁止包含开发文件
- 开发改动先提交 master，通过 CI 或手动同步静态文件到 gh-pages
- 推送到远端前必须先 `pull --rebase`，避免分支分叉导致 push 失败
- GitHub Actions 从 master 分支运行，将生成的静态文件推送到 gh-pages
- master 与 gh-pages 需保持双向同步，保留 2026-07-23/25/26 的原始报告

## 版本管理

- 遵循 SemVer 格式：MAJOR.MINOR.PATCH（当前版本：7.96.2）
  - PATCH (x.x.1)：bug 修复、样式调整
  - MINOR (x.1x.0)：新功能、功能修改
  - MAJOR (1.xx.0)：重大调整、架构重构
- `APP_VERSION` 常量驱动版本号，用于自动清理旧 localStorage 数据
- `version.txt` 使用时间戳格式，供 CI 检测是否需要刷新
- 版本更新时必须保留并自动迁移投注记录，使用 `jinbet_force_update` 标记强制加载线上赔率

## localStorage 规范

- 所有 key 必须带版本号（如 `jinbet_bets_7921`），版本更新时自动清理旧数据
- 赔率数据 key 统一使用 `STORAGE_KEY_ODDS` 变量，禁止硬编码
- 投注数据存在浏览器 localStorage 中，清缓存或换设备会丢失

## 数据格式约束

- 赔率 key 格式：`日期_主队_客队`（autoUpdateOdds 使用）
- `getOddsForMatch` 必须兼容多种 key 格式：`date_home_away`、`date_home vs away`、`home vs away`
- `updateScheduleFromOdds` 只能追加比赛，不能删除已有比赛
- 联赛字段优先从 `oddsData[key].league` 取，兜底填"国际赛"
- `aiCurrentMatches` 必须包含 `league` 字段，防止联赛标签丢失
- `loadAiSchedule` 函数中 `aiCurrentMatches` 必须携带 `league` 字段

## 前端规范

- HTML 必须包含 Cache-Control、Pragma、Expires meta 标签，防止浏览器缓存旧版本
- 版本号通过 `APP_VERSION` 动态渲染到 id 为 `appVersion` 的 footer 元素
- Favicon 使用相对路径，多格式兼容（ICO、PNG、SVG），Safari 需要 `rel="shortcut icon"` 并优先 PNG
- 移除 apple-touch-icon 标签（会导致 Safari favicon 显示异常）
- 禁止使用 emoji 内联 SVG（存在编码问题）
- 使用绝对路径会导致子目录部署 404，统一用相对路径

## Git 规范

- commit 格式：`type(scope): 中文描述`
- type 类型：feat / fix / data / style / ci / report
- `.DS_Store` 必须被 gitignore 忽略

## 踩坑经验

- force push 会导致分支内容重复，保持分支独立
- gh-pages 包含开发文件会暴露源码给用户
- 未暂存的修改切换分支会导致 CI 失败
- Safari 对 favicon 缓存极强，需提示用户手动清缓存
- Game 对象缺少 `match` 字段会在导入时显示 `undefined`
- `aiCurrentMatches` 与 `SCHEDULE` 数据源字段不一致会导致联赛标签丢失
