# -*- coding: utf-8 -*-
"""增量更新：每个交易日收盘后运行，把最新一天（以及最近若干天）补进数据库。

特点：重叠回看 + 整段重算，所以即使某天漏跑，下次运行会自动补上（自愈）。
用法：
    python update_daily.py                # 日常增量（回看约 25 个交易日）
    python update_daily.py --since 2025-01-01   # 重算指定日期之后
    python update_daily.py --force        # 即使已是最新也重算
"""
import argparse
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import config
import qq
import store


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    config.LOGS.mkdir(parents=True, exist_ok=True)
    with open(config.LOGS / "update.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def fetch_tail(stock, count, bust=False):
    try:
        return stock, qq.fetch_kline(stock["secid"], count=count, bust=bust), None
    except Exception as exc:  # noqa: BLE001
        return stock, None, str(exc)


def bucket_from_row(r):
    """把库里的一行还原成统计桶，用于异常时保留旧值。"""
    return {
        "up": r["up_cnt"] or 0, "down": r["down_cnt"] or 0, "flat": r["flat_cnt"] or 0,
        "up_amt": r["up_amt"] or 0.0, "down_amt": r["down_amt"] or 0.0, "flat_amt": r["flat_amt"] or 0.0,
        "up_vol": r["up_vol"] or 0.0, "down_vol": r["down_vol"] or 0.0, "flat_vol": r["flat_vol"] or 0.0,
        "limit_up": r["limit_up"] or 0, "limit_down": r["limit_down"] or 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="重算该日期之后的数据")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=config.WORKERS)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    conn = store.connect()
    existing = store.read_rows(conn)
    last_saved = existing[-1]["date"] if existing else None

    trade_date = qq.latest_trade_date()
    if not trade_date:
        log("!! 无法获取最近交易日，退出")
        sys.exit(1)

    if last_saved and last_saved >= trade_date and not args.since and not args.force:
        log(f"数据已是最新（{last_saved}），无需更新")
        conn.close()
        return

    if args.since:
        days = (datetime.strptime(trade_date, "%Y-%m-%d")
                - datetime.strptime(args.since, "%Y-%m-%d")).days
        count = min(config.MAX_BARS, max(config.TAIL_BARS, math.ceil(days * 0.72) + 40))
        cutoff = args.since
    else:
        count = config.TAIL_BARS
        cutoff = None

    log(f"目标交易日 {trade_date}，回看 {count} 根，并发 {args.workers}")
    stocks = qq.fetch_universe()
    if not stocks:
        log("!! 股票列表获取失败，退出")
        sys.exit(1)
    store.save_universe(stocks)
    name_map = {s["secid"]: s["name"] for s in stocks}
    log(f"股票列表 {len(stocks)} 只")

    agg = {}
    bars_map = {}       # secid -> bars；先全部收下，最后统一聚合，补抓时可直接覆盖
    failed = []
    last_bar = {}       # secid -> 该股最后一根 K 线的日期
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(fetch_tail, s, count) for s in stocks]
        for fut in as_completed(futures):
            stock, bars, err = fut.result()
            if err or not bars:
                failed.append(stock["secid"])
                continue
            bars_map[stock["secid"]] = bars
            last_bar[stock["secid"]] = bars[-1][0]

    if not bars_map:
        log("!! 未取到任何数据")
        sys.exit(1)

    # ---- 新鲜度校验：有多少只真的更新到了目标交易日 ----
    # 停牌股本来就没有当日 K 线，属于正常口径；
    # 但如果是大面积缺失，说明数据源返回了缓存旧值（境外节点尤其容易命中），必须拦截。
    stale = [s for s in stocks
             if s["secid"] in bars_map and last_bar.get(s["secid"]) != trade_date]
    ratio = len(stale) / max(1, len(stocks))
    log(f"{trade_date} 有数据 {len(bars_map) - len(stale)} 只 / 抓取成功 {len(bars_map)} 只"
        f"（未更新到当日 {len(stale)} 只，占 {ratio:.1%}）")

    if ratio > config.STALE_RATIO_MAX:
        log(f"!! {ratio:.1%} 的个股没有 {trade_date} 的 K 线，疑似数据源返回缓存旧值，开始补抓…")
        fixed = 0
        with ThreadPoolExecutor(max_workers=config.RETRY_WORKERS) as pool:
            futs = [pool.submit(fetch_tail, s, count, True) for s in stale]
            for fut in as_completed(futs):
                stock, bars, err = fut.result()
                if err or not bars or bars[-1][0] != trade_date:
                    continue
                bars_map[stock["secid"]] = bars
                last_bar[stock["secid"]] = bars[-1][0]
                fixed += 1
        ratio = (len(stale) - fixed) / max(1, len(stocks))
        log(f"补抓完成：{fixed} 只已更新到当日，仍缺 {len(stale) - fixed} 只（占 {ratio:.1%}）")

    if ratio > config.STALE_RATIO_MAX:
        log(f"!! 补抓后仍有 {ratio:.1%} 的个股缺少 {trade_date} 数据，本次抓取不完整，"
            f"放弃写入以免污染数据（库里保留上一次的正确值），请稍后重跑")
        sys.exit(1)

    # 统一聚合：bars_map 已是补抓后的最终结果，不会重复累加
    for secid, bars in bars_map.items():
        store.aggregate([(secid, name_map.get(secid, ""), bars)], agg)
    done = len(bars_map)

    if not agg:
        log("!! 未取到任何数据")
        sys.exit(1)

    if cutoff is None:
        # 用重叠窗口里第 5 个日期作为重算起点，避开"窗口首日缺前收盘"的失真
        window = sorted(agg)
        idx = min(4, max(0, len(window) - 1))
        cutoff = window[idx]
    cutoff = max(cutoff, config.START_DATE)

    # 只保留 cutoff 及之后的数据：窗口前几天的统计不完整，绝不能覆盖库里的历史值
    agg = {d: v for d, v in agg.items() if d >= cutoff}

    # 安全阀：若某天样本家数明显低于参照值（说明抓取大面积失败），不采信当天数据
    # 参照值优先用库里该日自己的值；库里没有这一天（全新日期）则用最近一个有效交易日，
    # —— 否则新日期永远没有参照，残缺数据会直接写进去（2026-10-30 就这么写坏过）
    old_rows = {r["date"]: r for r in existing}
    ref_total = None
    for r in reversed(existing):
        if r["total_cnt"]:
            ref_total = r["total_cnt"]
            break

    restored, dropped = [], []
    for d in sorted(list(agg)):
        old = old_rows.get(d)
        t = agg[d]["up"] + agg[d]["down"] + agg[d]["flat"]
        ref = (old["total_cnt"] if old and old["total_cnt"] else ref_total)
        if ref and t < ref * 0.92:
            if old:
                agg[d] = bucket_from_row(old)
                restored.append(d)
            else:
                agg.pop(d, None)
                dropped.append((d, t, ref))
    if restored:
        log(f"!! 以下日期样本异常偏少，已保留原值：{restored[:8]}")
    for d, t, ref in dropped:
        log(f"!! {d} 样本仅 {t} 只（参照 {ref} 只），已丢弃")
    if any(d == trade_date for d, _, _ in dropped):
        log("!! 目标交易日样本残缺，本次不写库、不推送；稍后重跑会自动补齐")
        sys.exit(1)

    n = store.save_buckets(conn, agg, since=cutoff)

    try:
        idx_bars = qq.fetch_kline("sh000001", count=max(count, 60))
        store.save_index(conn, idx_bars)
        store.fill_index(conn)
    except Exception as exc:  # noqa: BLE001
        log(f"指数拉取失败（不影响指标）：{exc}")

    meta = store.export(conn)
    latest_rows = store.read_rows(conn, start=meta["last"], end=meta["last"])
    conn.close()

    latest = latest_rows[-1] if latest_rows else {}
    trin = latest.get("trin_pct")
    ratio = latest.get("up_ratio")
    msg = (f"更新完成：重算 {cutoff} 之后共 {n} 个交易日，成功 {done} 只 / 失败 {len(failed)} 只，"
           f"最新 {meta['last']} TRIN={'-' if trin is None else f'{trin:.2f}%'} "
           f"上涨占比={'-' if ratio is None else f'{ratio:.2f}%'} "
           f"（涨 {latest.get('up_cnt')} / 跌 {latest.get('down_cnt')} / 平 {latest.get('flat_cnt')}），"
           f"耗时 {time.time() - t0:.0f}s")
    log(msg)
    store.write_status(state="ok", mode="update", cutoff=cutoff,
                       failed=len(failed), **meta)

    if not args.quiet:
        print("\n" + msg)


if __name__ == "__main__":
    main()
