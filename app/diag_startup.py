# -*- coding: utf-8 -*-
"""自检脚本（供「诊断.cmd」调用，也可手动运行）：一次性把排障需要的信息打全。

用法：runtime\\python\\python.exe diag_startup.py
输出：控制台 + app\\logs\\diag_YYYYmmdd_HHMMSS.txt

注意：embeddable 便携运行时的 ._pth 会锁死 sys.path（脚本所在目录不在其中），
所以这里必须手动把 app 目录插进 sys.path。
"""

import os
import platform
import sys
import time
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.join(APP_DIR, "core"))

from meta import AUTHOR_CONTACT  # noqa: E402

LOG_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
OUT_PATH = os.path.join(LOG_DIR, "diag_%s.txt" % time.strftime("%Y%m%d_%H%M%S"))
_lines = []


def say(msg=""):
    print(msg)
    _lines.append(str(msg))


def section(title):
    say()
    say("=" * 60)
    say(title)
    say("=" * 60)


def main():
    section("运行环境")
    say("时间        : %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    say("Python      : %s" % sys.version.replace("\n", " "))
    say("解释器路径  : %s" % sys.executable)
    say("app 目录    : %s" % APP_DIR)
    say("工作目录    : %s" % os.getcwd())
    say("系统        : %s %s (%s)" % (platform.system(), platform.release(), platform.machine()))

    runtime_py = os.path.join(os.path.dirname(APP_DIR), "runtime", "python", "python.exe")
    say("便携运行时  : %s %s" % (runtime_py, "存在" if os.path.exists(runtime_py) else "缺失！"))

    section("网络环境")
    try:
        from core.netfix import apply_env_fix, system_proxy

        proxy = system_proxy()
        say("系统代理    : %s" % (proxy or "未设置"))
        if apply_env_fix():
            say("            -> 是 socks 代理（Python 用不了），已自动切换直连")
    except Exception as e:
        say("网络自检失败: %s" % e)

    section("依赖检查")
    import importlib.util as u

    for mod in ("PySide6", "torch", "torchvision", "transformers", "accelerate", "docx", "pypdf", "numpy"):
        say("%-14s: %s" % (mod, "OK" if u.find_spec(mod) else "缺失"))

    section("torch 可用性（安全软件常会拦截）")
    try:
        import torch  # noqa: F401

        say("torch 导入  : OK  version=%s  cuda=%s" % (torch.__version__, torch.cuda.is_available()))
    except Exception as e:
        say("torch 导入  : 失败 -> %s: %s" % (type(e).__name__, e))
        say("            如果是 [WinError 5] 拒绝访问，多半是安全软件（搜狗 SCAegis / 管家类）")
        say("            拦截了 torch 的核心 DLL；把本程序目录加入白名单后重启软件即可。")
        _lines.append(traceback.format_exc())

    section("主程序模块导入")
    for name in ("core.meta", "core.settings", "core.i18n", "core.detector", "core.engines", "ui.main_window"):
        try:
            __import__(name)
            say("%-16s: OK" % name)
        except Exception as e:
            say("%-16s: 失败 -> %s: %s" % (name, type(e).__name__, e))

    section("安装内容")
    for rel in ("main.py", "first_run.py", "first_run_gui.exe", "core/netfix.py"):
        p = os.path.join(APP_DIR, rel)
        say("%-20s: %s" % (rel, "存在" if os.path.exists(p) else "缺失"))
    # 设置文件在安装根目录（app 的上一级），不在 app 内 —— 见 app/main.py 的 Settings(...)
    cfg = os.path.join(os.path.dirname(APP_DIR), "settings.json")
    say("%-20s: %s" % ("settings.json", "存在" if os.path.exists(cfg) else "缺失（安装器会创建）"))
    models = os.path.join(os.path.dirname(APP_DIR), "models")
    if os.path.isdir(models):
        total = sum(
            os.path.getsize(os.path.join(r, f))
            for r, _, fs in os.walk(models)
            for f in fs
        )
        say("模型目录            : %s（%.0f MB）" % (models, total / 1024 / 1024))
    else:
        say("模型目录            : 尚未下载（首次检测时会自动下载）")

    section("近期日志")
    for name in ("first_run.log", "main_stderr.log", "app.log"):
        p = os.path.join(LOG_DIR, name)
        say("--- %s ---" % name)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                for line in f.read().splitlines()[-12:]:
                    say(line)
        else:
            say("(无)")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))
    say()
    say("诊断报告已保存: %s" % OUT_PATH)
    say("遇到问题请把这份报告发到 %s" % AUTHOR_CONTACT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(_lines) + "\n" + traceback.format_exc())
        except Exception:
            pass
    try:
        input("\n按回车键关闭...")
    except EOFError:
        pass
