import os
import sys
import time

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.about_text import ABOUT_TEXT, ABOUT_TEXT_EN
from core.cluster import ClusterMaster, ClusterWorker
from core.detector import detect_local, detect_with_cluster
from core.doc_reader import extract_text, split_paragraphs
from core.engines import EngineManager, create_engine
from core.i18n import get_lang, set_lang, tr
from core.license import License
from core.logging_setup import export_logs, setup_logging
from core.meta import APP_NAME, APP_VERSION, AUTHOR_EMAIL
from core.report import build_report
from core.settings import Settings
from core.telemetry import Telemetry
from ui.engine_dialog import EngineDialog
from ui.glass import GlassButton, GlassPanel, TitleBar


if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DetectWorker(QThread):
    step = Signal(str, int)
    finished_ok = Signal(list, list, float, str, str)
    failed = Signal(str)

    def __init__(self, path, engine_id, engine_name, params, base_dir, master, tel=None):
        super().__init__()
        self.path = path
        self.engine_id = engine_id
        self.engine_name = engine_name
        self.params = params
        self.base_dir = base_dir
        self.master = master
        self.tel = tel
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
            if self.tel:
                self.tel.track(
                    "detection_start",
                    file_type=os.path.splitext(self.path)[1].lower(),
                    engine=self.engine_id,
                    paras=len(paras),
                )

            cfg = self.mgr.get(self.engine_id)
            if not cfg:
                self.failed.emit(tr("engine_not_found") % self.engine_id)
                return

            engine = create_engine(cfg, self.base_dir)
            self.step.emit(tr("preparing_model"), 4)
            engine.install(lambda pct, msg: self.step.emit(msg, 4 + int(pct * 0.10)))
            if self.tel:
                self.tel.track("engine_install", engine=self.engine_id)

            eparams = dict(cfg.get("params", {}))
            if "max_len" in self.params:
                eparams["max_len"] = self.params["max_len"]
            run_params = dict(self.params)
            run_params.update(eparams)

            def prog(done, total):
                pct = 15 + int(82 * done / max(total, 1))
                self.step.emit(tr("detecting_para") % (done, total), pct)

            if self.params.get("use_cluster") and self.master and self.master.nodes_snapshot():
                probs = detect_with_cluster(
                    cfg, self.base_dir, paras, run_params, self.master, prog
                )
            else:
                probs = detect_local(cfg, self.base_dir, paras, run_params, prog)

            valid = [p for p in probs if p is not None]
            ratio = sum(valid) / len(valid) if valid else 0.0
            self.step.emit(tr("generating_report"), 99)
            if self.tel:
                self.tel.track(
                    "detection_done",
                    engine=self.engine_id,
                    paras=len(paras),
                    duration_sec=int(time.time() - self.start_ts),
                    ratio=round(ratio, 3),
                )
            self.finished_ok.emit(
                paras, probs, ratio, os.path.basename(self.path), self.engine_name
            )
        except Exception as e:
            if self.tel:
                self.tel.track("detection_error", error=type(e).__name__)
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 780)
        self.base_dir = BASE_DIR
        self.settings = Settings(self.base_dir)
        set_lang(self.settings.get("ui", "language", default="zh"))
        self.log = setup_logging(self.base_dir)
        self.tel = Telemetry(self.base_dir, self.settings)
        self.start_time = time.time()
        self.mgr = EngineManager(self.base_dir)
        self.license = License(self.base_dir)
        self.master = ClusterMaster(on_log=self.on_cluster_log)
        self.worker_node = None
        self.worker_thread = None
        self.file_path = None
        self._build_ui()
        self._apply_params_from_settings()
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.on_heartbeat)
        self.heartbeat_timer.start(5 * 60 * 1000)
        self.tel.track("app_start", gpu=self._devices_text()[:80])

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self.maybe_show_consent)

    def maybe_show_consent(self):
        if self.settings.get("telemetry", "consent_shown", default=False):
            return
        self.settings.set(True, "telemetry", "consent_shown")
        ret = QMessageBox.question(
            self,
            tr("consent_title"),
            tr("consent_body"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        enabled = ret == QMessageBox.Yes
        self.tel.set_enabled(enabled)
        self.chk_telemetry.setChecked(enabled)

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(
            "QWidget#root{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #dbeafe, stop:0.5 #ede9fe, stop:1 #fce7f3);}"
        )
        central.setObjectName("root")
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 10, 18, 18)
        root.setSpacing(12)

        self.title_bar = TitleBar("%s  v%s" % (tr("app_name"), APP_VERSION), self)
        root.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_left(), 2)
        body.addWidget(self._build_right(), 3)
        root.addLayout(body, 1)
        self.setCentralWidget(central)

    def _build_left(self):
        panel = GlassPanel()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel("① " + tr("btn_select_file")))
        row = QHBoxLayout()
        self.btn_open = GlassButton(tr("btn_select_file"))
        self.btn_open.clicked.connect(self.choose_file)
        row.addWidget(self.btn_open)
        self.file_label = QLabel(tr("file_not_selected"))
        self.file_label.setStyleSheet("color:#475569;")
        row.addWidget(self.file_label, 1)
        lay.addLayout(row)

        lay.addWidget(QLabel(tr("label_engine")))
        row2 = QHBoxLayout()
        self.engine_combo = QComboBox()
        self._reload_engines()
        row2.addWidget(self.engine_combo, 1)
        self.btn_engine = GlassButton(tr("btn_manage"))
        self.btn_engine.clicked.connect(self.open_engine_dialog)
        row2.addWidget(self.btn_engine)
        lay.addLayout(row2)

        lay.addWidget(QLabel(tr("label_params")))
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
        thr_row.addWidget(self.thr_slider, 1)
        thr_row.addWidget(self.thr_spin)
        lay.addLayout(thr_row)

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
        lay.addWidget(self.chk_gpu)
        lay.addWidget(self.chk_cluster)

        lay.addWidget(QLabel(tr("label_presets")))
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

        lay.addWidget(QLabel(tr("label_cluster")))
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

        lay.addWidget(QLabel(tr("label_version")))
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

        lay.addWidget(QLabel(tr("label_contact")))
        cont_row = QHBoxLayout()
        self.author_label = QLabel(AUTHOR_EMAIL)
        self.author_label.setStyleSheet("color:#475569;")
        cont_row.addWidget(self.author_label, 1)
        self.btn_copy_mail = GlassButton(tr("btn_copy_email"))
        self.btn_copy_mail.clicked.connect(self.copy_author_email)
        cont_row.addWidget(self.btn_copy_mail)
        lay.addLayout(cont_row)

        lay.addWidget(QLabel(tr("label_data")))
        tel_row = QHBoxLayout()
        self.chk_telemetry = QCheckBox(tr("chk_telemetry"))
        self.chk_telemetry.setChecked(self.tel.enabled)
        self.chk_telemetry.toggled.connect(self.on_telemetry_toggled)
        tel_row.addWidget(self.chk_telemetry, 1)
        self.btn_export_log = GlassButton(tr("btn_export_log"))
        self.btn_export_log.clicked.connect(self.export_log)
        tel_row.addWidget(self.btn_export_log)
        lay.addLayout(tel_row)

        self.btn_start = GlassButton(tr("btn_start"), primary=True)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.start_detect)
        lay.addWidget(self.btn_start)
        lay.addStretch()
        return panel

    def _build_right(self):
        panel = GlassPanel()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(18, 16, 18, 16)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        lay.addWidget(self.progress)
        self.result_label = QLabel(tr("ratio_placeholder"))
        self.result_label.setStyleSheet(
            "font-size:24px;font-weight:800;color:#1d4ed8;background:transparent;"
        )
        lay.addWidget(self.result_label)
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        self.report.setStyleSheet(
            "QTextEdit{background:rgba(255,255,255,190);border:none;border-radius:12px;"
            "font-size:13px;}"
        )
        lay.addWidget(self.report, 1)
        return panel

    # ---- 引擎 ----
    def _reload_engines(self):
        self.engine_combo.clear()
        for e in self.mgr.all():
            self.engine_combo.addItem(e["name"], e["id"])
        idx = self.engine_combo.findData(self.settings.get("detect", "engine", default="simpleai"))
        if idx >= 0:
            self.engine_combo.setCurrentIndex(idx)

    def open_engine_dialog(self):
        EngineDialog(self.mgr, self).exec()
        current = self.engine_combo.currentData()
        self._reload_engines()
        if current is not None:
            idx = self.engine_combo.findData(current)
            if idx >= 0:
                self.engine_combo.setCurrentIndex(idx)

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
            "min_para_len": self.min_len.value(),
            "max_len": self.settings.get("detect", "max_len", default=500),
            "use_gpu": self.chk_gpu.isChecked(),
            "max_workers": self.workers.value(),
            "use_cluster": self.chk_cluster.isChecked(),
        }

    def _apply_params_from_settings(self):
        d = self.settings.get("detect", default={})
        self.thr_slider.setValue(int(d.get("threshold", 0.5) * 100))
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
        self.thr_slider.setValue(int(p.get("threshold", 0.5) * 100))
        self.min_len.setValue(p.get("min_para_len", 20))
        self.workers.setValue(p.get("max_workers", 0))
        self.chk_gpu.setChecked(p.get("use_gpu", True))
        self.chk_cluster.setChecked(p.get("use_cluster", False))
        idx = self.engine_combo.findData(p.get("engine"))
        if idx >= 0:
            self.engine_combo.setCurrentIndex(idx)

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
        dlg.resize(760, 720)
        box = QVBoxLayout(dlg)
        box.setContentsMargins(16, 16, 16, 16)
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
            cap.setStyleSheet("color:#475569;font-weight:600;")
            cell.addWidget(cap)
            qr_row.addLayout(cell)
        box.addLayout(qr_row)
        close_btn = GlassButton("关闭")
        close_btn.clicked.connect(dlg.accept)
        box.addWidget(close_btn, 0, Qt.AlignRight)
        dlg.exec()

    def _donate_image_path(self, name):
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", "")
            p = os.path.join(meipass, "app", "assets", "donate", name)
            if os.path.exists(p):
                return p
        return os.path.join(BASE_DIR, "app", "assets", "donate", name)

    def copy_author_email(self):
        QApplication.clipboard().setText(AUTHOR_EMAIL)
        QMessageBox.information(
            self, tr("copied_title"), tr("copied_body") % AUTHOR_EMAIL
        )

    def on_telemetry_toggled(self, checked):
        self.tel.set_enabled(checked)

    def on_heartbeat(self):
        self.tel.track(
            "heartbeat", minutes=int((time.time() - self.start_time) / 60)
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
        size_mb = round(os.path.getsize(path) / 1024 / 1024, 2)
        self.tel.track("log_export", size_mb=size_mb)
        QMessageBox.information(
            self,
            tr("export_done_title"),
            tr("export_done_body") % (path, AUTHOR_EMAIL),
        )

    # ---- 检测 ----
    def start_detect(self):
        if not self.file_path:
            return
        params = self._collect_params()
        for k, v in params.items():
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
            self.tel,
        )
        self.worker_thread.step.connect(self.on_step)
        self.worker_thread.finished_ok.connect(self.on_done)
        self.worker_thread.failed.connect(self.on_failed)
        self.worker_thread.start()

    def on_step(self, msg, pct):
        self.progress.setValue(pct)
        self.setWindowTitle("%s  v%s  |  %s" % (tr("app_name"), APP_VERSION, msg))
        self.title_bar.title.setText("%s  v%s  |  %s" % (tr("app_name"), APP_VERSION, msg))

    def on_done(self, paras, probs, ratio, name, engine_name):
        self.progress.setValue(100)
        self.result_label.setText("AI 生成占比：%.1f%%" % (ratio * 100))
        self.report.setHtml(
            build_report(
                paras,
                probs,
                ratio,
                name,
                engine_name,
                self.thr_slider.value() / 100.0,
            )
        )
        self.btn_start.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.title_bar.title.setText("%s  v%s" % (tr("app_name"), APP_VERSION))

    def on_failed(self, msg):
        self.btn_start.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.title_bar.title.setText("%s  v%s" % (tr("app_name"), APP_VERSION))
        QMessageBox.warning(self, tr("detect_fail_title"), msg)

    def closeEvent(self, e):
        self.tel.track(
            "app_close", duration_sec=int(time.time() - self.start_time)
        )
        self.tel.flush_now()
        self.master.stop()
        if self.worker_node:
            self.worker_node.stop()
        e.accept()
