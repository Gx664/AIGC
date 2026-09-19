import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.settings import Settings
from core.netfix import apply_env_fix

# 系统代理若是 socks（VPN 客户端常见写法），Python 侧一律走直连，否则模型下载必挂
apply_env_fix()

_settings = Settings(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_mirror = _settings.get("download", "hf_endpoint", default="https://hf-mirror.com")
os.environ.setdefault("HF_ENDPOINT", _mirror)

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.glass import apply_design_system


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # 显式指定中文字体，避免不同系统默认字体导致的渲染异常
    app.setFont(QFont("Microsoft YaHei UI", 9))
    apply_design_system(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
