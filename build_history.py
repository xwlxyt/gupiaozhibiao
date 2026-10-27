# -*- coding: utf-8 -*-
"""全量回补：从 2014-01-02 起，逐只个股取日线并聚合出每日涨跌家数/成交额。

支持断点续跑：进度与中间结果保存在 data/stage.json，中断后重跑会跳过已处理个股。
用法：
    python build_history.py            # 全量（首次）
    python build_history.py --limit 50 # 冒烟测试
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import config
import qq
import store

STAGE = config.DATA / "stage.json"


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    config.LOGS.mkdir(parents=True, exist_ok=True)
    with open(config.LOGS / "build.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_stage():
    if STAGE.exists():
        with open(STAGE, encoding="utf-8") as fh:
            obj = json.load(fh)
        log(f"发现断点：已完成 {len(obj.get('done', []))} 只，继续回补")
        return obj.get("done", []), obj.get("agg", {})
    return [], {}


def save_stage(done, agg):
    payload = {"done": done, "agg": agg, "saved_at": datetime.now().isoformat()}
    tmp = STAGE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    tmp.replace(STAGE)


def fetch_one(stock):
    # 多取 20 个自然日，保证 2014-01-02 当天也有"前收盘价"可比
    warmup = (datetime.strptime(config.START_DATE, "%Y-%m-%d")
              - timedelta(days=20)).strftime("%Y-%m-%d")
    try:
        bars = qq.fetch_history(stock["secid"], start_date=warmup)
        return stock, bars, None
    except Exception as exc:  # noqa: BLE001
        return stock, None, str(exc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只（测试用）")
    ap.add_argument("--workers", type=int, default=config.WORKERS)
    args = ap.parse_args()

    t0 = time.time()
    log("=" * 60)
    log("开始拉取沪深 A 股列表…")
    stocks = qq.fetch_universe()
    if not stocks:
        log("!! 未能获取股票列表，退出")
        sys.exit(1)
    store.save_universe(stocks)
    log(f"股票列表：{len(stocks)} 只（沪市 {sum(1 for s in stocks if s['secid'].startswith('sh'))}，"
        f"深市 {sum(1 for s in stocks if s['secid'].startswith('sz'))}）")
    if args.limit:
        stocks = stocks[: args.limit]

    done, agg = load_stage()
    done_set = set(done)
    todo = [s for s in stocks if s["secid"] not in done_set]
    log(f"待处理 {len(todo)} 只，并发 {args.workers}")

    name_map = {s["secid"]: s["name"] for s in stocks}
    failed = []
    ok = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, s): s for s in todo}
        for idx, fut in enumerate(as_completed(futures), 1):
            stock, bars, err = fut.result()
            if err or not bars:
                failed.append({"secid": stock["secid"], "err": err or "空数据"})
            else:
                store.aggregate([(stock["secid"], name_map.get(stock["secid"], ""), bars)], agg)
                done.append(stock["secid"])
                ok += 1
            if idx % 100 == 0 or idx == len(todo):
                save_stage(done, agg)
                rate = idx / max(time.time() - t0, 0.1)
                eta = (len(todo) - idx) / max(rate, 0.01)
                log(f"进度 {idx}/{len(todo)}  成功 {ok}  失败 {len(failed)}  "
                    f"速率 {rate:.0f}/s  预计剩余 {eta / 60:.1f} 分钟")

    if failed:
        log(f"失败明细（前 10 条）：{failed[:10]}")

    log("写入数据库…")
    conn = store.connect()
    n = store.save_buckets(conn, agg, since=config.START_DATE)

    log("拉取上证指数…")
    try:
        idx_bars = qq.fetch_index_history(start_date=config.START_DATE)
        store.save_index(conn, idx_bars)
        store.fill_index(conn)
        log(f"指数 {len(idx_bars)} 条")
    except Exception as exc:  # noqa: BLE001
        log(f"指数拉取失败（不影响指标）：{exc}")

    meta = store.export(conn)
    conn.close()
    if STAGE.exists():
        STAGE.unlink()
    log(f"完成：写入 {n} 个交易日，区间 {meta['first']} ~ {meta['last']}，"
        f"耗时 {(time.time() - t0) / 60:.1f} 分钟")
    store.write_status(state="ok", mode="build", rows=n, **meta)


if __name__ == "__main__":
    main()
