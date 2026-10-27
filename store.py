# -*- coding: utf-8 -*-
"""聚合、指标计算与本地存储（SQLite + CSV + JSON）"""
import csv
import json
import sqlite3
from datetime import datetime

import config

# ---------------------------------------------------------------- 聚合

BUCKET_KEYS = (
    "up", "down", "flat",
    "up_amt", "down_amt", "flat_amt",
    "up_vol", "down_vol", "flat_vol",
    "limit_up", "limit_down",
)


def empty_bucket():
    return {
        "up": 0, "down": 0, "flat": 0,
        "up_amt": 0.0, "down_amt": 0.0, "flat_amt": 0.0,
        "up_vol": 0.0, "down_vol": 0.0, "flat_vol": 0.0,
        "limit_up": 0, "limit_down": 0,
    }


def limit_pct(secid, name):
    """涨跌停幅度（近似判断）：科创板/创业板 20%，主板 10%，ST 主板 5%。"""
    code = secid[2:]
    growth = code.startswith(("688", "300", "301"))
    is_st = "ST" in (name or "").upper()
    if growth:
        return 0.20
    return 0.05 if is_st else 0.10


def aggregate(records, agg=None):
    """records: 可迭代的 (secid, name, bars)，bars 为 [(date, close, vol, amt), ...]

    逐日统计：上涨/下跌/平盘家数 + 对应成交量、成交额 + 涨跌停家数。
    停牌日（无 K 线）不计入任何一方；上市首日无前收盘不计入。
    """
    agg = agg if agg is not None else {}
    for secid, name, bars in records:
        lim = limit_pct(secid, name)
        prev = None
        for day, close, vol, amt in bars:
            if prev is not None and prev > 0 and close > 0:
                pct = close / prev - 1.0
                b = agg.get(day)
                if b is None:
                    b = agg[day] = empty_bucket()
                if pct > 0:
                    b["up"] += 1
                    b["up_amt"] += amt
                    b["up_vol"] += vol
                elif pct < 0:
                    b["down"] += 1
                    b["down_amt"] += amt
                    b["down_vol"] += vol
                else:
                    b["flat"] += 1
                    b["flat_amt"] += amt
                    b["flat_vol"] += vol
                if pct >= lim - 0.0015:
                    b["limit_up"] += 1
                elif pct <= -lim + 0.0015:
                    b["limit_down"] += 1
            prev = close
    return agg


def indicators(b):
    """由当日统计量派生两个指标。返回 (trin_pct, up_ratio_pct)"""
    trin = None
    if b["down"] > 0 and b["down_amt"] > 0 and b["up_amt"] > 0:
        trin = (b["up"] / b["down"]) / (b["up_amt"] / b["down_amt"]) * 100.0
    total = b["up"] + b["down"] + b["flat"]
    ratio = (b["up"] / total * 100.0) if total else None
    return trin, ratio


# ---------------------------------------------------------------- 存储

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily (
    date TEXT PRIMARY KEY,
    up_cnt INTEGER, down_cnt INTEGER, flat_cnt INTEGER, total_cnt INTEGER,
    up_amt REAL, down_amt REAL, flat_amt REAL,
    up_vol REAL, down_vol REAL, flat_vol REAL,
    limit_up INTEGER, limit_down INTEGER,
    trin_pct REAL, up_ratio REAL,
    idx_close REAL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS index_daily (
    date TEXT PRIMARY KEY, close REAL
);
"""


def connect():
    config.DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB, timeout=30)
    conn.executescript(SCHEMA)
    return conn


def save_buckets(conn, agg, index_close=None, since=None):
    """写入统计结果。since 不为空时先删除该日期（含）之后的数据，实现整段重算。"""
    if since:
        conn.execute("DELETE FROM daily WHERE date >= ?", (since,))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for day in sorted(agg):
        if day < config.START_DATE:
            continue
        b = agg[day]
        trin, ratio = indicators(b)
        total = b["up"] + b["down"] + b["flat"]
        rows.append((
            day, b["up"], b["down"], b["flat"], total,
            b["up_amt"], b["down_amt"], b["flat_amt"],
            b["up_vol"], b["down_vol"], b["flat_vol"],
            b["limit_up"], b["limit_down"],
            trin, ratio,
            (index_close or {}).get(day),
            now,
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
    )
    conn.commit()
    return len(rows)


def save_index(conn, bars):
    conn.executemany(
        "INSERT OR REPLACE INTO index_daily VALUES (?,?)",
        [(d, c) for d, c, _v, _a in bars],
    )
    conn.commit()


def fill_index(conn):
    """把指数收盘价回填到 daily 表（保证导出时能叠加指数）。"""
    conn.execute(
        "UPDATE daily SET idx_close = (SELECT close FROM index_daily i WHERE i.date = daily.date)"
        " WHERE idx_close IS NULL"
    )
    conn.commit()


def read_rows(conn, start=None, end=None):
    sql = "SELECT * FROM daily"
    cond, args = [], []
    if start:
        cond.append("date >= ?")
        args.append(start)
    if end:
        cond.append("date <= ?")
        args.append(end)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY date"
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, args)]


def add_derived(rows):
    """追加均线：TRIN 10 日均值、上涨占比 5 日均值。"""
    trin_hist, ratio_hist = [], []
    for r in rows:
        t, q = r.get("trin_pct"), r.get("up_ratio")
        trin_hist.append(t)
        ratio_hist.append(q)
        valid = [x for x in trin_hist[-10:] if x is not None]
        r["trin_ma10"] = round(sum(valid) / len(valid), 2) if len(valid) >= 5 else None
        valid5 = [x for x in ratio_hist[-5:] if x is not None]
        r["ratio_ma5"] = round(sum(valid5) / len(valid5), 2) if len(valid5) >= 3 else None
    return rows


def export(conn):
    """导出 CSV 与 Web 用 JSON。"""
    rows = add_derived(read_rows(conn))
    cols = [
        "date", "up_cnt", "down_cnt", "flat_cnt", "total_cnt",
        "up_amt", "down_amt", "flat_amt", "limit_up", "limit_down",
        "trin_pct", "up_ratio", "trin_ma10", "ratio_ma5", "idx_close",
    ]

    # CSV（金额单位：亿元）
    with open(config.CSV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow([
            "日期", "上涨家数", "下跌家数", "平盘家数", "总家数",
            "上涨成交额(亿元)", "下跌成交额(亿元)", "平盘成交额(亿元)",
            "涨停家数", "跌停家数",
            "TRIN(%)", "上涨占比(%)", "TRIN_MA10(%)", "上涨占比MA5(%)", "上证指数收盘",
        ])
        for r in rows:
            w.writerow([
                r["date"], r["up_cnt"], r["down_cnt"], r["flat_cnt"], r["total_cnt"],
                f'{r["up_amt"] / 1e8:.2f}', f'{r["down_amt"] / 1e8:.2f}', f'{r["flat_amt"] / 1e8:.2f}',
                r["limit_up"], r["limit_down"],
                "" if r["trin_pct"] is None else f'{r["trin_pct"]:.2f}',
                "" if r["up_ratio"] is None else f'{r["up_ratio"]:.2f}',
                "" if r["trin_ma10"] is None else f'{r["trin_ma10"]:.2f}',
                "" if r["ratio_ma5"] is None else f'{r["ratio_ma5"]:.2f}',
                "" if r["idx_close"] is None else f'{r["idx_close"]:.2f}',
            ])

    # JSON（金额单位：亿元，紧凑数组，减小体积）
    compact = []
    for r in rows:
        compact.append([
            r["date"], r["up_cnt"], r["down_cnt"], r["flat_cnt"], r["total_cnt"],
            round(r["up_amt"] / 1e8, 2), round(r["down_amt"] / 1e8, 2), round(r["flat_amt"] / 1e8, 2),
            None if r["trin_pct"] is None else round(r["trin_pct"], 2),
            None if r["up_ratio"] is None else round(r["up_ratio"], 2),
            None if r["idx_close"] is None else round(r["idx_close"], 2),
            r["limit_up"], r["limit_down"],
            r["trin_ma10"], r["ratio_ma5"],
        ])
    meta = {
        "first": rows[0]["date"] if rows else None,
        "last": rows[-1]["date"] if rows else None,
        "count": len(rows),
        "updated_at": rows[-1]["updated_at"] if rows else None,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(config.SERIES_JSON, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "cols": cols, "rows": compact}, fh, ensure_ascii=False)
    return meta


def write_status(**kw):
    payload = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    payload.update(kw)
    with open(config.STATUS, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)


def save_universe(stocks):
    with open(config.UNIVERSE_FILE, "w", encoding="utf-8") as fh:
        json.dump(stocks, fh, ensure_ascii=False)
