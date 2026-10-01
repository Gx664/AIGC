import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import platform_ops
from core.settings import Settings
from core.netfix import apply_env_fix

# 系统代理若是 socks（VPN 客户端常见写法），Python 侧一律走直连，否则模型下载必挂
apply_env_fix()

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
# 程序目录（代码 / 资源）与数据目录（配置 / 日志 / 模型）分开：
# Windows 两者相同 —— effective_base_dir 原样返回，行为与改造前一致；
# Unix 数据目录走用户级目录，因为 .app 在 /Applications 下可能不可写。
_PROGRAM_DIR = os.path.join(_APP_DIR, "..")
_BASE_DIR = platform_ops.effective_base_dir(_PROGRAM_DIR)
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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
