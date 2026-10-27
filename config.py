# -*- coding: utf-8 -*-
"""全局配置"""
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

HOST = "127.0.0.1"
PORT = 8730
