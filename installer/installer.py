"""AI 检测工具箱 安装器（不打包 AI 环境，运行时下载）。

架构：安装器只负责
  1) Python 便携运行时（官方 embeddable zip：解压即用，无注册表 / 无 UAC）
  2) 程序本体 + 卸载注册 + 桌面快捷方式
PyTorch / PySide6 等重依赖由首次启动引导器 first_run_gui.exe 按需下载。

安装逻辑全部落在模块级函数（perform_install / install_embed_runtime）里，
GUI 只是薄薄一层壳 —— 这样既可以用 `installer.py --cli D:\\目标` 无界面安装
（也方便自测），又避免"把逻辑写在 Tk 回调里没法验证"的老问题。
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile

try:  # 无 tkinter 的精简解释器下，CLI 模式（--cli）依然要能用
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover
    tk = filedialog = messagebox = ttk = None

APP_NAME = "AI 检测工具箱"
APP_VER = "1.3.7"
PY_VER = "3.12.10"
PY_EMBED_NAME = "python-%s-embed-amd64.zip" % PY_VER
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AIGC_Toolkit"
# embeddable 便携包：解压即用，无安装器 / 无注册表 / 无 UAC —— 从根上规避官方 exe 安装器的
# MSI 孤儿注册问题（用户删目录后重装：静默安装被"已注册"骗过返回 0、卸载/修复全 1603）。
# 国内镜像优先（无需 VPN，均已实测可下），官方源排最后兜底
PY_EMBED_URLS = [
    "https://registry.npmmirror.com/-/binary/python/%s/%s" % (PY_VER, PY_EMBED_NAME),
    "https://mirrors.huaweicloud.com/python/%s/%s" % (PY_VER, PY_EMBED_NAME),
    "https://www.python.org/ftp/python/%s/%s" % (PY_VER, PY_EMBED_NAME),
]
GET_PIP_URLS = [
    "https://bootstrap.pypa.io/get-pip.py",
    "https://mirrors.aliyun.com/pypi/get-pip.py",
]
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
MIN_DL_SIZE = 2 * 1024 * 1024   # Python 便携包 ~11MB
GETPIP_MIN_SIZE = 200 * 1024    # get-pip.py 各镜像 1.9~2.3MB，下限放宽
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PY_NAME = ("Python 便携包 (*.zip)", "*.zip")

# 卸载器由安装器生成到安装目录；自删用延迟 rd，避开运行中 python.exe 的文件锁
UNINSTALLER_TEMPLATE = '''# -*- coding: utf-8 -*-
"""AI 检测工具箱 卸载器（由安装器自动生成，勿手改）。"""
import os
import subprocess
import tkinter as tk
from tkinter import messagebox

TARGET = r"@TARGET@"
EMAIL = "@EMAIL@"
CREATE_NO_WINDOW = 0x08000000


def main():
    root = tk.Tk()
    root.withdraw()
    ok = messagebox.askyesno(
        "卸载 / Uninstall",
        "确定要卸载 AI 检测工具箱吗？\\nUninstall AI Detector Toolkit?\\n\\n"
        "将删除以下目录（含模型文件）：\\n%s\\n\\n"
        "遇到 Bug 或有建议？欢迎先联系反馈（反馈 / 意见 / 合作都欢迎）：\\n%s\\n"
        "(Found a bug or have a suggestion? Contact us first)" % (TARGET, EMAIL),
    )
    if not ok:
        return
    try:
        import winreg

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                         r"Software\\Microsoft\\Windows\\CurrentVersion"
                         r"\\Uninstall\\AIGC_Toolkit")
    except OSError:
        pass
    try:
        lnk = os.path.join(os.path.expanduser("~"), "Desktop",
                           "AI 检测工具箱.lnk")
        if os.path.exists(lnk):
            os.remove(lnk)
    except OSError:
        pass
    # 等本进程退出后再删整个目录（python.exe 运行中无法删除自身）
    subprocess.Popen(
        'cmd /c ping 127.0.0.1 -n 4 > nul & rd /s /q "%s"' % TARGET,
        creationflags=CREATE_NO_WINDOW,
    )
    messagebox.showinfo(
        "完成 / Done",
        "AI 检测工具箱 已卸载，感谢使用。\\nUninstalled.\\n\\n"
        "有 Bug 或建议随时联系（反馈 / 意见 / 合作都欢迎）：\\n%s" % EMAIL,
    )
    root.destroy()


main()
'''


class Cancelled(RuntimeError):
    """用户点了取消 —— 单独一个类型，避免被下载兜底逻辑当成"换个源再试"。"""


# 写进便携运行时的 Lib\site-packages\sitecustomize.py：解释器一启动就生效，
# 这样哪怕用户/别的工具手动用 runtime python 跑 pip，也不会被 socks 系统代理坑死。
# 逻辑与 app/core/netfix.py 保持一致（那边是源码侧的唯一真源）。
SITECUSTOMIZE = '''# -*- coding: utf-8 -*-
"""安装器自动写入，勿手改。让便携 Python 绕开"socks 系统代理"。

VPN / 加速器常把 Windows 系统代理写成 socks://127.0.0.1:66，而 Python 的
urllib / requests / pip 都不支持 socks（除非另装 PySocks），于是报
BadStatusLine 或 "Missing dependencies for SOCKS support"，下载全挂。
对应的源码侧实现：app/core/netfix.py
"""
import os

_VARS = ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
         "HTTPS_PROXY", "https_proxy")
_KEY = r"Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"


def _is_socks(value):
    if not value:
        return False
    scheme = value.split("=")[-1].split(":", 1)[0].strip().lower()
    return scheme in ("socks", "socks4", "socks5", "socks5h")


def _apply():
    bad = None
    for name in _VARS:
        if _is_socks(os.environ.get(name)):
            os.environ.pop(name, None)
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as key:
                if winreg.QueryValueEx(key, "ProxyEnable")[0]:
                    server = winreg.QueryValueEx(key, "ProxyServer")[0] or ""
                    if _is_socks(server):
                        bad = server
        except OSError:
            pass
    if bad:
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"


_apply()
'''


# --------------------------------------------------------------------------
# 路径 / i18n
# --------------------------------------------------------------------------
def app_source_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "app")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")


def _i18n_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "app", "core")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "core")


sys.path.insert(0, _i18n_dir())
from i18n import get_lang, set_lang, tr  # noqa: E402
from meta import AUTHOR_CONTACT, AUTHOR_EMAIL, AUTHOR_TG  # noqa: E402
from netfix import apply_env_fix, sanitize_env, unusable_system_proxy  # noqa: E402
from gpuinfo import detect as gpu_detect  # noqa: E402


# --------------------------------------------------------------------------
# 运行环境路径校验（「新建」模式）
# --------------------------------------------------------------------------
# Windows 文件名非法字符 —— **不含 \ 和 /**（它们在路径里是分隔符），
# 也**不含盘符那个冒号**：``D:\...`` 里的 ``:` 合法，故查之前先把盘符剥掉。
_BAD_PATH_CHARS = '<>:"|?*'
# Windows 保留设备名：这些名字做目录会创建失败或行为诡异
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + ["COM%d" % i for i in range(1, 10)]
    + ["LPT%d" % i for i in range(1, 10)]
)
# 长度上限留余量给 site-packages 的深层嵌套（Windows 路径上限 260）
_MAX_PATH_LEN = 200


def _danger_reason(norm):
    """危险位置判据：命中返回原因文案，否则空串。

    拒绝的都是"一旦按覆盖逻辑清空、后果不可挽回"的位置：盘根、Windows 目录、
    用户主目录或桌面**本身**、Program Files / ProgramData。
    **不拒绝**它们的子目录（如 ``C:\\Users\\me\\AIGC`` 是允许的）。
    """
    low = norm.lower().rstrip("\\")
    if len(low) <= 3 and low.endswith(":"):
        return tr("inst_rt_danger_root")
    sysroot = os.environ.get("SystemRoot", r"C:\Windows").lower().rstrip("\\")
    home = os.path.expanduser("~").lower().rstrip("\\")
    desktop = os.path.join(os.path.expanduser("~"), "Desktop").lower().rstrip("\\")
    for p, key in ((sysroot, "inst_rt_danger_system"),
                   (home, "inst_rt_danger_home"),
                   (desktop, "inst_rt_danger_desktop")):
        if low == p:
            return tr(key)
    drive = sysroot[:2]
    for frag in ("\\program files", "\\program files (x86)", "\\programdata"):
        if low.startswith(drive + frag):
            return tr("inst_rt_danger_programs")
    return ""


def check_runtime_path(path):
    """检查「新建运行环境」的目标路径是否可用。

    顺序即优先级：**先挑出必须改的（error），再看能不能带警告继续（warn）**，
    最后才是干净可用（ok）。一次只报第一个问题 —— 用户改完再点检测。

    :param path: 用户输入的原始路径
    :return: ``(level, msg)``；``level`` ∈ ``{"ok", "warn", "error"}``
    """
    raw = (path or "").strip()
    if not raw:
        return "error", tr("inst_rt_err_empty")

    # 盘符里的冒号是合法的（``D:\...``），先剥掉盘符再查非法字符 ——
    # 否则每个正常路径都会被判成"含非法字符 :"（实测踩过这个坑）
    body = raw[2:] if (len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha()) else raw
    bad = [c for c in _BAD_PATH_CHARS if c in body]
    if bad:
        return "error", tr("inst_rt_err_char") % bad[0]

    if len(raw) > _MAX_PATH_LEN:
        return "error", tr("inst_rt_err_long") % _MAX_PATH_LEN

    if raw.endswith(".") or raw.endswith(" "):
        return "error", tr("inst_rt_err_tail")

    # 保留名：逐个路径分量比对（去掉扩展名后的主体，如 "con.txt" 也是保留的）
    for part in raw.replace("/", "\\").split("\\"):
        if part.split(".")[0].upper() in _RESERVED_NAMES:
            return "error", tr("inst_rt_err_reserved") % part

    drive, _rest = os.path.splitdrive(raw)
    if drive:
        if not os.path.exists(drive + "\\"):
            return "error", tr("inst_rt_err_drive") % drive
    elif not raw.startswith("\\\\"):
        # 既没有盘符也不是 UNC（\\server\share）—— 相对路径不能用来装环境
        return "error", tr("inst_rt_err_absolute")

    norm = os.path.normpath(raw)
    danger = _danger_reason(norm)
    if danger:
        return "error", tr("inst_rt_err_danger") % danger

    if os.path.isdir(norm):
        try:
            n = len(os.listdir(norm))
        except OSError:
            n = 0
        if n:
            return "warn", tr("inst_rt_warn_not_empty") % n
    elif os.path.exists(norm):
        return "warn", tr("inst_rt_warn_is_file")

    if any(ord(c) > 127 for c in raw) or " " in raw:
        return "warn", tr("inst_rt_warn_nonascii")
    return "ok", tr("inst_rt_ok")


# --------------------------------------------------------------------------
# 下载（urllib -> 系统 curl 兜底 -> 多镜像 -> 手动选包）
# --------------------------------------------------------------------------
def _err_text(e):
    """异常转成纯 ASCII，避免个别网络库抛出的非 UTF-8 消息在界面上显示成乱码（如 'ÿ'）。"""
    return ("%s: %s" % (type(e).__name__, e)).encode("ascii", "replace").decode("ascii")


def _cleanup_partial(dest):
    for p in (dest + ".part", dest):
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def _validate_dl(dest, minimum=MIN_DL_SIZE, magic=None):
    """体积 + 文件头校验，防止把错误页 / 半截包当成安装包。"""
    if not os.path.exists(dest) or os.path.getsize(dest) < minimum:
        raise RuntimeError(tr("inst_size_bad"))
    if magic:
        with open(dest, "rb") as f:
            head = f.read(len(magic))
        if head != magic:
            raise RuntimeError(tr("inst_size_bad"))


def _fetch_urllib(url, dest, log, status, cancelled, direct=False):
    log(tr("inst_download_log") % url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    tmp = dest + ".part"
    # 系统代理是 socks（VPN 常见）时直接用无代理 opener —— 否则 urllib 会把它当
    # HTTP 代理用，报 BadStatusLine；normalize 完仍失败则由调用方改用直连/curl
    if direct or unusable_system_proxy():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    else:
        opener = urllib.request.build_opener()
    with opener.open(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = 5 + int(15 * done / total)
                    status(tr("inst_download_python_pct") % pct, pct)
                if cancelled():
                    raise Cancelled(tr("inst_cancelled"))
    os.replace(tmp, dest)


def _fetch_curl(url, dest, log, status, cancelled):
    """系统 curl 兜底（Win10 自带）：独立网络栈，能绕开 Python 网络层的问题。"""
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError(tr("inst_no_curl"))
    log(tr("inst_download_curl") % url)
    tmp = dest + ".part"
    status(tr("inst_download_curl_run"), 4)
    rc = subprocess.call(
        [curl, "-L", "--fail", "-sS", "--retry", "2",
         "--connect-timeout", "15", "--speed-time", "30",
         "--speed-limit", "1024", "-o", tmp, url],
        creationflags=CREATE_NO_WINDOW,
    )
    if rc != 0:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise RuntimeError(tr("inst_curl_rc") % rc)
    os.replace(tmp, dest)


def fetch_url(url, dest, log, status, cancelled, minimum=MIN_DL_SIZE, magic=None):
    """单个源：urllib -> 直连 urllib（绕开系统代理）-> 系统 curl，最后做体积校验。"""
    try:
        _fetch_urllib(url, dest, log, status, cancelled)
    except Cancelled:
        raise
    except Exception as e1:
        log(tr("inst_python_dl_fail") % _err_text(e1))
        _cleanup_partial(dest)
        if not unusable_system_proxy():
            try:
                log(tr("inst_proxy_bypass"))
                _fetch_urllib(url, dest, log, status, cancelled, direct=True)
                _validate_dl(dest, minimum, magic)
                return dest
            except Cancelled:
                raise
            except Exception as e2:
                log(tr("inst_python_dl_fail") % _err_text(e2))
                _cleanup_partial(dest)
        _fetch_curl(url, dest, log, status, cancelled)
    _validate_dl(dest, minimum, magic)


def download_with_mirrors(urls, dest, log, status, cancelled,
                          ask_manual=None, minimum=MIN_DL_SIZE, magic=None):
    """多镜像依次尝试；全挂则（可选的）让用户指一个本地已下好的包。"""
    err = None
    for u in urls:
        try:
            fetch_url(u, dest, log, status, cancelled, minimum, magic)
            return dest
        except Cancelled:
            raise
        except Exception as e:
            err = e
            log(tr("inst_python_dl_fail") % _err_text(e))
            _cleanup_partial(dest)
    if err is not None:
        log(tr("inst_all_dl_fail") % _err_text(err))
    if ask_manual:
        manual = ask_manual()
        if manual:
            log(tr("inst_manual_using") % manual)
            shutil.copyfile(manual, dest)
            _validate_dl(dest, minimum, magic)
            return dest
    raise RuntimeError(tr("inst_python_dl_err") % _err_text(err))


def run_stream(args, log, cwd=None, env=None):
    """跑一个子进程，逐行把输出喂给 log，返回退出码。"""
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=sanitize_env(env) if env is None else env,
        creationflags=CREATE_NO_WINDOW,
    )
    for line in proc.stdout:
        line = line.strip()
        if line:
            log(line)
    return proc.wait()


# --------------------------------------------------------------------------
# Python 便携运行时（embeddable）
# --------------------------------------------------------------------------
def python_ok(exe):
    """验证 Python 能完整初始化（标准库 encodings 可用）。"""
    if not os.path.exists(exe):
        return False
    try:
        out = subprocess.run(
            [exe, "-c", "import encodings, sys; print(sys.prefix)"],
            capture_output=True, text=True, timeout=60,
            creationflags=CREATE_NO_WINDOW,
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except Exception:
        return False


def pip_ok(pyexe):
    if not os.path.exists(pyexe):
        return False
    try:
        out = subprocess.run(
            [pyexe, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=90,
            creationflags=CREATE_NO_WINDOW,
        )
        return out.returncode == 0 and "pip" in (out.stdout or "").lower()
    except Exception:
        return False


def patch_embed_pth(pydir, log=print):
    """修补 embeddable 的 `python3xx._pth`。

    这个文件把 sys.path 完全写死（并且默认注释掉 `import site`），不改它的话
    pip 装进 Lib\\site-packages 的包 import 不到 —— 这是 embeddable 最经典的坑：
      1) 放开 `import site`，让 site.py 把 Lib\\site-packages 挂进 sys.path
      2) 补一行 `.`，保证安装目录本身可见
    """
    pth = None
    for name in sorted(os.listdir(pydir)):
        if name.endswith("._pth"):
            pth = os.path.join(pydir, name)
            break
    if not pth:
        raise RuntimeError(tr("inst_pth_missing"))
    with open(pth, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    out = []
    for ln in lines:
        # `#import site` / `import site` 统一成生效的那一行
        out.append("import site" if ln.strip().lstrip("#").strip() == "import site" else ln)
    if not any(l.strip() == "import site" for l in out):
        out.append("import site")
    if not any(l.strip() == "." for l in out):
        out.append(".")
    with open(pth, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    log(tr("inst_pth_patched") % os.path.basename(pth))
    return pth


def write_sitecustomize(pydir, log=None):
    """给便携运行时装一份网络自愈脚本（解释器启动即生效）。"""
    sp = os.path.join(pydir, "Lib", "site-packages")
    os.makedirs(sp, exist_ok=True)
    path = os.path.join(sp, "sitecustomize.py")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(SITECUSTOMIZE)
    if log:
        log(tr("inst_netfix_installed"))
    return path


def install_embed_runtime(pydir, dl, log=print, status=None, cancelled=None, ask_manual=None):
    """保证 pydir 下有一份带 pip 的可用 Python（便携版），返回 python.exe 路径。"""
    log = log or (lambda m: None)
    status = status or (lambda m, p=None: None)
    cancelled = cancelled or (lambda: False)
    pyexe = os.path.join(pydir, "python.exe")

    if python_ok(pyexe) and pip_ok(pyexe):
        log(tr("inst_runtime_reuse"))
        status(tr("inst_python_installed"), 25)
        write_sitecustomize(pydir, log)
        return pyexe

    # 坏的旧运行时一律清掉，避免半成品干扰（含旧版本遗留的 venv）
    if os.path.exists(pydir):
        log(tr("inst_runtime_purge"))
        shutil.rmtree(pydir, ignore_errors=True)
    shutil.rmtree(os.path.join(os.path.dirname(pydir), "venv"), ignore_errors=True)

    # 1. 便携包 zip
    zpath = os.path.join(dl, PY_EMBED_NAME)
    if os.path.exists(zpath) and os.path.getsize(zpath) >= MIN_DL_SIZE:
        status(tr("inst_python_downloaded"), 15)
    else:
        status(tr("inst_download_python"), 3)
        download_with_mirrors(PY_EMBED_URLS, zpath, log, status, cancelled,
                              ask_manual, MIN_DL_SIZE, b"PK")

    # 2. 解压 + 修补 ._pth
    status(tr("inst_extract_python"), 20)
    log(tr("inst_unzip_log") % (PY_EMBED_NAME, pydir))
    os.makedirs(pydir, exist_ok=True)
    try:
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(pydir)
    except zipfile.BadZipFile:
        _cleanup_partial(zpath)
        raise RuntimeError(tr("inst_unzip_bad"))
    patch_embed_pth(pydir, log)
    write_sitecustomize(pydir, log)

    if not python_ok(pyexe):
        raise RuntimeError(tr("inst_python_inst_err") % 0)

    # 3. 引导 pip（embeddable 不自带 ensurepip）
    status(tr("inst_install_pip"), 30)
    getpip = os.path.join(dl, "get-pip.py")
    if not (os.path.exists(getpip) and os.path.getsize(getpip) >= GETPIP_MIN_SIZE):
        download_with_mirrors(GET_PIP_URLS, getpip, log, status, cancelled,
                              None, GETPIP_MIN_SIZE)
    rc = run_stream([pyexe, getpip, "--no-warn-script-location", "-i", PYPI_MIRROR], log)
    log("get-pip 退出码: %d" % rc)
    if rc != 0 or not pip_ok(pyexe):
        raise RuntimeError(tr("inst_pip_err") % rc)
    log(tr("inst_pip_ready"))
    return pyexe


# --------------------------------------------------------------------------
# 程序本体 / 快捷方式 / 卸载注册
# --------------------------------------------------------------------------
def launcher_cmd(appdir, pydir):
    """返回 (可执行文件, 参数或 None)。

    引导器是独立 exe（自带 tkinter，因为 embeddable 没有 tkinter），直接运行即可 ——
    注意不能用 `pythonw.exe first_run_gui.exe`（那是把 exe 当脚本喂给解释器，必错）。
    """
    fr_exe = os.path.join(appdir, "first_run_gui.exe")
    if os.path.exists(fr_exe):
        return fr_exe, None
    return os.path.join(pydir, "pythonw.exe"), os.path.join(appdir, "first_run.py")


def _write_launchers(target, appdir, pydir, log):
    """写两个便捷脚本：启动.cmd（日常启动）、诊断.cmd（出问题时收集信息）。"""
    try:
        exe, args = launcher_cmd(appdir, pydir)
        cmdline = '"%s"' % exe if not args else '"%s" "%s"' % (exe, args)
        with open(os.path.join(target, "启动.cmd"), "w", encoding="ascii") as f:
            f.write('@echo off\r\nstart "" %s\r\n' % cmdline)
        py_exe = os.path.join(pydir, "python.exe")
        with open(os.path.join(target, "诊断.cmd"), "w", encoding="utf-8") as f:
            f.write(
                '@echo off\r\nchcp 65001 >nul\r\ncd /d "%s"\r\n'
                '"%s" diag_startup.py\r\necho.\r\n'
                "echo ============================\r\n"
                "echo 诊断完成，按任意键关闭窗口...\r\npause >nul\r\n"
                % (appdir, py_exe)
            )
    except Exception as e:
        log("启动脚本写入失败(不影响使用): %s" % e)


def app_icon(appdir):
    """程序图标路径（安装目录 app/assets/icon.ico）；没有就返回空串。"""
    p = os.path.join(appdir, "assets", "icon.ico")
    return p if os.path.exists(p) else ""


def make_shortcut(target, args, workdir, log=print, icon=""):
    """在桌面创建快捷方式（args 为 None 时不带参数）。

    注意：`CreateShortcut` 会**加载已存在的 .lnk**，脚本里没赋值的字段会保留旧值 ——
    比如从 pythonw+脚本 的旧快捷方式升级上来时，旧的 Arguments 会残留。
    所以 Arguments 必须无条件写入（空字符串也要写）。
    """
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    lnk = os.path.join(desktop, "%s.lnk" % APP_NAME)
    ps = (
        "$ws = New-Object -ComObject WScript.Shell;"
        "$s = $ws.CreateShortcut('%s');"
        "$s.TargetPath = '%s';"
        "$s.Arguments = '%s';"
        "$s.WorkingDirectory = '%s';"
        "$s.IconLocation = '%s';"
        "$s.Save()" % (
            lnk, target,
            args if args else "",
            workdir,
            icon if icon else target,
        )
    )
    subprocess.call(
        ["powershell", "-NoProfile", "-Command", ps],
        creationflags=CREATE_NO_WINDOW,
    )
    log(tr("inst_shortcut_done") % lnk)


def uninstaller_source():
    """打包好的卸载器 exe 在哪（安装时复制到安装目录）。

    打包后在 ``_MEIPASS``；源码模式看 ``dist\\uninstaller.exe`` —— 需要先跑
    ``tools\\build_exe.ps1``，否则注册卸载入口这步会被跳过并写进日志
    （不静默失败）。
    """
    cands = [
        os.path.join(getattr(sys, "_MEIPASS", ""), "uninstaller.exe"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "dist", "uninstaller.exe"),
    ]
    for p in cands:
        if p and os.path.exists(p):
            return p
    return ""


def register_uninstall(target, runtime_dir, log=print):
    """放置卸载器 exe 并注册到 Windows「设置 > 应用 / 控制面板卸载程序」。

    为什么是 exe，而不是"生成 .py 让 pythonw 去跑"（2026-09 改）：
      1. 一般软件的卸载入口都是 exe，用户看到 pythonw.exe 会以为装错了东西；
      2. 那个 .py 依赖运行环境 —— 环境被删或损坏后，卸载器自己也跑不起来，
         用户只能手动删目录 + 手动清注册表。exe 自带解释器，与环境解耦。

    ``runtime_dir`` 必须写进注册表（``RuntimeDir``），卸载器读它决定删哪个目录。
    **不能从 pythonw.exe 反推父目录** —— 用户若把环境放在 ``D:\\myenv``（只一层），
    反推得到 ``D:\\``，``rd /s /q`` 会把磁盘根删掉（旧版的真实缺陷）。
    """
    src = uninstaller_source()
    dst = os.path.join(target, "uninstaller.exe")
    unw = os.path.join(target, "uninstall.pyw")
    uninstall_cmd = ""
    if src:
        # 首选独立卸载器 exe：自带解释器，运行环境被删或损坏也照样能卸载
        try:
            shutil.copyfile(src, dst)
            uninstall_cmd = '"%s"' % dst
        except OSError as e:
            log(tr("inst_uninstall_reg_fail") % _err_text(e))
    if not uninstall_cmd:
        # 回退方案：生成 .py，交给运行环境里的 pythonw 执行 —— 安装器没把卸载器 exe
        # 打进去时，仍要保证「设置 > 应用」里有卸载入口，不能静默留白
        log(tr("inst_uninstaller_missing"))
        pythonw = os.path.join(
            runtime_dir or os.path.join(target, "runtime", "python"), "pythonw.exe")
        try:
            with open(unw, "w", encoding="utf-8") as f:
                f.write(
                    UNINSTALLER_TEMPLATE
                    .replace("@TARGET@", target)
                    .replace("@EMAIL@", AUTHOR_CONTACT)
                )
        except OSError as e:
            log(tr("inst_uninstall_reg_fail") % _err_text(e))
            return
        uninstall_cmd = '"%s" "%s"' % (pythonw, unw)
        dst = pythonw
    try:
        import winreg

        # 卸载项图标用程序自己的图标（否则是 exe 自带图标 / Python 图标）
        _ico = os.path.join(target, "app", "assets", "icon.ico")
        display_icon = _ico if os.path.exists(_ico) else dst

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        vals = [
            ("DisplayName", APP_NAME),
            ("DisplayVersion", APP_VER),
            ("Publisher", "gxgx3456"),
            ("DisplayIcon", display_icon),
            ("InstallLocation", target),
            ("RuntimeDir", runtime_dir or ""),
            ("UninstallString", uninstall_cmd),
            ("HelpLink", "mailto:%s" % AUTHOR_EMAIL),
            ("URLInfoAbout", "https://t.me/%s" % AUTHOR_TG.lstrip("@")),
            ("Contact", AUTHOR_CONTACT),
            ("Comments",
             "反馈 / 意见 / 合作欢迎联系 · Feedback, suggestions & collaboration: %s"
             % AUTHOR_CONTACT),
            ("NoModify", 1),
            ("NoRepair", 1),
        ]
        for name, value in vals:
            if isinstance(value, int):
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
            else:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        log(tr("inst_uninstall_registered"))
    except OSError as e:
        log(tr("inst_uninstall_reg_fail") % e)


def perform_install(target, log=None, status=None, cancelled=None, ask_manual=None,
                    opt_shortcut=True, opt_launch=True, lang=None, runtime_dir=None):
    """完整安装流程（GUI / CLI 共用）：Python 便携运行时 -> 程序本体 -> 注册卸载 -> 快捷方式。

    ``runtime_dir`` 是运行环境的落地目录（用户安装时可自选，默认
    ``<target>\\runtime\\python``）—— 环境约 4.8GB，允许放到别的盘。
    """
    log = log or (lambda m: None)
    status = status or (lambda m, p=None: None)
    cancelled = cancelled or (lambda: False)

    dl = os.path.join(target, "_downloads")
    pydir = runtime_dir or os.path.join(target, "runtime", "python")
    appdir = os.path.join(target, "app")
    os.makedirs(dl, exist_ok=True)

    apply_env_fix(log)  # 系统代理是 socks（VPN）时改为直连，否则 urllib / pip 全挂

    # 1. Python 便携运行时
    pyexe = install_embed_runtime(pydir, dl, log, status, cancelled, ask_manual)
    log("运行时 Python 就绪: %s" % pyexe)

    # 2. 复制程序本体（PyTorch / PySide6 等组件由首次启动引导器下载）
    #
    # 覆盖安装的关键：只替换「程序代码」，用户数据一律保留。
    # 早先这里是 shutil.rmtree(appdir) 整个删掉再复制，副作用有三：
    #   ① 用户的 logs/ 被清空 —— 升级后出问题查不到旧日志；
    #   ② 若用户在设置里没改模型路径，模型默认落在 <安装目录>/models，
    #      旧的引导器还会把依赖塞在 app 目录 —— 一起被删，升级后要重下几个 GB；
    #   ③ 软件正在运行时 app.log 被占用，rmtree 直接失败 → 覆盖安装装不上。
    # 现在改为「按文件覆盖 + 显式保护 + 清理陈旧文件」。
    status(tr("inst_copy_app"), 80)
    src = app_source_dir()

    # 这些目录在复制/清理时一律跳过，保留现场。
    #   logs   —— 旧运行日志，升级后排查问题要用
    #   models —— 用户已下载的模型（默认落在 <安装目录>/models），可能几个 GB
    #   cache  —— HF / transformers 缓存
    #   config —— 用户配置
    KEEP_DIRS = {"logs", "models", "cache", "config"}

    def _keep(rel):
        """rel 是相对 appdir 的路径（POSIX 分隔符）。返回 True 表示保留旧文件。"""
        first = rel.split("/", 1)[0]
        return first in KEEP_DIRS

    def _overwrite(src_dir, dst_dir, rel="", stats=None):
        """按文件覆盖：新文件写入，旧文件不在新版本里的删掉（但跳过保护目录）。"""
        stats = stats if stats is not None else {"add": 0, "upd": 0, "keep": 0, "del": 0}
        try:
            entries = os.listdir(src_dir)
        except OSError:
            return stats
        src_names = set()
        for name in entries:
            if name in ("logs", "__pycache__") or name.endswith(".pyc"):
                continue
            src_names.add(name)
            s = os.path.join(src_dir, name)
            d = os.path.join(dst_dir, name)
            r = (rel + "/" + name) if rel else name
            if os.path.isdir(s):
                if os.path.exists(d) and not os.path.isdir(d):
                    try:
                        os.remove(d)
                    except OSError:
                        pass
                os.makedirs(d, exist_ok=True)
                _overwrite(s, d, r, stats)
            else:
                if os.path.exists(d) and os.path.isdir(d):
                    # 新版本是文件、旧版本是目录 → 删旧目录
                    shutil.rmtree(d, ignore_errors=True)
                if not os.path.exists(d):
                    stats["add"] += 1
                else:
                    stats["upd"] += 1
                try:
                    shutil.copy2(s, d)
                except OSError as e:
                    # 单文件被占用（多半是正在运行的 app.log 之类）→ 记日志继续，不中断整个安装
                    log("  跳过被占用的文件 %s: %s" % (r, _err_text(e)))
        # 清理：旧版本有、新版本没有的文件 —— 同样跳过保护目录
        if os.path.isdir(dst_dir):
            for name in os.listdir(dst_dir):
                if name in src_names or name in ("logs", "__pycache__") or name.endswith(".pyc"):
                    continue
                r = (rel + "/" + name) if rel else name
                if _keep(r):
                    stats["keep"] += 1
                    continue
                p = os.path.join(dst_dir, name)
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                    stats["del"] += 1
                except OSError as e:
                    log("  跳过被占用的旧文件 %s: %s" % (r, _err_text(e)))
        return stats

    try:
        os.makedirs(appdir, exist_ok=True)
        st = _overwrite(src, appdir)
        log(
            "覆盖安装完成：新增 %d，更新 %d，清理旧文件 %d，保留 %d"
            % (st["add"], st["upd"], st["del"], st["keep"])
        )
    except OSError as e:
        raise RuntimeError(tr("inst_appdir_locked") % _err_text(e))

    # 3. 配置 + 便捷脚本
    #
    # 程序读的是 <安装目录>/settings.json（见 app/main.py：Settings(app 的上一级)），
    # 里面除了 install_dir 还存着用户自己调过的主题、引擎、阈值与参数预设。
    # 旧代码这里是无条件覆盖写，等于每次升级都把用户设置重置回默认值 ——
    # 覆盖安装「不丢用户数据」就名不副实了。改为：读旧值 → 只更新这两个键 → 写回。
    cfg_path = os.path.join(target, "settings.json")
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                cfg = saved
        except Exception as e:
            log("  旧的 settings.json 无法解析，将重建：%s" % _err_text(e))
    app_cfg = cfg.get("app")
    if not isinstance(app_cfg, dict):
        app_cfg = cfg["app"] = {}
    app_cfg["install_dir"] = target
    ui_cfg = cfg.get("ui")
    if not isinstance(ui_cfg, dict):
        ui_cfg = cfg["ui"] = {}
    ui_cfg["language"] = lang or get_lang()
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    _write_launchers(target, appdir, pydir, log)

    # 4. 卸载入口（复制卸载器 exe + 写注册表，注册表里带上 RuntimeDir）
    status(tr("inst_register_uninstall"), 90)
    register_uninstall(target, pydir, log)

    # 5. 快捷方式 + 启动
    status(tr("inst_create_shortcut"), 94)
    launch_target, launch_args = launcher_cmd(appdir, pydir)
    if opt_shortcut:
        make_shortcut(
            launch_target, launch_args, appdir, log,
            icon=app_icon(appdir) or launch_target,
        )
    else:
        log(tr("inst_skip_shortcut"))

    if opt_launch:
        try:
            subprocess.Popen(
                [launch_target] + ([launch_args] if launch_args else []),
                cwd=appdir, creationflags=CREATE_NO_WINDOW,
            )
            log(tr("inst_launching"))
        except Exception as e:
            log(tr("inst_launch_fail") % e)

    status(tr("inst_done"), 100)
    # 完成日志要跟着用户的选择走：跳过快捷方式时不能说"已创建快捷方式"
    if opt_shortcut:
        log(tr("inst_done_log") % APP_NAME)
    else:
        log(tr("inst_done_log_noshortcut"))
    return target


# --------------------------------------------------------------------------
# 运行环境选择对话框（「新建」模式）
# --------------------------------------------------------------------------
class RuntimeDialog(tk.Toplevel if tk else object):
    """让用户选「新建运行环境」的目标路径。

    为什么单独弹一个框
    ------------------
    环境路径和"安装目录"是两件事：默认在安装目录下，但用户可以放到别的盘
    （环境 4.8GB + 模型若干，系统盘吃紧时很需要）。单独一个框才有地方放
    「检测」按钮和逐条校验结果。

    交互约定
    --------
    * 打开即先检测一次（不用用户先点一下才知道行不行）
    * 点「检测」重跑校验，结果显示在提示行并按等级着色
    * 点「确定」时若等级是 ``error`` 则**不关闭**（弹提示说明为什么按不动）；
      若是 ``warn``（文件夹非空等）再弹一次确认 —— 不可恢复的操作必须二次确认
    """

    def __init__(self, parent, default_path):
        super().__init__(parent)
        self.title(tr("inst_rt_title"))
        self.resizable(False, False)
        self.result = None          # 点「确定」后写入最终路径
        self.level = "ok"

        tk.Label(self, text=tr("inst_rt_title"),
                 font=("Microsoft YaHei UI", 13, "bold")).pack(
            anchor="w", padx=18, pady=(16, 2))
        tk.Label(self, text=tr("inst_rt_note"), justify="left", fg="#475569",
                 wraplength=540, anchor="w").pack(fill="x", padx=18, pady=(0, 6))

        # 显卡探测：提前告诉用户会装 GPU 版还是 CPU 版，以及"为什么只能用 CPU"
        # （没 N 卡 / 驱动太旧）。这直接决定首次启动下载 2.6GB 还是 200MB，
        # 也解释得清后面检测为什么慢 —— 别让用户装完才发现走了 CPU。
        try:
            gpu_text = gpu_detect()["reason"]
        except Exception as e:  # noqa: BLE001
            gpu_text = "显卡探测失败：%s" % e
        tk.Label(self, text=gpu_text, justify="left", fg="#475569",
                 wraplength=540, anchor="w").pack(
            fill="x", padx=18, pady=(0, 6))

        row = tk.Frame(self)
        row.pack(fill="x", padx=18, pady=6)
        tk.Label(row, text=tr("inst_rt_path_label")).pack(side="left")
        self.path_var = tk.StringVar(value=default_path)
        self.entry = tk.Entry(row, textvariable=self.path_var, width=50)
        self.entry.pack(side="left", fill="x", expand=True, padx=6)
        self.btn_browse = tk.Button(row, command=self.browse, width=8)
        self.btn_browse.pack(side="left")

        self.msg_var = tk.StringVar(value="")
        self.msg_label = tk.Label(self, textvariable=self.msg_var, justify="left",
                                  fg="#475569", wraplength=560, anchor="w")
        self.msg_label.pack(fill="x", padx=18, pady=(4, 10))

        btns = tk.Frame(self)
        btns.pack(fill="x", padx=18, pady=(0, 16))
        self.btn_ok = tk.Button(btns, command=self.on_ok, width=10)
        self.btn_ok.pack(side="right")
        # 左「检测」右「确定」（按约定的布局）
        self.btn_check = tk.Button(btns, command=self.on_check, width=10)
        self.btn_check.pack(side="right", padx=6)

        self.btn_browse.config(text=tr("inst_rt_browse"))
        self.btn_check.config(text=tr("inst_rt_detect"))
        self.btn_ok.config(text=tr("inst_rt_ok_btn"))

        self.update_idletasks()
        self._center(parent)
        self.transient(parent)
        self.grab_set()
        self.entry.focus_set()
        self.after(120, self.on_check)   # 打开就检测一次

    def _center(self, parent):
        try:
            x = parent.winfo_rootx() + max(
                0, (parent.winfo_width() - self.winfo_width()) // 2)
            y = parent.winfo_rooty() + max(
                0, (parent.winfo_height() - self.winfo_height()) // 3)
            self.geometry("+%d+%d" % (x, y))
        except Exception:
            pass

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.path_var.get() or "D:\\")
        if d:
            self.path_var.set(os.path.normpath(d))
            self.on_check()

    def on_check(self):
        """跑一遍校验并把结果写到提示行；返回等级（供「确定」判断）。"""
        self.level, msg = check_runtime_path(self.path_var.get())
        self.msg_var.set(msg)
        self.msg_label.config(fg={"ok": "#15803d", "warn": "#b45309",
                                  "error": "#b91c1c"}.get(self.level, "#475569"))
        return self.level

    def on_ok(self):
        level = self.on_check()
        path = os.path.normpath(self.path_var.get().strip())
        if level == "error":
            # 不许带着错误继续；说明原因，别让用户以为按钮坏了
            messagebox.showwarning(tr("inst_rt_title"), tr("inst_rt_cannot_ok"),
                                   parent=self)
            return
        if level == "warn":
            # 非空目录/同名文件都会走"清空后新建"，不可恢复 -> 二次确认
            if not messagebox.askyesno(tr("inst_rt_confirm_title"),
                                       tr("inst_rt_confirm_clear") % path,
                                       parent=self):
                return
        self.result = path
        self.destroy()


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
class Installer(tk.Tk if tk else object):
    def __init__(self):
        super().__init__()
        self.title(tr("inst_title"))
        self.geometry("620x520")
        self.resizable(False, False)
        self.cancel_flag = False
        self.ui_q = queue.Queue()
        self.after(50, self._drain_ui)

        pad = {"padx": 18, "pady": 6}
        # 右上角全屏切换（系统按钮风格，安装/下载日志较长时方便查看）
        top_row = tk.Frame(self)
        top_row.pack(fill="x")
        self.btn_full = tk.Button(
            top_row, command=self.toggle_fullscreen,
            relief="flat", bd=0, fg="#475569",
            activeforeground="#1d4ed8", cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        self.btn_full.pack(side="right", padx=14, pady=(8, 0))
        self.btn_full.config(text=tr("inst_fullscreen"))
        self.bind("<Escape>", self._exit_fullscreen)
        self.title_label = tk.Label(self, font=("Microsoft YaHei UI", 16, "bold"))
        self.title_label.pack(anchor="w", **pad)
        self.desc_label = tk.Label(self, justify="left", fg="#475569")
        self.desc_label.pack(anchor="w", **pad)

        row = tk.Frame(self)
        row.pack(fill="x", **pad)
        self.dir_label = tk.Label(row)
        self.dir_label.pack(side="left")
        self.dir_var = tk.StringVar(value=r"D:\AIGC_Detector")
        self.dir_entry = tk.Entry(row, textvariable=self.dir_var)
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.btn_browse = tk.Button(row, command=self.browse)
        self.btn_browse.pack(side="left")

        # 安装选项（均默认勾选）
        opt_row = tk.Frame(self)
        opt_row.pack(fill="x", **pad)
        self.chk_shortcut = tk.BooleanVar(value=True)
        self.chk_launch = tk.BooleanVar(value=True)
        self.cb_shortcut = tk.Checkbutton(opt_row, variable=self.chk_shortcut)
        self.cb_shortcut.pack(side="left")
        self.cb_launch = tk.Checkbutton(opt_row, variable=self.chk_launch)
        self.cb_launch.pack(side="left", padx=(14, 0))

        self.progress = ttk.Progressbar(self, maximum=100, length=560)
        self.progress.pack(fill="x", **pad)
        self.status = tk.StringVar()
        tk.Label(self, textvariable=self.status, fg="#1d4ed8").pack(anchor="w", **pad)

        self.log = tk.Text(self, height=10, state="disabled")
        self.log.pack(fill="both", expand=True, **pad)

        btns = tk.Frame(self)
        btns.pack(fill="x", **pad)
        self.btn_start = tk.Button(btns, command=self.start, width=14)
        self.btn_start.pack(side="right")
        self.btn_cancel = tk.Button(btns, command=self.cancel, width=10, state="disabled")
        self.btn_cancel.pack(side="right", padx=6)
        self.btn_lang = tk.Button(btns, command=self.toggle_lang, width=6)
        self.btn_lang.pack(side="left")
        self.author_label = tk.Label(self, fg="#94a3b8", anchor="w")
        self.author_label.pack(
            fill="x", padx=18, pady=(0, 10)
        )
        self._apply_lang()

    def _apply_lang(self):
        self.title(tr("inst_title"))
        self.title_label.config(text=tr("inst_heading") % (APP_NAME, APP_VER))
        self.desc_label.config(text=tr("inst_desc"))
        self.dir_label.config(text=tr("inst_dir_label"))
        self.cb_shortcut.config(text=tr("inst_opt_shortcut"))
        self.cb_launch.config(text=tr("inst_opt_launch"))
        self.btn_browse.config(text=tr("inst_browse"))
        self.btn_start.config(text=tr("inst_start"))
        self.btn_cancel.config(text=tr("inst_cancel"))
        self.btn_lang.config(text="EN" if get_lang() == "zh" else "中文")
        self.author_label.config(text=tr("inst_author_email") % AUTHOR_CONTACT)
        if not self.status.get():
            self.status.set(tr("inst_ready"))

    def toggle_lang(self):
        set_lang("en" if get_lang() == "zh" else "zh")
        self._apply_lang()

    def toggle_fullscreen(self):
        fs = not self.attributes("-fullscreen")
        self.attributes("-fullscreen", fs)
        self.btn_full.config(text=tr("inst_fullscreen_exit") if fs else tr("inst_fullscreen"))

    def _exit_fullscreen(self, event=None):
        if self.attributes("-fullscreen"):
            self.attributes("-fullscreen", False)
            self.btn_full.config(text=tr("inst_fullscreen"))

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get() or "D:\\")
        if d:
            self.dir_var.set(d)

    def _drain_ui(self):
        try:
            while True:
                fn, args = self.ui_q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(50, self._drain_ui)

    def _ui(self, fn, *args):
        self.ui_q.put((fn, args))

    def log_msg(self, msg):
        self._ui(self._log_impl, msg)

    def _log_impl(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def set_status(self, msg, pct=None):
        self._ui(self._status_impl, msg, pct)

    def _status_impl(self, msg, pct):
        self.status.set(msg)
        if pct is not None:
            self.progress["value"] = pct

    def cancel(self):
        self.cancel_flag = True
        self.set_status(tr("inst_cancelling"))

    def ask_manual_file(self):
        """所有源下载失败时，让用户选择本地已下载的 Python 便携包。"""
        box = {"path": None}
        ev = threading.Event()

        def ask():
            p, _ = filedialog.askopenfilename(
                title=tr("inst_manual_pick_title"),
                filetypes=[PY_NAME, ("所有文件", "*.*")],
            )
            box["path"] = p or None
            ev.set()

        self._ui(ask)
        while not ev.wait(0.2):
            if self.cancel_flag:
                return None
        return box["path"]

    def default_runtime_dir(self):
        """环境路径默认值：``<安装目录>\\runtime\\python``。

        **实时读安装目录**（用户改了目录再点开始，默认值得跟着变），
        不缓存上次的选择 —— 缓存会让两者不一致。
        """
        target = self.dir_var.get().strip() or r"D:\AIGC_Detector"
        return os.path.join(target, "runtime", "python")

    def start(self):
        # 先在主线程弹「运行环境」对话框（tkinter 不能在子线程弹窗）；
        # 用户直接关掉对话框 = 取消安装，不往下走
        dlg = RuntimeDialog(self, self.default_runtime_dir())
        self.wait_window(dlg)
        if not dlg.result:
            return
        self.runtime_dir = dlg.result

        self.cancel_flag = False
        self.btn_start.config(state="disabled")
        self.btn_cancel.config(state="normal")
        threading.Thread(target=self.run_install, daemon=True).start()

    def run_install(self):
        try:
            target = self.dir_var.get().strip() or r"D:\AIGC_Detector"
            perform_install(
                target,
                log=self.log_msg,
                status=self.set_status,
                cancelled=lambda: self.cancel_flag,
                ask_manual=self.ask_manual_file,
                opt_shortcut=self.chk_shortcut.get(),
                opt_launch=self.chk_launch.get(),
                lang=get_lang(),
                runtime_dir=getattr(self, "runtime_dir", None),
            )
        except Exception as e:
            self.set_status(tr("inst_failed_prefix") % e)
            self.log_msg(tr("inst_fail_log") % e)
            self._ui(lambda: messagebox.showerror(tr("inst_fail_title"), str(e)))
            # 失败才复位按钮，让用户能改目录 / 重试
            self._ui(self._idle_buttons)
            return
        # 成功：提示一次后**关掉安装器**。
        # 留着这个窗口有两个坏处：① 用户以为还没装完；② "开始安装"又能点了，
        # 顺手再点一次就是把几 GB 依赖重装一遍（实测用户正好停在这一步）。
        self._ui(self._finish_ok)

    def _idle_buttons(self):
        self.btn_start.config(state="normal")
        self.btn_cancel.config(state="disabled")

    def _finish_ok(self):
        messagebox.showinfo(tr("inst_done_title"),
                            tr("inst_done_box") % APP_NAME, parent=self)
        self.destroy()


def _cli(argv):
    """无界面安装：python installer.py --cli [目标目录]。自测 / 静默部署用。"""
    target = None
    for i, a in enumerate(argv):
        if a in ("--cli", "--install-cli") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            target = argv[i + 1]
    target = target or r"D:\AIGC_Detector"
    print("[CLI] 安装目标: %s" % target)
    try:
        perform_install(
            target,
            log=lambda m: print("  " + str(m), flush=True),
            status=lambda m, p=None: print("[状态] %s%s" % (m, "" if p is None else " (%d%%)" % p), flush=True),
            opt_shortcut="--no-shortcut" not in argv,
            opt_launch=False,
        )
    except Exception as e:
        print("[CLI] 安装失败: %s" % e)
        return 1
    print("[CLI] 安装完成: %s" % target)
    return 0


if __name__ == "__main__":
    if "--cli" in sys.argv or "--install-cli" in sys.argv:
        sys.exit(_cli(sys.argv[1:]))
    if tk is None:
        print("当前解释器缺少 tkinter，无法显示安装界面。请直接双击安装器 exe，"
              "或使用命令行：installer.exe --cli <目标目录>")
        sys.exit(2)
    Installer().mainloop()
