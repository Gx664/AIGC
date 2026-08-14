from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class GlassPanel(QFrame):
    """半透明圆角玻璃面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("glassPanel")
        self.setStyleSheet(
            "QFrame#glassPanel{"
            "background:rgba(255,255,255,150);"
            "border:1px solid rgba(255,255,255,190);"
            "border-radius:18px;}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)


class GlassButton(QPushButton):
    def __init__(self, text, primary=False):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        if primary:
            ss = (
                "QPushButton{background:rgba(59,130,246,210);color:white;"
                "border:none;border-radius:10px;padding:10px 18px;"
                "font-size:14px;font-weight:600;}"
                "QPushButton:hover{background:rgba(37,99,235,235);}"
                "QPushButton:disabled{background:rgba(148,163,184,140);color:rgba(255,255,255,190);}"
            )
        else:
            ss = (
                "QPushButton{background:rgba(255,255,255,150);color:#1f2937;"
                "border:1px solid rgba(255,255,255,210);border-radius:10px;"
                "padding:7px 12px;font-size:13px;}"
                "QPushButton:hover{background:rgba(255,255,255,230);}"
                "QPushButton:disabled{color:#9ca3af;background:rgba(255,255,255,80);}"
            )
        self.setStyleSheet(ss)


class TitleBar(QWidget):
    """可拖动标题栏（无边框窗口用）。"""

    def __init__(self, title, parent_win):
        super().__init__()
        self.pw = parent_win
        self.setFixedHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 10, 0)
        self.title = QLabel(title)
        self.title.setStyleSheet(
            "font-size:15px;font-weight:700;color:#1e293b;background:transparent;"
        )
        lay.addWidget(self.title)
        lay.addStretch()
        self.min_btn = QPushButton("—")
        self.close_btn = QPushButton("✕")
        for b in (self.min_btn, self.close_btn):
            b.setFixedSize(34, 28)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{background:rgba(255,255,255,130);border:none;"
                "border-radius:8px;font-size:14px;color:#374151;}"
                "QPushButton:hover{background:rgba(59,130,246,90);color:white;}"
            )
        self.min_btn.clicked.connect(self.pw.showMinimized)
        self.close_btn.clicked.connect(self.pw.close)
        lay.addWidget(self.min_btn)
        lay.addWidget(self.close_btn)
        self._drag = False
        self._pos = QPoint()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = True
            self._pos = e.globalPosition().toPoint() - self.pw.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag:
            self.pw.move(e.globalPosition().toPoint() - self._pos)

    def mouseReleaseEvent(self, e):
        self._drag = False
