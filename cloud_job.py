# -*- coding: utf-8 -*-
"""云端每日任务（GitHub Actions / 云函数入口）。

流程：更新数据 → 生成当日简报 → 推送到手机 → 写运行摘要。

- 非交易日或数据已是最新时自动跳过推送（省消息、省额度），退出码仍为 0；
- 更新失败时退出码 1，Actions 页面会标红，方便发现抓取异常。

用法：
    python cloud_job.py            # 正常每日任务
    python cloud_job.py --force    # 即使已最新也推送一次
"""
import json
import os
import sys
import time

import config
import store
import update_daily


def latest_date():
    try:
        conn = store.connect()
        try:
            rows = store.read_rows(conn)
        finally:
            conn.close()
        return rows[-1]["date"] if rows else None
    except Exception:  # noqa: BLE001
        return None


def write_summary(text):
    """GitHub Actions 运行页展示；本地运行时忽略。"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text.replace("\n", "  \n") + "\n")
    except Exception:  # noqa: BLE001
        pass


def record(before, after, changed, skipped, results, line, seconds):
    """把每次运行的结果落到 data/last_run.json，便于事后排查推送为什么没到。"""
    from datetime import datetime
    rec = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latest_before": before,
        "latest_after": after,
        "changed": changed,
        "skipped": skipped,
        "push_results": [{"channel": n, "ok": bool(ok), "msg": m} for n, ok, m in results],
        "push_line": line,
        "seconds": round(seconds),
    }
    try:
        with open(config.DATA / "last_run.json", "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass


def main():
    force = "--force" in sys.argv
    t0 = time.time()
    before = latest_date()

    # 抓取并入库（update_daily 自己处理"已是最新"的情况）
    saved_argv = sys.argv[:]
    sys.argv = ["update_daily.py", "--quiet"]
    try:
        update_daily.main()
    except SystemExit as exc:     # update_daily 失败时会 sys.exit(1)
        if exc.code:
            msg = f"❌ 数据更新失败（退出码 {exc.code}），请查看 logs/update.log"
            print(msg)
            write_summary(msg)
            raise
    except Exception as exc:  # noqa: BLE001
        msg = f"❌ 数据更新异常：{exc}"
        print(msg)
        write_summary(msg)
        raise
    finally:
        sys.argv = saved_argv

    after = latest_date()
    changed = bool(after) and after != before

    if not changed and not force:
        msg = f"⏭ 今日无需更新（最新交易日 {after}），未推送"
        print(msg)
        write_summary(msg)
        record(before, after, changed, True, [], msg, time.time() - t0)
        return

    import notify
    import push

    payload, err = notify.build(None)
    if err:
        msg = f"❌ 简报生成失败：{err}"
        print(msg)
        write_summary(msg)
        raise SystemExit(1)

    subject, text = payload["subject"], payload["text"]
    print(text)

    results = push.push_all(subject, text)
    if not results:
        line = "⚠️ 未配置推送通道（BARK_KEY / SERVERCHAN_KEY / PUSHPLUS_TOKEN），仅完成数据更新"
    else:
        line = "　".join(f"{'✅' if ok else '❌'} {name}" + ("" if ok else f"（{m}）")
                         for name, ok, m in results)
    print(line)
    record(before, after, changed, False, results, line, time.time() - t0)
    write_summary(f"### {subject}\n\n{text}\n\n**推送**：{line}\n\n耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
