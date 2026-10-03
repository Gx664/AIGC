import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import platform_ops
from core.settings import Settings, migrate_legacy_layout
from core.netfix import apply_env_fix

# 系统代理若是 socks（VPN 客户端常见写法），Python 侧一律走直连，否则模型下载必挂
apply_env_fix()

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
# 程序目录（代码 / 资源）与数据目录（配置 / 日志 / 模型）分开：
# Windows 两者相同 —— effective_base_dir 原样返回，行为与改造前一致；
# Unix 数据目录走用户级目录，因为 .app 在 /Applications 下可能不可写。
_PROGRAM_DIR = os.path.join(_APP_DIR, "..")
_BASE_DIR = platform_ops.effective_base_dir(_PROGRAM_DIR)
# 旧布局（用户数据在 app\ 里）搬到安装目录根：只做一次，失败不影响启动
migrate_legacy_layout(_BASE_DIR)
_settings = Settings(_BASE_DIR)
_mirror = _settings.get("download", "hf_endpoint", default="https://hf-mirror.com")
os.environ.setdefault("HF_ENDPOINT", _mirror)

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.glass import apply_design_system


def _app_icon():
    """应用图标：按平台挑格式（Windows→.ico / macOS→.icns 回退 .png / Linux→.png）。

    同时兼容源码运行与被 PyInstaller 打包（打包后资源在 _MEIPASS/app/assets）。
    """
    return platform_ops.find_icon(
        os.path.join(getattr(sys, "_MEIPASS", ""), "app", "assets"),
        os.path.join(_APP_DIR, "assets"),
    )


def _set_taskbar_identity():
    """声明进程身份，让任务栏把窗口归到本应用而不是 pythonw.exe。

    不做这一步，任务栏 / Alt-Tab 里显示的是 Python 解释器的图标。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "gxgx3456.AIGCToolkit.1"
        )
    except Exception:
        pass


def _show_selfcheck_problem(parent, level, problems):
    """把自检发现的问题告诉用户，并给出**用户自己能做**的下一步。

    这里刻意不做"一键自动修复"：修复要联网重装几 GB 的包、还可能改动环境，
    放在启动路径上风险太大。引导用户重跑引导器（``启动.cmd``）即可 ——
    那本来就会补装缺失组件，且带完整的进度与失败重试。
    """
    from PySide6.QtWidgets import QMessageBox

    from core.i18n import tr

    text = "\n".join("· " + p for p in problems)
    body = tr("sc_err_body" if level == "error" else "sc_warn_body") % text
    box = QMessageBox(parent)
    box.setWindowTitle(tr("sc_title"))
    box.setIcon(QMessageBox.Critical if level == "error" else QMessageBox.Warning)
    box.setText(body)
    box.exec()


def _selfcheck_async(win):
    """后台跑环境自检，有问题才提示。

    为什么绕这一圈：自检最慢约 3 秒（``import torch``），不能卡住窗口显示；
    而 Qt 控件只能在主线程碰，所以子线程只写结果、主线程轮询取。
    """
    import threading

    from PySide6.QtCore import QTimer

    state = {"done": False, "level": "ok", "problems": []}

    def worker():
        try:
            from core.selfcheck import run_check

            state["level"], state["problems"] = run_check()
        except Exception as e:  # noqa: BLE001
            state["level"], state["problems"] = "error", ["自检异常：%s" % e]
        state["done"] = True

    threading.Thread(target=worker, daemon=True).start()

    timer = QTimer()

    def poll():
        if not state["done"]:
            return
        timer.stop()
        if state["level"] != "ok":
            _show_selfcheck_problem(win, state["level"], state["problems"])

    timer.timeout.connect(poll)
    timer.start(500)


def main():
    _set_taskbar_identity()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # 中文字体按平台选（Windows 雅黑 / macOS 苹方 / Linux Noto），
    # 系统缺这个字体时由 Qt 自行回退，不会报错
    app.setFont(QFont(platform_ops.ui_font_family(), 9))
    _icon = _app_icon()
    if _icon:
        app.setWindowIcon(QIcon(_icon))
    apply_design_system(app)
    win = MainWindow()
    win.show()
    # 窗口先显示，自检在后台跑（有问题才弹提示）
    _selfcheck_async(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()