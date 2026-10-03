# -*- coding: utf-8 -*-
"""AI 检测工具箱 卸载器（独立 exe，由 tools/build_exe.ps1 打包）。

为什么是 exe（2026-09 改）
--------------------------
此前由安装器**生成一个 .py** 放进安装目录，注册表里写 ``pythonw.exe 卸载.py``。
两个问题：

1. 一般软件的卸载入口都是 exe，用户看到 pythonw.exe 会怀疑装错了东西；
2. 那个 .py **依赖 Python 运行环境** —— 环境被删或损坏之后，卸载器自己也跑不起来，
   用户只能手动删目录、手动清注册表。

exe 自带解释器，与环境彻底解耦：环境删了照样能卸载。

运行时信息从哪来
----------------
* ``TARGET``      = 本 exe 所在目录（安装时被复制到那里）
* ``RUNTIME_DIR`` = 注册表 ``RuntimeDir``（安装时写入；用户可能把环境放到别的盘），
                    取不到则回退 ``<TARGET>\\runtime\\python``

清理策略（三个勾默认都不打）
----------------------------
默认只删"软件的壳"：注册表卸载项、桌面快捷方式、程序本体 ``app\\``，以及
settings.json / 启动.cmd / 诊断.cmd。运行环境与模型**默认保留** ——
前者重装能复用（省几 GB 下载），后者是用户花时间下的东西。

三个勾对应三类**性质完全不同**的东西：
    下载缓存与日志 —— 软件自己产生的，删了零损失
    Python 运行环境 —— 软件装的，删了重装要重下，慢但不丢东西
    已下载的模型   —— 用户花时间下的资产，删了要重下（10GB 的可能几小时）

合并成一个勾是危险的：用户想"清个缓存"，会顺手把 10GB 模型删掉且不可恢复。

模型目录可能被设置指到别的盘（settings.json 的 download.models_dir），
所以只删**我们自己的那几个子目录**，绝不整删 models_dir —— 用户可能把
别的软件也指向同一个目录。

自删
----
本 exe 自己也在被删之列，但进程运行中删不掉，故把 ``del`` / ``rd`` 交给
cmd 延迟几秒执行（``ping`` 只用于等待，不联网）。
"""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

EMAIL = "gxgx3456@qq.com"
APP_NAME = "AI 检测工具箱"
CREATE_NO_WINDOW = 0x08000000
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AIGC_Toolkit"

# exe 所在目录就是安装目录（安装时被复制过去）；
# 源码直跑（python installer/uninstaller.py）时退回仓库根，方便调试。
if getattr(sys, "frozen", False):
    TARGET = os.path.dirname(os.path.abspath(sys.executable))
else:
    TARGET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 有模型的引擎 id —— 即 models 下属于我们的子目录名，与
# app/core/engines/catalog.py 的 id 对应。卸载器没法 import catalog
# （此时 app\ 可能已被删），故在此列一份，**新增引擎时记得同步**。
_ENGINE_DIRS = ("simpleai", "gltr", "zh_perplexity", "binoculars",
                "detectgpt", "fastdetectgpt")


def _runtime_dir():
    """运行环境目录：先问注册表，取不到再按默认布局猜。"""
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        try:
            val, _ = winreg.QueryValueEx(key, "RuntimeDir")
        finally:
            winreg.CloseKey(key)
        if val:
            return val
    except OSError:
        pass
    return os.path.join(TARGET, "runtime", "python")


def _models_dir():
    """模型目录：默认 ``<TARGET>\\models``；设置里可指到别的盘。"""
    try:
        p = os.path.join(TARGET, "settings.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            md = ((d.get("download") or {}).get("models_dir") or "").strip()
            if md and os.path.isdir(md):
                return md
    except Exception:
        pass
    d = os.path.join(TARGET, "models")
    return d if os.path.isdir(d) else ""


def _human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


def _dir_size(path):
    total = 0
    if not os.path.isdir(path):
        return total
    for root_dir, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root_dir, f))
            except OSError:
                pass
    return total


def _count_files(paths):
    """先数一遍要删多少文件 —— 进度条需要分母。"""
    n = 0
    for p in paths:
        if os.path.isdir(p):
            for _root, _dirs, files in os.walk(p):
                n += len(files)
        elif os.path.exists(p):
            n += 1
    return n


def _rm_counted(path, on_file):
    """删文件或目录，**每删掉一个文件回报一次**（进度条靠它）。

    为什么不用 ``shutil.rmtree``：它的回调只在**出错**时触发，报不了进度；
    而卸载要删 ``app/`` 以及可能几 GB 的模型 —— 用户得看见它在动，
    否则窗口一关就像"程序自动退出了"（用户实测反馈）。

    :param path: 要删的文件或目录
    :param on_file: ``on_file(删掉的文件数)``
    """
    if os.path.isdir(path):
        for root_dir, dirs, files in os.walk(path, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root_dir, name))
                    on_file(1)
                except OSError:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root_dir, name))
                except OSError:
                    pass
        try:
            os.rmdir(path)
        except OSError:
            pass
    elif os.path.exists(path):
        try:
            os.remove(path)
            on_file(1)
        except OSError:
            pass


def do_uninstall(chk_cache, chk_run, chk_models,
                 run_dir, cache_dirs, models_dir, on_progress=None):
    """执行清理；返回给用户看的说明文字。

    顺序有讲究：先删"软件的壳"，再按勾选删大件，最后把**自删**交给 cmd。
    ``on_progress(text, done, total)`` 会被频繁调用（每删一个文件一次），
    界面据此画进度条 —— 删几 GB 的时候不能让用户干等一个不动的窗口。
    """
    def report(text, done, total):
        if on_progress:
            on_progress(text, done, total)

    # 1) 注册表卸载项（瞬间完成，不进进度条）
    try:
        import winreg

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    # 2) 快捷方式：桌面 + 开始菜单（旧版本可能建过开始菜单项，一并收拾）
    lnk_dirs = [os.path.join(os.path.expanduser("~"), "Desktop"),
                os.path.join(os.environ.get("APPDATA", ""),
                             "Microsoft", "Windows", "Start Menu", "Programs")]
    for d in lnk_dirs:
        if not d:
            continue
        p = os.path.join(d, APP_NAME + ".lnk")
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    # 3) 要删的清单 —— **先把分母数出来**，再逐个删着报进度
    #    （uninstall.pyw / build_info.json 是旧版本留下的产物，顺手清掉）
    targets = [os.path.join(TARGET, n) for n in
               ("app", "settings.json", "启动.cmd", "诊断.cmd",
                "build_info.json", "uninstall.pyw")]
    if chk_cache.get():
        targets.extend(cache_dirs)
    if chk_models.get() and models_dir:
        # 只删**我们自己的那几个子目录**：models_dir 可能是用户共用的目录，
        # 整删会连带删掉别的软件放在那里的模型
        targets.extend(os.path.join(models_dir, n) for n in _ENGINE_DIRS)

    total = _count_files(targets) or 1
    counter = {"done": 0}

    def on_file(n, _name):
        counter["done"] += n
        report("正在删除 %s …（%d/%d）"
               % (_name, counter["done"], total), counter["done"], total)

    for p in targets:
        if not os.path.exists(p):
            continue
        name = os.path.basename(p)
        report("正在删除 %s …（%d/%d）" % (name, counter["done"], total),
               counter["done"], total)
        _rm_counted(p, lambda n, _n=name: on_file(n, _n))

    # 4) 自删 + 收尾：本进程还锁着 uninstaller.exe，交给 cmd 等几秒再删。
    #    ping 只用来等待（不联网），比 timeout 更稳（timeout 在无控制台时报错）。
    report("清理卸载器自身…", total, total)
    cmds = ["ping 127.0.0.1 -n 4 > nul"]
    if chk_run.get():
        # 只删用户选定的那个环境目录本身，绝不删它的父目录 ——
        # 自选路径时父目录里可能是用户自己的东西
        cmds.append('rd /s /q "%s"' % run_dir)
        parent = os.path.dirname(run_dir)
        if os.path.normcase(parent) == os.path.normcase(
                os.path.join(TARGET, "runtime")):
            # 默认布局下这个父目录只装着我们这份环境，空了顺手删掉
            cmds.append('rd "%s"' % parent)
    cmds.append('del /f /q "%s"' % os.path.join(TARGET, "uninstaller.exe"))
    cmds.append('rd "%s"' % TARGET)     # 空目录才成功（模型还在时保留）
    # uninstaller.exe 刚被 del 掉，系统释放句柄要一会儿 —— 不重试的话
    # 常留下一个空目录（实测踩过）
    for _ in range(2):
        cmds.append("ping 127.0.0.1 -n 3 > nul")
        cmds.append('rd "%s"' % TARGET)
    subprocess.Popen(
        "cmd /c " + " & ".join(cmds),
        creationflags=CREATE_NO_WINDOW,
    )

    msg = "已卸载，感谢使用。"
    if chk_run.get():
        msg += "\n\n运行环境将在几秒后删除（本卸载器自身也会随之删除）。"
    else:
        msg += ("\n\n运行环境与模型仍保留在：\n%s\n"
                "（如需彻底删除，请再次运行卸载器并勾选对应项）" % TARGET)
    msg += "\n\n遇到 Bug 或建议随时邮件：\n" + EMAIL
    return msg


def main():
    root = tk.Tk()
    root.title("卸载 " + APP_NAME)
    root.geometry("580x470")
    root.resizable(False, False)

    run_dir = _runtime_dir()
    cache_dirs = [os.path.join(TARGET, "_downloads"),
                  os.path.join(TARGET, "_pipcache"),
                  os.path.join(TARGET, "logs")]
    models_dir = _models_dir()

    cache_size = sum(_dir_size(p) for p in cache_dirs)
    run_size = _dir_size(run_dir)
    mdl_size = (sum(_dir_size(os.path.join(models_dir, n))
                    for n in _ENGINE_DIRS) if models_dir else 0)

    tk.Label(root, text="卸载 " + APP_NAME,
             font=("Microsoft YaHei UI", 14, "bold")).pack(
        anchor="w", padx=18, pady=(16, 4))
    tk.Label(root, justify="left", fg="#475569", wraplength=540,
             text="将删除：卸载注册项、桌面快捷方式、程序本体。\n"
                  "运行环境与模型默认保留（重装可复用，省几 GB 下载）。"
             ).pack(anchor="w", padx=18, pady=(0, 10))

    chk_cache = tk.BooleanVar(value=False)
    chk_run = tk.BooleanVar(value=False)
    chk_models = tk.BooleanVar(value=False)

    def add_chk(var, text):
        tk.Checkbutton(root, variable=var, anchor="w", justify="left",
                       wraplength=540, text=text).pack(
            fill="x", padx=18, pady=2)

    add_chk(chk_cache, "同时清理下载缓存与日志（可释放 %s）" % _human(cache_size))
    add_chk(chk_run, "同时删除 Python 运行环境（%s，删后重装需重新下载）"
            % _human(run_size))
    add_chk(chk_models, "同时删除已下载的模型（%s，删后需重新下载）"
            % _human(mdl_size))

    if models_dir and os.path.normcase(os.path.abspath(models_dir)) != \
            os.path.normcase(os.path.join(os.path.abspath(TARGET), "models")):
        tk.Label(root, fg="#475569", justify="left", wraplength=540,
                 text="模型目录（设置里指定的位置）：%s" % models_dir
                 ).pack(anchor="w", padx=18, pady=(6, 0))

    tk.Label(root, fg="#475569", justify="left", wraplength=540,
             text="遇到 Bug？欢迎先邮件反馈，很多问题都能修：\n" + EMAIL
             ).pack(anchor="w", padx=18, pady=(10, 0))

    # 进度条 + 状态行：卸载要删 app/ 甚至几 GB 模型，必须让用户**看见它在动**。
    # 此前是"点完就关窗"，用户看到的是"程序自动退出了"（实测反馈）。
    status_var = tk.StringVar(value="准备就绪")
    tk.Label(root, textvariable=status_var, fg="#1d4ed8", justify="left",
             anchor="w", wraplength=544).pack(fill="x", padx=18, pady=(8, 2))
    pbar = ttk.Progressbar(root, maximum=100, length=544)
    pbar.pack(fill="x", padx=18, pady=(0, 4))

    q = queue.Queue()
    busy = {"on": False}

    def drain():
        """主线程：把后台线程的进度搬到界面上（tkinter 只能在主线程碰控件）。"""
        try:
            while True:
                item = q.get_nowait()
                kind = item[0]
                if kind == "prog":
                    _kind, text, done, total = item
                    status_var.set(text)
                    pbar["value"] = min(100, int(done * 100 / max(total, 1)))
                elif kind == "done":
                    busy["on"] = False
                    status_var.set("卸载完成")
                    pbar["value"] = 100
                    btn_un.config(state="disabled")
                    btn_cancel.config(state="normal", text="关闭")
                    messagebox.showinfo("完成 / Done", item[1], parent=root)
                elif kind == "err":
                    busy["on"] = False
                    status_var.set("卸载过程出错")
                    btn_un.config(state="normal")
                    btn_cancel.config(state="normal")
                    messagebox.showerror("失败", item[1], parent=root)
        except queue.Empty:
            pass
        root.after(80, drain)

    def worker():
        try:
            msg = do_uninstall(
                chk_cache, chk_run, chk_models, run_dir, cache_dirs, models_dir,
                on_progress=lambda text, done, total:
                    q.put(("prog", text, done, total)))
        except Exception as e:  # noqa: BLE001
            q.put(("err", str(e)))
            return
        q.put(("done", msg))

    def on_uninstall():
        if busy["on"]:
            return
        if not messagebox.askyesno(
            "确认卸载",
            "确定要卸载 %s 吗？\n\n卸载器不会修改你系统里已安装的 Python 环境。"
            % APP_NAME, parent=root,
        ):
            return
        busy["on"] = True
        btn_un.config(state="disabled")
        btn_cancel.config(state="disabled")
        status_var.set("开始卸载…")
        pbar["value"] = 0
        threading.Thread(target=worker, daemon=True).start()

    def on_close():
        if busy["on"]:
            # 删除线程是 daemon，这时候关窗会把它掐断，留下半删的目录
            messagebox.showinfo("请稍候", "正在删除文件，跑完再关。", parent=root)
            return
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    btns = tk.Frame(root)
    btns.pack(fill="x", padx=18, pady=(10, 16), side="bottom")
    btn_un = tk.Button(btns, text="卸载", width=10, command=on_uninstall)
    btn_un.pack(side="right")
    btn_cancel = tk.Button(btns, text="取消", width=10, command=root.destroy)
    btn_cancel.pack(side="right", padx=6)

    root.after(80, drain)
    root.mainloop()


if __name__ == "__main__":
    main()
