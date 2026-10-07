import os
import sys
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.about_text import ABOUT_TEXT, ABOUT_TEXT_EN
from core.cluster import ClusterMaster, ClusterWorker
from core.detector import detect_local, detect_with_cluster
from core.diagnosis import diagnose
from core.doc_reader import extract_text, split_paragraphs
from core.engines import EngineManager, create_engine
from core.gpuinfo import detect as gpu_detect
from core.i18n import get_lang, set_lang, tr
from core.license import License
from core.logging_setup import export_logs, setup_logging
from core.meta import (
    APP_NAME,
    APP_VERSION,
    AUTHOR_CONTACT,
    AUTHOR_EMAIL,
    AUTHOR_TG,
)
from core import platform_ops
from core.report import build_report
from core.settings import Settings, base_dir
from ui.engine_dialog import EngineDialog
from ui.glass import EdgeResizer, GlassButton, GlassPanel, TitleBar, fit_to_screen
from ui.rewrite_dialog import RewriteDialog
from ui.settings_dialog import SettingsDialog


# 用户数据根目录 = 安装目录（与安装器写 settings.json 的位置一致）。
# 定义收敛到 core.settings.base_dir()，别再各自算一遍 —— 差一层 `app`
# 就会引出"安装器写的设置读不到、用户设置被重装覆盖、卸载器删不到模型"那一串。
BASE_DIR = base_dir()


# 窗口尺寸：**中英统一**（按英文需求定 —— 英文标签更长，此前按中文定宽度，
# 英文界面下按钮文字会被裁："Import presets"、"Run as worker" 都被切掉）。
_WIN_W = 1240
_WIN_H = 780
# 左栏初始宽度：英文标签更长，给它多一点（用户可拖分隔条自行调整）
_LEFT_W_ZH = 400
_LEFT_W_EN = 470


def _mmss(sec):
    """秒 → ``mm:ss``（耗时 / 剩余时间显示用）。"""
    sec = max(0, int(sec))
    return "%02d:%02d" % (sec // 60, sec % 60)

# BASE_DIR  = 程序目录：代码、app/assets 等**只读**资源从这儿找
# DATA_DIR  = 数据目录：settings.json / logs / models 等**要写**的东西落这儿
# Windows 两者相同（行为与改造前一致）；Unix 的 DATA_DIR 走用户级目录，
# 因为 .app 装在 /Applications 下、AppImage 也可能是只读的。
DATA_DIR = platform_ops.effective_base_dir(BASE_DIR)


class DetectWorker(QThread):
    step = Signal(str, int)
    # 第 6 项是逐段四档占比（GLTR Test-2），非统计派引擎为 None
    finished_ok = Signal(list, list, float, str, str, object)
    failed = Signal(str)

    def __init__(self, path, engine_id, engine_name, params, base_dir, master):
        super().__init__()
        self.path = path
        self.engine_id = engine_id
        self.engine_name = engine_name
        self.params = params
        self.base_dir = base_dir
        self.master = master
        self.start_ts = time.time()
        self.mgr = EngineManager(base_dir)

    def run(self):
        try:
            self.step.emit(tr("reading_doc"), 2)
            text = extract_text(self.path)
            paras = split_paragraphs(text, self.params.get("min_para_len", 20))
            if not paras:
                self.failed.emit(tr("no_valid_text"))
                return

            cfg = self.mgr.get(self.engine_id)
            if not cfg:
                self.failed.emit(tr("engine_not_found") % self.engine_id)
                return

            engine = create_engine(cfg, self.base_dir)
            self.step.emit(tr("preparing_model"), 4)
            engine.install(lambda pct, msg: self.step.emit(msg, 4 + int(pct * 0.10)))

            # 参数合并：先铺引擎清单里的默认值，再用界面参数覆盖 ——
            # 顺序反了会让用户调好的阈值被清单默认值悄悄改回去。
            run_params = dict(cfg.get("params", {}))
            run_params.update(self.params)

            def prog(done, total):
                pct = 15 + int(82 * done / max(total, 1))
                elapsed = time.time() - self.start_ts
                eta = (elapsed / done * (total - done)) if done else 0.0
                # 带上耗时与剩余时间：只有百分比时用户不知道还要等多久。
                # `start_ts` 是原作者留下的字段，此前一直没人用。
                self.step.emit(
                    tr("detecting_para_eta")
                    % (done, total, _mmss(elapsed), _mmss(eta)),
                    pct,
                )

            if self.params.get("use_cluster") and self.master and self.master.nodes_snapshot():
                probs = detect_with_cluster(
                    cfg, self.base_dir, paras, run_params, self.master, prog
                )
                use_cluster = True
                ran_engine = None
            else:
                # detect_local 一并回传**真正跑检测的那个引擎实例** ——
                # 上面的 self 里那个 engine 只用于 install()，检测是在
                # detect_local 内部另建实例跑的，从它上面取不到四档。
                probs, ran_engine = detect_local(
                    cfg, self.base_dir, paras, run_params, prog
                )
                use_cluster = False

            valid = [p for p in probs if p is not None]
            ratio = sum(valid) / len(valid) if valid else 0.0
            self.step.emit(tr("generating_report"), 99)
            # 四档（GLTR Test-2）走旁路：统计派引擎跑完存在实例属性上，
            # 其他引擎没有这个概念（为 None）。走旁路而非改返回值，
            # 是因为 `predict_paragraphs` 的 `list[float]` 被三处共用。
            #
            # 注：**集群模式暂不传四档** —— 分片在各节点跑，`last_buckets`
            # 留在节点进程内，主窗口只拿到合并后的 probs。跨节点合并需另
            # 设计协议，非本次范围（论文原产物是逐段涂色图）。
            self.finished_ok.emit(
                paras, probs, ratio, os.path.basename(self.path),
                self.engine_name,
                None if use_cluster else getattr(ran_engine, "last_buckets", None)
            )
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setWindowTitle(APP_NAME)
        # 初始尺寸按屏幕可用区域收敛，避免小屏（如 1440x900）上一开窗就超出屏幕底部；
        # 宽度中英统一（见 _WIN_W 的说明）
        fit_to_screen(self, _WIN_W, _WIN_H)
        # 无边框窗口要自己实现边缘拖拽缩放（系统边框被 FramelessWindowHint 去掉了）
        self._resizer = EdgeResizer(self)
        self.base_dir = DATA_DIR
        self.settings = Settings(self.base_dir)
        set_lang(self.settings.get("ui", "language", default="zh"))
        self.log = setup_logging(self.base_dir)
        self.mgr = EngineManager(self.base_dir)
        self.license = License(self.base_dir)
        self.master = ClusterMaster(on_log=self.on_cluster_log)
        self.worker_node = None
        self.worker_thread = None
        self.file_path = None
        self.last_paras = None
        self.last_probs = None
        self.last_ratio = 0.0
        self.last_diag = None
        self._build_ui()
        self._apply_params_from_settings()

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(
            "QWidget#root{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #f8fafc, stop:1 #edf0f5);}"
        )
        central.setObjectName("root")
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 10, 18, 18)
        root.setSpacing(12)

        self.title_bar = TitleBar("%s  v%s" % (tr("app_name"), APP_VERSION), self)
        root.addWidget(self.title_bar)

        # 标题栏下方常驻一行版权声明，让「禁止商业使用」一开窗就可见
        _nc = QLabel(
            "© 2026 gxgx3456 · 禁止商业使用 · Noncommercial use only"
            if get_lang() != "en"
            else "© 2026 gxgx3456 · Commercial use prohibited"
        )
        _nc.setAlignment(Qt.AlignCenter)
        _nc.setStyleSheet(
            "color:#94a3b8;font-size:11px;padding:1px 0 0 0;"
        )
        root.addWidget(_nc)

        # 左/右栏用 QSplitter：中间那条是**可以左右拖**的分隔条。此前是写死的
        # 2:3 布局，用户想拉宽左栏只能看着滚动条把「管理」按钮挤掉。
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_left())
        self.splitter.addWidget(self._build_right())
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        left_w = _LEFT_W_EN if get_lang() == "en" else _LEFT_W_ZH
        self.splitter.setSizes([left_w, _WIN_W - left_w])
        root.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

    def _section(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("sectionHeader")
        return lbl

    def _build_left(self):
        # 外层保留白色圆角卡片，卡片内部滚动；这样屏幕不够高时滚动条出现在卡片内，
        # 而不是让 Qt 把按钮等比压扁（压扁 = 按钮文字上下被裁）。
        panel = GlassPanel()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(6, 6, 4, 6)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.viewport().setStyleSheet("background:transparent;")
        # 左栏最小宽度：滚动条（10px）+ 引擎行的「管理」按钮都要放得下，
        # 否则窄屏上按钮会被压出可视区
        scroll.setMinimumWidth(360)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        lay.addWidget(self._section("① " + tr("btn_select_file")))
        row = QHBoxLayout()
        self.btn_open = GlassButton(tr("btn_select_file"))
        self.btn_open.clicked.connect(self.choose_file)
        row.addWidget(self.btn_open)
        self.file_label = QLabel(tr("file_not_selected"))
        self.file_label.setStyleSheet("color:#64748b;")
        row.addWidget(self.file_label, 1)
        lay.addLayout(row)

        lay.addWidget(self._section(tr("label_engine")))
        row2 = QHBoxLayout()
        self.engine_combo = QComboBox()
        self._reload_engines()
        row2.addWidget(self.engine_combo, 1)
        self.btn_engine = GlassButton(tr("btn_manage"))
        self.btn_engine.clicked.connect(self.open_engine_dialog)
        row2.addWidget(self.btn_engine)
        lay.addLayout(row2)

        lay.addWidget(self._section(tr("label_params")))
        thr_row = QHBoxLayout()
        thr_row.addWidget(QLabel(tr("label_threshold")))
        self.thr_slider = QSlider(Qt.Horizontal)
        self.thr_slider.setRange(10, 90)
        self.thr_slider.setValue(50)
        self.thr_spin = QSpinBox()
        self.thr_spin.setRange(10, 90)
        self.thr_spin.setSuffix("%")
        self.thr_slider.valueChanged.connect(self.thr_spin.setValue)
        self.thr_spin.valueChanged.connect(self.thr_slider.setValue)
        # 两个控件必须**显式对齐初值**：QSpinBox 默认值是 0，被 setRange 夹到 10，
        # 而 slider 已经是 50；后面 `_apply_params_from_settings` 再设 50 时值没变、
        # 不发 valueChanged —— 于是数字框永远显示 10% 而滑块居中（v1.0 起就有的 bug，
        # 全新安装必现：默认阈值恰好等于滑块初值）。
        self.thr_spin.setValue(self.thr_slider.value())
        thr_row.addWidget(self.thr_slider, 1)
        thr_row.addWidget(self.thr_spin)
        lay.addLayout(thr_row)

        sug_row = QHBoxLayout()
        sug_row.addWidget(QLabel(tr("label_rewrite_suggest")))
        self.suggest_thr = QSpinBox()
        self.suggest_thr.setRange(10, 90)
        self.suggest_thr.setSuffix("%")
        self.suggest_thr.setValue(int(
            self.settings.get("rewrite", "suggest_threshold", default=0.30) * 100
        ))
        sug_row.addWidget(self.suggest_thr)
        sug_row.addStretch()
        lay.addLayout(sug_row)

        p_row = QHBoxLayout()
        p_row.addWidget(QLabel(tr("label_min_len")))
        self.min_len = QSpinBox()
        self.min_len.setRange(10, 200)
        self.min_len.setValue(20)
        p_row.addWidget(self.min_len)
        p_row.addWidget(QLabel(tr("label_workers")))
        self.workers = QSpinBox()
        self.workers.setRange(0, 16)
        self.workers.setSpecialValueText(tr("opt_auto"))
        self.workers.setValue(0)
        p_row.addWidget(self.workers)
        lay.addLayout(p_row)

        self.chk_gpu = QCheckBox(tr("chk_gpu"))
        self.chk_gpu.setChecked(True)
        self.chk_cluster = QCheckBox(tr("chk_cluster"))
        self.chk_cluster.stateChanged.connect(self.on_cluster_toggled)
        # 两个勾旁边各给一个「检测」按钮：勾了却用不上（驱动旧 / 装了 CPU 版
        # torch / 局域网上根本没别的机器）时，用户只会觉得"慢"，不会知道原因。
        # 检测不通过就**自动取消勾选**并说明。
        gpu_row = QHBoxLayout()
        gpu_row.addWidget(self.chk_gpu)
        gpu_row.addStretch()
        self.btn_check_gpu = GlassButton(tr("btn_check_gpu"))
        self.btn_check_gpu.clicked.connect(self.check_gpu)
        gpu_row.addWidget(self.btn_check_gpu)
        lay.addLayout(gpu_row)

        clu_chk_row = QHBoxLayout()
        clu_chk_row.addWidget(self.chk_cluster)
        clu_chk_row.addStretch()
        self.btn_check_cluster = GlassButton(tr("btn_check_cluster"))
        self.btn_check_cluster.clicked.connect(self.check_cluster)
        clu_chk_row.addWidget(self.btn_check_cluster)
        lay.addLayout(clu_chk_row)

        lay.addWidget(self._section(tr("label_presets")))
        pre_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self._reload_presets()
        pre_row.addWidget(self.preset_combo, 1)
        b_save = GlassButton(tr("btn_save"))
        b_load = GlassButton(tr("btn_load"))
        b_save.clicked.connect(self.save_preset)
        b_load.clicked.connect(self.load_preset)
        pre_row.addWidget(b_save)
        pre_row.addWidget(b_load)
        lay.addLayout(pre_row)

        exp_row = QHBoxLayout()
        b_exp = GlassButton(tr("btn_export_presets"))
        b_imp = GlassButton(tr("btn_import_presets"))
        b_exp.clicked.connect(self.export_presets)
        b_imp.clicked.connect(self.import_presets)
        exp_row.addWidget(b_exp)
        exp_row.addWidget(b_imp)
        lay.addLayout(exp_row)

        lay.addWidget(self._section(tr("label_cluster")))
        self.device_label = QLabel(tr("device_loading"))
        self.device_label.setWordWrap(True)
        lay.addWidget(self.device_label)
        clu_row = QHBoxLayout()
        self.btn_scan = GlassButton(tr("btn_scan"))
        self.btn_worker = GlassButton(tr("btn_worker"))
        self.btn_scan.clicked.connect(self.scan_cluster)
        self.btn_worker.clicked.connect(self.toggle_worker)
        clu_row.addWidget(self.btn_scan)
        clu_row.addWidget(self.btn_worker)
        lay.addLayout(clu_row)

        lay.addWidget(self._section(tr("label_version")))
        lic_row = QHBoxLayout()
        self.lic_label = QLabel(
            self.license.current_tier() == "pro" and tr("tier_pro") or tr("tier_free")
        )
        lic_row.addWidget(self.lic_label, 1)
        self.btn_lic = GlassButton(tr("btn_activate"))
        self.btn_lic.clicked.connect(self.activate_license)
        lic_row.addWidget(self.btn_lic)
        self.btn_about = GlassButton(tr("btn_about"))
        self.btn_about.clicked.connect(self.show_about)
        lic_row.addWidget(self.btn_about)
        self.btn_lang = GlassButton(tr("lang_btn"))
        self.btn_lang.clicked.connect(self.switch_language)
        lic_row.addWidget(self.btn_lang)
        lay.addLayout(lic_row)

        lay.addWidget(self._section(tr("label_download")))
        dl_row = QHBoxLayout()
        self.btn_download_settings = GlassButton(tr("btn_download_settings"))
        self.btn_download_settings.clicked.connect(self.open_download_settings)
        dl_row.addWidget(self.btn_download_settings)
        self.btn_benchmark = GlassButton(tr("btn_benchmark"))
        self.btn_benchmark.clicked.connect(self.open_benchmark)
        dl_row.addWidget(self.btn_benchmark)
        lay.addLayout(dl_row)

        lay.addWidget(self._section(tr("label_contact")))
        cont_row = QHBoxLayout()
        self.author_label = QLabel(
            "%s  ｜  Telegram %s" % (AUTHOR_EMAIL, AUTHOR_TG)
        )
        self.author_label.setStyleSheet("color:#64748b;")
        cont_row.addWidget(self.author_label, 1)
        self.btn_copy_mail = GlassButton(tr("btn_copy_contact"))
        self.btn_copy_mail.clicked.connect(self.copy_author_email)
        cont_row.addWidget(self.btn_copy_mail)
        lay.addLayout(cont_row)

        lay.addWidget(self._section(tr("label_data")))
        tel_row = QHBoxLayout()
        self.btn_export_log = GlassButton(tr("btn_export_log"))
        self.btn_export_log.clicked.connect(self.export_log)
        tel_row.addWidget(self.btn_export_log, 1)
        lay.addLayout(tel_row)

        self.btn_start = GlassButton(tr("btn_start"), primary=True)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.start_detect)
        lay.addWidget(self.btn_start)

        self.btn_rewrite = GlassButton(tr("btn_start_rewrite"))
        self.btn_rewrite.setEnabled(False)
        self.btn_rewrite.clicked.connect(self.start_rewrite)
        lay.addWidget(self.btn_rewrite)
        lay.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)
        return panel

    def _build_right(self):
        panel = GlassPanel()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(18, 16, 18, 16)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        lay.addWidget(self.progress)
        self.result_label = QLabel(tr("ratio_placeholder"))
        self.result_label.setStyleSheet(
            "font-size:26px;font-weight:800;color:#2563eb;background:transparent;"
        )
        lay.addWidget(self.result_label)
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        self.report.setStyleSheet(
            "QTextEdit{background:rgba(255,255,255,230);border:1px solid rgba(15,23,42,20);border-radius:12px;"
            "font-size:13px;}"
        )
        lay.addWidget(self.report, 1)
        return panel

    # ---- 引擎 ----
    def _reload_engines(self):
        """检测引擎下拉只列「检查」类；修复 / 评测类在引擎管理里单独入口。

        名称带语言标注（🌐 中文 / 🌐 英文）：项目定位是中英双语查重，而除
        simpleai 外其余引擎都源自英文模型，拿它们测中文会得到完全错误的
        结果（实测 binoculars 的中文 FNR 100%），标注可避免误用。
        """
        from ui.engine_dialog import engine_label

        self.engine_combo.clear()
        for e in self.mgr.runnable():
            self.engine_combo.addItem(engine_label(e), e["id"])
        idx = self.engine_combo.findData(self.settings.get("detect", "engine", default="simpleai"))
        if idx >= 0:
            self.engine_combo.setCurrentIndex(idx)

    def open_engine_dialog(self):
        EngineDialog(self.mgr, DATA_DIR, self.settings, self).exec()
        current = self.engine_combo.currentData()
        self._reload_engines()
        if current is not None:
            idx = self.engine_combo.findData(current)
            if idx >= 0:
                self.engine_combo.setCurrentIndex(idx)

    def open_benchmark(self):
        """打开评测基准（RAID / MGTBench）。"""
        benches = self.mgr.by_category("benchmark")
        if not benches:
            QMessageBox.information(self, tr("notice"), tr("bench_none"))
            return
        names = [b.get("name", b["id"]) for b in benches]
        choice, ok = QInputDialog.getItem(
            self, tr("btn_benchmark"), tr("bench_pick_title"), names, 0, False
        )
        if not ok:
            return
        bench = benches[names.index(choice)]
        from ui.benchmark_dialog import BenchmarkDialog

        BenchmarkDialog(self.mgr, DATA_DIR, self.settings, bench["id"], self).exec()

    def open_download_settings(self):
        SettingsDialog(self.settings, DATA_DIR, self).exec()

    # ---- 勾选自检（GPU / 集群）----
    def check_gpu(self):
        """检测"勾了 GPU 到底能不能用"；不能用就取消勾选并说明原因。

        以``torch`` 为唯一权威：只有"这台机器上实际装着的这套 torch 现在能不能
        调起CUDA"才算数。``gpuinfo`` 只提供机器侧参考（卡名/驱动/CUDA 上限），
        它的结论**不能**推翻 torch 的实测——早期版本两行都打出来时会自相矛盾
        （上半句"驱动过旧只能用 CPU"、下半句"torch 已能调用显卡"），
        原因是 nvidia-smi 的字段名变了（``CUDA Version`` → ``CUDA UMD Version``）
        而正则没跟上，于是把好卡读成CUDA 未知。
        """
        info = gpu_detect()
        ok = False
        runtime = ""
        try:
            import torch

            ok = bool(torch.cuda.is_available())
            if ok:
                runtime = tr("gpu_ok_runtime") % torch.cuda.get_device_name(0)
        except Exception as e:  # noqa: BLE001
            runtime = tr("gpu_no_torch") % e
        if ok:
            # torch 说能用就是能用，只报实际状态，不叠加机器侧的悲观结论
            lines = [runtime]
            if info.get("driver"):
                lines.append(tr("gpu_env_ok") % (info["gpu"] or tr("gpu_generic_card"),
                                                info["driver"]))
        else:
            # torch 说不能用才需要解释原因，这时gpuinfo 的结论才有参考价值
            lines = [info.get("reason", ""), runtime]
            self.chk_gpu.setChecked(False)
        QMessageBox.information(self, tr("btn_check_gpu"), "\n".join(l for l in lines if l))

    def check_cluster(self):
        """检测局域网上有没有工作节点；没有就取消勾选并给出下一步。"""
        nodes = self.master.nodes_snapshot()
        if not nodes:
            self.chk_cluster.setChecked(False)
            QMessageBox.information(self, tr("btn_check_cluster"),
                                    tr("cluster_no_node"))
            return
        QMessageBox.information(self, tr("btn_check_cluster"),
                                tr("cluster_ok") % len(nodes))

    # ---- 文件 ----
    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("select_doc"), "", tr("doc_filter")
        )
        if path:
            self.load_file(path)

    def load_file(self, path):
        self.file_path = path
        self.file_label.setText(os.path.basename(path))
        self.btn_start.setEnabled(True)
        self.btn_rewrite.setEnabled(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            p = urls[0].toLocalFile()
            if os.path.splitext(p)[1].lower() in (".pdf", ".docx", ".txt"):
                self.load_file(p)

    # ---- 参数与预设 ----
    def _collect_params(self):
        return {
            "engine": self.engine_combo.currentData(),
            "threshold": self.thr_slider.value() / 100.0,
            "suggest_threshold": self.suggest_thr.value() / 100.0,
            "min_para_len": self.min_len.value(),
            "max_len": self.settings.get("detect", "max_len", default=500),
            "use_gpu": self.chk_gpu.isChecked(),
            "max_workers": self.workers.value(),
            "use_cluster": self.chk_cluster.isChecked(),
            "rewrite": dict(self.settings.get("rewrite", default={})),
        }

    def _apply_params_from_settings(self):
        d = self.settings.get("detect", default={})
        # 设数字框（会经信号同步滑块）—— 直接设滑块时若值未变就不发信号，
        # 数字框会留在旧值上
        self.thr_spin.setValue(int(d.get("threshold", 0.5) * 100))
        self.suggest_thr.setValue(int(
            self.settings.get("rewrite", "suggest_threshold", default=0.30) * 100
        ))
        self.min_len.setValue(d.get("min_para_len", 20))
        self.workers.setValue(d.get("max_workers", 0))
        self.chk_gpu.setChecked(d.get("use_gpu", True))
        self.chk_cluster.setChecked(d.get("use_cluster", False))

    def _reload_presets(self):
        self.preset_combo.clear()
        self.preset_combo.addItems(self.settings.list_presets())

    def save_preset(self):
        name, ok = QInputDialog.getText(self, tr("save_preset_title"), tr("preset_name_prompt"))
        if ok and name.strip():
            self.settings.save_preset(name.strip(), self._collect_params())
            self._reload_presets()

    def load_preset(self):
        name = self.preset_combo.currentText()
        if not name:
            return
        p = self.settings.load_preset(name)
        self.thr_spin.setValue(int(p.get("threshold", 0.5) * 100))
        if p.get("suggest_threshold") is not None:
            self.suggest_thr.setValue(int(p["suggest_threshold"] * 100))
        self.min_len.setValue(p.get("min_para_len", 20))
        self.workers.setValue(p.get("max_workers", 0))
        self.chk_gpu.setChecked(p.get("use_gpu", True))
        self.chk_cluster.setChecked(p.get("use_cluster", False))
        idx = self.engine_combo.findData(p.get("engine"))
        if idx >= 0:
            self.engine_combo.setCurrentIndex(idx)
        rw = p.get("rewrite")
        if isinstance(rw, dict):
            for k, v in rw.items():
                self.settings.set(v, "rewrite", k)

    def export_presets(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("btn_export_presets"), "presets.json", "JSON (*.json)")
        if path:
            self.settings.export_presets(path)

    def import_presets(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("btn_import_presets"), "", "JSON (*.json)")
        if path:
            self.settings.import_presets(path)
            self._reload_presets()

    # ---- 集群 ----
    def on_cluster_log(self, msg):
        self.device_label.setText(tr("cluster_log") % (msg, self._devices_text()))

    def _devices_text(self):
        try:
            import torch

            if torch.cuda.is_available():
                parts = []
                for i in range(torch.cuda.device_count()):
                    parts.append(
                        "%s (%dGB)"
                        % (torch.cuda.get_device_name(i),
                           torch.cuda.get_device_properties(i).total_memory // (2**30))
                    )
                return tr("gpu_line") % ("；".join(parts))
        except Exception:
            pass
        return tr("no_gpu")

    def scan_cluster(self):
        if not self.master.running:
            self.master.start()
        nodes = self.master.nodes_snapshot()
        if nodes:
            self.device_label.setText(
                tr("cluster_devices") % (len(nodes), self._devices_text())
            )
        else:
            self.device_label.setText(
                tr("scanning_lan") % self._devices_text()
            )

    def on_cluster_toggled(self, state):
        if state == Qt.Checked and not self.master.running:
            self.master.start()

    def toggle_worker(self):
        if self.worker_node is None:
            self.worker_node = ClusterWorker(
                lambda eid: create_engine(self.mgr.get(eid), self.base_dir),
                on_log=self.on_cluster_log,
            )
            self.worker_node.start()
            self.btn_worker.setText(tr("btn_worker_stop"))
        else:
            self.worker_node.stop()
            self.worker_node = None
            self.btn_worker.setText(tr("btn_worker"))

    # ---- 授权 ----
    def activate_license(self):
        key, ok = QInputDialog.getText(self, tr("activate_title"), tr("license_prompt"))
        if not ok:
            return
        ok, msg = self.license.activate(key)
        QMessageBox.information(self, tr("btn_activate"), msg)
        self.lic_label.setText(
            self.license.current_tier() == "pro" and tr("tier_pro") or tr("tier_free")
        )

    def switch_language(self):
        new_lang = "en" if get_lang() == "zh" else "zh"
        set_lang(new_lang)
        self.settings.set(new_lang, "ui", "language")
        file_path = self.file_path
        engine_id = self.engine_combo.currentData() if hasattr(self, "engine_combo") else None
        self._build_ui()
        self._apply_params_from_settings()
        if file_path:
            self.load_file(file_path)
        if engine_id is not None:
            idx = self.engine_combo.findData(engine_id)
            if idx >= 0:
                self.engine_combo.setCurrentIndex(idx)
        self.device_label.setText(self._devices_text())

    def show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("about_title"))
        fit_to_screen(dlg, 760, 720)
        box = QVBoxLayout(dlg)
        box.setContentsMargins(16, 16, 16, 16)

        # 禁止商业使用横幅：协议里写了还不够，软件里必须一眼看见
        banner = QLabel(tr("nc_banner"))
        banner.setAlignment(Qt.AlignCenter)
        banner.setStyleSheet(
            "background:#fee2e2;color:#b91c1c;font-size:15px;font-weight:700;"
            "border:1px solid #fca5a5;border-radius:10px;padding:10px;"
        )
        banner.setToolTip(tr("nc_banner_tip"))
        box.addWidget(banner)

        nc_tip = QLabel(tr("nc_banner_tip"))
        nc_tip.setWordWrap(True)
        nc_tip.setStyleSheet(
            "background:#fff7ed;color:#9a3412;font-size:12px;"
            "border:1px solid #fed7aa;border-radius:8px;padding:8px;"
        )
        box.addWidget(nc_tip)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(ABOUT_TEXT_EN if get_lang() == "en" else ABOUT_TEXT)
        text.setStyleSheet(
            "QTextEdit{background:rgba(255,255,255,200);border:none;border-radius:12px;"
            "font-size:13px;line-height:150%;}"
        )
        box.addWidget(text, 1)
        qr_row = QHBoxLayout()
        for fname, caption in (
            ("alipay.jpg", "支付宝  Alipay"),
            ("wechat_pay.jpg", "微信支付  WeChat Pay"),
        ):
            cell = QVBoxLayout()
            img_path = self._donate_image_path(fname)
            img_label = QLabel()
            img_label.setAlignment(Qt.AlignCenter)
            if img_path and os.path.exists(img_path):
                pix = QPixmap(img_path)
                img_label.setPixmap(
                    pix.scaledToWidth(
                        240, Qt.SmoothTransformation
                    )
                )
            else:
                img_label.setText("赞赏码图片缺失")
            cell.addWidget(img_label)
            cap = QLabel(caption)
            cap.setAlignment(Qt.AlignCenter)
            cap.setStyleSheet("color:#64748b;font-weight:600;")
            cell.addWidget(cap)
            qr_row.addLayout(cell)
        box.addLayout(qr_row)
        close_btn = GlassButton("关闭")
        close_btn.clicked.connect(dlg.accept)
        box.addWidget(close_btn, 0, Qt.AlignRight)
        dlg.exec()

    def _donate_image_path(self, name):
        """赞赏码图片（``alipay.jpg`` / ``wechat_pay.jpg``）的绝对路径。

        **别把 ``app`` 拼两次**：``BASE_DIR`` 本身已经是 app 目录
        （``ui/main_window.py`` 上溯两级 = ``<安装目录>\\app``），所以
        ``BASE_DIR + "app/assets/donate/..."`` 会得到 ``app\\app\\assets\\...``，
        永远找不到文件，界面上只能显示"赞赏码图片缺失"（v1.0 起就错了）。

        候选顺序：
            1. PyInstaller 解包目录 ``<_MEIPASS>/app/assets/donate``
            2. ``<BASE_DIR>/assets/donate`` —— 正常路径
            3. ``<BASE_DIR 的上一级>/app/assets/donate`` —— 兜底
        """
        meipass = getattr(sys, "_MEIPASS", "")
        cands = []
        if meipass:
            cands.append(os.path.join(meipass, "app", "assets", "donate", name))
        cands.append(os.path.join(BASE_DIR, "app", "assets", "donate", name))
        cands.append(os.path.join(
            os.path.dirname(BASE_DIR), "app", "assets", "donate", name))
        for p in cands:
            if os.path.exists(p):
                return p
        return ""

    def copy_author_email(self):
        QApplication.clipboard().setText(AUTHOR_CONTACT)
        QMessageBox.information(
            self, tr("copied_title"), tr("copied_body") % AUTHOR_CONTACT
        )

    def export_log(self):
        default_name = tr("log_default_name") % time.strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("export_log_title"), default_name, tr("zip_filter")
        )
        if not path:
            return
        try:
            export_logs(self.base_dir, path)
        except Exception as e:
            QMessageBox.warning(self, tr("export_fail_title"), str(e))
            return
        QMessageBox.information(
            self,
            tr("export_done_title"),
            tr("export_done_body") % (path, AUTHOR_CONTACT),
        )

    # ---- 检测 ----
    def start_detect(self):
        if not self.file_path:
            return
        params = self._collect_params()
        self.settings.set(
            params.get("suggest_threshold", 0.30), "rewrite", "suggest_threshold"
        )
        for k, v in params.items():
            if k == "rewrite":
                continue
            self.settings.set(v, "detect", k)
        self.settings.save()

        engine_cfg = self.mgr.get(params["engine"])
        self.btn_start.setEnabled(False)
        self.btn_open.setEnabled(False)
        self.progress.setValue(0)
        self.result_label.setText(tr("detecting"))

        self.worker_thread = DetectWorker(
            self.file_path,
            params["engine"],
            engine_cfg["name"],
            params,
            self.base_dir,
            self.master if params.get("use_cluster") else None,
        )
        self.worker_thread.step.connect(self.on_step)
        self.worker_thread.finished_ok.connect(self.on_done)
        self.worker_thread.failed.connect(self.on_failed)
        self.worker_thread.start()

    def on_step(self, msg, pct):
        self.progress.setValue(pct)
        self.setWindowTitle("%s  v%s  |  %s" % (tr("app_name"), APP_VERSION, msg))
        self.title_bar.title.setText("%s  v%s  |  %s" % (tr("app_name"), APP_VERSION, msg))

    def on_done(self, paras, probs, ratio, name, engine_name, buckets=None):
        self.progress.setValue(100)
        self.result_label.setText("AI 生成占比：%.1f%%" % (ratio * 100))
        threshold = self.thr_slider.value() / 100.0
        try:
            self.last_diag = diagnose(paras, probs, threshold)
        except Exception:
            self.last_diag = None
        self.last_paras = paras
        self.last_probs = probs
        self.last_ratio = ratio
        self.report.setHtml(
            build_report(
                paras,
                probs,
                ratio,
                name,
                engine_name,
                threshold,
                self.last_diag,
                buckets,
            )
        )
        self.btn_start.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.btn_rewrite.setEnabled(True)
        self.title_bar.title.setText("%s  v%s" % (tr("app_name"), APP_VERSION))

        suggest = self.suggest_thr.value() / 100.0
        if self.last_diag and ratio > suggest:
            ret = QMessageBox.question(
                self,
                tr("rewrite_suggest_title"),
                tr("rewrite_suggest_body") % (ratio * 100, suggest * 100),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ret == QMessageBox.Yes:
                self.start_rewrite()

    def on_failed(self, msg):
        self.btn_start.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.title_bar.title.setText("%s  v%s" % (tr("app_name"), APP_VERSION))
        QMessageBox.warning(self, tr("detect_fail_title"), msg)

    # ---- 降重（检测 → 诊断 → 治疗） ----
    def start_rewrite(self):
        if self.last_paras is None:
            if not self.file_path:
                return
            # 还没检测过：先读文档做纯规则诊断
            try:
                text = extract_text(self.file_path)
                paras = split_paragraphs(
                    text, self.min_len.value()
                )
                self.last_paras = paras
                self.last_probs = None
                self.last_diag = diagnose(paras, None, self.thr_slider.value() / 100.0)
            except Exception as e:
                QMessageBox.warning(self, tr("detect_fail_title"), str(e))
                return
        if self.last_diag is None:
            self.last_diag = diagnose(
                self.last_paras, self.last_probs, self.thr_slider.value() / 100.0
            )
        engine_id = self.engine_combo.currentData()
        engine_cfg = self.mgr.get(engine_id) if engine_id else None
        dlg = RewriteDialog(
            self.last_paras,
            self.last_probs,
            self.last_diag,
            self.base_dir,
            self.settings,
            parent=self,
            engine_cfg=engine_cfg,
            detect_params=self._collect_params(),
            detect_threshold=self.thr_slider.value() / 100.0,
        )
        dlg.exec()

    def closeEvent(self, e):
        self.master.stop()
        if self.worker_node:
            self.worker_node.stop()
        e.accept()
