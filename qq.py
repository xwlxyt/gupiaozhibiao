# -*- coding: utf-8 -*-
"""腾讯行情数据客户端（仅依赖标准库）

数据口径说明
------------
* K 线接口返回字段：[日期, 开, 收, 高, 低, 成交量(手), {}, 换手率, 成交额(万元), ...]
* 使用前复权（qfq）价格判断涨跌，这样除权除息日不会被误判为下跌。
* 成交量、成交额为当日真实值（不做复权），单位为 手 / 万元，这里统一换算为 股 / 元。
"""
import json
import random
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import config

# ---------------------------------------------------------------- 限速与退避
# 数据源对短时间高并发会限流，这里做全局匀速（令牌间隔）+ 连续失败时全体暂停。
_RATE = 9.0                     # 全局每秒最多请求数
_gate_lock = threading.Lock()
_next_slot = [0.0]
_pause_until = [0.0]
_err_streak = [0]


def _gate():
    with _gate_lock:
        slot = max(time.time(), _next_slot[0], _pause_until[0])
        _next_slot[0] = slot + 1.0 / _RATE
    wait = slot - time.time()
    if wait > 0:
        time.sleep(wait)


def _on_error(streak):
    pause = min(20.0, 1.5 * streak)
    with _gate_lock:
        _pause_until[0] = max(_pause_until[0], time.time() + pause)

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Referer": "https://gu.qq.com/",
}

_KLINE = (
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    "?_var=k&param={secid},day,{start},{end},{count},qfq"
)
_RANK = (
    "https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
    "?board_code=aStock&sort_type=price&direct=down&offset={offset}&count={count}&_appver=11.17.0"
)


class FetchError(RuntimeError):
    pass


def _get(url, timeout=None, retries=None):
    """带限速、退避与备用域名回退的 GET。

    主域名 proxy.finance.qq.com 在境外网络偶尔不稳，重试耗尽后换
    web.ifzq.gtimg.cn 再试一轮（K 线接口两边都支持）。
    """
    try:
        return _get_with(url, timeout, retries)
    except FetchError:
        # 备用域名的路径少一层 /ifzqgtimg，替换时一起换掉
        alt = url.replace("proxy.finance.qq.com/ifzqgtimg", "web.ifzq.gtimg.cn")
        if alt == url:
            raise
        return _get_with(alt, timeout, retries)


def _get_with(url, timeout=None, retries=None):
    timeout = timeout or config.TIMEOUT
    retries = retries or config.RETRIES
    last = None
    for attempt in range(retries):
        _gate()
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "ignore")
            if not raw.strip():
                raise FetchError("空响应")
            _err_streak[0] = 0
            return raw
        except Exception as exc:  # noqa: BLE001
            last = exc
            _err_streak[0] += 1
            _on_error(_err_streak[0])
            time.sleep(0.8 * (attempt + 1) + random.random() * 0.8)
    raise FetchError(str(last))


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def fetch_kline(secid, end_date=None, count=None):
    """取一段日线（以 end_date 为终点向前 count 根）。返回按日期升序的列表。"""
    end_date = end_date or _today_str()
    count = count or config.MAX_BARS
    raw = _get(_KLINE.format(secid=secid, start="1990-01-01", end=end_date, count=count))
    payload = raw.split("=", 1)[1] if raw.startswith("k=") else raw
    obj = json.loads(payload)
    node = (obj.get("data") or {}).get(secid) or {}
    rows = node.get("qfqday") or node.get("day") or []
    bars = []
    for r in rows:
        try:
            day = r[0]
            close = float(r[2])
            vol = float(r[5]) * 100.0 if len(r) > 5 and r[5] not in ("", None) else 0.0
            amt = float(r[8]) * 10000.0 if len(r) > 8 and r[8] not in ("", None) else 0.0
        except (ValueError, TypeError, IndexError):
            continue
        bars.append((day, close, vol, amt))
    bars.sort(key=lambda x: x[0])
    return bars


def fetch_history(secid, start_date=None):
    """向前翻页取全历史（从 start_date 到最新），自动去重、防死循环。"""
    start_date = start_date or config.START_DATE
    collected = {}
    end = _today_str()
    for _ in range(40):
        chunk = fetch_kline(secid, end_date=end, count=config.MAX_BARS)
        if not chunk:
            break
        for bar in chunk:
            collected[bar[0]] = bar
        earliest = chunk[0][0]
        if earliest <= start_date:
            break
        if len(chunk) < 5:          # 已到上市首日
            break
        prev_end = end
        end = (datetime.strptime(earliest, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        if end >= prev_end:         # 接口未按 end 回退，避免死循环
            break
    bars = [v for k, v in sorted(collected.items()) if k >= start_date]
    return bars


def fetch_universe():
    """沪深 A 股列表（不含北交所）。返回 [{secid, code, name}, ...]"""
    stocks, seen = [], set()
    for page in range(80):
        url = _RANK.format(offset=page * 200, count=200)
        try:
            obj = json.loads(_get(url))
        except Exception:  # noqa: BLE001
            break
        rows = ((obj.get("data") or {}).get("rank_list")) or []
        if not rows:
            break
        for r in rows:
            secid = str(r.get("code") or "").lower()
            name = str(r.get("name") or "")
            if not (secid.startswith(("sh6", "sz0", "sz3"))):
                continue
            if secid in seen:
                continue
            seen.add(secid)
            stocks.append({"secid": secid, "code": secid[2:], "name": name})
        if len(rows) < 200:
            break
    if not stocks:
        # 接口挂了也不能让整个任务失败：退回上次保存的股票列表（可能缺少新上市个股）
        try:
            stocks = json.loads(config.UNIVERSE_FILE.read_text(encoding="utf-8"))
            print(f"!! 股票列表接口异常，改用缓存列表（{len(stocks)} 只）", flush=True)
        except Exception:  # noqa: BLE001
            stocks = []
    return stocks


def latest_trade_date():
    """用上证指数日线确定最近一个交易日。"""
    bars = fetch_kline("sh000001", count=10)
    return bars[-1][0] if bars else None


def fetch_index_history(start_date=None):
    """上证指数日线收盘（用于图表叠加）。"""
    return fetch_history("sh000001", start_date=start_date)
