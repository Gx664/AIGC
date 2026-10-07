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
_FROZEN = getattr(sys, "frozen", False)


def _bootstrap_app_dir():
    """打包后 ``app/`` 源码目录到底在哪（此时还没法 import 适配层，只能自己找）。

    * **Windows** —— 引导器 ``first_run_gui.exe`` 与 app/ 源码同在
      ``<安装目录>/app/`` 里，``dirname(sys.executable)`` 就是它 → 行为不变
    * **Unix**    —— 可执行文件在产物根，源码被 PyInstaller 放进
      ``_internal/app``（macOS 的 .app 可能在外层的 Frameworks/Resources）；
      ``sys._MEIPASS`` 指向的正是 datas 落点，最可靠

    判据统一为"这一层有没有 ``main.py``"。
    """
    here = os.path.dirname(os.path.abspath(sys.executable))
    meipass = getattr(sys, "_MEIPASS", "") or ""
    for c in (
        here,                                        # Windows：exe 与源码同级
        os.path.join(meipass, "app") if meipass else "",   # Unix：datas 落点
        os.path.join(here, "app"),
        os.path.join(here, "_internal", "app"),
    ):
        if c and os.path.isfile(os.path.join(c, "main.py")):
            return os.path.normpath(c)
    return here


if _FROZEN:
    # 打包后：资源在 _MEIPASS，源码目录按实际布局探测（_internal 等）
    RESOURCE_DIR = sys._MEIPASS
    APP_DIR = _bootstrap_app_dir()
else:
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = RESOURCE_DIR

# 源码目录（APP_DIR）优先入 path：打包后 core/ 可能只在那儿（_internal/app/core）
for _p in (os.path.join(RESOURCE_DIR, "core"), RESOURCE_DIR,
           os.path.join(APP_DIR, "core"), APP_DIR):
    if _p and os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
del _p

from core import platform_ops  # noqa: E402
from core import runtime_deps  # noqa: E402
from core.i18n import tr  # noqa: E402
from core.gpuinfo import detect as gpu_detect  # noqa: E402
from core.meta import AUTHOR_CONTACT  # noqa: E402
from core.netfix import apply_env_fix, sanitize_env  # noqa: E402
from core.runtime_deps import has_nvidia  # noqa: E402

# 程序根目录（含 app/ 与 runtime/）：
#   Windows —— first_run_gui.exe 在 <安装目录>/app/ 里，上一级才是根
#   Unix    —— PyInstaller 的可执行文件与 app/ 平级，自己就是根
# 交给适配层按实际布局判断，两种都不写死。
PROGRAM_ROOT = (
    platform_ops.program_base_dir(sys.executable) if _FROZEN else os.path.dirname(APP_DIR)
)

# 数据根目录（settings.json 所在层级）：
#   Windows —— 与程序根相同（行为与改造前一致）
#   Unix    —— 用户目录，因为 .app / AppImage 里的包体是只读的
DATA_ROOT = platform_ops.effective_base_dir(PROGRAM_ROOT)
BASE_ROOT = DATA_ROOT

# 打包自带的解释器（只读）；Unix 首次启动要先把整个 runtime 复制到用户目录
BUNDLED_PY = platform_ops.runtime_python(PROGRAM_ROOT)
# 真正的目标解释器（依赖装在它这里、主程序由它启动）
_WORK_PY = platform_ops.work_python(PROGRAM_ROOT)
RUNTIME_PY = _WORK_PY if os.path.exists(_WORK_PY) else sys.executable


def refresh_runtime_py():
    """重新解析目标解释器。

    首次启动会把打包自带的 runtime 复制到可写位置，复制前后路径不同，
    所以复制完必须调一次（模块级 RUNTIME_PY 是快照）。
    """
    global RUNTIME_PY
    p = platform_ops.work_python(PROGRAM_ROOT)
    if os.path.exists(p):
        RUNTIME_PY = p
    return RUNTIME_PY

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

# 日志：Windows 维持原位置（app/logs，行为不变）；Unix 写到用户数据目录
LOG_DIR = (
    os.path.join(APP_DIR, "logs")
    if platform_ops.IS_WIN
    else os.path.join(DATA_ROOT, "logs")
)
LOG_PATH = os.path.join(LOG_DIR, "first_run.log")


# find_spec 不执行代码（快）。
_SPEC_PROBE = "import importlib.util as u,sys;sys.exit(0 if u.find_spec(%r) else 1)"
# 严格模式下真跑一次 import：能发现"找得到但一 import 就炸"的假健康包。
# find_spec 对这类包完全无感 —— PyPI 上的远古 docx 0.2.4 就是如此：被装上了、
# find_spec 说"已装"，但 Python 3 下一 import 就抛 No module named 'exceptions'。
# 注意不要改成"必须是包目录"这类通用限制：标准库 enum / json 等单文件模块会被误伤。
_IMPORT_PROBE = "import %s"


def module_ok(name, strict=False):
    """在目标解释器（runtime python）里检查模块是否可用。

    :param strict: True 时真的执行 ``import``（而不只是 find_spec），
        用于那些"能被找到但一 import 就炸"的包（见 ``runtime_deps.STRICT_IMPORT``）。
    """
    probe = (_IMPORT_PROBE % name) if strict else (_SPEC_PROBE % name)
    if os.path.normcase(os.path.abspath(RUNTIME_PY)) != os.path.normcase(
        os.path.abspath(sys.executable)
    ):
        try:
            out = subprocess.run(
                [RUNTIME_PY, "-c", probe],
                capture_output=True, timeout=60,
                creationflags=CREATE_NO_WINDOW,
            )
            return out.returncode == 0
        except Exception:
            return False
    try:
        if strict:
            __import__(name)
            return True
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def deps_missing():
    """返回**缺失或损坏**的组件（pip 包名，含版本约束）。

    ``DEPS`` 是 ``(导入名, pip 包名, 版本约束)`` 三元组 —— 导入名与 pip 名
    必须分开写（python-docx 的导入名是 docx），版本约束用来锁主版本
    （本项目用的是 transformers 5.x / PySide6 6.x 的 API）。
    对踩过坑的包还要真跑一次 import 才算健康（见 runtime_deps.STRICT_IMPORT）。
    """
    missing = []
    for imp, pip_name, spec in DEPS:
        if not module_ok(imp, strict=runtime_deps.needs_strict_import(imp)):
            missing.append(pip_name + spec)
    return missing


def torch_ok():
    return module_ok("torch") and module_ok("torchvision")


def pip_cwd():
    """pip 子进程的工作目录（必须是可写的）。

    Windows 维持 app 目录（与改造前一致）；Unix 用数据目录 —— AppImage 是
    只读的 squashfs 镜像、.app 常在 /Applications 下，在只读目录里跑 pip
    容易踩到写缓存的坑。任何异常都退回 APP_DIR，不让它成为失败原因。
    """
    if platform_ops.IS_WIN:
        return APP_DIR
    try:
        os.makedirs(DATA_ROOT, exist_ok=True)
        return DATA_ROOT
    except Exception:
        return APP_DIR
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


def run_pip_raw(pip_args, on_line, progress=None):
    """执行 ``pip <pip_args...>``，逐行回调输出，返回退出码。

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
        [RUNTIME_PY, "-m", "pip", "--cache-dir", PIP_CACHE] + list(pip_args),
        cwd=pip_cwd(),
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
             font=platform_ops.tk_font(13, bold=True)).pack(
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


def run_pip(args, on_line, progress=None):
    """执行 ``pip install <args...>``，逐行回调输出，返回退出码。"""
    return run_pip_raw(["install", "--progress-bar", "off"] + list(args), on_line,
                       progress)


def pkg_installed(pip_name):
    """询问 pip 该发行包是否已安装（用于决定要不要先卸掉它）。"""
    try:
        out = subprocess.run(
            [RUNTIME_PY, "-m", "pip", "show", pip_name],
            capture_output=True, timeout=60,
            creationflags=CREATE_NO_WINDOW,
        )
        return out.returncode == 0
    except Exception:
        return False


def purge_conflicting(pip_names, log_line):
    """装正确包之前，先卸掉会遮蔽它的旧同名包。

    典型：PyPI 上的 ``docx``（2011 年 Python 2 版，单文件 ``docx.py``）会遮蔽
    ``python-docx`` 提供的 ``docx/`` 包 —— 装错时它不仅让 .docx 解析整个失效，
    还会让"是否已安装"的检查一直返回真，导致永远修不好。
    """
    removed = []
    for pip_name in pip_names:
        for old in runtime_deps.old_pkgs_to_remove(pip_name):
            if not pkg_installed(old):
                continue  # 没装过就不必调用 pip
            log_line(tr("fr_purge_old") % old)
            rc = run_pip_raw(["uninstall", "-y", old], log_line)
            log_line("pip uninstall %s -> rc=%s" % (old, rc))
            removed.append(old)
    return removed


def icon_path():
    """应用图标路径；按平台挑格式（Windows→.ico / macOS→.icns / Linux→.png）。

    源码运行时在 app/assets，打包后在 _MEIPASS/app/assets。
    """
    return platform_ops.find_icon(
        os.path.join(RESOURCE_DIR, "app", "assets"),
        os.path.join(APP_DIR, "assets"),
        os.path.join(RESOURCE_DIR, "assets"),
    )


class FirstRun:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.root = tk.Tk()
        self.root.title(tr("fr_title"))
        # 窗口 / 任务栏图标（打包进产物的资源，缺了也不影响功能）
        # Windows 的 tkinter 只认 .ico（iconbitmap）；Unix 上要用 iconphoto + PNG，
        # 传 .ico 过去会直接抛 TclError。PhotoImage 必须留引用，否则会被回收。
        self._icon_img = None
        _ico = icon_path()
        if _ico and platform_ops.IS_WIN:
            try:
                self.root.iconbitmap(default=_ico)
            except Exception:
                try:
                    self.root.iconbitmap(_ico)
                except Exception:
                    pass
        elif _ico:
            try:
                self._icon_img = tk.PhotoImage(file=_ico)
                self.root.iconphoto(True, self._icon_img)
            except Exception:
                self._icon_img = None
        self.root.geometry("620x420")
        self.root.resizable(False, False)

        self.q = queue.Queue()
        # 后台线程 → 主线程询问的"回信"通道（选择框是模态的，必须在主线程弹）
        self.answer_q = queue.Queue()
        self.status_var = tk.StringVar(value=tr("fr_checking"))
        self.pct_var = tk.IntVar(value=0)

        tk.Label(
            self.root,
            text=tr("fr_title"),
            font=platform_ops.tk_font(14, bold=True),
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
                elif kind == "ask":
                    self.answer_q.put(self._ask_variant(payload))
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

    # ---------- 运行组件选择 ----------
    def ask_variant(self, default):
        """后台线程调用：请主线程弹选择框，然后等结果。"""
        self.q.put(("ask", default))
        try:
            return self.answer_q.get(timeout=600)
        except queue.Empty:
            return default

    def _ask_variant(self, default):
        """主线程里弹模态选择框，返回 "cuda" / "cpu"。关窗（未点按钮）时用默认值。"""
        tk, ttk = self.tk, self.ttk
        win = tk.Toplevel(self.root)
        win.title(tr("fr_pick_title"))
        win.transient(self.root)
        win.resizable(False, False)
        var = tk.StringVar(value=default)

        tk.Label(
            win,
            text=tr("fr_pick_head"),
            font=platform_ops.tk_font(11, bold=True),
            justify="left",
            wraplength=470,
        ).pack(anchor="w", padx=16, pady=(14, 8))
        def _radio(value, label):
            return tk.Radiobutton(
                win,
                text=label,
                variable=var,
                value=value,
                justify="left",
                wraplength=450,
                anchor="w",
            )

        _radio("cuda", tr("fr_pick_cuda")).pack(anchor="w", padx=24, pady=3)
        _radio("cpu", tr("fr_pick_cpu")).pack(anchor="w", padx=24, pady=3)
        tk.Label(
            win,
            text=tr("fr_pick_hint"),
            fg="#666666",
            justify="left",
            wraplength=470,
        ).pack(anchor="w", padx=16, pady=(8, 0))
        ttk.Button(win, text=tr("fr_pick_ok"), command=win.destroy).pack(pady=(12, 14))

        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.grab_set()
        win.wait_window()
        return runtime_deps.normalize_variant(var.get()) or default

    def fatal(self, err):
        self.set_status(tr("fr_fail") % (err, AUTHOR_CONTACT), 0)

    # ---------- 运行环境落地（Unix） ----------
    def ensure_runtime_local(self):
        """Unix：把打包自带的解释器复制到可写位置，之后依赖装在副本里。

        为什么要复制：macOS 的 .app 常驻 /Applications、AppImage 是只读镜像，
        包里那份解释器只能读不能写；而且 AppImage 每次挂载点都不同
        （/tmp/.mount_xxxx），在挂载点上建环境下次启动就废了。

        Windows 恒为"已就位"，本方法直接返回 —— 行为与改造前一致。
        """
        if platform_ops.runtime_is_local(PROGRAM_ROOT):
            return
        src = platform_ops.runtime_dir(PROGRAM_ROOT)
        dst = platform_ops.runtime_root(PROGRAM_ROOT)
        if not os.path.isdir(src):
            # 打包了却没有自带运行时：包体不完整，别硬跑
            raise RuntimeError(tr("fr_no_runtime") % AUTHOR_CONTACT)
        self.set_status(tr("fr_prep_runtime"), 1)
        self.log_line(tr("fr_prep_runtime"))
        self.log_line("%s -> %s" % (src, dst))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            shutil.rmtree(dst)  # 清掉上次复制到一半留下的残骸
        shutil.copytree(src, dst, symlinks=True)
        try:
            # 复制过程可能丢掉可执行位
            os.chmod(platform_ops.work_python(PROGRAM_ROOT), 0o755)
        except OSError:
            pass

    def ensure_desktop_entry(self):
        """Linux：装一个 .desktop 桌面入口（用户级，不需要 root）。

        失败不算致命 —— 入口只是锦上添花，不该拦住用户用软件。
        """
        if platform_ops.shortcut_mode() != "desktop":
            return
        try:
            exe = sys.executable if _FROZEN else os.path.join(APP_DIR, "main.py")
            icon = platform_ops.find_icon(
                os.path.join(RESOURCE_DIR, "app", "assets"),
                os.path.join(APP_DIR, "assets"),
            )
            p = platform_ops.install_desktop_entry(exe, icon)
            if p:
                self.log_line(tr("fr_desktop_done") % p)
        except Exception as e:  # noqa: BLE001 - 入口失败不影响主流程
            self._write_log("desktop entry failed: %r" % (e,))

    # ---------- 主流程 ----------
    def main(self):
        try:
            self._write_log("=== first_run 启动 ===")
            self._write_log(platform_ops.describe())
            self._write_log("PROGRAM_ROOT = %s" % PROGRAM_ROOT)
            self._write_log("DATA_ROOT    = %s" % DATA_ROOT)
            self._write_log("RUNTIME_PY   = %s" % RUNTIME_PY)
            apply_env_fix(self.log_line)  # socks 系统代理会让 pip 直接报 SOCKS 错

            self.ensure_runtime_local()
            refresh_runtime_py()

            if _FROZEN and os.path.normcase(os.path.abspath(RUNTIME_PY)) == os.path.normcase(
                os.path.abspath(sys.executable)
            ):
                # 打包了却没解析出自带运行时：说明包体不完整，别硬跑
                raise RuntimeError(tr("fr_no_runtime") % AUTHOR_CONTACT)

            self.ensure_desktop_entry()

            need = deps_missing()
            need_torch = not torch_ok()
            if not need and not need_torch:
                self.set_status(tr("fr_recheck_ok"), 100)
                self.launch()
                return

            self.set_status(tr("fr_need_deps"), 2)
            self.log_line(tr("fr_need_deps"))

            if need_torch:
                gpu = has_nvidia()
                if gpu:
                    self.log_line(tr("fr_gpu_found"))
                # 有独立显卡才问（CUDA 版约 3GB / CPU 版约 0.2GB，差别值得让用户选）；
                # 没有显卡就装 CPU 版，不打扰。选过的记在 settings.json 里，重装时沿用。
                variant = runtime_deps.pick_variant(
                    gpu,
                    runtime_deps.get_variant(BASE_ROOT),
                    self.ask_variant,
                )
                runtime_deps.set_variant(BASE_ROOT, variant)
                self.log_line(tr("fr_cuda_chosen") if variant == runtime_deps.VARIANT_CUDA
                              else (tr("fr_cpu_chosen") if gpu else tr("fr_gpu_none")))
                self.install_torch(variant)

            need = deps_missing()
            if need:
                self.set_status(tr("fr_deps_phase"), 70)
                # 先清掉会遮蔽正确包的旧同名包（如远古 docx），否则装了也白装
                purge_conflicting(need, self.log_line)
                rc = run_pip(
                    need + ["--index-url", PYPI_MIRROR], self.log_line
                )
                if rc != 0 or deps_missing():
                    raise RuntimeError("pip exit %d (%s)" % (rc, ", ".join(deps_missing()) or "unknown"))
                self.log_line(tr("fr_recheck_ok"))

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
            # 重试**沿用用户已经选过的那一套**（settings.json 里的 torch_variant）：
            # 首轮问过就不再问，更不能偷偷换成另一套 —— 否则选了 CPU 的用户重试时
            # 会被换成 CUDA 版，白等几十分钟、多占几个 GB。
            variant = runtime_deps.get_variant(BASE_ROOT) or runtime_deps.default_variant(
                has_nvidia())
            self.install_torch(variant)

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

    def install_torch(self, variant):
        """按 ``variant`` 装 torch —— **全程唯一的入口**。

        首轮（``main``）与失败重试（``install_all``）都走这里，于是
        ``phase_torch_cuda`` 只有一个调用点，不会再出现"调用点漏传 index"
        这类签名错配（v1.3.6 的线上事故就是这么来的）。具体 CUDA 档位由
        ``gpuinfo`` 按**驱动支持的版本**选，探测理由直接写进日志，用户能
        看懂为什么快/慢。
        """
        info = gpu_detect()
        self.log_line(info["reason"])
        if variant == runtime_deps.VARIANT_CUDA:
            self.phase_torch_cuda(info["index"])
        else:
            self.phase_torch_cpu()

    def phase_torch_cuda(self, index=None):
        """装 GPU 版 torch。

        ``index`` 是索引名（``cu129`` / ``cu128`` / …），由 ``gpuinfo`` 按
        **驱动支持的 CUDA 版本**选出 —— 选高了会报
        "CUDA driver version is insufficient"，选低了浪费卡的性能。
        不传时自己探测一次，兜住漏传的调用点。
        """
        if not index:
            index = gpu_detect()["index"]
        if not index:
            # 驱动太老 / CUDA 版本串认不出 → 拿不到可用档位。不能拿 "<base>/"
            # 这种目录当索引源（pip 解析不出包，只会白等一轮超时），直接走 CPU 版。
            self.log_line(tr("fr_cuda_no_index"))
            runtime_deps.set_variant(BASE_ROOT, runtime_deps.VARIANT_CPU)
            return self.phase_torch_cpu()
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
            # 所有 CUDA 源都失败 → 自动回退 CPU 版，别让用户卡在"装不上"。
            # （CUDA 版约 3GB、对网络更敏感；CPU 版小得多，通常能装上）
            self.log_line(tr("fr_cuda_fallback") % last_err)
            runtime_deps.set_variant(BASE_ROOT, runtime_deps.VARIANT_CPU)
            return self.phase_torch_cpu()

        # **装完必须真验一次 CUDA**：驱动太旧时上面这步照样成功，但
        # torch.cuda.is_available() 是 False。这时回退 CPU 版，否则用户拿到
        # 一个"装了 GPU 版却用不了"的环境 —— 还得自己排错。
        if not cuda_available():
            self.log_line(tr("fr_cuda_fallback") % "cuda-not-available")
            runtime_deps.set_variant(BASE_ROOT, runtime_deps.VARIANT_CPU)
            return self.phase_torch_cpu()
        self.set_status(tr("fr_torch_phase"), 65)

    def phase_torch_cpu(self):
        """装 CPU 版 PyTorch。

        ⚠️ Unix 不能顺手用 PyPI 镜像：PyPI 上 **Linux** 的 torch wheel 默认捆了
        CUDA 运行库（约 2 GB），用户明明选的是"CPU 版"（约 0.2 GB）却下到 CUDA 版，
        白等几十分钟还吃磁盘。候选源交给 runtime_deps.cpu_mirrors() 决定 ——
        Windows 返回的就是普通 PyPI 镜像，与改造前完全一致。
        """
        self.set_status(tr("fr_torch_phase"), 5)
        last_rc = None
        for m in runtime_deps.cpu_mirrors():
            self.log_line(tr("inst_mirror_log") % m)
            prog = PipProgress(PIP_CACHE, self.on_download_tick, tr("fr_dl_prefix"))
            rc = run_pip(["torch", "torchvision", "--index-url", m], self.log_line,
                         progress=prog)
            if rc == 0 and torch_ok():
                self.set_status(tr("fr_torch_phase"), 65)
                return
            last_rc = rc
        raise RuntimeError("PyTorch install failed (rc=%s)" % last_rc)

    def launch(self):
        """启动主程序并关闭引导窗口。"""
        main_py = os.path.join(APP_DIR, "main.py")
        # 日志写 LOG_DIR：Windows 仍是 app/logs（行为不变）；Unix 是用户数据目录
        # —— 包体在只读挂载里，往 APP_DIR 写会失败
        err_path = os.path.join(LOG_DIR, "main_stderr.log")
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
    # CI 冒烟开关（对应 .github/workflows/cross-platform-build.yml 的「冒烟自测」）：
    # 能走到这里，说明**模块级 import 与常量计算已全部成功** —— 正是要验的东西。
    #
    # 为什么需要它：本文件在 Unix 侧由 unix_launcher.py 用 runpy **运行时**加载，
    # PyInstaller 的静态分析看不见它；若打包时没把 "first_run" 交给分析器
    # （见 packaging/AIGC_Toolkit_unix.spec 的 hiddenimports），它模块级 import 的
    # 那些标准库一个都不会进 PYZ，在干净机器上首启直接：
    #   ModuleNotFoundError: No module named 'queue'
    # （v1.3.7 的 AppImage 就是这样被 appimage.github.io 收录测试打回的。）
    #
    # ⚠️ 这个开关**必须**只依赖 os.environ，绝不能为了自测在本文件里新增任何 import
    #   —— 那会让分析器顺着它把模块收进去，自测就永远通过、彻底失去意义。
    if os.environ.get("AIGC_TOOLKIT_SELFTEST") == "1":
        print("SELFTEST_OK: first_run module-level imports resolved")
        raise SystemExit(0)
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
