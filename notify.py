# -*- coding: utf-8 -*-
"""生成"当日指标简报"，供每日推送使用（邮件/消息/终端）。

用法：
    python notify.py                # 最新交易日
    python notify.py --date 2026-10-23
"""
import argparse
import json
from datetime import datetime

import config
import store


def pct_rank(rows, key, value):
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals or value is None:
        return None
    return round(sum(1 for v in vals if v <= value) / len(vals) * 100, 1)


def verdict(trin, ratio):
    """把两个指标放在一起解读（单看一个容易误判）。"""
    if trin is None or ratio is None:
        return "数据不足，暂无法判断。"
    if ratio >= 80:
        breadth = "市场普涨"
    elif ratio >= 55:
        breadth = "多数个股上涨"
    elif ratio >= 45:
        breadth = "多空大致均衡"
    elif ratio >= 20:
        breadth = "多数个股下跌"
    else:
        breadth = "市场普跌"

    if trin >= 300:
        state = "TRIN 极高，上涨股家数远超其成交额占比"
    elif trin >= 150:
        state = "TRIN 偏高，上涨缺少量能确认"
    elif trin >= 100:
        state = "TRIN 略高于100%"
    elif trin >= 70:
        state = "TRIN 处于70%~100%的均衡区"
    elif trin >= 40:
        state = "TRIN 偏低，成交额更多流向上涨股"
    else:
        state = "TRIN 极低（下跌股放量或上涨股量能枯竭）"

    if ratio < 20 and trin < 40:
        tail = "普跌叠加下跌股放量，抛压仍在释放；若后续量能萎缩，往往对应短期情绪冰点"
    elif ratio < 20 and trin >= 100:
        tail = "普跌但下跌股成交额占比不高，多为跌停锁仓所致，关注能否缩量止跌"
    elif ratio > 80 and trin < 70:
        tail = "普涨且量能集中在上涨股，多头结构相对健康"
    elif ratio > 80 and trin >= 150:
        tail = "普涨但上涨股量能占比偏低，涨势缺少确认，留意冲高回落"
    elif 40 <= ratio <= 60 and 70 <= trin <= 120:
        tail = "家数与量能都比较均衡，市场偏震荡"
    else:
        tail = "家数与量能出现一定背离，建议结合指数位置和后续量能变化观察"
    return f"{breadth}，{state}；{tail}。"


def build(date=None):
    conn = store.connect()
    rows = store.add_derived(store.read_rows(conn))
    conn.close()
    if not rows:
        return None, "数据库为空，请先运行 build_history.py"
    if date:
        rows = [r for r in rows if r["date"] <= date]
        if not rows:
            return None, f"没有 {date} 及之前的数据"
    cur = rows[-1]
    prev = rows[-2] if len(rows) > 1 else None

    trin_rank = pct_rank(rows, "trin_pct", cur["trin_pct"])
    ratio_rank = pct_rank(rows, "up_ratio", cur["up_ratio"])
    idx_chg = None
    if prev and prev.get("idx_close") and cur.get("idx_close"):
        idx_chg = (cur["idx_close"] / prev["idx_close"] - 1) * 100

    amt = (cur["up_amt"] + cur["down_amt"] + cur["flat_amt"]) / 1e8
    text = f"""【A股市场宽度】{cur['date']}

TRIN：{'—' if cur['trin_pct'] is None else f"{cur['trin_pct']:.2f}%"}（10日均 {'—' if cur['trin_ma10'] is None else f"{cur['trin_ma10']:.2f}%"}，历史分位 {trin_rank}%）
上涨占比：{'—' if cur['up_ratio'] is None else f"{cur['up_ratio']:.2f}%"}（历史分位 {ratio_rank}%）
涨跌家数：上涨 {cur['up_cnt']} / 下跌 {cur['down_cnt']} / 平盘 {cur['flat_cnt']}（共 {cur['total_cnt']} 只）
涨跌停：涨停 {cur['limit_up']} / 跌停 {cur['limit_down']}
成交额：上涨股 {cur['up_amt'] / 1e8:.1f} 亿 / 下跌股 {cur['down_amt'] / 1e8:.1f} 亿，两市合计 {amt:.1f} 亿
上证指数：{'—' if cur['idx_close'] is None else f"{cur['idx_close']:.2f}"}{'' if idx_chg is None else f"（{idx_chg:+.2f}%）"}

解读：{verdict(cur['trin_pct'], cur['up_ratio'])}
（口径：沪深两市 A 股，剔除停牌与新股首日；TRIN =（涨家数/跌家数）÷（涨成交额/跌成交额）×100%）"""

    html = f"""<div style="font-family:system-ui,'Microsoft YaHei',sans-serif;max-width:620px">
<h3 style="margin:0 0 4px">A股市场宽度 · {cur['date']}</h3>
<table cellpadding="7" style="border-collapse:collapse;font-size:14px;width:100%">
<tr style="background:#fafbfc"><td>TRIN</td><td style="text-align:right;font-weight:600">{'—' if cur['trin_pct'] is None else f"{cur['trin_pct']:.2f}%"}</td>
<td style="color:#6b7280">10日均 {'—' if cur['trin_ma10'] is None else f"{cur['trin_ma10']:.2f}%"} · 分位 {trin_rank}%</td></tr>
<tr><td>上涨占比</td><td style="text-align:right;font-weight:600;color:{'#d93a3a' if (cur['up_ratio'] or 0) >= 50 else '#159a6b'}">{'—' if cur['up_ratio'] is None else f"{cur['up_ratio']:.2f}%"}</td>
<td style="color:#6b7280">历史分位 {ratio_rank}%</td></tr>
<tr style="background:#fafbfc"><td>涨跌家数</td><td style="text-align:right"><span style="color:#d93a3a">{cur['up_cnt']} 涨</span> / <span style="color:#159a6b">{cur['down_cnt']} 跌</span> / {cur['flat_cnt']} 平</td>
<td style="color:#6b7280">涨停 {cur['limit_up']} · 跌停 {cur['limit_down']}</td></tr>
<tr><td>成交额</td><td style="text-align:right">{cur['up_amt'] / 1e8:.1f} / {cur['down_amt'] / 1e8:.1f} 亿</td>
<td style="color:#6b7280">两市 {amt:.1f} 亿</td></tr>
<tr style="background:#fafbfc"><td>上证指数</td><td style="text-align:right;font-weight:600">{'—' if cur['idx_close'] is None else f"{cur['idx_close']:.2f}"}</td>
<td style="color:{'#d93a3a' if (idx_chg or 0) >= 0 else '#159a6b'}">{'' if idx_chg is None else f"{idx_chg:+.2f}%"}</td></tr>
</table>
<p style="color:#444;line-height:1.7;font-size:13.5px;margin-top:12px">解读：{verdict(cur['trin_pct'], cur['up_ratio'])}</p>
<p style="color:#9aa0a6;font-size:12px">口径：沪深两市 A 股，剔除当日停牌与新股上市首日；TRIN =（上涨家数/下跌家数）÷（上涨成交额/下跌成交额）×100%。仅作研究参考。</p>
</div>"""

    trin_txt = "—" if cur["trin_pct"] is None else f"{cur['trin_pct']:.2f}%"
    ratio_txt = "—" if cur["up_ratio"] is None else f"{cur['up_ratio']:.2f}%"
    subject = (f"[A股宽度] {cur['date']} TRIN {trin_txt} · 上涨占比 {ratio_txt}"
               f" · 涨{cur['up_cnt']}跌{cur['down_cnt']}")
    return {"date": cur["date"], "text": text, "html": html, "subject": subject,
            "row": cur, "trin_rank": trin_rank, "ratio_rank": ratio_rank,
            "trin_txt": trin_txt, "ratio_txt": ratio_txt}, None


def desktop_toast(title, message):
    """Windows 桌面通知（尽力而为，失败不影响主流程）。"""
    import subprocess
    import sys
    if not sys.platform.startswith("win"):
        return False
    safe = lambda s: s.replace('"', "'").replace("\n", " ")[:180]  # noqa: E731
    script = f'''
$ErrorActionPreference='SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] > $null
$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$txt = $tpl.GetElementsByTagName('text')
$txt.Item(0).AppendChild($tpl.CreateTextNode("{safe(title)}")) > $null
$txt.Item(1).AppendChild($tpl.CreateTextNode("{safe(message)}")) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("A股市场宽度").Show($toast)
'''
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       timeout=25, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:  # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--json", action="store_true", help="输出 JSON（供程序读取）")
    ap.add_argument("--notify", action="store_true", help="同时弹 Windows 桌面通知")
    args = ap.parse_args()
    payload, err = build(args.date)
    if err:
        print(err)
        raise SystemExit(1)
    with open(config.DATA / "latest_summary.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    if args.notify:
        r = payload["row"]
        desktop_toast(
            f"A股宽度 {r['date']}　TRIN {payload['trin_txt']}",
            f"上涨占比 {payload['ratio_txt']}　涨 {r['up_cnt']} / 跌 {r['down_cnt']}"
            + (f"　上证 {r['idx_close']:.2f}" if r.get("idx_close") else ""),
        )
    if args.json:
        print(json.dumps({k: v for k, v in payload.items() if k != "row"}, ensure_ascii=False))
    else:
        print(payload["text"])


if __name__ == "__main__":
    main()
