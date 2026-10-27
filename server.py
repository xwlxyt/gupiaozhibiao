# -*- coding: utf-8 -*-
"""本地 Web 服务：提供指标数据 API + 静态页面（标准库实现，无第三方依赖）

启动： python server.py
访问： http://127.0.0.1:8730
"""
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import config

COLS = [
    "date", "up", "down", "flat", "total",
    "up_amt", "down_amt", "flat_amt",
    "trin", "ratio", "idx", "lu", "ld", "trin_ma10", "ratio_ma5",
]

_cache = {"mtime": None, "data": None}
_lock = threading.Lock()
_refreshing = {"running": False, "started_at": None, "log": ""}


def load_series():
    """按文件修改时间缓存，更新数据后自动生效。"""
    path = config.SERIES_JSON
    if not path.exists():
        return {"meta": {}, "rows": []}
    mtime = path.stat().st_mtime
    if _cache["mtime"] != mtime:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        rows = [dict(zip(COLS, r)) for r in raw["rows"]]
        _cache["data"] = {"meta": raw["meta"], "rows": rows}
        _cache["mtime"] = mtime
    return _cache["data"]


def percentile(values, x):
    vals = [v for v in values if v is not None]
    if not vals or x is None:
        return None
    return round(sum(1 for v in vals if v <= x) / len(vals) * 100, 1)


class Handler(SimpleHTTPRequestHandler):
    server_version = "AStockBreadth/1.0"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(config.WEB), **kw)

    # ---------------------------------------------------------- helpers
    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 精简日志
        if "/api/" in (self.path or ""):
            sys.stderr.write("[api] %s\n" % (fmt % args))

    # ---------------------------------------------------------- routes
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        route = parsed.path

        if route in ("/", "/index.html"):
            # 页面文件必须每次取最新的，避免改动后浏览器还在用旧缓存
            html = (config.WEB / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(html)
            return

        if route == "/api/meta":
            data = load_series()
            rows = data["rows"]
            latest = rows[-1] if rows else None
            status = {}
            if config.STATUS.exists():
                try:
                    status = json.loads(Path(config.STATUS).read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    status = {}
            return self._json({
                "ok": True,
                "meta": data["meta"],
                "latest": latest,
                "universe_total": latest["total"] if latest else 0,
                "refreshing": _refreshing["running"],
                "status": status,
            })

        if route == "/api/series":
            data = load_series()
            rows = data["rows"]
            start = (qs.get("start") or [None])[0]
            end = (qs.get("end") or [None])[0]
            if start:
                rows = [r for r in rows if r["date"] >= start]
            if end:
                rows = [r for r in rows if r["date"] <= end]
            return self._json({"ok": True, "cols": COLS, "rows": rows,
                               "meta": data["meta"], "count": len(rows)})

        if route == "/api/day":
            data = load_series()
            rows = data["rows"]
            day = (qs.get("date") or [""])[0]
            idx = next((i for i, r in enumerate(rows) if r["date"] == day), None)
            if idx is None:
                return self._json({"ok": False, "error": f"没有 {day} 的数据（非交易日或超出范围）"}, 404)
            row = rows[idx]
            trin_vals = [r["trin"] for r in rows]
            ratio_vals = [r["ratio"] for r in rows]
            prev = rows[idx - 1] if idx > 0 else None
            around = rows[max(0, idx - 5): idx + 6]
            return self._json({
                "ok": True,
                "row": row,
                "prev": prev,
                "rank": {
                    "trin_pct": percentile(trin_vals, row["trin"]),
                    "ratio_pct": percentile(ratio_vals, row["ratio"]),
                    "samples": len(trin_vals),
                },
                "around": around,
            })

        if route == "/api/status":
            payload = {}
            if config.STATUS.exists():
                try:
                    payload = json.loads(Path(config.STATUS).read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    payload = {}
            payload["refreshing"] = _refreshing["running"]
            return self._json({"ok": True, **payload})

        if route.startswith("/api/"):
            return self._json({"ok": False, "error": "not found"}, 404)

        # 其余路径走静态文件（web/ 目录）
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path == "/api/refresh":
            with _lock:
                if _refreshing["running"]:
                    return self._json({"ok": False, "error": "正在更新中，请稍候"}, 429)
                _refreshing["running"] = True
                threading.Thread(target=self._run_update, daemon=True).start()
            return self._json({"ok": True, "message": "已开始更新"})
        return self._json({"ok": False, "error": "not found"}, 404)

    def _run_update(self):
        try:
            config.LOGS.mkdir(parents=True, exist_ok=True)
            with open(config.LOGS / "manual_refresh.log", "w", encoding="utf-8") as fh:
                subprocess.run(
                    [sys.executable, str(config.BASE / "update_daily.py")],
                    cwd=str(config.BASE), stdout=fh, stderr=subprocess.STDOUT, timeout=1800,
                )
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[refresh] failed: {exc}\n")
        finally:
            _refreshing["running"] = False


def main():
    if not config.SERIES_JSON.exists():
        print("!! 尚未生成数据，请先运行 python build_history.py")
    httpd = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    url = f"http://{config.HOST}:{config.PORT}/"
    print(f"A股市场宽度看板已启动： {url}    (Ctrl+C 停止)")
    if os.environ.get("OPEN_BROWSER", "1") == "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
