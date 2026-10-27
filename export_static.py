# -*- coding: utf-8 -*-
"""导出静态版看板（放到 docs/，可直接用 GitHub Pages 托管，手机随时打开）。

生成内容：
    docs/index.html            与本地看板同一份页面（会自动切换到静态数据模式）
    docs/vendor/echarts.min.js 图表库（离线可用）
    docs/data/series.json      全量序列（页面直接读取）
    docs/data/daily.csv        明细表下载

用法：
    python export_static.py            # 生成/更新 docs/
"""
import json
import shutil

import config
import server
import store


def build():
    out = config.BASE / "docs"
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (out / "vendor").mkdir(parents=True, exist_ok=True)

    # 页面与图表库
    shutil.copy2(config.WEB / "index.html", out / "index.html")
    shutil.copy2(config.WEB / "vendor" / "echarts.min.js", out / "vendor" / "echarts.min.js")

    # 序列数据（Web 字段名，页面直接消费，无需再转换）
    raw = json.loads(config.SERIES_JSON.read_text(encoding="utf-8"))
    rows = [dict(zip(server.COLS, r)) for r in raw["rows"]]
    payload = {"ok": True, "meta": raw["meta"], "cols": server.COLS, "rows": rows}
    (data_dir / "series.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 明细 CSV
    if config.CSV.exists():
        shutil.copy2(config.CSV, data_dir / "daily.csv")

    # GitHub Pages 默认走 Jekyll，加这个文件避免多余处理
    (out / ".nojekyll").write_text("", encoding="utf-8")

    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"✅ 静态看板已生成：{out}")
    print(f"   数据区间 {raw['meta'].get('first')} ~ {raw['meta'].get('last')}，"
          f"{len(rows)} 个交易日，共 {size / 1024 / 1024:.1f} MB")
    return out


if __name__ == "__main__":
    build()
