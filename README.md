# 🏆 竞彩足球投注记录工具

世界杯/各大联赛竞彩足球投注记录与分析工具，支持胜平负、让球、比分、总进球、半全场等多种玩法。

## 🌐 在线访问

**👉 https://jinbigbig.github.io/jinbet/**

> 赔率每日北京时间 12:00 和 18:00 自动从网易体育抓取更新

## 功能

- 📊 **多种玩法**：胜平负 / 让球 / 比分 / 总进球 / 半全场
- 💰 **盈亏统计**：实时显示各玩法胜率与盈亏
- 🔄 **自动赔率**：每日 12:00 / 18:00 GitHub Actions 自动更新
- 📱 **响应式**：支持手机、电脑端访问
- 💾 **本地存储**：投注数据保存在浏览器本地（不同设备数据独立）

## 目录结构

```
jinbet/
├── index.html              # 主页面（单文件应用）
├── odds_data.json          # 赔率数据（CI自动更新）
├── prediction.html         # AI预测页面
├── predictions/            # AI预测结果存档
├── version.txt             # 版本号
├── update_odds_net.py      # 网易赔率抓取+更新HTML/JSON
├── update_163_odds.py      # 网易赔率更新（完整版）
├── fetch_odds.py           # 赔率抓取（CI调用）
├── push_bets.py            # 推送投注记录到线上
├── clear_bets.py           # 清空线上投注记录
├── odds_proxy.py           # 本地代理（绕过CORS）
├── check_json.py           # 检查odds_data.json
├── tools/                  # 临时调试脚本
├── .github/workflows/      # GitHub Actions配置
├── CHANGELOG.md            # 版本变更记录
└── .nojekyll               # GitHub Pages配置
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `index.html` | 单文件应用，包含所有HTML/CSS/JS，直接打开即可使用 |
| `odds_data.json` | 最新赔率数据，供网页在线查看，CI自动更新 |
| `prediction.html` | AI赛果预测页面，展示AI生成的比赛预测结果 |
| `predictions/` | AI预测结果历史存档，按日期组织 |
| `version.txt` | 当前版本号，用于版本检测和自动更新 |
| `update_odds_net.py` | 从网易体育抓取赔率，替换index.html中的赛程和赔率数据，更新odds_data.json，CI每日调用 |
| `update_163_odds.py` | 从网易竞彩页面抓取所有玩法赔率，转换格式后注入index.html的localStorage初始化代码 |
| `fetch_odds.py` | 从网易体育抓取赔率数据，解析后生成odds_data.json文件 |
| `push_bets.py` | 读取投注记录JSON（默认从Downloads找最新文件），重算统计字段后注入index.html并push到gh-pages |
| `clear_bets.py` | 将index.html中的_injectedBets数组置空，删除线上所有投注记录，需输入YES确认 |
| `odds_proxy.py` | 本地HTTP代理服务（127.0.0.1:51888），帮浏览器绕过CORS限制抓取数据 |
| `check_json.py` | 读取odds_data.json，打印更新时间、比赛数量和前5场赔率数据 |
| `tools/*.py` | 临时调试脚本，用于检查和修复数据问题 |

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

项目采用 **GitHub Pages** 双分支架构：

| 分支 | 角色 | 内容 |
|------|------|------|
| `master` | 工厂 | 开发源码、Python脚本、CI配置 |
| `gh-pages` | 商店 | 静态文件（index.html、odds_data.json等） |

GitHub Actions 每天从 `master` 分支执行脚本，更新后推送到 `gh-pages`：

- **定时触发**：每天 UTC 4:00（北京时间 12:00）、UTC 10:00（北京时间 18:00）自动抓取赔率
- **手动触发**：在 GitHub Actions 页面可手动运行
- **变更检测**：仅当数据有变化时才会提交

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