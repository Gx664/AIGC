from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

# ---- 设计令牌（现代工具风：单色系 + 发丝边框 + 克制阴影）----
C_TEXT = "#0f172a"          # 主文字
C_TEXT_2 = "#64748b"        # 次级文字
C_ACCENT = "#2563eb"        # 唯一强调色
C_ACCENT_HOVER = "#1d4ed8"
C_DANGER = "#ef4444"        # 仅关闭按钮悬停
C_BORDER = "rgba(15,23,42,30)"       # 发丝边框
C_BORDER_HOVER = "rgba(15,23,42,70)"
SURFACE = "rgba(255,255,255,215)"    # 面板表面
SURFACE_HOVER = "rgba(255,255,255,245)"
R_PANEL = 16
R_CTRL = 10


class GlassPanel(QFrame):
    """浅色圆角面板（发丝边框，不用图形阴影——阴影在分数缩放下会导致花字）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("glassPanel")
        self.setStyleSheet(
            "QFrame#glassPanel{"
            "background:%s;"
            "border:1px solid %s;"
            "border-radius:%dpx;}" % (SURFACE, C_BORDER, R_PANEL)
        )


class GlassButton(QPushButton):
    def __init__(self, text, primary=False):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        if primary:
            ss = (
                "QPushButton{background:%s;color:white;"
                "border:none;border-radius:%dpx;padding:10px 18px;"
                "font-size:14px;font-weight:600;}"
                "QPushButton:hover{background:%s;}"
                "QPushButton:pressed{background:#1e40af;}"
                "QPushButton:disabled{background:rgba(148,163,184,140);color:rgba(255,255,255,190);}"
                % (C_ACCENT, R_CTRL, C_ACCENT_HOVER)
            )
        else:
            ss = (
                "QPushButton{background:rgba(255,255,255,225);color:#334155;"
                "border:1px solid %s;border-radius:%dpx;"
                "padding:7px 12px;font-size:13px;}"
                "QPushButton:hover{background:%s;border:1px solid %s;}"
                "QPushButton:pressed{background:rgba(241,245,249,240);}"
                "QPushButton:disabled{color:#9ca3af;background:rgba(255,255,255,120);border:1px solid rgba(15,23,42,15);}"
                % (C_BORDER, R_CTRL, SURFACE_HOVER, C_BORDER_HOVER)
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
            "font-size:15px;font-weight:700;color:%s;background:transparent;" % C_TEXT
        )
        lay.addWidget(self.title)
        lay.addStretch()
        self.min_btn = QPushButton("—")
        self.full_btn = QPushButton("⛶")
        self.close_btn = QPushButton("✕")
        normal_ss = (
            "QPushButton{background:transparent;border:none;"
            "border-radius:8px;font-size:14px;color:#475569;}"
            "QPushButton:hover{background:rgba(15,23,42,14);color:%s;}" % C_TEXT
        )
        close_ss = (
            "QPushButton{background:transparent;border:none;"
            "border-radius:8px;font-size:14px;color:#475569;}"
            "QPushButton:hover{background:%s;color:white;}" % C_DANGER
        )
        for b in (self.min_btn, self.full_btn, self.close_btn):
            b.setFixedSize(34, 28)
            b.setCursor(Qt.PointingHandCursor)
        self.min_btn.setStyleSheet(normal_ss)
        self.full_btn.setStyleSheet(normal_ss)
        self.close_btn.setStyleSheet(close_ss)
        self.min_btn.clicked.connect(self.pw.showMinimized)
        self.full_btn.clicked.connect(self.toggle_fullscreen)
        self.close_btn.clicked.connect(self.pw.close)
        lay.addWidget(self.min_btn)
        lay.addWidget(self.full_btn)
        lay.addWidget(self.close_btn)
        self._drag = False
        self._pos = QPoint()
        self.pw.installEventFilter(self)

    def toggle_fullscreen(self):
        if self.pw.isFullScreen():
            self.pw.showNormal()
            self.full_btn.setText("⛶")
        else:
            self.pw.showFullScreen()
            self.full_btn.setText("❐")

    def eventFilter(self, obj, event):
        # 全屏状态下按 Esc 退出
        if obj is self.pw and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key_Escape and self.pw.isFullScreen():
                self.pw.showNormal()
                self.full_btn.setText("⛶")
                return True
        return False

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = True
            self._pos = e.globalPosition().toPoint() - self.pw.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag:
            self.pw.move(e.globalPosition().toPoint() - self._pos)

    def mouseReleaseEvent(self, e):
        self._drag = False
