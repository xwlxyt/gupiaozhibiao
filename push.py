# -*- coding: utf-8 -*-
"""多通道推送：Bark（iPhone）、Server酱 / PushPlus（微信）。

配置优先级：环境变量 > data/push.json

环境变量（GitHub Actions 里用 Secrets 注入）
    BARK_KEY          Bark 的 key，即 https://api.day.app/<key> 中的 key
    BARK_URL          完整推送地址（自建 Bark 服务器时用，默认 https://api.day.app）
    SERVERCHAN_KEY    Server酱³ 的 SendKey（SCT 开头）
    PUSHPLUS_TOKEN    PushPlus 的 token

data/push.json（本机跑时更方便）
    {"bark_key": "...", "serverchan_key": "...", "pushplus_token": "..."}

用法
    python push.py --test          # 发一条测试消息，验证配置
    python push.py                 # 推送当日简报
"""
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import config

UA = {"User-Agent": "Mozilla/5.0 (AStockBreadth / push)"}
CONF_FILE = config.DATA / "push.json"


def load_conf():
    conf = {}
    if CONF_FILE.exists():
        try:
            conf = json.loads(CONF_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            conf = {}
    return {
        "bark_key": os.environ.get("BARK_KEY") or conf.get("bark_key") or "",
        "bark_url": (os.environ.get("BARK_URL") or conf.get("bark_url")
                     or "https://api.day.app").rstrip("/"),
        "serverchan_key": os.environ.get("SERVERCHAN_KEY") or conf.get("serverchan_key") or "",
        "pushplus_token": os.environ.get("PUSHPLUS_TOKEN") or conf.get("pushplus_token") or "",
    }


def _post_json(url, payload, timeout=15):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def _post_form(url, fields, timeout=15):
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={**UA,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


# ---------------------------------------------------------------- 各通道
def send_bark(title, body, conf, subtitle=""):
    key = conf["bark_key"]
    if not key:
        return None, "未配置 BARK_KEY"
    payload = {"device_key": key, "title": title, "body": body,
               "group": "A股宽度", "icon": "", "level": "active",
               "autoCopy": "0", "call": "0", "isArchive": "1"}
    if subtitle:
        payload["subtitle"] = subtitle
    try:
        raw = _post_json(conf["bark_url"] + "/push", payload)
        js = json.loads(raw)
        if js.get("code") == 200:
            return True, "ok"
        return False, f"Bark 返回 {js.get('code')} {js.get('message')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Bark 异常：{exc}"


def send_serverchan(title, body, conf):
    key = conf["serverchan_key"]
    if not key:
        return None, "未配置 SERVERCHAN_KEY"
    url = f"https://sctapi.ftqq.com/{key}.send"
    try:
        raw = _post_form(url, {"title": title[:60], "desp": body})
        js = json.loads(raw)
        if js.get("code") == 0:
            return True, "ok"
        return False, f"Server酱返回 {js.get('code')} {js.get('message')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Server酱异常：{exc}"


def send_pushplus(title, body, conf):
    token = conf["pushplus_token"]
    if not token:
        return None, "未配置 PUSHPLUS_TOKEN"
    try:
        raw = _post_json("https://www.pushplus.plus/send",
                         {"token": token, "title": title, "content": body, "template": "markdown"})
        js = json.loads(raw)
        if js.get("code") == 200:
            return True, "ok"
        return False, f"PushPlus 返回 {js.get('code')} {js.get('msg')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"PushPlus 异常：{exc}"


CHANNELS = (
    ("Bark", send_bark),
    ("Server酱", send_serverchan),
    ("PushPlus", send_pushplus),
)


def push_all(title, body, subtitle=""):
    """向所有已配置的通道推送，返回 [(通道, 是否成功, 说明)]。"""
    conf = load_conf()
    results = []
    for name, fn in CHANNELS:
        if name == "Bark":
            ok, msg = fn(title, body, conf, subtitle=subtitle)
        else:
            ok, msg = fn(title, body, conf)
        if ok is None:            # 没配置就跳过，不算失败
            continue
        results.append((name, ok, msg))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="发送测试消息")
    args = ap.parse_args()

    if args.test:
        title = "A股宽度 · 推送测试"
        body = "如果你看到这条消息，说明推送通道已打通。每个交易日收盘后会收到当日指标。"
    else:
        import notify
        payload, err = notify.build(None)
        if err:
            print(err)
            raise SystemExit(1)
        title = payload["subject"]
        body = payload["text"]

    conf = load_conf()
    configured = [k for k in ("bark_key", "serverchan_key", "pushplus_token") if conf.get(k)]
    if not configured:
        print("!! 没有配置任何推送通道。请设置环境变量 BARK_KEY / SERVERCHAN_KEY / PUSHPLUS_TOKEN，"
              f"或创建 {CONF_FILE}")
        raise SystemExit(2)

    results = push_all(title, body)
    if not results:
        print("!! 配置里的通道名无法识别")
        raise SystemExit(2)
    all_ok = True
    for name, ok, msg in results:
        print(f"{'✅' if ok else '❌'} {name}: {msg}")
        all_ok = all_ok and ok
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
