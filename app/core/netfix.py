# -*- coding: utf-8 -*-
"""网络环境自愈：绕开"用不了的"系统代理。

背景（真实踩坑）：很多 VPN / 加速器的 Windows 系统代理写的是 `socks://127.0.0.1:66`
（注册表 HKCU\\...\\Internet Settings\\ProxyServer），而 Python 的 urllib / requests / pip
只认 HTTP 代理，遇到 socks 就会：
  - urllib：把 socks 代理当 HTTP 代理连 -> `BadStatusLine: ?`（下载直接失败）
  - pip / requests：`Missing dependencies for SOCKS support`（要 PySocks，便携 Python 没装）
而 curl.exe 不读注册表，所以"curl 能下、程序里下不了"。

这里只做两件事，且只针对 socks 这类 Python 用不了的代理：
  1) apply_env_fix()：进程内打补丁（NO_PROXY=* + 清 socks 代理变量），
     让 urllib / requests / huggingface_hub 都走直连；
  2) sanitize_env()：给子进程（pip 等）准备的干净 env。
正常的 HTTP(S) 代理不动，避免误伤"必须走代理"的用户。
"""

import os

PROXY_VARS = (
    "ALL_PROXY", "all_proxy",
    "HTTP_PROXY", "http_proxy",
    "HTTPS_PROXY", "https_proxy",
)

_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def is_unusable_proxy(value):
    """socks 系列代理对标准库 / pip 都不可用（需要 PySocks）。"""
    if not value:
        return False
    scheme = value.split("=")[-1].split(":", 1)[0].strip().lower()
    return scheme in ("socks", "socks4", "socks5", "socks5h")


def system_proxy():
    """读取 Windows 系统代理设置（未启用返回 None）。"""
    env = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    if env:
        return env
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY) as key:
            try:
                enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
            except OSError:
                return None
            if not enabled:
                return None
            try:
                return winreg.QueryValueEx(key, "ProxyServer")[0] or None
            except OSError:
                return None
    except OSError:
        return None


def unusable_system_proxy():
    """系统代理是 socks 时返回该字符串，否则 None。"""
    value = system_proxy()
    return value if is_unusable_proxy(value) else None


def apply_env_fix(log=None):
    """进程内生效：让本进程及其子进程都不再使用 socks 系统代理。"""
    bad = unusable_system_proxy()
    for name in PROXY_VARS:
        if is_unusable_proxy(os.environ.get(name)):
            os.environ.pop(name, None)
    if bad:
        # 光删环境变量不够：libs 还会回退读注册表，NO_PROXY=* 才能短路掉
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        if log:
            log("检测到系统代理为 %s（Python 不支持 socks），已自动改为直连" % bad)
    return bad


def sanitize_env(env=None):
    """给 pip 等子进程准备 env（不改动当前进程）。"""
    env = dict(os.environ if env is None else env)
    for name in PROXY_VARS:
        if is_unusable_proxy(env.get(name)):
            env.pop(name, None)
    if unusable_system_proxy():
        env["NO_PROXY"] = "*"
        env["no_proxy"] = "*"
    return env

# aigc-toolkit: file purpose marker
