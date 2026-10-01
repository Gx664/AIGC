"""首次启动引导器：缺什么装什么，装完自动进主界面。

设计：安装器只负责 Python 便携运行时（embeddable）+ 程序本体；PyTorch /
PySide6 / transformers 等组件在本引导器里带进度下载安装，AI 检测模型则由
主程序在首次检测时按所选镜像下载。

可独立运行（源码模式，用当前解释器），也可由 PyInstaller 打包成
first_run_gui.exe（自带 tkinter 界面，因为 embeddable Python 没有 tkinter），
此时所有检测/pip/启动动作都指向安装目录的 runtime\\python。
"""

import importlib.util
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

if getattr(sys, "frozen", False):
    # first_run_gui.exe：资源在 _MEIPASS，工作目录在 exe 所在的 app 目录
    RESOURCE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = RESOURCE_DIR

# runtime\python\python.exe：真正的目标解释器（依赖装在这里、主程序由它启动）
_runtime_py = os.path.join(os.path.dirname(APP_DIR), "runtime", "python", "python.exe")
RUNTIME_PY = _runtime_py if os.path.exists(_runtime_py) else sys.executable

sys.path.insert(0, RESOURCE_DIR)
sys.path.insert(0, os.path.join(RESOURCE_DIR, "core"))

from core.i18n import tr  # noqa: E402
from core.gpuinfo import detect as gpu_detect  # noqa: E402
from core.netfix import apply_env_fix, sanitize_env  # noqa: E402

LOG_PATH = os.path.join(APP_DIR, "logs", "first_run.log")
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
# pip 的下载缓存目录 —— **放我们自己的地盘**（app/ 下）。
#
# 为什么不让它用默认的 %LOCALAPPDATA%\pip\Cache：
#   * 装 CUDA 版 torch 会在缓存里留 2~3GB 的 wheel，纯占地方；
#   * 全局缓存是全用户共享的，我们无权也不该去清理别人；
#   * 放 app/ 下，卸载时随 app 一起删，天然回收。
# 装完（或重试时选「重新开始」）由 _clean_caches() 清空。
PIP_CACHE = os.path.join(APP_DIR, "_pipcache")
# pip 的**临时目录**也收到我们自己的地盘。为什么必须这样：
#   ``--cache-dir`` 只决定"下载完之后缓存放哪"，pip 下载**途中**的数据写在
#   ``tempfile`` 目录（``%TEMP%\\pip-xxxx``）—— 于是按"缓存目录字节"画进度条
#   会长时间不动、下完才跳（实测：3.5GB 的 torch 卡在 11.5MB 不动，2 分 45 秒
#   后直接跳到 3.4GB）。把 TEMP 指到这里，两部分字节都能统计到。
PIP_TMP = os.path.join(APP_DIR, "_piptmp")
# PyTorch wheel 源（国内镜像 -> 官方兜底）；实际 URL = ``<base>/<cuXXX>``，
# 其中 cuXXX 由 gpuinfo 按**驱动支持的 CUDA 版本**选（见 app/core/gpuinfo.py）。
#
# **实测（2026-09-24，别再踩）**：
#   清华 mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/ -> 404，**已失效**（别放首位）
#   阿里云 / 华为云 -> 索引里只有 Linux wheel，Windows 装了会失败
#   上海交大 mirror.sjtu.edu.cn/pytorch-wheels/ -> 有 win_amd64，cu128/cu129 都齐 ✓
TORCH_MIRRORS = [
    "https://mirror.sjtu.edu.cn/pytorch-wheels",
    "https://download.pytorch.org/whl",
]
# 依赖清单：(导入名, pip 包名, 版本约束)
#
# **导入名 ≠ pip 包名**：python-docx 的导入名是 docx，若直接把 "docx" 交给 pip，
# 会装成 PyPI 上 2014 年的另一个旧库（实测核实过）—— 两者必须分开写。
#
# 版本约束的理由：本项目用的是 transformers 5.x 的 API（勿降级），
# 上游一旦发 6.x 改了 API，不锁版本的新装用户会直接崩；锁住主版本即可。
DEPS = [
    ("PySide6", "PySide6", ">=6.9,<7"),
    ("transformers", "transformers", ">=5.17,<6"),
    ("accelerate", "accelerate", ""),
    ("docx", "python-docx", ""),
    ("pypdf", "pypdf", ""),
    ("numpy", "numpy", ""),
]
AUTHOR_EMAIL = "gxgx3456@qq.com"


def module_ok(name):
    """在目标解释器（runtime python）里检查模块是否存在（find_spec 不执行代码，快）。"""
    if os.path.normcase(os.path.abspath(RUNTIME_PY)) != os.path.normcase(
        os.path.abspath(sys.executable)
    ):
        try:
            out = subprocess.run(
                [
                    RUNTIME_PY, "-c",
                    "import importlib.util as u,sys;"
                    "sys.exit(0 if u.find_spec(%r) else 1)" % name,
                ],
                capture_output=True, timeout=60,
                creationflags=CREATE_NO_WINDOW,
            )
            return out.returncode == 0
        except Exception:
            return False
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def deps_missing():
    """返回缺失依赖的 **pip 包名（带版本约束）** 列表。

    注意返回的是 pip 名而不是导入名 —— 见 ``DEPS`` 上方的说明。
    """
    return [pkg + spec for mod, pkg, spec in DEPS if not module_ok(mod)]


def torch_ok():
    return module_ok("torch") and module_ok("torchvision")


def cuda_available():
    """在 runtime 解释器里**真**试一次 CUDA（import torch + 分配张量）。

    为什么要真试：驱动太旧时 pip 照样能装成功、文件也都在，但
    ``torch.cuda.is_available()`` 是 False —— 只查"文件在不在"发现不了，
    用户会拿到一个"装了 GPU 版却用不了"的环境。
    """
    if os.path.normcase(os.path.abspath(RUNTIME_PY)) == os.path.normcase(
            os.path.abspath(sys.executable)):
        return False        # 还在用引导器自己的解释器，没法判断
    try:
        out = subprocess.run(
            [RUNTIME_PY, "-c",
             "import torch,sys;sys.exit(0 if torch.cuda.is_available() else 1)"],
            capture_output=True, timeout=300,
            creationflags=CREATE_NO_WINDOW,
        )
        return out.returncode == 0
    except Exception:
        return False


# --------------------------------------------------------------------------
# 真实的下载进度（pip 没有进度 API，只能从它的输出 + 缓存目录反推）
# --------------------------------------------------------------------------
# **为什么不做"定时器走到 99% 再跳完"**：那是假进度，网络慢时用户以为卡死，
# 想判断"还要多久"也判断不了。这里的百分比来自真实字节数：
#     分母 = pip 输出的 "Downloading xxx (2.6 GB)" 逐行累加
#     分子 = --cache-dir 目录的实际字节数（每 0.1 秒量一次）
# 任一侧拿不到（pip 换了输出格式 / 走的是本地缓存）→ 退化成"只报已下载量"，
# **绝不编一个百分比出来**。
_PIP_SIZE_RE = re.compile(r"Downloading\s+\S+\s+\(([\d.]+)\s*([kKMGT]?)B\)")
_SIZE_UNIT = {"": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3, "t": 1024 ** 4}


def _fmt_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


def _fmt_mmss(sec):
    sec = max(0, int(sec))
    return "%02d:%02d" % (sec // 60, sec % 60)


def _dir_bytes(path):
    """目录总字节数（量不出来就当 0，不抛）。"""
    total = 0
    try:
        for root_dir, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root_dir, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


class PipProgress:
    """装包期间每 0.1 秒回调一次真实进度。

    :param cache_dir: pip 的 ``--cache-dir``（下载的字节都落在这里）
    :param on_tick: ``on_tick(text, pct)``；``pct`` 为 None 表示"不确定模式"
    :param prefix: 显示前缀（如"下载中："）
    """

    def __init__(self, cache_dir, on_tick, prefix=""):
        self.cache = cache_dir
        self.on_tick = on_tick
        self.prefix = prefix
        self.expect = 0            # 预期总字节；0 = 还不知道（走不确定模式）
        self.done = 0
        self.t0 = time.time()
        self._stop = threading.Event()
        self.install_phase = False
        # 基线：本阶段开始前，缓存目录与临时目录里**已有**的字节（上一阶段下好的包）。
        # 不减掉它，第二阶段的"已下载"会直接超过分母（实测 3.6GB / 275.5MB > 100%）。
        self.base = _dir_bytes(cache_dir) + _dir_bytes(PIP_TMP)

    def feed(self, line):
        """喂一行 pip 输出：攒分母；并识别"下载完、开始安装"的转折。"""
        if "Installing collected packages" in (line or ""):
            # 下载阶段结束。此后字节不再增长，进度条不该再当"下载"用 ——
            # 改成只报已下载量 + 安装中，免得卡在 97% 让人以为死了。
            self.install_phase = True
            return
        m = _PIP_SIZE_RE.search(line or "")
        if m:
            unit = (m.group(2) or "").lower()
            self.expect += float(m.group(1)) * _SIZE_UNIT.get(unit, 1)

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(0.1):        # 0.1 秒一跳（按用户要求）
            self.done = max(
                _dir_bytes(self.cache) + _dir_bytes(PIP_TMP) - self.base, 0)
            elapsed = time.time() - self.t0
            if self.install_phase:
                self.on_tick(
                    "%s已下载 %s ｜ 安装中 ｜ 已用 %s"
                    % (self.prefix, _fmt_size(self.done), _fmt_mmss(elapsed)),
                    None,
                )
            elif self.expect > 0:
                pct = min(99, int(self.done * 100 / self.expect))
                # 起步阶段算不出剩余就显示 `--:--`：写 00:00 是在说"马上好"，
                # 而实际还要等好几分钟（实测第一屏就是 11.5MB / 3.5GB + 00:00）。
                eta_txt = _fmt_mmss(elapsed / pct * (100 - pct)) if pct > 0 else "--:--"
                self.on_tick(
                    "%s%s / %s ｜ 已用 %s ｜ 剩余 %s"
                    % (self.prefix, _fmt_size(self.done), _fmt_size(self.expect),
                       _fmt_mmss(elapsed), eta_txt),
                    pct,
                )
            else:
                self.on_tick(
                    "%s已下载 %s ｜ 已用 %s"
                    % (self.prefix, _fmt_size(self.done), _fmt_mmss(elapsed)),
                    None,
                )


def run_pip(args, on_line, progress=None):
    """执行 pip 命令，逐行回调输出，返回退出码。

    注意 1：必须用 RUNTIME_PY 而不是 sys.executable —— 打包成 first_run_gui.exe 后
    sys.executable 指向 exe 自身，拿它跑 pip 会直接失败。
    注意 2：``progress`` 传了 ``PipProgress`` 时，装包期间会每 0.1 秒回调真实进度。
    """
    env = sanitize_env()
    env["PYTHONUNBUFFERED"] = "1"
    # 见 PIP_TMP 的说明：pip 下载途中的数据落在 TEMP 下，指到我们自己的目录
    # 才能被进度条统计到（也顺带不往用户 %TEMP% 里倒垃圾）。
    env["TEMP"] = PIP_TMP
    env["TMP"] = PIP_TMP
    for d in (PIP_CACHE, PIP_TMP):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
    proc = subprocess.Popen(
        [RUNTIME_PY, "-m", "pip", "install", "--progress-bar", "off",
         "--cache-dir", PIP_CACHE] + args,
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        creationflags=CREATE_NO_WINDOW,
    )
    if progress:
        progress.start()
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if progress:
                progress.feed(line)     # 从 "Downloading x (2.6 GB)" 攒分母
            on_line(line)
        return proc.wait()
    finally:
        if progress:
            progress.stop()


def _retry_dialog(parent, err):
    """安装失败弹窗：三个按钮（继续 / 重新开始 / 退出）。

    为什么不用 ``messagebox.askyesnocancel``：它的按钮文案固定是「是 / 否 / 取消」，
    表达不出这三个动作的不同后果（取消还会被误解成"放弃本次安装"）。
    """
    import tkinter as tk

    dlg = tk.Toplevel(parent)
    dlg.title(tr("fr_retry_title"))
    dlg.resizable(False, False)
    box = {"v": "quit"}

    tk.Label(dlg, text=tr("fr_retry_title"),
             font=("Microsoft YaHei UI", 13, "bold")).pack(
        anchor="w", padx=18, pady=(16, 4))
    tk.Label(dlg, text=str(err)[:300], fg="#b91c1c", justify="left",
             wraplength=520, anchor="w").pack(fill="x", padx=18, pady=(0, 8))
    tk.Label(dlg, text=tr("fr_retry_hint"), justify="left",
             wraplength=520, anchor="w").pack(fill="x", padx=18, pady=(0, 12))

    row = tk.Frame(dlg)
    row.pack(fill="x", padx=18, pady=(0, 16))

    def pick(v):
        box["v"] = v
        dlg.destroy()

    tk.Button(row, text=tr("fr_retry_continue"), width=12,
              command=lambda: pick("retry")).pack(side="right")
    tk.Button(row, text=tr("fr_retry_restart"), width=12,
              command=lambda: pick("restart")).pack(side="right", padx=6)
    tk.Button(row, text=tr("fr_retry_quit"), width=10,
              command=lambda: pick("quit")).pack(side="right", padx=6)

    dlg.transient(parent)
    dlg.grab_set()
    parent.wait_window(dlg)
    return box["v"]


def icon_path():
    """应用图标路径；源码运行时在 app/assets，打包后在 _MEIPASS/app/assets。"""
    for p in (
        os.path.join(RESOURCE_DIR, "app", "assets", "icon.ico"),
        os.path.join(APP_DIR, "assets", "icon.ico"),
        os.path.join(RESOURCE_DIR, "assets", "icon.ico"),
    ):
        if os.path.exists(p):
            return p
    return ""


class FirstRun:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.root = tk.Tk()
        self.root.title(tr("fr_title"))
        # 窗口 / 任务栏图标（打包进 exe 的资源，缺了也不影响功能）
        _ico = icon_path()
        if _ico:
            try:
                self.root.iconbitmap(default=_ico)
            except Exception:
                try:
                    self.root.iconbitmap(_ico)
                except Exception:
                    pass
        self.root.geometry("620x420")
        self.root.resizable(False, False)

        self.q = queue.Queue()
        self.status_var = tk.StringVar(value=tr("fr_checking"))
        self.pct_var = tk.IntVar(value=0)

        tk.Label(
            self.root,
            text=tr("fr_title"),
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(self.root, textvariable=self.status_var, fg="#1d4ed8", justify="left").pack(
            anchor="w", padx=18, pady=4
        )
        ttk.Progressbar(
            self.root, length=560, maximum=100, variable=self.pct_var
        ).pack(anchor="w", padx=18, pady=4)
        self.log = tk.Text(self.root, height=14, state="disabled")
        self.log.pack(fill="both", expand=True, padx=18, pady=8)

        self.root.after(80, self._drain)
        threading.Thread(target=self.main, daemon=True).start()
        self.root.mainloop()

    # ---------- UI helpers ----------
    def _write_log(self, msg):
        try:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

    def _drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._write_log(payload)
                    self.log.config(state="normal")
                    self.log.insert("end", payload + "\n")
                    self.log.see("end")
                    self.log.config(state="disabled")
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "pct":
                    self.pct_var.set(payload)
                elif kind == "retry":
                    # 装失败时弹三选项对话框（必须主线程）；回完再放行子线程
                    err, ev, box = payload
                    try:
                        box["v"] = _retry_dialog(self.root, err)
                    finally:
                        ev.set()
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def log_line(self, msg):
        self.q.put(("log", msg))

    def on_download_tick(self, text, pct):
        """下载进度的每一跳（由 PipProgress 的轮询线程回调，每 0.1 秒一次）。

        ``pct`` 为 None = 不确定模式（拿不到总量）：**只更文字、不动进度条**，
        免得进度条乱跳让用户以为出问题。
        """
        self.q.put(("status", text))
        if pct is not None:
            self.q.put(("pct", pct))

    def set_status(self, msg, pct=None):
        self.q.put(("status", msg))
        if pct is not None:
            self.q.put(("pct", pct))

    def fatal(self, err):
        self.set_status(tr("fr_fail") % (err, AUTHOR_EMAIL), 0)

    # ---------- 主流程 ----------
    def main(self):
        try:
            self._write_log("=== first_run 启动 ===")
            self._write_log("RUNTIME_PY = %s" % RUNTIME_PY)
            apply_env_fix(self.log_line)  # socks 系统代理会让 pip 直接报 SOCKS 错
            if getattr(sys, "frozen", False) and os.path.normcase(
                os.path.abspath(RUNTIME_PY)
            ) == os.path.normcase(os.path.abspath(sys.executable)):
                # 打包成 exe 却没找到 runtime\python：说明安装不完整，别硬跑
                raise RuntimeError(tr("fr_no_runtime") % AUTHOR_EMAIL)

            # 装不好**不要直接退出** —— 弹「继续 / 重新开始 / 退出」让用户选。
            # 网络断掉是常见情况，直接从零来过对用户代价太大。
            while True:
                try:
                    self.install_all()
                    break
                except Exception as e:
                    self._write_log("install failed: %s" % e)
                    choice = self.ask_retry(e)
                    if choice == "quit":
                        raise
                    if choice == "restart":
                        self.clean_caches()
                    # retry：什么都不清，靠 pip 自己的重试/缓存接着来
                    self.set_status(tr("fr_need_deps"), 2)

            self.launch()
        except Exception as e:
            self._write_log("FATAL: %s" % traceback.format_exc())
            self.fatal(e)

    def install_all(self):
        """装齐 torch 与其余依赖。**必须幂等** —— 重试会反复调它。"""
        need = deps_missing()
        need_torch = not torch_ok()
        if not need and not need_torch:
            self.set_status(tr("fr_recheck_ok"), 100)
            return

        self.set_status(tr("fr_need_deps"), 2)
        self.log_line(tr("fr_need_deps"))

        if need_torch:
            # 探测显卡与 CUDA，决定装 GPU 版还是 CPU 版 ——
            # 探测结果是 i18n 文案，直接写进日志，用户能看懂为什么快/慢
            info = gpu_detect()
            self.log_line(info["reason"])
            if info["device"] == "cuda":
                self.phase_torch_cuda(info["index"])
            else:
                self.phase_torch_cpu()

        need = deps_missing()
        if need:
            self.set_status(tr("fr_deps_phase"), 70)
            prog = PipProgress(PIP_CACHE, self.on_download_tick,
                               tr("fr_dl_prefix"))
            rc = run_pip(need + ["--index-url", PYPI_MIRROR], self.log_line,
                         progress=prog)
            if rc != 0 or deps_missing():
                raise RuntimeError(
                    "pip exit %d (%s)" % (rc, ", ".join(deps_missing()) or "unknown"))
            self.log_line(tr("fr_recheck_ok"))

        self.set_status(tr("fr_launching"), 100)

    def clean_caches(self):
        """清掉 pip 缓存与下载缓存（供「重新开始」调用）。

        为什么必须清干净：pip 遇到半成品文件会报一些莫名其妙的错，
        用户选了「重新开始」就是要一个干净起点，留着残渣等于没重开。
        """
        targets = [PIP_CACHE, PIP_TMP, os.path.join(os.path.dirname(APP_DIR), "_downloads")]
        for p in targets:
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
        self.log_line(tr("fr_clean_caches"))

    def ask_retry(self, err):
        """请主线程弹失败对话框，返回 ``"retry"`` / ``"restart"`` / ``"quit"``。

        tkinter 只能在主线程操作，所以走队列 + Event 等结果（与
        ``installer.Installer.ask_manual_file`` 同一套办法）。
        """
        box = {"v": "quit"}
        ev = threading.Event()
        self.q.put(("retry", (err, ev, box)))
        ev.wait()
        return box["v"]

    def phase_torch_cuda(self, index):
        """装 GPU 版 torch。

        ``index`` 是索引名（``cu129`` / ``cu128`` / …），由 ``gpuinfo`` 按
        **驱动支持的 CUDA 版本**选出 —— 选高了会报
        "CUDA driver version is insufficient"，选低了浪费卡的性能。
        """
        self.set_status(tr("fr_torch_phase"), 5)
        last_err = None
        for base in TORCH_MIRRORS:
            url = "%s/%s" % (base, index)
            self.log_line(tr("inst_mirror_log") % url)
            # 装 torch 时用 --index-url 指向 pytorch 索引：该索引**自带** torch
            # 的全部依赖（filelock / sympy / networkx / jinja2 / fsspec …），
            # 所以切断默认 PyPI 也不会找不到依赖。
            prog = PipProgress(PIP_CACHE, self.on_download_tick,
                               tr("fr_dl_prefix"))
            rc = run_pip(
                ["torch", "torchvision", "--index-url", url],
                self.log_line, progress=prog,
            )
            if rc == 0 and torch_ok():
                break
            last_err = rc
        else:
            raise RuntimeError("PyTorch CUDA install failed (rc=%s)" % last_err)

        # **装完必须真验一次 CUDA**：驱动太旧时上面这步照样成功，但
        # torch.cuda.is_available() 是 False。这时回退 CPU 版，否则用户拿到
        # 一个"装了 GPU 版却用不了"的环境 —— 还得自己排错。
        if not cuda_available():
            self.log_line(tr("fr_cuda_fallback"))
            self.phase_torch_cpu()
            return
        self.set_status(tr("fr_torch_phase"), 65)

    def phase_torch_cpu(self):
        self.set_status(tr("fr_torch_phase"), 5)
        prog = PipProgress(PIP_CACHE, self.on_download_tick, tr("fr_dl_prefix"))
        rc = run_pip(
            ["torch", "torchvision", "--index-url", PYPI_MIRROR],
            self.log_line, progress=prog,
        )
        if rc != 0 or not torch_ok():
            raise RuntimeError("PyTorch install failed (rc=%d)" % rc)
        self.set_status(tr("fr_torch_phase"), 65)

    def launch(self):
        """启动主程序并关闭引导窗口。"""
        main_py = os.path.join(APP_DIR, "main.py")
        err_path = os.path.join(APP_DIR, "logs", "main_stderr.log")
        os.makedirs(os.path.dirname(err_path), exist_ok=True)
        err_f = open(err_path, "a", encoding="utf-8")
        err_f.write("\n===== launch %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        err_f.flush()
        subprocess.Popen(
            [RUNTIME_PY, main_py],
            cwd=APP_DIR,
            creationflags=CREATE_NO_WINDOW,
            stderr=err_f,
        )
        self.root.after(200, self.root.destroy)


if __name__ == "__main__":
    try:
        FirstRun()
    except Exception:
        try:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write("FATAL(boot): %s" % traceback.format_exc())
        except Exception:
            pass
        raise
