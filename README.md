# A股市场宽度指标（TRIN + 上涨占比）

从 **2014-01-02** 起，逐交易日统计沪深两市 A 股的涨跌家数与成交额，计算两个指标并提供可查询的图表看板、每日自动更新与推送。

| 指标 | 公式 | 说明 |
|---|---|---|
| **TRIN** | `(上涨家数 ÷ 下跌家数) ÷ (上涨成交额 ÷ 下跌成交额) × 100%` | 阿姆氏指标（成交额口径），>100% 上涨缺量能配合（偏弱），<100% 量能集中在上涨股（偏强） |
| **上涨占比** | `上涨家数 ÷ 当日有交易的全部A股家数 × 100%` | 市场宽度，直观反映普涨/普跌 |

## 快速开始

```bash
# 1) 全量回补（首次，约 35 分钟，可中断续跑）
python build_history.py

# 2) 启动看板
python server.py            # 打开 http://127.0.0.1:8730

# 3) 日常增量更新（每个交易日收盘后跑一次，约 10 分钟，自动补漏）
python update_daily.py

# 4) 生成当日简报（供推送）
python notify.py            # 加 --json 供程序读取，加 --notify 同时弹桌面通知

# 5) 云端部署（电脑关机也能每天更新并推送到手机）
#    见 DEPLOY_CLOUD.md；日常由 GitHub Actions 自动执行
python cloud_job.py         # 云端任务入口，本机也可直接跑
python export_static.py     # 生成 docs/ 静态看板（GitHub Pages 用）
```

Windows 下双击即可：`启动看板.bat`、`更新数据.bat`。

> 数据接口（腾讯证券）对高并发敏感，`qq.py` 内置全局限速（约 9 请求/秒）与自适应退避；
> 首次回补 5224 只股票 × 约 5 段历史 ≈ 2 万多次请求，耗时 30~40 分钟，中断后重跑会从断点继续。

当前数据：**2014-01-02 ~ 2026-10-27，共 3114 个交易日**。

## 目录结构

```
astock-breadth/
├── config.py          配置：起始日期、并发、端口
├── qq.py              行情客户端（腾讯证券公开接口，支持翻页取全历史）
├── store.py           聚合 + 指标计算 + SQLite/CSV/JSON 导出
├── build_history.py   全量回补（断点续跑）
├── update_daily.py    增量更新（重叠回看重算，自愈补漏）
├── notify.py          当日简报（文本 + HTML）
├── push.py            推送通道（Bark / Server酱 / PushPlus）
├── cloud_job.py       云端每日任务入口（更新→简报→推送→摘要）
├── export_static.py   导出静态看板到 docs/（GitHub Pages 用）
├── server.py          本地 Web 服务（标准库，无第三方依赖）
├── web/index.html     看板页面（ECharts 已本地化，可离线；兼容静态托管）
├── web/vendor/        echarts.min.js
├── docs/              静态版看板（云端自动生成，手机可访问）
├── .github/workflows/ GitHub Actions 定时任务
└── data/
    ├── breadth.db     SQLite 主库
    ├── daily.csv      导出明细（Excel 可直接打开）
    ├── series.json    看板数据
    └── logs/          运行日志
```

## 计算口径

- **样本**：沪深两市 A 股（沪市 600/601/603/605/688，深市 000/001/002/003/300/301），**不含北交所**；当前约 5224 只。
- **涨跌判断**：用**前复权**收盘价与前一交易日收盘价比较，除权除息日不会误判为下跌。
- **剔除**：当日停牌（无成交）不计入；新股上市首日无前收盘，不计入。
- **成交额**：当日真实成交金额，单位为元（展示为亿元）。
- **涨跌停**：主板 10%、创业板/科创板 20%、ST 主板 5%，按涨跌幅阈值近似判定。
- **已知局限**：样本取"当前仍在交易"的股票，历史早期（2014~2016）已退市个股未纳入，故早期家数略有低估；该偏差对家数比、成交额比这类比值型指标影响很小。

## 每日自动更新与推送

### 方式一：本机（WorkBuddy 定时任务）

定时任务 **「A股市场宽度指标 每日更新与推送」**：每周一至周五 **16:30** 自动执行。
依赖这台电脑开机；关机、休眠、断网时不会运行。

### 方式二：云端（电脑关机也能跑）★ 推荐

搬到 GitHub Actions 免费服务器，每个交易日北京时间 **16:40** 自动更新并推送到手机，
数据写回仓库，同时更新静态看板（GitHub Pages）。**完整步骤见 [DEPLOY_CLOUD.md](DEPLOY_CLOUD.md)**。

三条命令说明全部：

```bash
python cloud_job.py        # 云端入口：更新数据 → 简报 → 推送（非交易日自动跳过）
python push.py --test      # 单独测试推送通道是否通
python export_static.py    # 重新生成 docs/ 静态看板
```

推送通道用环境变量配置（GitHub Secrets 同名）：

| 变量 | 说明 |
|---|---|
| `BARK_KEY` | Bark 的 key（iPhone） |
| `SERVERCHAN_KEY` | Server酱 SendKey（微信） |
| `PUSHPLUS_TOKEN` | PushPlus token（微信） |

本机测试时也可以写进 `data/push.json`（该文件已在 .gitignore 中，不会被提交）：

```json
{"bark_key": "你的key", "serverchan_key": "", "pushplus_token": ""}
```

非交易日会自动判定并跳过，不会重复推送。

> 安全阀：若某天抓取到的样本家数明显低于库中已有值（如接口大面积失败），该日会保留原值不被覆盖；
> 增量更新只重算最近 25 个交易日，写入前严格截断，不会污染历史数据。
> 行情接口另有备用域名回退，股票列表接口异常时自动改用上次缓存，避免整次任务失败。

## 数据库表

`daily`：`date, up_cnt, down_cnt, flat_cnt, total_cnt, up_amt, down_amt, flat_amt, up_vol, down_vol, flat_vol, limit_up, limit_down, trin_pct, up_ratio, idx_close, updated_at`

`index_daily`：`date, close`（上证指数收盘，用于图表叠加）

## HTTP 接口

| 接口 | 说明 |
|---|---|
| `GET /api/meta` | 数据区间、最新交易日、更新状态 |
| `GET /api/series?start=&end=` | 区间序列 |
| `GET /api/day?date=YYYY-MM-DD` | 单日数据 + 历史分位 + 前后各 5 日 |
| `POST /api/refresh` | 触发一次增量更新（页面"更新数据"按钮） |

> 数据来自腾讯证券公开行情接口，仅用于个人研究，不构成投资建议。
