# -*- coding: utf-8 -*-
"""全局配置"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
WEB = BASE / "web"
LOGS = BASE / "logs"

DB = DATA / "breadth.db"
CSV = DATA / "daily.csv"
SERIES_JSON = DATA / "series.json"
UNIVERSE_FILE = DATA / "universe.json"
STATUS = DATA / "status.json"

# 统计起点（用户要求）
START_DATE = "2014-01-02"

# 并发与重试（腾讯接口对高并发敏感，并发数配合 qq.py 里的全局限速一起用）
WORKERS = 16
RETRIES = 5
TIMEOUT = 15

# 单次请求最多返回的 K 线根数（腾讯接口上限）
MAX_BARS = 640

# 增量更新时回看的交易日根数（用于自愈补漏）
TAIL_BARS = 30

# 数据新鲜度校验：目标交易日有 K 线的个股占比低于该值，判定本次抓取不可信
# （真实停牌占比一般在 0.1%~2%，5% 是很宽的容忍线；超过就是数据源返回了缓存旧值）
STALE_RATIO_MAX = 0.05
# 补抓轮的并发数（刻意压低，避免再次触发限流）
RETRY_WORKERS = 4

HOST = "127.0.0.1"
PORT = 8730

# 线上看板地址（推送消息里附带的链接）。换仓库/自定义域名时改这里，或设环境变量 DASHBOARD_URL
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "https://xwlxyt.github.io/gupiaozhibiao/")
