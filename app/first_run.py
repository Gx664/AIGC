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
from core.netfix import apply_env_fix, sanitize_env  # noqa: E402

LOG_PATH = os.path.join(APP_DIR, "logs", "first_run.log")
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
TORCH_CUDA_MIRRORS = [
    "https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu128",
    "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128",
    "https://download.pytorch.org/whl/cu128",
]
DEPS = ["PySide6", "transformers", "accelerate", "docx", "pypdf", "numpy"]
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
    return [m for m in DEPS if not module_ok(m)]


def torch_ok():
    return module_ok("torch") and module_ok("torchvision")


def has_nvidia():
    if shutil.which("nvidia-smi"):
        return True
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.exists(os.path.join(sysroot, "System32", "nvapi64.dll"))


def run_pip(args, on_line):
    """执行 pip 命令，逐行回调输出，返回退出码。

    注意：必须用 RUNTIME_PY 而不是 sys.executable —— 打包成 first_run_gui.exe 后
    sys.executable 指向 exe 自身，拿它跑 pip 会直接失败。
    """
    env = sanitize_env()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [RUNTIME_PY, "-m", "pip", "install", "--progress-bar", "off"] + args,
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
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def log_line(self, msg):
        self.q.put(("log", msg))

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
            need = deps_missing()
            need_torch = not torch_ok()
            if not need and not need_torch:
                self.set_status(tr("fr_recheck_ok"), 100)
                self.launch()
                return

            self.set_status(tr("fr_need_deps"), 2)
            self.log_line(tr("fr_need_deps"))

            if need_torch:
                if has_nvidia():
                    self.log_line(tr("fr_gpu_found"))
                    self.phase_torch_cuda()
                else:
                    self.log_line(tr("fr_gpu_none"))
                    self.phase_torch_cpu()

            need = deps_missing()
            if need:
                self.set_status(tr("fr_deps_phase"), 70)
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
        raise RuntimeError("PyTorch CUDA install failed (rc=%s)" % last_err)

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

# aigc-toolkit: file purpose marker
