# -*- coding: utf-8 -*-
import os
import shutil

from core.i18n import tr
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
)


MIRRORS = {
    "hf-mirror.com": "https://hf-mirror.com",
    "HuggingFace 官方": "https://huggingface.co",
}


class DownloadWorker(QThread):
    progress = Signal(str, int)
    done = Signal(str, bool, str)

    def __init__(self, engine_cfg, base_dir, mirror_url):
        super().__init__()
        self.engine_cfg = engine_cfg
        self.base_dir = base_dir
        self.mirror_url = mirror_url

    def run(self):
        eid = self.engine_cfg["id"]
        old = os.environ.get("HF_ENDPOINT")
        os.environ["HF_ENDPOINT"] = self.mirror_url
        try:
            from core.engines import create_engine

            engine = create_engine(self.engine_cfg, self.base_dir)
            engine.install(lambda pct, msg: self.progress.emit(msg, pct))
            self.done.emit(eid, True, "")
        except Exception as e:
            self.done.emit(eid, False, str(e))
        finally:
            if old is not None:
                os.environ["HF_ENDPOINT"] = old
            else:
                os.environ.pop("HF_ENDPOINT", None)


class SettingsDialog(QDialog):
    def __init__(self, settings, base_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.resize(520, 480)
        self.settings = settings
        self.base_dir = base_dir
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        grp_mirror = QGroupBox(tr("settings_mirror_group"))
        ml = QVBoxLayout(grp_mirror)

        self.rb_mirror = QRadioButton(tr("settings_mirror_domestic"))
        self.rb_direct = QRadioButton(tr("settings_mirror_direct"))
        hint = QLabel(tr("settings_mirror_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")

        cur = self.settings.get("download", "mirror", default="hf-mirror.com")
        self.rb_mirror.setChecked(cur == "hf-mirror.com")
        self.rb_direct.setChecked(cur == "huggingface.co")

        ml.addWidget(self.rb_mirror)
        ml.addWidget(self.rb_direct)
        ml.addWidget(hint)
        lay.addWidget(grp_mirror)

        grp_model = QGroupBox(tr("settings_model_group"))
        mll = QVBoxLayout(grp_model)

        from core.engines.manager import BUILTIN_ENGINES

        self._model_rows = []
        for eng in BUILTIN_ENGINES:
            row = QHBoxLayout()
            name_lbl = QLabel(eng["name"])
            name_lbl.setMinimumWidth(200)
            size_lbl = QLabel(eng.get("size_hint", ""))
            size_lbl.setMinimumWidth(60)
            btn_dl = QPushButton(tr("settings_btn_download"))
            btn_dl.setFixedWidth(80)
            btn_del = QPushButton(tr("settings_btn_delete"))
            btn_del.setFixedWidth(60)
            btn_dl.clicked.connect(lambda _, e=eng: self._download(e))
            btn_del.clicked.connect(lambda _, e=eng: self._delete(e))
            row.addWidget(name_lbl)
            row.addWidget(size_lbl)
            row.addWidget(btn_dl)
            row.addWidget(btn_del)
            mll.addLayout(row)
            self._model_rows.append((eng["id"], btn_dl, btn_del))

        self.progress_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        mll.addWidget(self.progress_label)
        mll.addWidget(self.progress_bar)
        lay.addWidget(grp_model)

        grp_hint = QGroupBox(tr("settings_usage_group"))
        gl = QVBoxLayout(grp_hint)
        usage = QTextEdit()
        usage.setPlainText(tr("settings_usage_text"))
        usage.setReadOnly(True)
        usage.setMaximumHeight(120)
        gl.addWidget(usage)
        lay.addWidget(grp_hint)

        row_btn = QHBoxLayout()
        btn_save = QPushButton(tr("settings_btn_save"))
        btn_save.clicked.connect(self._save)
        btn_close = QPushButton(tr("btn_close"))
        btn_close.clicked.connect(self.accept)
        row_btn.addStretch()
        row_btn.addWidget(btn_save)
        row_btn.addWidget(btn_close)
        lay.addLayout(row_btn)

    def _current_mirror(self):
        if self.rb_mirror.isChecked():
            return "hf-mirror.com", MIRRORS["hf-mirror.com"]
        return "huggingface.co", MIRRORS["HuggingFace 官方"]

    def _save(self):
        mid, _ = self._current_mirror()
        self.settings.set(mid, "download", "mirror")
        self.settings.set(mid, "download", "hf_endpoint")
        self.accept()

    def _download(self, engine_cfg):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, tr("notice"), tr("settings_download_busy"))
            return
        mid, url = self._current_mirror()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText(tr("settings_downloading") % engine_cfg["name"])
        for _, b, _ in self._model_rows:
            b.setEnabled(False)
        self._worker = DownloadWorker(engine_cfg, self.base_dir, url)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, msg, pct):
        self.progress_label.setText(msg)
        self.progress_bar.setValue(pct)

    def _on_done(self, eid, ok, err):
        self.progress_bar.setVisible(False)
        for _, b, _ in self._model_rows:
            b.setEnabled(True)
        if ok:
            self.progress_label.setText(tr("settings_download_ok") % eid)
        else:
            self.progress_label.setText(tr("settings_download_fail") % err[:80])

    def _delete(self, engine_cfg):
        model_dir = os.path.join(self.base_dir, "models", engine_cfg["id"])
        if not os.path.exists(model_dir):
            QMessageBox.information(self, tr("notice"), tr("settings_no_model"))
            return
        ret = QMessageBox.question(
            self,
            tr("notice"),
            tr("settings_confirm_delete") % engine_cfg["name"],
        )
        if ret == QMessageBox.Yes:
            shutil.rmtree(model_dir, ignore_errors=True)
            self.progress_label.setText(tr("settings_deleted") % engine_cfg["id"])
