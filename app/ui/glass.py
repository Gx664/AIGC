import os

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QApplication,
    QWidget,
)

# ---- 设计令牌（浅色 Modern Tool：单色系 + 发丝边框，无阴影）----
C_TEXT = "#0f172a"          # 主文字
C_TEXT_2 = "#64748b"        # 次级文字
C_TEXT_3 = "#334155"        # 控件文字 / 节标题
C_ACCENT = "#2563eb"        # 唯一强调色
C_ACCENT_HOVER = "#1d4ed8"
C_DANGER = "#ef4444"        # 仅关闭按钮悬停
C_BORDER = "rgba(15,23,42,28)"       # 发丝边框
C_BORDER_HOVER = "rgba(15,23,42,70)"
SURFACE = "#ffffff"                  # 面板表面（纯白，不发花）
SURFACE_HOVER = "#f8fafc"
R_PANEL = 16    # 大面板
R_BTN = 10      # 按钮（中等）
R_CTRL = 6      # 输入控件（小）
SP = (4, 8, 12, 16, 24)              # 间距刻度

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets").replace("\\", "/")


def fit_to_screen(widget, w, h, margin=40, min_w=560, min_h=420):
    """把窗口尺寸收敛到屏幕可用区域内。

    小屏（如 1440x900）上如果窗口比屏幕高，Qt 会把内容等比压扁，
    按钮文字上下被裁（花字）。所有顶层窗口都应先过这个函数。
    """
    scr = QApplication.primaryScreen()
    avail = scr.availableGeometry() if scr else None
    if avail:
        w = max(min_w, min(w, avail.width() - margin))
        h = max(min_h, min(h, avail.height() - margin))
    widget.resize(w, h)
    return widget


def design_stylesheet():
    """全局设计系统样式（QApplication 级），覆盖所有原生控件。"""
    down = _ASSETS + "/combo_down.svg"
    up = _ASSETS + "/combo_up.svg"
    check = _ASSETS + "/check.svg"
    return """
QLabel { color:%(text)s; background:transparent; }
QLabel#sectionHeader { color:%(text3)s; font-size:12px; font-weight:700; margin-top:6px; }
QLabel#mutedLabel { color:%(text2)s; }

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background:#ffffff; border:1px solid %(border)s; border-radius:%(rc)dpx;
    padding:4px 10px; color:%(text)s;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover { border:1px solid %(border_h)s; }
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border:1px solid %(accent)s; }
QComboBox::drop-down { border:none; width:24px; }
QComboBox::down-arrow { image:url(%(down)s); width:10px; height:6px; margin-right:6px; }
QComboBox QAbstractItemView {
    background:#ffffff; border:1px solid %(border)s; border-radius:6px;
    selection-background-color:#eff6ff; selection-color:%(text)s; outline:none; padding:4px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    border:none; background:transparent; width:16px; margin-right:3px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background:#f1f5f9; border-radius:4px; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image:url(%(up)s); width:8px; height:5px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image:url(%(down)s); width:8px; height:5px; }

QCheckBox { color:%(text3)s; spacing:8px; background:transparent; }
QCheckBox::indicator {
    width:18px; height:18px; border-radius:5px;
    border:1px solid rgba(15,23,42,60); background:#ffffff;
}
QCheckBox::indicator:hover { border:1px solid %(accent)s; }
QCheckBox::indicator:checked { background:%(accent)s; border:1px solid %(accent)s; image:url(%(check)s); }

QSlider::groove:horizontal { height:4px; background:rgba(15,23,42,25); border-radius:2px; }
QSlider::sub-page:horizontal { background:%(accent)s; border-radius:2px; }
QSlider::handle:horizontal {
    width:16px; height:16px; margin:-6px 0; border-radius:8px;
    background:#ffffff; border:1px solid %(border_h)s;
}
QSlider::handle:horizontal:hover { border:1px solid %(accent)s; }

QProgressBar { background:rgba(15,23,42,18); border:none; border-radius:4px; min-height:8px; max-height:8px; }
QProgressBar::chunk { background:%(accent)s; border-radius:4px; }

QTextEdit, QPlainTextEdit {
    background:#ffffff; border:1px solid %(border)s; border-radius:8px;
    color:%(text)s; selection-background-color:%(accent)s;
}

/* 细滚动条（左侧参数面板内容高于屏幕时滚动，而不是把控件压扁） */
QScrollArea { background:transparent; border:none; }
QScrollBar:vertical {
    background:transparent; width:10px; margin:0; border:none;
}
QScrollBar::handle:vertical {
    background:rgba(15,23,42,55); border-radius:5px; min-height:36px;
}
QScrollBar::handle:vertical:hover { background:rgba(15,23,42,105); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; border:none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar:horizontal { background:transparent; height:10px; margin:0; border:none; }
QScrollBar::handle:horizontal {
    background:rgba(15,23,42,55); border-radius:5px; min-width:36px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; border:none; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:transparent; }
""" % dict(
        text=C_TEXT, text2=C_TEXT_2, text3=C_TEXT_3, accent=C_ACCENT,
        border=C_BORDER, border_h=C_BORDER_HOVER, rc=R_CTRL,
        down=down, up=up, check=check,
    )


def apply_design_system(app):
    app.setStyleSheet(design_stylesheet())


class GlassPanel(QFrame):
    """白色圆角面板（发丝边框，不用图形阴影——阴影在分数缩放下会导致花字）。"""

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
                "min-height:18px;"
                "font-size:14px;font-weight:600;}"
                "QPushButton:hover{background:%s;}"
                "QPushButton:pressed{background:#1e40af;}"
                "QPushButton:disabled{background:rgba(148,163,184,140);color:rgba(255,255,255,190);}"
                % (C_ACCENT, R_BTN, C_ACCENT_HOVER)
            )
        else:
            ss = (
                "QPushButton{background:#ffffff;color:%s;"
                "border:1px solid %s;border-radius:%dpx;"
                "padding:8px 14px;min-height:18px;font-size:13px;}"
                "QPushButton:hover{background:%s;border:1px solid %s;}"
                "QPushButton:pressed{background:#f1f5f9;}"
                "QPushButton:disabled{color:#9ca3af;background:rgba(255,255,255,120);border:1px solid rgba(15,23,42,15);}"
                % (C_TEXT_3, C_BORDER, R_BTN, SURFACE_HOVER, C_BORDER_HOVER)
            )
        self.setStyleSheet(ss)
        # 高度兜底：QSS 的 min-height 只管内容区，这里再钉死总高，
        # 保证任何窗口尺寸下按钮都不会被布局压扁（否则文字上下被裁 = 花字）。
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)


class TitleBar(QWidget):
    """可拖动标题栏（无边框窗口用）。"""

    def __init__(self, title, parent_win):
        super().__init__()
        self.pw = parent_win
        self.setFixedHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 10, 0)
        lay.setSpacing(4)
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

# aigc-toolkit: file purpose marker
