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

from core import platform_ops  # noqa: E402
from core import runtime_deps  # noqa: E402
from core.i18n import tr  # noqa: E402
from core.meta import AUTHOR_CONTACT  # noqa: E402
from core.netfix import apply_env_fix, sanitize_env  # noqa: E402
from core.runtime_deps import (  # noqa: E402
    DEPS,
    PYPI_MIRROR,
    TORCH_CUDA_MIRRORS,
    has_nvidia,
)

LOG_PATH = os.path.join(APP_DIR, "logs", "first_run.log")
# 安装根目录（settings.json 所在层级）；APP_DIR 是 app 子目录
BASE_ROOT = os.path.dirname(APP_DIR)


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
    """返回**缺失或损坏**的组件（pip 包名列表）。

    检查用 import 名（与 pip 名可能不同，如 python-docx → docx），
    并对踩过坑的包做真实导入校验。
    """
    missing = []
    for pip_name in DEPS:
        imp = runtime_deps.import_name(pip_name)
        if not module_ok(imp, strict=runtime_deps.needs_strict_import(imp)):
            missing.append(pip_name)
    return missing


def torch_ok():
    return module_ok("torch") and module_ok("torchvision")


def run_pip_raw(pip_args, on_line):
    """执行 ``pip <pip_args...>``，逐行回调输出，返回退出码。

    注意：必须用 RUNTIME_PY 而不是 sys.executable —— 打包成 first_run_gui.exe 后
    sys.executable 指向 exe 自身，拿它跑 pip 会直接失败。
    """
    env = sanitize_env()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [RUNTIME_PY, "-m", "pip"] + list(pip_args),
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        creationflags=CREATE_NO_WINDOW,
    )
    for line in proc.stdout:
        line = line.strip()
        if line:
            on_line(line)
    return proc.wait()


def run_pip(args, on_line):
    """执行 ``pip install <args...>``，逐行回调输出，返回退出码。"""
    return run_pip_raw(["install", "--progress-bar", "off"] + list(args), on_line)


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
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def log_line(self, msg):
        self.q.put(("log", msg))

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
                raise RuntimeError(tr("fr_no_runtime") % AUTHOR_CONTACT)
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
                if variant == runtime_deps.VARIANT_CUDA:
                    self.log_line(tr("fr_cuda_chosen"))
                    self.phase_torch_cuda()
                else:
                    self.log_line(tr("fr_cpu_chosen") if gpu else tr("fr_gpu_none"))
                    self.phase_torch_cpu()

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

            self.set_status(tr("fr_launching"), 100)
            self.launch()
        except Exception as e:
            self._write_log("FATAL: %s" % traceback.format_exc())
            self.fatal(e)

    def phase_torch_cuda(self):
        self.set_status(tr("fr_torch_phase"), 5)
        last_err = None
        for m in TORCH_CUDA_MIRRORS:
            self.log_line(tr("inst_mirror_log") % m)
            rc = run_pip(
                ["torch", "torchvision", "--index-url", m], self.log_line
            )
            if rc == 0 and torch_ok():
                self.set_status(tr("fr_torch_phase"), 65)
                return
            last_err = rc
        # 所有 CUDA 源都失败 → 自动回退 CPU 版，别让用户卡在"装不上"。
        # （CUDA 版约 3GB、对网络更敏感；CPU 版小得多，通常能装上）
        self.log_line(tr("fr_cuda_fallback") % last_err)
        runtime_deps.set_variant(BASE_ROOT, runtime_deps.VARIANT_CPU)
        return self.phase_torch_cpu()

    def phase_torch_cpu(self):
        self.set_status(tr("fr_torch_phase"), 5)
        rc = run_pip(
            ["torch", "torchvision", "--index-url", PYPI_MIRROR], self.log_line
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
