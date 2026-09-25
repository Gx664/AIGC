# -*- coding: utf-8 -*-
"""网络环境自愈：绕开"用不了的"系统代理。

背景（真实踩坑）：很多 VPN / 加速器的 Windows 系统代理写的是 `socks://127.0.0.1:66`
（注册表 HKCU\\...\\Internet Settings\\ProxyServer），而 Python 的 urllib / requests / pip
只认 HTTP 代理，遇到 socks 就会：
  - urllib：把 socks 代理当 HTTP 代理连 -> `BadStatusLine: ?`（下载直接失败）
  - pip / requests：`Missing dependencies for SOCKS support`（要 PySocks，便携 Python 没装）
而 curl.exe 不读注册表，所以"curl 能下、程序里下不了"。

这里只做两件事，且只针对 Python 用不了的代理（socks 系列，以及没有主机名的
畸形残留值 —— 例如代理软件卸载后留在注册表里的 `http://`）：
  1) apply_env_fix()：进程内打补丁（NO_PROXY=* + 清不可用的代理变量），
     让 urllib / requests / huggingface_hub / pip 都走直连；
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
    """Python 拿到也用不了的代理串。

    两类：
      1) socks 系列 —— urllib / requests / pip 都不认，要额外装 PySocks；
      2) 没有主机名的畸形值 —— 典型是代理软件卸载后残留在注册表里的 `http://`
         （ProxyEnable 可能已是 0，但 urllib.getproxies_registry() 仍会把它读出来）。
         此时 pip 直接报 "proxy URL is malformed and could be missing the host"，
         连接根本建不起来，安装器会卡在 get-pip 这一步。
    """
    if not value:
        return False
    v = value.split("=")[-1].strip()  # 兼容 "http=http://xxx" 这种写法
    scheme = v.split(":", 1)[0].strip().lower()
    if scheme in ("socks", "socks4", "socks5", "socks5h"):
        return True
    # 有没有 host：`http://host:port`、`http://user:pw@host` 才算正常
    rest = v.split("://", 1)[1] if "://" in v else v
    host = rest.split("@")[-1].split("/")[0].split(":")[0].strip()
    return not host


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
    """Python 实际会拿到、却用不了的代理串；没有则返回 None。

    用 urllib.request.getproxies() 取得，而不是只看注册表的 ProxyEnable：
      - getproxies() 正是 urllib / requests / pip 的共同入口（环境变量与注册表
        已经合并好），拿到的就是它们真正会用的东西；
      - 只看 ProxyEnable 会漏掉一类真实故障：代理软件卸载后残留的 `http://`
        （ProxyEnable=0，但 getproxies_registry() 照样把它读出来），
        这时 pip 报 "proxy URL is malformed"，安装器 100% 装不上。
    正常的 HTTP(S) 代理（有 host）不会命中，保持原样不动。
    """
    try:
        import urllib.request as _ur

        proxies = _ur.getproxies()
    except Exception:
        proxies = {}
    for v in proxies.values():
        if is_unusable_proxy(v):
            return v
    return None


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
            log("检测到不可用的系统代理 %s（socks 或缺少主机名），已自动改为直连" % bad)
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
