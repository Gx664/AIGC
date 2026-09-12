import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.settings import Settings

_settings = Settings(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_mirror = _settings.get("download", "hf_endpoint", default="https://hf-mirror.com")
os.environ.setdefault("HF_ENDPOINT", _mirror)

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
