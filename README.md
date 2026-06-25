# 🏆 竞彩足球投注记录工具

世界杯/各大联赛竞彩足球投注记录与分析工具，支持胜平负、让球、比分、总进球、半全场等多种玩法。

## 🌐 在线访问

**👉 https://782117977.github.io/jinbet/**

> 赔率每日北京时间 08:00 自动从网易体育抓取更新

## 功能

- 📊 **多种玩法**：胜平负 / 让球 / 比分 / 总进球 / 半全场
- 💰 **盈亏统计**：实时显示各玩法胜率与盈亏
- 🔄 **自动赔率**：每日 08:00 GitHub Actions 自动更新
- 📱 **响应式**：支持手机、电脑端访问
- 💾 **本地存储**：投注数据保存在浏览器本地（不同设备数据独立）

## 目录结构

```
jinbet/
├── index.html              # 主页面（单文件应用，所有 HTML/CSS/JS 内联）
├── odds_data.json          # 最新赔率数据（由 GitHub Actions 自动更新）
├── fetch_odds.py           # 赔率抓取脚本（GitHub Actions 调用）
├── update_163_odds.py      # 完整版赔率抓取 + 注入工具
├── odds_proxy.py           # 本地代理（绕开浏览器 CORS 限制）
├── tools/                  # 临时调试脚本（move from root）
├── .github/workflows/      # GitHub Actions 配置
├── requirements.txt        # Python 依赖（当前仅使用标准库）
├── CHANGELOG.md            # 版本变更记录
├── .editorconfig           # 编辑器配置
└── .prettierrc             # 代码风格配置
```

## 本地使用

```bash
# 1. 安装依赖（当前仅标准库，可跳过此步）
pip install -r requirements.txt

# 2. 手动抓取赔率（写入 odds_data.json）
python fetch_odds.py

# 3. 打开本地网页
# 直接双击 index.html，或：
python -m http.server 8000
# 浏览器访问 http://localhost:8000
```

## 手动更新赔率（本地 + 注入到 HTML）

```bash
python update_163_odds.py          # 立即执行一次
python update_163_odds.py --test   # 仅测试解析，不写入文件
python update_163_odds.py --cron   # 显示定时任务配置说明
```

## 部署

项目部署在 **GitHub Pages**（分支 `gh-pages`）。`.github/workflows/odds.yml` 配置了：

- **定时触发**：每天 UTC 00:00（北京时间 08:00）自动抓取最新赔率
- **手动触发**：在 GitHub Actions 页面可手动运行
- **变更检测**：仅当 `odds_data.json` 有变化时才会提交

## 数据备份

> ⚠️ 投注数据全部存在浏览器 `localStorage` 中，清缓存或换浏览器/设备会丢失。

建议定期通过页面内的「导出」功能备份数据（待开发），或手动：
```js
// 浏览器控制台执行，导出所有数据
copy(JSON.stringify({
  bets: JSON.parse(localStorage.getItem('worldcup_bets_v737') || '[]'),
  odds: JSON.parse(localStorage.getItem('worldcup_odds_v738') || '{}')
}, null, 2));
```

## 维护与开发

- **代码风格**：根目录的 `.editorconfig` 和 `.prettierrc` 统一定义
- **临时脚本**：一次性调试脚本统一放 `tools/` 目录
- **版本变更**：见 [CHANGELOG.md](./CHANGELOG.md)

## License

MIT
