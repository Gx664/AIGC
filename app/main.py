import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.settings import Settings

_settings = Settings(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_mirror = _settings.get("download", "hf_endpoint", default="https://hf-mirror.com")
os.environ.setdefault("HF_ENDPOINT", _mirror)

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # 显式指定中文字体，避免不同系统默认字体导致的渲染异常
    app.setFont(QFont("Microsoft YaHei UI", 9))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
