"""截图小工具（验收用）：用运行时 Python 把当前屏幕存成 PNG。"""
import os
import sys

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
pm = app.primaryScreen().grabWindow(0)
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "ui_verify_app.png")
print("saved:", pm.save(out, "PNG"), "%dx%d" % (pm.width(), pm.height()), "->", out)
