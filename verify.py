# -*- coding: utf-8 -*-
"""数据体检：检查区间完整性、指标合理性与几个已知关键交易日。

用法： python verify.py
"""
import sqlite3

import config
import store


def main():
    conn = store.connect()
    rows = store.add_derived(store.read_rows(conn))
    conn.close()
    if not rows:
        print("数据库为空")
        return

    print(f"区间：{rows[0]['date']} ~ {rows[-1]['date']}　共 {len(rows)} 个交易日")
    bad = [r["date"] for r in rows if not r["total_cnt"] or r["total_cnt"] < 100]
    print(f"家数异常(<100)的日期：{len(bad)} 个 {bad[:5]}")
    miss = [r["date"] for r in rows if r["trin_pct"] is None]
    print(f"TRIN 缺失的日期：{len(miss)} 个 {miss[:5]}")
    idx_miss = [r["date"] for r in rows if r["idx_close"] is None]
    print(f"缺上证指数的日期：{len(idx_miss)} 个 {idx_miss[:5]}")

    trins = [r["trin_pct"] for r in rows if r["trin_pct"] is not None]
    ratios = [r["up_ratio"] for r in rows if r["up_ratio"] is not None]
    print(f"TRIN 分布：最小 {min(trins):.1f}% / 中位 {sorted(trins)[len(trins)//2]:.1f}% / 最大 {max(trins):.1f}%")
    print(f"上涨占比分布：最小 {min(ratios):.1f}% / 中位 {sorted(ratios)[len(ratios)//2]:.1f}% / 最大 {max(ratios):.1f}%")

    print("\n样本抽查（关键交易日）：")
    watch = ["2014-01-02", "2015-06-26", "2015-07-08", "2016-01-04", "2018-10-19",
             "2019-02-25", "2020-02-03", "2024-02-05", "2024-09-30", rows[-1]["date"]]
    index = {r["date"]: r for r in rows}
    for d in watch:
        r = index.get(d)
        if not r:
            print(f"  {d}  无数据")
            continue
        print(f"  {d}  涨{r['up_cnt']:>4} 跌{r['down_cnt']:>4} 平{r['flat_cnt']:>3} 共{r['total_cnt']:>4}"
              f"  TRIN {r['trin_pct'] if r['trin_pct'] is None else round(r['trin_pct'], 1)}%"
              f"  上涨占比 {round(r['up_ratio'], 1)}%  指数 {r['idx_close']}")

    # 最近 10 个交易日
    print("\n最近 10 个交易日：")
    for r in rows[-10:]:
        print(f"  {r['date']}  TRIN {r['trin_pct']:.2f}%  上涨占比 {r['up_ratio']:.2f}%"
              f"  涨{r['up_cnt']}/跌{r['down_cnt']}/平{r['flat_cnt']}  指数 {r['idx_close']}")


if __name__ == "__main__":
    main()
