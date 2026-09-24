# -*- coding: utf-8 -*-
"""评测基准窗口：RAID / MGTBench 的实际落地界面。

用真实标注样本给检测器做体检，输出准确率、假阳性率（最要命的指标）、
按生成模型分项，并可导出 Markdown 报告。
"""
import os

from core.i18n import tr
from ui.glass import fit_to_screen
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextBrowser,
    QVBoxLayout,
)


class BenchWorker(QThread):
    step = Signal(str)
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, engine_cfg, base_dir, samples, threshold, params, sample_note):
        super().__init__()
        self.engine_cfg = engine_cfg
        self.base_dir = base_dir
        self.samples = samples
        self.threshold = threshold
        self.params = params
        self.sample_note = sample_note

    def run(self):
        try:
            from core import benchmark
            from core.engines import create_engine

            engine = create_engine(self.engine_cfg, self.base_dir)
            self.step.emit(tr("preparing_model"))
            engine.install(lambda pct, msg: self.step.emit(msg))

            device = "cpu"
            try:
                import torch

                if torch.cuda.is_available():
                    device = "cuda:0"
            except Exception:  # noqa: BLE001
                pass

            res = benchmark.run(
                self.samples,
                engine,
                device=device,
                threshold=self.threshold,
                engine_params=self.params,
                progress_cb=lambda d, t: self.progress.emit(d, t),
            )
            res["engine"] = self.engine_cfg.get("name", self.engine_cfg.get("id", ""))
            res["sample_note"] = self.sample_note
            self.done.emit(res)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class BenchmarkDialog(QDialog):
    def __init__(self, mgr, base_dir, settings, bench_id="raid", parent=None):
        super().__init__(parent)
        self.mgr = mgr
        self.base_dir = base_dir
        self.settings = settings
        self.bench_id = bench_id
        self.bench_cfg = mgr.get(bench_id) or {}
        self.samples = []
        self.sample_note = ""
        self._worker = None
        self._last_report = None

        from core import benchmark

        self.builtin = benchmark.builtin_samples()
        self.samples = list(self.builtin)
        self.sample_note = "内置快速体检样本（%d 条，作者手写，非官方基准）" % len(self.builtin)

        self.setWindowTitle(tr("bench_title") % self.bench_cfg.get("name", bench_id))
        fit_to_screen(self, 860, 640, min_w=600, min_h=420)

        lay = QVBoxLayout(self)

        hint = QLabel(tr("bench_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#475569;font-size:12px;")
        lay.addWidget(hint)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(tr("bench_engine")))
        self.cmb_engine = QComboBox()
        for e in mgr.runnable():
            self.cmb_engine.addItem(e.get("name", e["id"]), e["id"])
        idx = self.cmb_engine.findData(self.settings.get("detect", "engine", default="simpleai"))
        if idx >= 0:
            self.cmb_engine.setCurrentIndex(idx)
        row1.addWidget(self.cmb_engine, 1)
        row1.addWidget(QLabel(tr("bench_threshold")))
        self.spin_thr = QDoubleSpinBox()
        self.spin_thr.setRange(0.05, 0.95)
        self.spin_thr.setSingleStep(0.05)
        self.spin_thr.setValue(float(self.settings.get("detect", "threshold", default=0.5)))
        row1.addWidget(self.spin_thr)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        self.rb_builtin = QRadioButton(tr("bench_use_builtin") % len(self.builtin))
        self.rb_builtin.setChecked(True)
        self.rb_file = QRadioButton(tr("bench_import"))
        self.rb_builtin.toggled.connect(self._sync_samples)
        self.btn_pick = QPushButton(tr("bench_pick"))
        self.btn_pick.clicked.connect(self._pick_file)
        row2.addWidget(self.rb_builtin)
        row2.addWidget(self.rb_file)
        row2.addWidget(self.btn_pick)
        row2.addStretch()
        lay.addLayout(row2)

        self.lbl_samples = QLabel(self.sample_note)
        self.lbl_samples.setWordWrap(True)
        self.lbl_samples.setStyleSheet("color:#0f172a;font-size:12px;")
        lay.addWidget(self.lbl_samples)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setPlaceholderText(tr("bench_placeholder"))
        lay.addWidget(self.browser, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        row3 = QHBoxLayout()
        self.btn_run = QPushButton(tr("bench_run"))
        self.btn_run.clicked.connect(self._run)
        self.btn_export = QPushButton(tr("bench_export"))
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export)
        btn_close = QPushButton(tr("btn_close"))
        btn_close.clicked.connect(self.accept)
        row3.addWidget(self.btn_run)
        row3.addWidget(self.btn_export)
        row3.addStretch()
        row3.addWidget(btn_close)
        lay.addLayout(row3)

    # ------------------------------------------------------------------ 样本
    def _sync_samples(self):
        if self.rb_builtin.isChecked():
            self.samples = list(self.builtin)
            self.sample_note = "内置快速体检样本（%d 条，作者手写，非官方基准）" % len(self.builtin)
        self.lbl_samples.setText(self.sample_note or tr("bench_need_samples"))

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("bench_import_title"), "", tr("bench_import_filter")
        )
        if not path:
            return
        from core import benchmark

        samples, note = benchmark.load_samples(path, max_samples=300)
        if not samples:
            QMessageBox.warning(self, tr("notice"), note or tr("bench_need_samples"))
            return
        ai_n = len([s for s in samples if s["label"] == 1])
        self.samples = samples
        self.sample_note = "%s ｜ AI 样本 %d 条 / 人类样本 %d 条" % (
            note, ai_n, len(samples) - ai_n
        )
        self.rb_file.setChecked(True)
        self.lbl_samples.setText(self.sample_note)

    # ------------------------------------------------------------------ 运行
    def _run(self):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, tr("notice"), tr("bench_busy"))
            return
        if not self.samples:
            QMessageBox.warning(self, tr("notice"), tr("bench_need_samples"))
            return
        eid = self.cmb_engine.currentData()
        cfg = self.mgr.get(eid)
        if not cfg:
            QMessageBox.warning(self, tr("notice"), tr("bench_no_engine"))
            return
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.browser.setPlainText(tr("bench_prepare"))
        self._worker = BenchWorker(
            cfg,
            self.base_dir,
            self.samples,
            float(self.spin_thr.value()),
            dict(cfg.get("params") or {}),
            self.sample_note,
        )
        self._worker.step.connect(lambda m: self.browser.setPlainText(m))
        self._worker.progress.connect(
            lambda d, t: (
                self.progress.setValue(int(100 * d / max(t, 1))),
                self.browser.setPlainText(tr("bench_running") % (d, t)),
            )
        )
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, res):
        self.progress.setVisible(False)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(True)
        self._last_report = res
        from core import benchmark

        md = benchmark.to_markdown(
            res,
            engine_name=res.get("engine", ""),
            bench_name=self.bench_cfg.get("name", self.bench_id),
            sample_note=res.get("sample_note", ""),
        )
        try:
            self.browser.setMarkdown(md)
        except Exception:  # noqa: BLE001
            self.browser.setPlainText(md)

    def _on_failed(self, msg):
        self.progress.setVisible(False)
        self.btn_run.setEnabled(True)
        self.browser.setPlainText(tr("bench_fail") % msg)

    def _export(self):
        if not self._last_report:
            return
        from core import benchmark

        default = "%s_评测报告.md" % self.bench_id
        path, _ = QFileDialog.getSaveFileName(
            self, tr("bench_export_title"), default, tr("bench_export_filter")
        )
        if not path:
            return
        md = benchmark.to_markdown(
            self._last_report,
            engine_name=self._last_report.get("engine", ""),
            bench_name=self.bench_cfg.get("name", self.bench_id),
            sample_note=self._last_report.get("sample_note", ""),
        )
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("notice"), str(e))
            return
        QMessageBox.information(self, tr("notice"), tr("bench_export_done") % os.path.basename(path))
