import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.settings import Settings
from core.netfix import apply_env_fix

# 系统代理若是 socks（VPN 客户端常见写法），Python 侧一律走直连，否则模型下载必挂
apply_env_fix()

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_settings = Settings(os.path.join(_APP_DIR, ".."))
_mirror = _settings.get("download", "hf_endpoint", default="https://hf-mirror.com")
os.environ.setdefault("HF_ENDPOINT", _mirror)

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.glass import apply_design_system


def _asset(*parts):
    """定位 app/assets 下的静态资源；同时兼容源码运行与被 PyInstaller 打包。"""
    for p in (
        os.path.join(getattr(sys, "_MEIPASS", ""), "app", "assets", *parts),
        os.path.join(_APP_DIR, "assets", *parts),
    ):
        if p and os.path.exists(p):
            return p
    return ""


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
    # 显式指定中文字体，避免不同系统默认字体导致的渲染异常
    app.setFont(QFont("Microsoft YaHei UI", 9))
    _icon = _asset("icon.ico")
    if _icon:
        app.setWindowIcon(QIcon(_icon))
    apply_design_system(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

# aigc-toolkit: file purpose marker
