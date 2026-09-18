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
# 国内镜像优先（无需 VPN，均已实测可用），官方源排最后兜底
# 注：阿里云镜像站不收录 Windows 版安装包，故不放进来
PY_URLS = [
    "https://registry.npmmirror.com/-/binary/python/%s/%s" % (PY_VER, PY_NAME),
    "https://mirrors.huaweicloud.com/python/%s/%s" % (PY_VER, PY_NAME),
    "https://www.python.org/ftp/python/%s/%s" % (PY_VER, PY_NAME),
]
MIN_PY_SIZE = 5 * 1024 * 1024  # 安装包体积下限，防止下到错误页/半截包
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
        # 左上角全屏切换（安装/下载日志较长时方便查看）
        self.btn_full = tk.Button(self, command=self.toggle_fullscreen, width=8)
        self.btn_full.pack(anchor="w", padx=18, pady=(10, 0))
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
        """所有源下载失败时，让用户选择本地已下载的 Python 安装包。"""
        box = {"path": None}
        ev = threading.Event()

        def ask():
            p, _ = filedialog.askopenfilename(
                title=tr("inst_manual_pick_title"),
                filetypes=[("Python 安装包", PY_NAME), ("所有文件", "*.*")],
            )
            box["path"] = p or None
            ev.set()

        self._ui(ask)
        while not ev.wait(0.2):
            if self.cancel_flag:
                return None
        return box["path"]

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

    def _cleanup_partial(self, dest):
        for p in (dest + ".part", dest):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    def _validate_dl(self, dest):
        """下载结果体积校验，防止拿到错误页/半截包。"""
        if not os.path.exists(dest) or os.path.getsize(dest) < MIN_PY_SIZE:
            raise RuntimeError(tr("inst_size_bad"))

    def _fetch_urllib(self, url, dest):
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

    def _fetch_curl(self, url, dest):
        """系统 curl 兜底（Win10 自带）：独立网络栈，能绕开 Python 网络层的问题。"""
        curl = shutil.which("curl")
        if not curl:
            raise RuntimeError(tr("inst_no_curl"))
        self.log_msg(tr("inst_download_curl") % url)
        tmp = dest + ".part"
        self.set_status(tr("inst_download_curl_run"), 4)
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

    def download(self, url, dest):
        """单个源：先 urllib，失败再 curl，成功后做体积校验。"""
        try:
            self._fetch_urllib(url, dest)
        except Exception as e1:
            if self.cancel_flag:
                raise
            self.log_msg(tr("inst_python_dl_fail") % e1)
            try:
                if os.path.exists(dest + ".part"):
                    os.remove(dest + ".part")
            except OSError:
                pass
            self._fetch_curl(url, dest)
        self._validate_dl(dest)

    def run_install(self):
        try:
            target = self.dir_var.get().strip() or r"D:\AIGC_Detector"
            dl = os.path.join(target, "_downloads")
            runtime = os.path.join(target, "runtime")
            pydir = os.path.join(runtime, "python")
            venv = os.path.join(runtime, "venv")
            appdir = os.path.join(target, "app")
            os.makedirs(dl, exist_ok=True)

            # 1. Python 运行时（优先复用已有 runtime，其次系统 Python，最后官方安装器）
            pyexe_path = os.path.join(pydir, "python.exe")

            def python_ok(exe):
                """验证 Python 能完整初始化（标准库 encodings 可用）。"""
                try:
                    out = subprocess.run(
                        [exe, "-c", "import encodings, sys; print(sys.prefix)"],
                        capture_output=True, text=True, timeout=60,
                        creationflags=CREATE_NO_WINDOW,
                    )
                    return out.returncode == 0 and bool(out.stdout.strip())
                except Exception:
                    return False

            have_runtime = os.path.exists(pyexe_path) and python_ok(pyexe_path)
            if have_runtime:
                self.log_msg("检测到可用的本地运行时 Python，跳过安装")
                self.set_status(tr("inst_python_installed"), 25)

            if not have_runtime:
                # 坏的旧 runtime 一律清掉，避免半成品干扰
                if os.path.exists(pydir):
                    shutil.rmtree(pydir, ignore_errors=True)

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
                    # python.exe 就在 Python 根目录，只取一层 dirname
                    sys_py_dir = os.path.dirname(sys_python)
                    self.log_msg("系统 Python 目录: %s" % sys_py_dir)
                    # 只有带完整标准库的源目录才值得复制
                    if os.path.exists(os.path.join(sys_py_dir, "Lib", "encodings")):
                        try:
                            shutil.copytree(sys_py_dir, pydir)
                            self.log_msg("已复制系统 Python 到目标目录")
                        except Exception as e:
                            self.log_msg("复制失败: %s，改用官方安装器" % e)
                    else:
                        self.log_msg("系统 Python 缺少 Lib 标准库，不复制，改用官方安装器")
                    # 复制后必须验证可用，不可用就删掉走官方安装器
                    if os.path.exists(pyexe_path) and python_ok(pyexe_path):
                        have_runtime = True
                        self.set_status(tr("inst_python_installed"), 25)
                    elif os.path.exists(pydir):
                        shutil.rmtree(pydir, ignore_errors=True)

            if not have_runtime and not os.path.exists(pyexe_path):
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
                            self._cleanup_partial(pyexe)
                            if self.cancel_flag:
                                raise RuntimeError(tr("inst_cancelled"))
                    if err:
                        # 全部源失败：允许手动指定本地已下载的安装包
                        self.log_msg(tr("inst_all_dl_fail") % err)
                        manual = self.ask_manual_file()
                        if manual:
                            self.log_msg("使用本地安装包: %s" % manual)
                            shutil.copyfile(manual, pyexe)
                        else:
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
                if rc == 3010:
                    self.log_msg("需要重启完成安装，不影响继续使用")

                # 校验：python.exe + 完整标准库 + 可初始化，缺一不可
                def runtime_valid(d):
                    return (
                        os.path.exists(os.path.join(d, "python.exe"))
                        and os.path.exists(os.path.join(d, "Lib", "encodings"))
                        and python_ok(os.path.join(d, "python.exe"))
                    )

                def find_installed_python():
                    """机器上有旧注册记录时，官方安装器可能无视 TargetDir
                    装到别处——从注册表找它实际安装的位置。"""
                    try:
                        import winreg
                    except ImportError:
                        return None
                    for hive, view in (
                        (winreg.HKEY_CURRENT_USER, 0),
                        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
                    ):
                        for tag in ("3.12", "3.12-32"):
                            try:
                                k = winreg.OpenKey(
                                    hive,
                                    r"Software\Python\PythonCore\%s\InstallPath" % tag,
                                    0,
                                    view | winreg.KEY_READ,
                                )
                                d = winreg.QueryValueEx(k, "")[0].rstrip("\\")
                                self.log_msg("注册表指向的安装位置: %s" % d)
                                if runtime_valid(d):
                                    return d
                            except OSError:
                                continue
                    return None

                local_appdata = os.environ.get("LOCALAPPDATA", "")
                default_py = os.path.join(local_appdata, "Programs", "Python", "Python312")

                def recover_runtime():
                    """TargetDir 无效时，从注册表/默认位置找回并复制。"""
                    src = find_installed_python()
                    if not src and runtime_valid(default_py):
                        src = default_py
                    if src:
                        self.log_msg("从 %s 复制到目标目录" % src)
                        shutil.rmtree(pydir, ignore_errors=True)
                        try:
                            shutil.copytree(src, pydir)
                        except Exception as e:
                            self.log_msg("复制失败: %s" % e)

                if not runtime_valid(pydir):
                    recover_runtime()

                # 仍无效：改用 /passive 可见安装重试一次（静默模式偶发被拦截/静默失败）
                if not runtime_valid(pydir):
                    self.log_msg("静默安装未生效，改用可见安装重试一次")
                    args2 = list(args)
                    args2[1] = "/passive"
                    rc2 = subprocess.call(args2, creationflags=CREATE_NO_WINDOW)
                    self.log_msg("重试退出码: %d" % rc2)
                    if not runtime_valid(pydir):
                        recover_runtime()
                    if not runtime_valid(pydir):
                        raise RuntimeError(tr("inst_python_inst_err") % rc)
            else:
                self.set_status(tr("inst_python_installed"), 25)

            # 2. venv
            if not os.path.exists(os.path.join(venv, "Scripts", "python.exe")):
                self.set_status(tr("inst_create_venv"), 60)
                self.run_cmd([os.path.join(pydir, "python.exe"), "-m", "venv", venv])
            vp = os.path.join(venv, "Scripts", "python.exe")
            if not os.path.exists(vp):
                raise RuntimeError("虚拟环境创建失败（venv 不存在），请查看上方日志")

            # 3. 复制软件（PyTorch / PySide6 等组件由首次启动引导器下载）
            self.set_status(tr("inst_copy_app"), 80)
            if os.path.exists(appdir):
                shutil.rmtree(appdir)
            shutil.copytree(app_source_dir(), appdir)

            # 4. 配置文件 + 快捷方式
            with open(os.path.join(target, "settings.json"), "w", encoding="utf-8") as f:
                f.write(
                    '{"app": {"install_dir": "%s"}, "ui": {"language": "%s"}}'
                    % (target.replace("\\", "\\\\"), get_lang())
                )

            self.set_status(tr("inst_create_shortcut"), 94)
            pythonw = os.path.join(venv, "Scripts", "pythonw.exe")
            self.make_shortcut(pythonw, os.path.join(appdir, "first_run.py"), appdir)

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
