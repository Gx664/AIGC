# -*- coding: utf-8 -*-
"""Linux / macOS 启动入口（PyInstaller 的入口脚本）。

Windows 那条链路是「安装器 → first_run_gui.exe → 主程序」三段式；
Unix 没有独立的安装器（.app / AppImage 本身就是安装形态），所以把
「准备运行时 + 装依赖 + 启动主程序」合并到一个可执行文件里：

    AIGC_Toolkit（本文件打包而成）
        ├─ 依赖齐全 → 直接起主程序（first_run 内部判断，不会闪窗）
        └─ 缺依赖   → 起 tkinter 引导界面，装完自动进主界面

本文件刻意保持"薄"：只负责定位程序根目录与 app 源码目录，然后把
``app/first_run.py`` 跑起来。所有平台差异都在 ``app/core/platform_ops.py``，
引导逻辑都在 ``app/first_run.py`` —— 这里不重复实现任何一条。

⚠️ 目录定位为什么不能写死：PyInstaller 6 起，onedir 产物的 datas 不再摊在
   产物根，而是放进 ``_internal/``；macOS 的 .app 还更靠外一层（``Contents/
   Frameworks`` 或 ``Contents/Resources``，且两者会互相交叉软链）。所以下面
   先按候选探测，再退化为**有限深度搜索**，判据统一是"这一层有没有 main.py"。

⚠️ 为什么这里自带一份搜索函数而不是复用 ``platform_ops``：本文件的作用正是
   先找到 ``app/``、把它放进 sys.path 之后 ``core`` 才 import 得到 —— 顺序上
   不可能反过来依赖它。这份实现很薄，改布局时**两处一起改**，并有测试钉住。
"""
import os
import runpy
import sys

_FROZEN = getattr(sys, "frozen", False)


def _candidates():
    """``app/`` 源码目录的可能位置，按可能性排序（打包后才有意义）。"""
    here = os.path.dirname(os.path.abspath(sys.executable))
    meipass = getattr(sys, "_MEIPASS", "") or ""
    up = os.path.dirname(here)
    out = [here]  # Windows 式：exe 就放在 app/ 里
    if meipass:
        out.append(os.path.join(meipass, "app"))
        out.append(os.path.join(meipass, "_internal", "app"))
        out.append(meipass)  # 万一把 core/ 直接摊在 _MEIPASS
    out += [
        os.path.join(here, "app"),
        os.path.join(here, "_internal", "app"),                # PyInstaller 6 onedir
        os.path.join(up, "Frameworks", "app"),                 # macOS .app
        os.path.join(up, "Frameworks", "_internal", "app"),
        os.path.join(up, "Resources", "app"),
        os.path.join(up, "Resources", "_internal", "app"),
    ]
    return out


def _search_app_dir(root, max_depth=3):
    """在 ``root`` 下有限深度内找名为 ``app`` 且含 ``main.py`` 的目录。

    深度语义是"**含**第 max_depth 层"（root 自己算第 0 层）—— 否则 macOS 的
    ``Contents/Frameworks/_internal/app``（相对 ``Contents`` 正好第 3 层）会被漏掉。
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return ""
    base_depth = os.path.normpath(root).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = os.path.normpath(dirpath).count(os.sep) - base_depth
        if depth >= max_depth:
            dirnames[:] = []  # 到顶了，本层仍检查，但不往下走
        if "main.py" in filenames and os.path.basename(dirpath) == "app":
            return os.path.normpath(dirpath)
    return ""


def _find_app_dir():
    """候选里第一个含 ``main.py`` 的目录；都没有再有限深度搜索。"""
    for d in _candidates():
        if d and os.path.isfile(os.path.join(d, "main.py")):
            return os.path.normpath(d)
    # 从 exe 所在目录与其上一层各搜一遍：onedir 产物在第 2 层命中，
    # macOS 的 .app 里 app/ 在 Contents/Frameworks/_internal 下、要从上一层搜
    here = os.path.dirname(os.path.abspath(sys.executable))
    for root in (here, os.path.dirname(here)):
        hit = _search_app_dir(root)
        if hit:
            return hit
    return ""


def _ensure_importable():
    """把能让 ``import core.*`` / ``import ui.*`` 生效的目录塞进 sys.path。

    源码运行时不做事（仓库根已经在 path 上）；打包后按候选逐个补。
    """
    if not _FROZEN:
        return
    for d in _candidates():
        if d and os.path.isdir(os.path.join(d, "core")) and d not in sys.path:
            sys.path.insert(0, d)


def _program_root():
    """程序根目录（含 ``app/`` 与 ``runtime/``）。

    打包后交给适配层按实际布局判断（Windows 式 ``<root>/app/exe`` 与
    Unix 式 ``<root>/exe`` 都认）；源码运行时是仓库根目录。
    """
    if not _FROZEN:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    _ensure_importable()
    try:
        from core import platform_ops
    except Exception:  # noqa: BLE001 - 包体异常时退化为"exe 所在目录"
        return os.path.dirname(os.path.abspath(sys.executable))
    return platform_ops.program_base_dir(sys.executable)


def app_dir(root):
    """``app/`` 源码目录的绝对路径（打包后可能在 ``_internal/`` 下）。"""
    if not _FROZEN:
        return os.path.join(root, "app")
    return _find_app_dir() or os.path.join(root, "app")


def main():
    root = _program_root()
    src = app_dir(root)
    if not os.path.isdir(src):
        sys.stderr.write("[ERR] 找不到 app/ 目录（程序根：%s）\n" % root)
        return 2

    for p in (src, os.path.join(src, "core")):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)

    # 程序根 / 数据根写进环境变量，first_run 与它拉起的子进程都沿用
    try:
        from core import platform_ops

        platform_ops.export_env(root)
    except Exception:  # noqa: BLE001 - 非致命，first_run 会自己再算一遍
        os.environ.setdefault("AIGC_TOOLKIT_HOME", root)

    entry = os.path.join(src, "first_run.py")
    if not os.path.isfile(entry):
        sys.stderr.write("[ERR] 找不到引导入口：%s\n" % entry)
        return 2

    runpy.run_path(entry, run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
