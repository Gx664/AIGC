import json

from core.i18n import tr
from ui.glass import fit_to_screen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class EngineDialog(QDialog):
    """引擎管理：查看、添加自定义引擎、删除自定义引擎。"""

    def __init__(self, mgr, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("engine_mgr_title"))
        fit_to_screen(self, 560, 460, min_w=460, min_h=340)
        self.mgr = mgr

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("engine_mgr_hint")))
        self.list = QListWidget()
        lay.addWidget(self.list)

        row = QHBoxLayout()
        self.btn_add = QPushButton(tr("btn_add_custom"))
        self.btn_del = QPushButton(tr("btn_del_custom"))
        self.btn_close = QPushButton(tr("btn_close"))
        self.btn_add.clicked.connect(self.add_custom)
        self.btn_del.clicked.connect(self.delete_selected)
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_del)
        row.addStretch()
        row.addWidget(self.btn_close)
        lay.addLayout(row)
        self._refresh()

    def _refresh(self):
        self.list.clear()
        for e in self.mgr.all():
            tag = (
                tr("tag_custom")
                if any(c["id"] == e["id"] for c in self.mgr.custom)
                else tr("tag_builtin")
            )
            item = QListWidgetItem(
                "%s ｜ %s ｜ %s ｜ %s"
                % (e["name"], tag, e.get("type", "?"), e.get("size_hint", ""))
            )
            item.setData(256, e["id"])
            self.list.addItem(item)

    def add_custom(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("add_custom_title"))
        form = QFormLayout(dlg)
        eid = QLineEdit()
        name = QLineEdit()
        etype = QComboBox()
        etype.addItems(["classifier", "perplexity"])
        model = QLineEdit()
        params = QPlainTextEdit()
        params.setPlaceholderText(tr("params_placeholder"))
        form.addRow(tr("field_id"), eid)
        form.addRow(tr("field_name"), name)
        form.addRow(tr("field_type"), etype)
        form.addRow(tr("field_model"), model)
        form.addRow(tr("field_params"), params)
        btn = QPushButton(tr("btn_ok"))
        form.addRow(btn)

        def ok():
            if not eid.text().strip() or not model.text().strip():
                QMessageBox.warning(dlg, tr("notice"), tr("err_id_model"))
                return
            try:
                p = json.loads(params.toPlainText() or "{}")
            except Exception:
                QMessageBox.warning(dlg, tr("notice"), tr("err_json"))
                return
            self.mgr.add_custom(
                {
                    "id": eid.text().strip(),
                    "name": name.text().strip() or eid.text().strip(),
                    "type": etype.currentText(),
                    "model_id": model.text().strip(),
                    "size_hint": tr("tag_custom"),
                    "desc": tr("custom_desc"),
                    "params": p,
                }
            )
            dlg.accept()
            self._refresh()

        btn.clicked.connect(ok)
        dlg.exec()

    def delete_selected(self):
        item = self.list.currentItem()
        if not item:
            return
        eid = item.data(256)
        if not any(c["id"] == eid for c in self.mgr.custom):
            QMessageBox.information(self, tr("notice"), tr("builtin_no_del"))
            return
        self.mgr.remove(eid)
        self._refresh()
