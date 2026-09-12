"""AI 检测工具箱 安装器（不打包 AI 环境，运行时下载）。"""

import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, ttk

APP_NAME = "AI 检测工具箱"
PY_VER = "3.12.10"
PY_NAME = "python-%s-amd64.exe" % PY_VER
PY_URLS = [
    "https://www.python.org/ftp/python/%s/%s" % (PY_VER, PY_NAME),
    "https://registry.npmmirror.com/-/binary/python/%s/%s" % (PY_VER, PY_NAME),
]
TORCH_MIRRORS = [
    "https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu128",
    "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128",
    "https://download.pytorch.org/whl/cu128",
]
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
AUTHOR_EMAIL = "gxgx3456@qq.com"


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


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(tr("inst_title"))
        self.geometry("620x520")
        self.resizable(False, False)
        self.cancel_flag = False
        self.ui_q = queue.Queue()
        self.after(50, self._drain_ui)

        pad = {"padx": 18, "pady": 6}
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
        self.title_label.config(text=tr("inst_heading") % APP_NAME)
        self.desc_label.config(text=tr("inst_desc"))
        self.dir_label.config(text=tr("inst_dir_label"))
        self.btn_browse.config(text=tr("inst_browse"))
        self.btn_start.config(text=tr("inst_start"))
        self.btn_cancel.config(text=tr("inst_cancel"))
        self.btn_lang.config(text="EN" if get_lang() == "zh" else "中文")
        self.author_label.config(text=tr("inst_author_email") % AUTHOR_EMAIL)
        if not self.status.get():
            self.status.set(tr("inst_ready"))

    def toggle_lang(self):
        set_lang("en" if get_lang() == "zh" else "zh")
        self._apply_lang()

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

    def start(self):
        self.cancel_flag = False
        self.btn_start.config(state="disabled")
        self.btn_cancel.config(state="normal")
        threading.Thread(target=self.run_install, daemon=True).start()

    def run_cmd(self, args, cwd=None):
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        for line in proc.stdout:
            line = line.strip()
            if line:
                self.log_msg(line)
        return proc.wait()

    def check_import(self, vp, code):
        """检查环境中是否已存在某个组件（True=已存在，无需安装）。"""
        try:
            out = subprocess.run(
                [vp, "-c", code],
                capture_output=True,
                text=True,
                timeout=180,
                creationflags=CREATE_NO_WINDOW,
            )
            return out.returncode == 0 and "TRUE" in out.stdout.upper()
        except Exception:
            return False

    def download(self, url, dest):
        self.log_msg(tr("inst_download_log") % url)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        tmp = dest + ".part"
        with urllib.request.urlopen(req, timeout=60) as r:
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
                        self.set_status(tr("inst_download_python_pct") % pct, pct)
                    if self.cancel_flag:
                        raise RuntimeError(tr("inst_cancelled"))
        os.replace(tmp, dest)

    def run_install(self):
        try:
            target = self.dir_var.get().strip() or r"D:\AIGC_Detector"
            dl = os.path.join(target, "_downloads")
            runtime = os.path.join(target, "runtime")
            pydir = os.path.join(runtime, "python")
            venv = os.path.join(runtime, "venv")
            appdir = os.path.join(target, "app")
            os.makedirs(dl, exist_ok=True)

            # 1. Python - 优先使用已安装的系统 Python
            self.set_status("检测系统 Python...", 5)
            sys_python = None
            for cmd in ["python", "python3", "python3.12"]:
                for ext in ["", ".exe"]:
                    try:
                        out = subprocess.run(
                            [cmd + ext, "-c", "import sys; print(sys.version)"],
                            capture_output=True, text=True, timeout=10,
                            creationflags=CREATE_NO_WINDOW,
                        )
                        if out.returncode == 0 and "3.12" in out.stdout:
                            sys_python = shutil.which(cmd + ext)
                            self.log_msg("检测到系统 Python: %s (%s)" % (sys_python, out.stdout.strip()))
                            break
                    except Exception:
                        pass
                if sys_python:
                    break

            if sys_python:
                sys_py_dir = os.path.dirname(os.path.dirname(sys_python))
                self.log_msg("系统 Python 目录: %s" % sys_py_dir)
                self.log_msg("目标目录: %s" % pydir)
                if os.path.exists(pydir):
                    shutil.rmtree(pydir, ignore_errors=True)
                try:
                    shutil.copytree(sys_py_dir, pydir)
                    self.log_msg("已复制系统 Python 到目标目录")
                    self.set_status(tr("inst_python_installed"), 25)
                except Exception as e:
                    self.log_msg("复制失败: %s，尝试直接使用系统 Python" % e)
                    pydir = sys_py_dir

            if not os.path.exists(os.path.join(pydir, "python.exe")):
                pyexe = os.path.join(dl, PY_NAME)
                if not os.path.exists(pyexe):
                    self.set_status(tr("inst_download_python"), 3)
                    err = None
                    for u in PY_URLS:
                        try:
                            self.download(u, pyexe)
                            err = None
                            break
                        except Exception as e:
                            err = e
                            self.log_msg(tr("inst_python_dl_fail") % e)
                    if err:
                        raise RuntimeError(tr("inst_python_dl_err") % err)
                else:
                    self.set_status(tr("inst_python_downloaded"), 20)

                self.set_status(tr("inst_install_python"), 22)
                self.log_msg("目标目录: %s" % pydir)
                os.makedirs(pydir, exist_ok=True)
                args = [
                    pyexe, "/quiet",
                    "InstallAllUsers=0",
                    "TargetDir=%s" % pydir,
                    "Include_pip=1", "Include_launcher=0",
                    "PrependPath=0", "Shortcuts=0", "Include_test=0",
                ]
                self.log_msg("执行: %s" % " ".join(args))
                rc = subprocess.call(args, creationflags=CREATE_NO_WINDOW)
                self.log_msg("退出码: %d" % rc)
                if not os.path.exists(os.path.join(pydir, "python.exe")):
                    local_appdata = os.environ.get("LOCALAPPDATA", "")
                    default_py = os.path.join(local_appdata, "Programs", "Python", "Python312")
                    if os.path.exists(os.path.join(default_py, "python.exe")):
                        self.log_msg("从默认位置复制: %s" % default_py)
                        shutil.copytree(default_py, pydir, dirs_exist_ok=True)
                    else:
                        raise RuntimeError(tr("inst_python_inst_err") % rc)
            else:
                self.set_status(tr("inst_python_installed"), 25)

            # 2. venv
            if not os.path.exists(os.path.join(venv, "Scripts", "python.exe")):
                self.set_status(tr("inst_create_venv"), 28)
                self.run_cmd([os.path.join(pydir, "python.exe"), "-m", "venv", venv])
            vp = os.path.join(venv, "Scripts", "python.exe")

            # 3. pip 升级（先检查版本，已较新则跳过）
            self.set_status(tr("inst_check_pip"), 32)
            if self.check_import(vp, "import pip; print(pip.__version__ >= '25')"):
                self.log_msg(tr("inst_pip_skip"))
            else:
                self.run_cmd([vp, "-m", "pip", "install", "--upgrade", "pip"])

            # 4. PyTorch CUDA（先检查是否已装 CUDA 版，避免重复下载约 3GB）
            torch_code = (
                "import torch, torchvision;"
                "print(bool(torch.version.cuda and torchvision.__version__))"
            )
            self.set_status(tr("inst_check_torch"), 36)
            if self.check_import(vp, torch_code):
                self.log_msg(tr("inst_torch_installed"))
                self.set_status(tr("inst_torch_skip"), 70)
            else:
                self.set_status(tr("inst_download_torch"), 36)
                ok = False
                for m in TORCH_MIRRORS:
                    if self.cancel_flag:
                        raise RuntimeError(tr("inst_cancelled"))
                    self.log_msg(tr("inst_mirror_log") % m)
                    rc = self.run_cmd(
                        [vp, "-m", "pip", "install", "torch", "torchvision", "--index-url", m]
                    )
                    if rc == 0:
                        ok = True
                        break
                if not ok:
                    raise RuntimeError(tr("inst_torch_fail"))

            # 5. 其他依赖（先检查是否已齐全）
            deps_code = (
                "import importlib.util as u;"
                "mods=['PySide6','transformers','accelerate','docx','pypdf','numpy'];"
                "print(all(u.find_spec(m) is not None for m in mods))"
            )
            self.set_status(tr("inst_check_deps"), 70)
            if self.check_import(vp, deps_code):
                self.log_msg(tr("inst_deps_skip"))
            else:
                self.set_status(tr("inst_install_deps"), 70)
                rc = self.run_cmd(
                    [
                        vp, "-m", "pip", "install",
                        "PySide6", "transformers", "accelerate",
                        "python-docx", "pypdf", "numpy",
                        "--index-url", PYPI_MIRROR,
                    ]
                )
                if rc != 0:
                    raise RuntimeError(tr("inst_deps_fail"))

            # 6. 复制软件
            self.set_status(tr("inst_copy_app"), 86)
            if os.path.exists(appdir):
                shutil.rmtree(appdir)
            shutil.copytree(app_source_dir(), appdir)

            # 7. 配置文件 + 快捷方式
            with open(os.path.join(target, "settings.json"), "w", encoding="utf-8") as f:
                f.write(
                    '{"app": {"install_dir": "%s"}, "ui": {"language": "%s"}}'
                    % (target.replace("\\", "\\\\"), get_lang())
                )

            self.set_status(tr("inst_create_shortcut"), 94)
            pythonw = os.path.join(venv, "Scripts", "pythonw.exe")
            self.make_shortcut(pythonw, os.path.join(appdir, "main.py"), appdir)

            self.set_status(tr("inst_done"), 100)
            self.log_msg(tr("inst_done_log") % APP_NAME)
            self._ui(
                lambda: messagebox.showinfo(
                    tr("inst_done_title"),
                    tr("inst_done_box") % APP_NAME,
                )
            )
        except Exception as e:
            self.set_status(tr("inst_failed_prefix") % e)
            self.log_msg(tr("inst_fail_log") % e)
            self._ui(lambda: messagebox.showerror(tr("inst_fail_title"), str(e)))
        finally:
            self.btn_start.config(state="normal")
            self.btn_cancel.config(state="disabled")

    @staticmethod
    def make_shortcut(target, args, workdir):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        lnk = os.path.join(desktop, "%s.lnk" % APP_NAME)
        ps = (
            "$ws = New-Object -ComObject WScript.Shell;"
            "$s = $ws.CreateShortcut('%s');"
            "$s.TargetPath = '%s';"
            "$s.Arguments = '%s';"
            "$s.WorkingDirectory = '%s';"
            "$s.Save()" % (lnk, target, args, workdir)
        )
        subprocess.call(
            ["powershell", "-NoProfile", "-Command", ps],
            creationflags=CREATE_NO_WINDOW,
        )


if __name__ == "__main__":
    Installer().mainloop()
