#!/usr/bin/env bash
#
# 取 python-build-standalone 最新 release 的原始 JSON 并打到 stdout。
# 成功才输出 JSON；失败（重试若干次后）非 0 退出，绝不输出半截内容。
#
# 为什么要认证 + 重试（都是实跑踩出来的）：
#   · 未认证访问 api.github.com 是**出口 IP 共享**的 60 次/小时额度，CI runner
#     的 IP 常年被别人用光 → 返回 403 + 一段错误 JSON；
#   · 原来的写法是 `curl -sSL ... | jq`，`-s` 把错误吞了、`-f` 又没加，
#     于是错误 JSON 流进 jq，`.assets` 是 null → 报
#     `jq: error (at <stdin>:1): Cannot iterate over null (null)`，
#     完全看不出真实原因（macOS job 首次实跑就栽在这）。
#   带 workflow 自带的 token 后额度提到 5000 次/小时，再叠加 `curl -f` 与
#   重试，才算稳。
#
# 注意保持 bash 3.2 兼容（macOS runner 的 /bin/bash 是 3.2，数组 + set -u
# 在空数组上会报 unbound variable），所以这里不用数组。
set -euo pipefail

API="https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"

_curl() {
    if [ -n "${GH_API_TOKEN:-}" ]; then
        curl -fsSL --retry 4 --retry-delay 5 --retry-all-errors \
            -H "Authorization: Bearer ${GH_API_TOKEN}" \
            -H "Accept: application/vnd.github+json" \
            -H "User-Agent: aigc-ci" "$API"
    else
        echo "（未提供 GH_API_TOKEN，按匿名额度请求，容易被限流）" >&2
        curl -fsSL --retry 4 --retry-delay 5 --retry-all-errors \
            -H "Accept: application/vnd.github+json" \
            -H "User-Agent: aigc-ci" "$API"
    fi
}

for i in 1 2 3 4 5; do
    if JSON=$(_curl 2>/dev/null); then
        # 只认「真的有 assets 数组且非空」的响应
        if printf '%s' "$JSON" | jq -e '.assets | type == "array" and length > 0' >/dev/null 2>&1; then
            printf '%s' "$JSON"
            exit 0
        fi
        echo "第 ${i} 次取到的 release JSON 不含 assets，重试…" >&2
    else
        echo "第 ${i} 次请求 release 失败，重试…" >&2
    fi
    sleep 6
done

echo "拿不到 python-build-standalone 的 release 信息（已重试 5 次）" >&2
exit 1
