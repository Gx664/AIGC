"""AIGC 后台数据链路自检：发送测试事件 -> 等待入库 -> 看板同款查询确认。

只依赖 Python 标准库。需要本地存在（均不入库）：
  - posthog_config.json          （上报用 Project API Key，phc_）
  - tools/dashboard_config.json  （查询用 Personal API Key，phx_ + project_id）
"""

import json
import os
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(TOOLS_DIR)
QUERY_HOST = "https://us.posthog.com"
# 上报地址：官方推荐 us.i.posthog.com（专用采集端点），us.posthog.com 也可用。
# 两个都试一遍并自动重试，兼容网络抖动 / 部分地区拦截。
SEND_HOSTS = ["https://us.posthog.com", "https://us.i.posthog.com"]
RESULT_FILE = os.path.join(TOOLS_DIR, "test_telemetry_result.txt")


def load_json(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


phc_cfg = load_json(os.path.join(BASE, "posthog_config.json"))
phx_cfg = load_json(os.path.join(TOOLS_DIR, "dashboard_config.json"))
PHC = phc_cfg.get("api_key", "")
PHX = phx_cfg.get("posthog", {}).get("personal_api_key", "")
PID = phx_cfg.get("posthog", {}).get("project_id", 0)
MARKER = "test_" + uuid.uuid4().hex[:8]


def post(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers
        or {"Content-Type": "application/json", "User-Agent": "telemetry-selftest"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def query(hogql):
    resp = post(
        QUERY_HOST + "/api/projects/%s/query/" % PID,
        {"query": {"kind": "HogQLQuery", "query": hogql}},
        headers={
            "Authorization": "Bearer " + PHX,
            "Content-Type": "application/json",
            "User-Agent": "telemetry-selftest",
        },
    )
    return json.loads(resp).get("results", [])


def main():
    lines = []
    lines.append("=" * 70)
    lines.append("后台数据链路自检（发送 -> PostHog -> 看板同款查询确认）")
    lines.append("=" * 70)
    lines.append("测试标记: " + MARKER)
    lines.append("")

    if not PHC or not PHX or not PID:
        lines.append("配置缺失：请检查 posthog_config.json 和 tools/dashboard_config.json")
        _finish(lines)
        return

    ts = datetime.now(timezone.utc).isoformat()
    batch = [
        {
            "event": "app_start",
            "distinct_id": "test-suite",
            "timestamp": ts,
            "properties": {"app_version": "0.0.0-TEST", "os": "TEST-OS", "gpu": "TEST-GPU", "test_marker": MARKER},
        },
        {
            "event": "detection_done",
            "distinct_id": "test-suite",
            "timestamp": ts,
            "properties": {"engine": "simpleai", "paras": 12, "duration_sec": 123, "ratio": 0.55, "test_marker": MARKER},
        },
        {
            "event": "app_close",
            "distinct_id": "test-suite",
            "timestamp": ts,
            "properties": {"duration_sec": 456, "test_marker": MARKER},
        },
    ]

    lines.append("[1/4] 发送 3 条测试事件到 PostHog ...")
    send_ok = False
    last_err = ""
    for host in SEND_HOSTS:
        for attempt in range(1, 4):
            try:
                resp = post(host + "/batch/", {"api_key": PHC, "batch": batch})
                lines.append("      发送成功: %s（第 %d 次尝试）-> %s" % (host, attempt, resp[:80]))
                send_ok = True
                break
            except Exception as e:
                last_err = str(e)
                lines.append("      发送失败: %s（第 %d 次尝试）-> %s" % (host, attempt, e))
        if send_ok:
            break
    if not send_ok:
        lines.append("")
        lines.append("结果: FAIL（发送环节全不通，最后错误: %s）" % last_err)
        lines.append("提示: 这是网络层问题，不是钥匙问题。请依次尝试：")
        lines.append("  1) 关掉 VPN 再跑一次；")
        lines.append("  2) 开 VPN 再跑一次；")
        lines.append("  3) 换个网络（如手机热点）再跑一次。")
        _finish(lines)
        return

    lines.append("[2/4] 轮询等待 PostHog 入库（最长 90 秒）...")
    q = (
        "SELECT event, count() FROM events "
        "WHERE properties.test_marker = '%s' GROUP BY event ORDER BY count() DESC" % MARKER
    )
    total = 0
    rows = []
    for attempt in range(1, 19):
        time.sleep(5)
        try:
            rows = query(q)
            total = sum(int(r[1]) for r in rows)
            lines.append("      第 %d 次查询: 已收到 %d/3 条" % (attempt, total))
        except Exception as e:
            lines.append("      第 %d 次查询失败: %s" % (attempt, e))
        if total >= 3:
            break

    lines.append("")
    for row in rows:
        lines.append("      %-18s %d 条" % (row[0], row[1]))
    lines.append("")

    lines.append("[3/4] 用看板同款查询跑一遍（确认看板能正常出数）...")
    dash_queries = {
        "总启动次数 total_starts": "SELECT count() FROM events WHERE event='app_start'",
        "今日启动 today_starts": "SELECT count() FROM events WHERE event='app_start' AND timestamp >= today()",
        "近7天活跃设备 week_active": "SELECT uniqExact(distinct_id) FROM events WHERE event IN ('app_start','heartbeat','detection_done') AND timestamp >= now() - INTERVAL 7 DAY",
        "总检测次数 total_detections": "SELECT count() FROM events WHERE event='detection_done'",
        "平均会话时长 avg_session": "SELECT avg(toFloat64OrNull(properties.duration_sec)) FROM events WHERE event='app_close' AND toFloat64OrNull(properties.duration_sec) > 0",
        "在线设备 online_now": "SELECT uniqExact(distinct_id) FROM events WHERE event='heartbeat' AND timestamp >= now() - INTERVAL 5 MINUTE",
    }
    dash_ok = True
    for label, hogql in dash_queries.items():
        try:
            rows2 = query(hogql)
            v = rows2[0][0] if rows2 and rows2[0] else None
            lines.append("      %-22s = %s" % (label, v))
        except Exception as e:
            dash_ok = False
            lines.append("      %-22s 查询失败: %s" % (label, e))

    lines.append("")
    if total >= 3 and dash_ok:
        lines.append("结果: PASS ✅ 全链路通（发送/存储/查询/看板查询全部正常）")
        lines.append("提示: 现在打开手机 APK 或电脑看板，引擎分布里会出现 simpleai，总启动会 +1")
    elif total >= 3:
        lines.append("结果: PARTIAL ⚠ 事件已入库，但看板部分查询报错，请把本文件发给我")
    elif total > 0:
        lines.append("结果: PARTIAL ⚠ 收到 %d/3 条，PostHog 入库偏慢，稍后再查一次" % total)
    else:
        lines.append("结果: FAIL ❌ 查询始终为 0，检查 phx_ 个人密钥/project_id")

    lines.append("=" * 70)
    _finish(lines)


def _finish(lines):
    text = "\n".join(lines)
    print(text)
    try:
        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        print("\n结果已保存: " + RESULT_FILE)
    except Exception:
        pass


if __name__ == "__main__":
    main()
